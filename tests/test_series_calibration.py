import os
import json
import pytest
import numpy as np
from pipeline import library

def test_per_pack_calibration_independence(monkeypatch, tmp_path):
    """
    Test that calibrating two series packs against the same index yields
    independent thresholds written to their respective pack files without
    overwriting each other or writing to a shared config.
    """
    # Create mock CLIP index
    embeddings = np.random.randn(10, 512).astype(np.float32)
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    embeddings = embeddings / norms
    paths = [f"library/images/test_{i}.jpg" for i in range(10)]

    def mock_load_index():
        return embeddings, paths

    def mock_encode(text):
        vec = np.ones((512,), dtype=np.float32)
        if "desert" in text or "manuscript" in text:
            vec[0] = 5.0
        elif "saturn" in text or "space" in text:
            vec[1] = 5.0
        else:
            vec[2] = 5.0
        return vec / np.linalg.norm(vec)

    monkeypatch.setattr(library, "load_index", mock_load_index)
    monkeypatch.setattr(library, "encode_text_query", mock_encode)

    # Make temporary series config dir
    series_dir = tmp_path / "series"
    series_dir.mkdir()
    monkeypatch.setattr(library, "SERIES_CONFIG_DIR", str(series_dir))

    # Create pack A (islamic_history)
    pack_a = {
        "series_slug": "islamic_history",
        "display_name": "Islamic History",
        "voice": {"id": "en-US-GuyNeural"},
        "world_anchor": "7th century Arabian Peninsula",
        "style_block": "35mm film",
        "negative_block": "no modern objects",
        "calibration": {
            "min_score": None,
            "weak_band": None,
            "real_queries": [f"desert query {i}" for i in range(10)],
            "fake_queries": [f"space query {i}" for i in range(10)]
        }
    }
    path_a = series_dir / "islamic_history.json"
    path_a.write_text(json.dumps(pack_a, indent=2), encoding="utf-8")

    # Create pack B (space_science)
    pack_b = {
        "series_slug": "space_science",
        "display_name": "Space Science",
        "voice": {"id": "en-US-News-M"},
        "world_anchor": "NASA Space Program",
        "style_block": "70mm Hasselblad film",
        "negative_block": "no cartoon",
        "calibration": {
            "min_score": None,
            "weak_band": None,
            "real_queries": [f"space query {i}" for i in range(10)],
            "fake_queries": [f"desert query {i}" for i in range(10)]
        }
    }
    path_b = series_dir / "space_science.json"
    path_b.write_text(json.dumps(pack_b, indent=2), encoding="utf-8")

    # Calibrate pack A
    score_a, band_a = library.calibrate(series_slug="islamic_history")

    # Verify pack A updated on disk
    with open(path_a, "r", encoding="utf-8") as f:
        updated_a = json.load(f)
    assert updated_a["calibration"]["min_score"] == score_a

    # Calibrate pack B
    score_b, band_b = library.calibrate(series_slug="space_science")

    # Verify pack B updated on disk
    with open(path_b, "r", encoding="utf-8") as f:
        updated_b = json.load(f)
    assert updated_b["calibration"]["min_score"] == score_b

    # Verify pack A was NOT overwritten when pack B was calibrated
    with open(path_a, "r", encoding="utf-8") as f:
        rechecked_a = json.load(f)
    assert rechecked_a["calibration"]["min_score"] == score_a

    # Verify thresholds differ due to opposite query sets
    assert score_a != score_b


def test_uncalibrated_or_under_200_images_status(monkeypatch, tmp_path):
    """
    Test that get_calibration_config returns 'not calibrated — generation-first' status
    when min_score is None or index has fewer than 200 images.
    """
    # Create mock index with only 10 images (< 200)
    embeddings = np.random.randn(10, 512).astype(np.float32)
    paths = [f"img_{i}.jpg" for i in range(10)]
    monkeypatch.setattr(library, "load_index", lambda: (embeddings, paths))

    series_dir = tmp_path / "series"
    series_dir.mkdir()
    monkeypatch.setattr(library, "SERIES_CONFIG_DIR", str(series_dir))

    pack = {
        "series_slug": "space_science",
        "display_name": "Space Science",
        "voice": {"id": "en-US-News-M"},
        "world_anchor": "NASA",
        "style_block": "Hasselblad",
        "negative_block": "no cartoon",
        "calibration": {
            "min_score": 0.28,
            "weak_band": 0.005,
            "real_queries": ["query"] * 10,
            "fake_queries": ["query"] * 10
        }
    }
    (series_dir / "space_science.json").write_text(json.dumps(pack), encoding="utf-8")

    calib_cfg = library.get_calibration_config("space_science")
    assert calib_cfg["status"] == "not calibrated — generation-first"
    assert calib_cfg["min_score"] is None
