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
    assert len(PACK_PATHS) >= 11, f"expected at least 11 packs, found {len(PACK_PATHS)}"


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
