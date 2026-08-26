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
            "series_slug": "default",
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
    # Negative blocks are off by default: the image tools this is pasted into take
    # one prompt box, so "Negative prompt: no firearms" was read as a request for
    # firearms. Still available behind the flag — see the tests below.
    assert "Negative prompt:" not in composed


# ── Adversarial Regression Tests ─────────────────────────────────────────────

def test_islamic_series_prompt_composition():
    """The pack's world anchor reaches the prompt; its negative block stays out."""
    cfg = library.get_series_config(series_slug="islamic_history")
    assert "7th century" in cfg["world_anchor"].lower()
    assert "scimitar" in cfg["negative_block"].lower()

    composed = library.compose_gap_prompt(
        shot_query="desert caravan",
        series_slug="islamic_history"
    )
    assert "7th century" in composed.lower()
    assert "scimitar" not in composed.lower()


def test_negative_block_is_still_available_when_asked_for():
    """Turning it off by default must not quietly delete the capability."""
    composed = library.compose_gap_prompt(
        shot_query="desert caravan",
        series_slug="islamic_history",
        include_negative=True,
    )
    assert "Negative prompt:" in composed
    assert "scimitar" in composed.lower()


def test_the_prompt_describes_the_scene_from_the_script():
    """
    The subject used to be the extracted keyword alone, so an image generated
    from the prompt had no relationship to what was being narrated.
    """
    composed = library.compose_gap_prompt(
        shot_query="Prophet Bai'ah Bakr",
        series_slug="islamic_history",
        script_context="The Prophet was buried. Abu Bakr al-Siddiq was the Caliph of Islam.",
    )
    assert "Abu Bakr al-Siddiq was the Caliph" in composed
    assert "Prophet Bai'ah Bakr" in composed


def test_presenter_asides_are_kept_out_of_the_prompt():
    """"Hit subscribe" is something said, not something a picture can show."""
    composed = library.compose_gap_prompt(
        shot_query="the flood",
        series_slug="islamic_history",
        script_context="The water is gone. Hit subscribe so you are here for the next one. "
                       "The mountain is dry.",
    )
    assert "subscribe" not in composed.lower()
    assert "The water is gone" in composed


def test_space_series_prompt_composition():
    """Script with series_slug 'space' must contain neither scimitars nor Arabian Peninsula anchors."""
    cfg = library.get_series_config(series_slug="space_science")
    assert "scimitar" not in cfg.get("negative_block", "").lower()
    assert "arabian" not in cfg.get("world_anchor", "").lower()

    composed = library.compose_gap_prompt(
        shot_query="lunar rover on dusty crater rim",
        series_slug="space_science"
    )
    assert "scimitar" not in composed.lower()
    assert "arabian" not in composed.lower()
    assert "7th century" not in composed.lower()


def test_missing_series_slug_warning():
    """Script with missing series_slug must emit UserWarning naming project title."""
    with pytest.warns(UserWarning, match="The Rise of Baghdad") as record:
        cfg = library.get_series_config(series_slug=None, project_title="The Rise of Baghdad")
    assert cfg["series_slug"] == "default"


def test_unknown_series_slug_raises():
    """Unknown series_slug must raise ValueError listing available series packs."""
    with pytest.raises(ValueError) as exc_info:
        library.get_series_config(series_slug="martian_chronicles")
    err_str = str(exc_info.value)
    assert "martian_chronicles" in err_str
    assert "islamic_history" in err_str


def test_no_composed_prompt_contains_title_or_narration():
    """Composed prompts must never include video title or raw narration sentences directly."""
    title = "The Great Siege of 1863"
    narration = "The army marched thirty miles through heavy rain without stopping for food or rest."
    composed = library.compose_gap_prompt(
        shot_query="soldiers marching through rain",
        script_context=narration,
        series_slug="civil_war",
        project_title=title
    )
    assert title not in composed
    assert narration not in composed


def test_report_counters_agree_with_lists(tmp_path, monkeypatch):
    """Counters report['gaps'] and report['weak'] must strictly equal list lengths."""
    images_dir = tmp_path / "images"
    images_dir.mkdir(parents=True)
    index_file = tmp_path / "index.npz"

    img = Image.new("RGB", (100, 100), color=(100, 100, 100))
    img.save(images_dir / "sample.jpg")

    monkeypatch.setattr(library, "ROOT", str(tmp_path))
    monkeypatch.setattr(library, "LIBRARY_DIR", str(tmp_path))
    monkeypatch.setattr(library, "IMAGES_DIR", str(images_dir))
    monkeypatch.setattr(library, "INDEX_PATH", str(index_file))

    library.reindex(force=True)

    script_data = {
        "project": {
            "title": "Test Agreement Project",
            "series_slug": "default"
        },
        "segments": [
            {
                "segment_id": 1,
                "narration": "First scene narration",
                "shots": [
                    {"shot_id": "1a", "query": "impossible query delta alpha 999", "min_score": 0.99}
                ]
            }
        ]
    }

    report = library.plan_shots(script_data, min_score=0.99)
    assert report["gaps"] == len(report["ranked_gaps"])
    assert report["weak"] == len(report["ranked_weak"])


def test_weak_band_read_from_config(monkeypatch):
    """Categorization changes dynamically when weak_band in config is modified."""
    monkeypatch.setattr(library, "get_calibration_config", lambda: {"min_score": 0.28, "weak_band": 0.05})
    band1 = library.get_calibrated_weak_band()
    assert band1 == 0.05

    monkeypatch.setattr(library, "get_calibration_config", lambda: {"min_score": 0.28, "weak_band": 0.001})
    band2 = library.get_calibrated_weak_band()
    assert band2 == 0.001
