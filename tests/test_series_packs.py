"""
Every series pack on disk must validate and resolve.

A pack that fails validation is not a cosmetic problem: get_series_config
re-raises, so selecting that niche crashes the planner.
"""

import glob
import json
import os
import pytest

from pipeline.library import validate_series_pack, get_series_config

PACK_PATHS = sorted(glob.glob(os.path.join("config", "series", "*.json")))
PACK_SLUGS = [os.path.basename(p)[:-5] for p in PACK_PATHS]


def test_there_are_packs_to_check():
    # A guard against this file silently testing nothing if the glob breaks.
    # The count is not pinned - packs come and go - but "default" must exist,
    # because get_series_config falls back to it for projects with no slug.
    assert len(PACK_PATHS) >= 5, f"expected several packs, found {len(PACK_PATHS)}"
    assert "default" in PACK_SLUGS, PACK_SLUGS


@pytest.mark.parametrize("path", PACK_PATHS, ids=PACK_SLUGS)
def test_pack_validates(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    errors = validate_series_pack(data)
    assert errors == [], f"{os.path.basename(path)} failed validation: {errors}"


@pytest.mark.parametrize("slug", PACK_SLUGS, ids=PACK_SLUGS)
def test_pack_resolves_without_raising(slug):
    cfg = get_series_config(series_slug=slug)
    assert cfg.get("series_slug"), f"{slug} resolved to a pack with no series_slug"


from pipeline.composer import SINGLE_IMAGE_TREATMENTS


def _minimal_pack(**overrides):
    pack = {
        "series_slug": "x", "display_name": "X",
        "world_anchor": "somewhere", "style_block": "a look",
        "negative_block": "no text",
        "voice": {"id": "en-US-RogerNeural"},
        "calibration": {"real_queries": ["q"] * 10, "fake_queries": ["q"] * 10},
        "style_presets": {"a_look": {"prompt": "a look", "treatment": "documentary"}},
    }
    pack.update(overrides)
    return pack


def test_missing_style_presets_is_an_error():
    errors = validate_series_pack(_minimal_pack(style_presets=None))
    assert any("style_presets" in e for e in errors), errors


def test_empty_style_presets_is_an_error():
    errors = validate_series_pack(_minimal_pack(style_presets={}))
    assert any("style_presets" in e for e in errors), errors


def test_entry_without_prompt_is_an_error():
    errors = validate_series_pack(_minimal_pack(style_presets={"a": {"treatment": "documentary"}}))
    assert any("style_presets.a" in e for e in errors), errors


def test_unknown_treatment_is_an_error():
    errors = validate_series_pack(
        _minimal_pack(style_presets={"a": {"prompt": "x", "treatment": "sepia_tone"}})
    )
    assert any("style_presets.a.treatment" in e for e in errors), errors


def test_plain_string_entry_is_accepted():
    assert validate_series_pack(_minimal_pack(style_presets={"a": "just prose"})) == []


@pytest.mark.parametrize("path", PACK_PATHS, ids=PACK_SLUGS)
def test_every_authored_treatment_is_real(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for key, entry in (data.get("style_presets") or {}).items():
        if isinstance(entry, dict) and entry.get("treatment"):
            assert entry["treatment"] in SINGLE_IMAGE_TREATMENTS, \
                f"{os.path.basename(path)}: {key} maps to unknown treatment {entry['treatment']}"
