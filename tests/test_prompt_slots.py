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


from pipeline.library import compose_gap_prompt

CTX = ("Khalid ibn al-Walid rode through the night with the advance guard, reaching the "
       "Jordan valley before dawn. The ground at Fahl had been flooded deliberately, and "
       "the horses sank to the knee in churned mire.")


def _prompt(**kw):
    base = dict(shot_query="Khalid ibn al-Walid leading cavalry",
                script_context=CTX, series_slug="islamic_history")
    base.update(kw)
    return compose_gap_prompt(**base)


def test_the_world_anchor_appears_exactly_once():
    out = _prompt(visual_type="architectural_plate")
    assert out.lower().count("7th century arabian peninsula") == 1


def test_the_prompt_does_not_end_mid_phrase():
    out = _prompt(visual_type="architectural_plate")
    assert not out.rstrip().endswith("churned,")
    assert not out.rstrip().endswith(",")


def test_narration_is_not_quoted_verbatim():
    out = _prompt(visual_type="architectural_plate")
    assert "reaching the Jordan valley" not in out


def test_the_picked_preset_supplies_the_medium():
    out = _prompt(visual_type="architectural_plate")
    assert "muqarnas" in out


def test_no_visual_type_falls_back_to_style_block():
    out = _prompt(visual_type=None)
    assert "35mm film" in out


def test_light_and_ground_slots_are_present():
    out = _prompt(visual_type="architectural_plate")
    assert "pre-dawn" in out
    assert "waterlogged" in out


def test_a_bare_shot_with_no_context_still_composes():
    out = compose_gap_prompt(shot_query="a walled city", script_context="",
                             series_slug="islamic_history",
                             visual_type="architectural_plate")
    assert out.endswith(".")
    assert "wide establishing shot" in out
    assert "a walled city" in out


def test_the_brief_opens_the_prompt():
    out = _prompt(visual_type="architectural_plate", project_brief="Documentary still from a film")
    assert out.startswith("Documentary still from a film")


def test_no_negative_block_is_emitted_by_default():
    out = _prompt(visual_type="architectural_plate")
    assert "Negative prompt" not in out


from pipeline.composer import treatment_for_style


def test_preset_object_treatment_wins():
    preset = {"prompt": "x", "treatment": "documentary"}
    assert treatment_for_style("anything", preset=preset) == "documentary"


def test_preset_key_that_is_itself_a_treatment_is_used():
    assert treatment_for_style("", preset=None, visual_type="illustration") == "illustration"


def test_prose_substring_match_still_works():
    assert treatment_for_style("Vox paper-collage") == "vox_collage"


def test_nothing_to_go_on_returns_none():
    assert treatment_for_style("") is None


def test_the_anchor_is_not_repeated_when_the_brief_already_carries_it():
    brief = "Documentary still from a film set in 7th century Arabian Peninsula, early Islamic era"
    out = _prompt(visual_type="architectural_plate", project_brief=brief)
    assert out.lower().count("7th century arabian peninsula") == 1, out


def test_the_anchor_still_appears_when_the_brief_omits_it():
    out = _prompt(visual_type="architectural_plate", project_brief="Documentary still from a film")
    assert out.lower().count("7th century arabian peninsula") == 1, out
