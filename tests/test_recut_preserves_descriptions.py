"""
Re-cutting a script must not throw away the AI's work.

`apply_shot_rhythm` and `plan_image_budget` both rebuild every shot from
scratch. Neither carried `visual_description` or the planner's `query`, so
moving the Storyboard's rhythm slider — or changing the image count — silently
replaced a written shot description with a two-word `extract_keyword` guess.

The owner's last film showed the result: 347 shots, no `visual_description`
anywhere, and queries like "fought defeated drove". The recipe he had spent an
evening on never reached a single picture.

A chunk that covers exactly the same narration as before is the same shot. Its
description and query are carried. A chunk whose text changed is genuinely new
and is re-planned, as it always was.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.text_parser import apply_shot_rhythm, plan_image_budget


NARRATION = (
    "The river rose through the night and by dawn the fields were gone. "
    "Families carried what they could to the high ground above the bend. "
    "The granaries stood empty for the first time in living memory. "
    "By the third day the water had begun to fall back toward the channel. "
    "What it left behind was a plain of grey silt, and the work of a season lost."
)


def _script():
    return {
        "segments": [
            {"segment_id": 1, "narration": NARRATION, "shots": []},
        ]
    }


def _describe(script, prefix="A written description of "):
    """Stand in for the AI description pass: one description per shot."""
    for seg in script["segments"]:
        for i, shot in enumerate(seg["shots"]):
            # Stripped, because a carried description is stored stripped; a
            # fixture with a trailing space would fail on the whitespace alone.
            shot["visual_description"] = f"{prefix}{shot['scene'][:40]}".strip()
            shot["query"] = f"planner query {i}"


def _all_shots(script):
    return [s for seg in script["segments"] for s in (seg.get("shots") or [])]


def test_rhythm_recut_keeps_descriptions_when_the_narration_slice_is_unchanged():
    script = _script()
    apply_shot_rhythm(script, 7)
    _describe(script)

    before = {s["scene"]: s["visual_description"] for s in _all_shots(script)}
    queries_before = {s["scene"]: s["query"] for s in _all_shots(script)}
    assert before, "the fixture produced no shots"

    # Same rhythm, so every chunk is byte-identical to the one it replaces.
    apply_shot_rhythm(script, 7)

    for shot in _all_shots(script):
        assert shot.get("visual_description") == before[shot["scene"]], (
            "re-cutting at the same rhythm discarded a written description"
        )
        assert shot.get("query") == queries_before[shot["scene"]], (
            "re-cutting at the same rhythm discarded the planner's query"
        )


def test_image_budget_recut_keeps_descriptions_when_the_narration_slice_is_unchanged():
    script = _script()
    plan_image_budget(script, 3)
    _describe(script)

    before = {s["scene"]: s["visual_description"] for s in _all_shots(script)}
    assert before, "the fixture produced no shots"

    plan_image_budget(script, 3)

    for shot in _all_shots(script):
        assert shot.get("visual_description") == before[shot["scene"]], (
            "changing the image count discarded a written description"
        )


def test_a_genuinely_new_slice_is_replanned_not_carried():
    """A chunk whose text changed must not inherit another chunk's description."""
    script = _script()
    apply_shot_rhythm(script, 12)
    _describe(script)
    old_scenes = {s["scene"] for s in _all_shots(script)}

    # A much faster rhythm cuts different slices of the same narration.
    apply_shot_rhythm(script, 3)

    for shot in _all_shots(script):
        if shot["scene"] not in old_scenes:
            assert not shot.get("visual_description"), (
                "a new narration slice inherited a description written for different text"
            )
