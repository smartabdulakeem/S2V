"""
An image made for a shot has to be findable by that shot.

Images generated from a shot's own composed prompt ranked between 43rd and 833rd
for that shot on picture similarity alone, and none reached the 0.2796 match
floor — so a user could generate exactly the right picture, add it, and still see
a gap. Their filenames carry the prompt they were made from; retrieval ignored it.

The threshold matters more than the mechanism. CLIP text-to-text similarity has a
high floor — unrelated English phrases score 0.6-0.75 — so a permissive bar makes
a third of the library "match" anything. These tests hold the bar above what an
unrelated query can reach.
"""

import numpy as np
import pytest
from PIL import Image

from pipeline import library


@pytest.fixture
def lib(tmp_path, monkeypatch):
    images_dir = tmp_path / "images"
    images_dir.mkdir(parents=True)
    monkeypatch.setattr(library, "ROOT", str(tmp_path))
    monkeypatch.setattr(library, "LIBRARY_DIR", str(tmp_path))
    monkeypatch.setattr(library, "IMAGES_DIR", str(images_dir))
    monkeypatch.setattr(library, "INDEX_PATH", str(tmp_path / "index.npz"))
    monkeypatch.setattr(library, "MANIFEST_PATH", str(tmp_path / "manifest.jsonl"))
    monkeypatch.setattr(library, "REJECTIONS_PATH", str(tmp_path / "rejections.jsonl"))
    monkeypatch.setattr(library, "RENDER_USAGE_PATH", str(tmp_path / "usage.json"))
    library._DESC_CACHE.clear()
    return images_dir


# ── Descriptions ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("filename,expected", [
    ("Madinah_outside_borders_7th_century_202608112344.jpeg", "Madinah outside borders 7th century"),
    ("Prophet_Abu_Bakr_early_Islamic_202608112344.jpeg", "Prophet Abu Bakr early Islamic"),
    ("Early_Islamic_era_in_Arabia_202608112344 (1).jpeg", "Early Islamic era in Arabia"),
    ("desert-caravan-at-dusk.jpg", "desert caravan at dusk"),
])
def test_description_is_recovered_from_the_filename(filename, expected):
    assert library.describe_image(f"library/images/{filename}") == expected


def test_a_content_hash_filename_yields_no_description():
    """A hash is not a description, and pretending otherwise invents meaning."""
    assert library.describe_image("library/images/8389f2a74fa3.jpg") == ""
    assert library.describe_image("library/images/cedf4411fb15.png") == ""


def test_a_recorded_prompt_beats_the_filename(tmp_path, monkeypatch):
    monkeypatch.setattr(library, "MANIFEST_PATH", str(tmp_path / "m.jsonl"))
    prompts = {"library/images/8389f2a74fa3.jpg": "a lone rider on a ridge at dusk"}
    assert library.describe_image("library/images/8389f2a74fa3.jpg", prompts) == \
        "a lone rider on a ridge at dusk"


# ── The threshold ─────────────────────────────────────────────────────────────

def test_threshold_is_above_what_unrelated_phrases_reach():
    """
    Measured on the real library: unrelated queries topped out at 0.797. A bar at
    0.62 let a third of the library through for "quantum computing data centre".
    """
    assert library.DESCRIPTION_MIN_SCORE >= 0.82


def test_a_near_paraphrase_scores_above_the_bar_and_a_stranger_does_not():
    paths = ["library/images/Madinah_outside_borders_7th_century_2026.jpeg"]

    close = library.description_scores("Madinah outside borders", paths)[0]
    unrelated = library.description_scores("sushi restaurant kitchen", paths)[0]

    assert close >= library.DESCRIPTION_MIN_SCORE, close
    assert unrelated < library.DESCRIPTION_MIN_SCORE, unrelated
    assert close > unrelated + 0.1


def test_hashed_images_never_get_rescued():
    """No description means no description-based rescue, not a free pass."""
    scores = library.description_scores("anything at all", ["library/images/abc123def456.jpg"])
    assert scores[0] == 0.0


# ── Search behaviour ──────────────────────────────────────────────────────────

def test_search_finds_an_image_named_after_the_query(lib):
    for i in range(4):
        Image.new("RGB", (64, 64), color=(i * 50, 60, 200)).save(lib / f"filler_{i}.jpg")
    Image.new("RGB", (64, 64), color=(30, 30, 30)).save(
        lib / "Madinah_outside_borders_7th_century_2026.jpeg"
    )
    library.reindex(force=True)

    results = library.search("Madinah outside borders", k=1, min_score=0.9)

    assert results, "nothing returned at all"
    assert "Madinah_outside_borders" in results[0][0]
    assert results[0][1] >= 0.9, "the rescued image was left below the match floor"


def test_descriptions_can_be_switched_off(lib):
    Image.new("RGB", (64, 64), color=(30, 30, 30)).save(
        lib / "Madinah_outside_borders_7th_century_2026.jpeg"
    )
    Image.new("RGB", (64, 64), color=(200, 30, 30)).save(lib / "other.jpg")
    library.reindex(force=True)

    with_desc = library.search("Madinah outside borders", k=1, min_score=0.9, use_descriptions=True)
    without = library.search("Madinah outside borders", k=1, min_score=0.9, use_descriptions=False)

    assert with_desc[0][1] >= 0.9
    assert without[0][1] < 0.9, "scores were lifted even with descriptions disabled"
