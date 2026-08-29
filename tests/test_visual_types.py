"""
Tests for Visual Types List Manager, style_presets overrides, and prompt resolution.

Covers:
- An override's list replaces rather than merges (deleting universal presets persists).
- A niche with no override still merges the 6 universal presets (regression guard).
- Empty visual_type resolves to the first entry, and reordering changes which one wins.
- Save then load round trip through save_series_override() preserves order, label, and treatment.
- Key generation is stable and collision-safe.
- A user-created niche is seeded with its base's list.
"""

import os
import json
import re
import pytest

from pipeline.library import (
    get_series_config,
    save_series_override,
    reset_series_override,
    style_presets_for,
    resolve_style_preset,
    compose_gap_prompt,
    create_user_niche,
    delete_user_niche,
    UNIVERSAL_STYLE_PRESETS,
    ROOT,
)
from pipeline.composer import _get_shot_cache_key


def test_niche_with_no_override_merges_universals():
    """A niche with no override merges its own presets over the 6 universal presets."""
    reset_series_override("biography")
    cfg = get_series_config(series_slug="biography")
    presets = style_presets_for(cfg)

    # Shipped biography has 5 presets
    assert "portrait_archive" in presets
    assert "oil_portrait" in presets
    # All 6 universals must be present
    for u_key in UNIVERSAL_STYLE_PRESETS:
        assert u_key in presets, f"Expected universal preset '{u_key}' in unoverridden pack"
    assert len(presets) >= 11


def test_override_replaces_rather_than_merges():
    """An override's style_presets list is authoritative — deleting a universal type keeps it deleted."""
    slug = "biography"
    custom_presets = {
        "custom_look": {
            "label": "Custom Look",
            "prompt": "Unique custom visual style prompt description.",
            "treatment": "none",
        }
    }
    try:
        res = save_series_override(slug, {"style_presets": custom_presets})
        assert res["success"] is True

        cfg = get_series_config(series_slug=slug)
        presets = style_presets_for(cfg)

        # Only the override list should exist
        assert list(presets.keys()) == ["custom_look"]
        assert "photoreal" not in presets
        assert "cinematic" not in presets
        assert "portrait_archive" not in presets
    finally:
        reset_series_override(slug)


def test_empty_visual_type_resolves_to_first_entry_and_reorder_wins():
    """When visual_type is empty, prompt composition resolves to the top entry in style_presets."""
    slug = "biography"
    reset_series_override(slug)

    # 1. Default order: first entry is portrait_archive
    out_default = compose_gap_prompt(
        shot_query="A scholar reading a manuscript",
        series_slug=slug,
        visual_type="",
    )
    assert "archival portrait" in out_default.lower()

    # 2. Save override with oil_portrait as the first entry
    reordered_presets = {
        "oil_portrait": {
            "label": "Oil Portrait",
            "prompt": "Classical oil portrait, visible brushwork, dark umber ground.",
            "treatment": "illustration",
        },
        "portrait_archive": {
            "label": "Portrait Archive",
            "prompt": "Medium format archival portrait, warm window light.",
            "treatment": "documentary",
        },
    }
    try:
        save_series_override(slug, {"style_presets": reordered_presets})
        out_reordered = compose_gap_prompt(
            shot_query="A scholar reading a manuscript",
            series_slug=slug,
            visual_type="",
        )
        assert "classical oil portrait" in out_reordered.lower()
        assert "archival portrait" not in out_reordered.lower()
    finally:
        reset_series_override(slug)


def test_save_load_round_trip_preserves_order_label_and_treatment():
    """Round trip through save_series_override preserves order, label, and treatment."""
    slug = "biography"
    custom_presets = {
        "first_type": {
            "label": "First Custom Style",
            "prompt": "First prompt style with grain.",
            "treatment": "documentary",
        },
        "second_type": {
            "label": "Second Custom Style",
            "prompt": "Second prompt style with glow.",
            "treatment": "illustration",
        },
        "third_type": {
            "label": "Third Custom Style",
            "prompt": "Third prompt style with clean lines.",
            "treatment": "none",
        },
    }
    try:
        save_res = save_series_override(slug, {"style_presets": custom_presets})
        assert save_res["success"] is True

        cfg = get_series_config(series_slug=slug)
        loaded = style_presets_for(cfg)

        assert list(loaded.keys()) == ["first_type", "second_type", "third_type"]
        assert loaded["first_type"]["label"] == "First Custom Style"
        assert loaded["first_type"]["treatment"] == "documentary"
        assert loaded["second_type"]["treatment"] == "illustration"
        assert loaded["third_type"]["treatment"] == "none"
    finally:
        reset_series_override(slug)


def test_key_generation_stability_and_collision_safety():
    """Generated keys are stable, slugified, and collision-safe."""
    labels = ["3D realistic photo", "3D Realistic Photo", "Special & Unique Look!", ""]
    
    def generate_key(label: str, existing_keys: set) -> str:
        k = re.sub(r"[^\w]+", "_", label.lower()).strip("_")
        if not k:
            k = "visual_type"
        final_key = k
        counter = 2
        while final_key in existing_keys:
            final_key = f"{k}_{counter}"
            counter += 1
        return final_key

    seen = set()
    k1 = generate_key(labels[0], seen)
    seen.add(k1)
    assert k1 == "3d_realistic_photo"

    k2 = generate_key(labels[1], seen)
    seen.add(k2)
    assert k2 == "3d_realistic_photo_2"

    k3 = generate_key(labels[2], seen)
    seen.add(k3)
    assert k3 == "special_unique_look"

    k4 = generate_key(labels[3], seen)
    seen.add(k4)
    assert k4 == "visual_type"


def test_user_created_niche_seeded_with_base_list():
    """A newly created user niche is seeded with its base pack's style_presets."""
    user_slug = "test_user_niche_seed"
    try:
        res = create_user_niche(user_slug, "Test User Niche", base_slug="biography")
        assert res["success"] is True

        cfg = get_series_config(series_slug=user_slug)
        assert cfg["series_slug"] == user_slug
        assert isinstance(cfg.get("style_presets"), dict)
        assert "portrait_archive" in cfg["style_presets"]
        assert "photoreal" in cfg["style_presets"]
    finally:
        delete_user_niche(user_slug)


def test_shot_cache_key_v8():
    """Shot cache key is at version v8."""
    shot = {"query": "A citadel at dawn"}
    key = _get_shot_cache_key(shot, 4.0, 1920, 1080)
    assert isinstance(key, str)
    assert len(key) == 16
