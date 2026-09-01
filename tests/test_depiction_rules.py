"""
Who may appear in a picture, and what a picture must exclude.

Two defects, both visible by laying the app's sixty prompts beside the sixty the
owner wrote himself for the same film.

**Nothing was ever excluded.** All sixty of the app's prompts contained no
exclusion of any kind; all sixty of his ended with one — "no identifiable face,
no red skin, no horns, no wings, no modern elements, no text, no watermark, no
logo". The app has held that list all along, in the niche's `negative_block`,
and never showed it to the model: it was appended to the finished prompt, and
only when a setting was on. A request asking for a complete, production-ready
prompt was asking for one with nothing ruled out.

**Only the Divine had a depiction rule.** `never_depict` removes a figure and
shows the scene around it, which is right for Allah and wrong for everyone else.
Iblis is the subject of this film and has to be in it; the angels have to be
present when they speak. With no rule covering them the model reached for the
nearest stock idea of a person, and pictures 9 to 14 came back as "a commanding,
imposing cloaked figure", "one distinct veiled figure", and — the one that
cannot be used at all — "a close framing of a figure's tense, furrowed brow in
heavy shadow, cold eyes staring with bitter envy". An image generator renders
that as a photographed human model.

So there is a second list. `never_depict` is absent from the frame;
`never_show_face` is present in it, and never identifiable.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.shot_description import _build_instruction, INSTRUCTION


RECIPE = "You are the visual storyboard planner for ancient sacred history."

CFG = {
    "series_slug": "pre_islamic_prophetic___global_history",
    "prompt_recipe": RECIPE,
    "era_block": "",
    "negative_block": "modern elements, plastic, firearms, fantasy creatures, text, watermark",
    "never_depict": ["Allah", "God"],
    "never_show_face": ["Iblis", "angels", "Adam"],
}


# ── the two lists are different rules ─────────────────────────────────────────

def test_the_divine_is_absent_from_the_frame():
    built = _build_instruction(CFG)
    assert "Never depict, and never describe the appearance of: Allah, God" in built
    assert "never their form, face, hands or figure" in built


def test_iblis_and_the_angels_are_present_but_never_identifiable():
    built = _build_instruction(CFG)

    assert "must never be identifiable: Adam, Angels, Iblis" in built, (
        "the beings the film is about have no depiction rule"
    )
    for forbidden in ("No face", "no facial features", "no eyes",
                      "photographed human model", "no wings", "no horns"):
        assert forbidden in built, f"the rule does not rule out: {forbidden}"


def test_the_faceless_rule_says_what_to_show_instead_of_only_what_to_hide():
    """
    A rule made only of prohibitions produces "a cloaked figure" — vague, and
    still a person. The model needs somewhere to put the meaning instead.
    """
    built = _build_instruction(CFG)
    assert "far from the camera, from behind, or as a silhouette" in built
    assert "Carry their state through the scene instead" in built


def test_both_lists_survive_together():
    built = _build_instruction(CFG)
    assert built.count("- Never depict, and never describe") == 1
    assert built.count("- These may appear in a picture") == 1


def test_a_niche_that_names_nobody_gets_no_rules():
    cfg = dict(CFG, never_depict=[], never_show_face=[])
    built = _build_instruction(cfg)
    assert "must never be identifiable" not in built
    assert "Never depict, and never describe" not in built


# ── what a picture must exclude ───────────────────────────────────────────────

def test_the_films_standing_exclusions_reach_the_model():
    built = _build_instruction(CFG)
    assert CFG["negative_block"] in built, (
        "the niche's negative block still never reaches the request"
    )


def test_every_description_is_required_to_exclude_something():
    built = _build_instruction(CFG)
    assert 'End every description with what must NOT appear' in built
    assert "A picture with nothing excluded is not finished." in built


def test_a_niche_with_no_negative_block_still_builds():
    cfg = dict(CFG, negative_block="")
    built = _build_instruction(cfg)
    assert "Standing exclusions" not in built
    assert "must never be identifiable" in built, "an unrelated rule was lost"


def test_no_recipe_still_leaves_the_built_in_instruction_alone():
    assert _build_instruction(None) == INSTRUCTION


# ── the lists have to survive being saved ─────────────────────────────────────

def test_saving_a_niche_does_not_drop_the_depiction_rules(tmp_path, monkeypatch):
    """
    `save_series_override` keeps a fixed list of keys and silently drops the
    rest. Neither list was on it, so editing any other niche field would have
    erased the only thing keeping a face out of a picture that must not have one.
    """
    from pipeline import library

    monkeypatch.setattr(library, "ROOT", str(tmp_path))

    res = library.save_series_override("test_depiction_roundtrip", {
        "prompt_recipe": RECIPE,
        "never_depict": ["Allah"],
        "never_show_face": ["Iblis"],
    })
    assert res["success"], res

    saved = res["overrides"]
    assert saved.get("never_depict") == ["Allah"], "never_depict was dropped on save"
    assert saved.get("never_show_face") == ["Iblis"], "never_show_face was dropped on save"


def test_the_names_are_read_case_insensitively():
    from pipeline.library import never_show_face_names

    assert never_show_face_names({"never_show_face": ["IBLIS", " Angels "]}) == {"iblis", "angels"}
    assert never_show_face_names({"never_show_face": "Iblis"}) == {"iblis"}
    assert never_show_face_names({}) == set()
