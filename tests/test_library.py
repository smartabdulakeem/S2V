"""
Unit tests for pipeline/library.py (CLIP index, search diversity, rejection memory, gap detection).
"""

import os
import json
import tempfile
import pytest
import numpy as np
from PIL import Image

from pipeline import library


def test_index_determinism(tmp_path, monkeypatch):
    """Test that reindex produces deterministic paths and embeddings format."""
    images_dir = tmp_path / "images"
    images_dir.mkdir(parents=True)
    index_file = tmp_path / "index.npz"

    # Create 3 test dummy images
    for i in range(3):
        img = Image.new("RGB", (100, 100), color=(i * 50, 100, 150))
        img.save(images_dir / f"test_{i}.jpg")

    monkeypatch.setattr(library, "ROOT", str(tmp_path))
    monkeypatch.setattr(library, "LIBRARY_DIR", str(tmp_path))
    monkeypatch.setattr(library, "IMAGES_DIR", str(images_dir))
    monkeypatch.setattr(library, "INDEX_PATH", str(index_file))

    count1, elapsed1 = library.reindex(force=True)
    assert count1 == 3
    assert index_file.exists()

    data1 = np.load(index_file)
    emb1 = data1.get("embeddings") if "embeddings" in data1 else data1.get("emb")
    paths1 = data1["paths"]

    count2, elapsed2 = library.reindex(force=True)
    data2 = np.load(index_file)
    emb2 = data2.get("embeddings") if "embeddings" in data2 else data2.get("emb")
    paths2 = data2["paths"]

    assert list(paths1) == list(paths2)
    np.testing.assert_array_almost_equal(emb1, emb2)


def test_search_diversity_no_duplicates_in_render(tmp_path, monkeypatch):
    """Test that search with exclude set never returns the same image twice."""
    images_dir = tmp_path / "images"
    images_dir.mkdir(parents=True)
    index_file = tmp_path / "index.npz"

    # Create 5 test images
    img_paths = []
    for i in range(5):
        p = images_dir / f"img_{i}.jpg"
        img = Image.new("RGB", (100, 100), color=(i * 40, i * 40, 200))
        img.save(p)
        img_paths.append(f"images/img_{i}.jpg")

    monkeypatch.setattr(library, "ROOT", str(tmp_path))
    monkeypatch.setattr(library, "LIBRARY_DIR", str(tmp_path))
    monkeypatch.setattr(library, "IMAGES_DIR", str(images_dir))
    monkeypatch.setattr(library, "INDEX_PATH", str(index_file))

    library.reindex(force=True)

    exclude = set()
    used_results = []
    
    # Query 3 times
    for _ in range(3):
        res = library.search("blue canvas", k=1, exclude=exclude, min_score=0.0)
        assert len(res) > 0
        path, score = res[0]
        assert path not in exclude, f"Image {path} was returned despite being in exclude set"
        exclude.add(path)
        used_results.append(path)

    assert len(set(used_results)) == 3, "Duplicate images returned across render search calls"


def test_rejection_memory(tmp_path, monkeypatch):
    """Test that a rejected query-image pair is never returned again."""
    images_dir = tmp_path / "images"
    images_dir.mkdir(parents=True)
    index_file = tmp_path / "index.npz"
    rejections_file = tmp_path / "rejections.jsonl"

    for i in range(2):
        img = Image.new("RGB", (100, 100), color=(100, i * 100, 50))
        img.save(images_dir / f"img_{i}.jpg")

    monkeypatch.setattr(library, "ROOT", str(tmp_path))
    monkeypatch.setattr(library, "LIBRARY_DIR", str(tmp_path))
    monkeypatch.setattr(library, "IMAGES_DIR", str(images_dir))
    monkeypatch.setattr(library, "INDEX_PATH", str(index_file))
    monkeypatch.setattr(library, "REJECTIONS_PATH", str(rejections_file))

    library.reindex(force=True)

    query = "green landscape"
    res1 = library.search(query, k=1, min_score=0.0)
    top_path, score1 = res1[0]

    # Record rejection
    library.record_rejection(query, top_path)

    # Search again
    res2 = library.search(query, k=5, min_score=0.0)
    returned_paths = [p for p, s in res2]

    assert top_path not in returned_paths, f"Rejected path {top_path} was returned in search results"


def test_gap_detection_thresholds(tmp_path, monkeypatch):
    """Test plan_shots categorization: matched, weak, gap and ready-to-use prompt composition."""
    images_dir = tmp_path / "images"
    images_dir.mkdir(parents=True)
    index_file = tmp_path / "index.npz"

    # Create dummy images
    img = Image.new("RGB", (100, 100), color=(200, 100, 50))
    img.save(images_dir / "desert.jpg")

    monkeypatch.setattr(library, "ROOT", str(tmp_path))
    monkeypatch.setattr(library, "LIBRARY_DIR", str(tmp_path))
    monkeypatch.setattr(library, "IMAGES_DIR", str(images_dir))
    monkeypatch.setattr(library, "INDEX_PATH", str(index_file))

    library.reindex(force=True)

    script_data = {
        "project": {
            "title": "Test Gap Project",
            "visual_style": "historical documentary"
        },
        "segments": [
            {
                "segment_id": 1,
                "narration": "A caravan moves across the dunes.",
                "shots": [
                    {"shot_id": "1a", "query": "desert caravan at dusk", "min_score": 0.26},
                    {"shot_id": "1b", "query": "cyberpunk neon robot battles space dragons", "min_score": 0.26}
                ]
            }
        ]
    }

    report = library.plan_shots(script_data, min_score=0.26)
    assert report["total_shots"] == 2
    assert "shot_reports" in report
    
    # Check 1b query composed prompt specifically
    shot_1b = next(s for s in report["shot_reports"] if s["shot_id"] == "1b")
    assert shot_1b["state"] == "gap"
    composed = shot_1b["composed_prompt"]
    assert "cyberpunk neon robot battles space dragons" in composed
    assert "historical documentary" in composed
    assert "cinematic documentary photography" in composed or "film" in composed
    assert "Negative prompt:" in composed
