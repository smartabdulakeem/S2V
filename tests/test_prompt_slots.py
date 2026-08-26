"""Preset resolution and slot-based prompt composition."""

import pytest

from pipeline.library import resolve_style_preset


def test_string_entry_becomes_prompt_with_no_treatment():
    cfg = {"style_presets": {"oil_portrait": "Classical oil portrait, visible brushwork."}}
    out = resolve_style_preset(cfg, "oil_portrait")
    assert out == {"prompt": "Classical oil portrait, visible brushwork.", "treatment": None}


def test_object_entry_carries_its_treatment():
    cfg = {"style_presets": {"evidence_photo": {
        "prompt": "Flash-lit evidence photograph, flat frontal light.",
        "treatment": "documentary",
    }}}
    out = resolve_style_preset(cfg, "evidence_photo")
    assert out["prompt"] == "Flash-lit evidence photograph, flat frontal light."
    assert out["treatment"] == "documentary"


def test_unknown_key_resolves_to_none():
    cfg = {"style_presets": {"oil_portrait": "x"}}
    assert resolve_style_preset(cfg, "no_such_preset") is None


def test_empty_visual_type_resolves_to_none():
    cfg = {"style_presets": {"oil_portrait": "x"}}
    assert resolve_style_preset(cfg, "") is None
    assert resolve_style_preset(cfg, None) is None


def test_malformed_object_resolves_to_none():
    cfg = {"style_presets": {"broken": {"treatment": "documentary"}}}
    assert resolve_style_preset(cfg, "broken") is None


from pipeline.prompt_slots import (
    match_slot, PROMPT_FRAMING, PROMPT_MOTION, PROMPT_GROUND,
    PROMPT_ATMOSPHERE, PROMPT_LIGHT, DEFAULT_FRAMING,
)


def test_match_slot_returns_the_first_matching_phrase():
    assert "pre-dawn" in match_slot(PROMPT_LIGHT, "reaching the valley before dawn")


def test_match_slot_returns_default_when_nothing_matches():
    assert match_slot(PROMPT_LIGHT, "a quiet room", default="none") == "none"


def test_match_slot_returns_none_by_default():
    assert match_slot(PROMPT_LIGHT, "a quiet room") is None


def test_match_slot_is_case_insensitive():
    assert match_slot(PROMPT_LIGHT, "AT MIDNIGHT") is not None


def test_ground_matches_mire():
    assert "waterlogged" in match_slot(PROMPT_GROUND, "horses sank into churned mire")


def test_motion_matches_riding():
    assert "mid-movement" in match_slot(PROMPT_MOTION, "Khalid rode through the night")


def test_atmosphere_matches_smoke():
    assert "smoke" in match_slot(PROMPT_ATMOSPHERE, "mud and smoke over the field")


def test_framing_defaults_to_wide_establishing():
    assert match_slot(PROMPT_FRAMING, "a man on a horse", default=DEFAULT_FRAMING) == DEFAULT_FRAMING


def test_framing_honours_an_explicit_close_shot():
    assert "detail" in match_slot(PROMPT_FRAMING, "close detail of a bridle")


def test_every_table_is_pairs_of_pattern_and_phrase():
    for table in (PROMPT_FRAMING, PROMPT_MOTION, PROMPT_GROUND, PROMPT_ATMOSPHERE, PROMPT_LIGHT):
        for pattern, phrase in table:
            assert isinstance(pattern, str) and pattern
            assert isinstance(phrase, str) and phrase
