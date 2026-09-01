"""
A picture plan becomes `share_with` on the shots, and nothing downstream knows.

`share_with` is how the app has always said "these segments share one image".
Writing the model's spans through the same field means numbering, prompt
export, folder matching and the WolfCut timeline all keep working untouched.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.picture_plan import apply_spans
from pipeline.library import picture_owning_shots


def _script(n):
    return {"segments": [
        {"segment_id": i + 1, "narration": f"line {i + 1}",
         "shots": [{"shot_id": f"{i + 1}a", "query": "q", "scene": f"line {i + 1}"}]}
        for i in range(n)]}


SPANS = [
    {"number": 1, "first_line": 1, "last_line": 3, "description": "the first picture"},
    {"number": 2, "first_line": 4, "last_line": 5, "description": "the second picture"},
]


def test_the_first_line_of_a_span_owns_the_picture():
    script = _script(5)
    apply_spans(script, SPANS)

    owners = [shot.get("shot_id") for _seg, shot in picture_owning_shots(script)]
    assert owners == ["1a", "4a"]


def test_every_other_line_in_the_span_points_at_that_owner():
    script = _script(5)
    apply_spans(script, SPANS)

    shots = [seg["shots"][0] for seg in script["segments"]]
    assert [s.get("share_with") for s in shots] == [None, "1a", "1a", None, "4a"]


def test_the_description_lands_on_the_owning_shot_only():
    script = _script(5)
    apply_spans(script, SPANS)

    shots = [seg["shots"][0] for seg in script["segments"]]
    assert shots[0]["visual_description"] == "the first picture"
    assert shots[3]["visual_description"] == "the second picture"
    assert "visual_description" not in shots[1]


def test_applying_a_new_plan_clears_the_old_one():
    """A re-plan must not leave a shot pointing at an owner that no longer owns."""
    script = _script(5)
    apply_spans(script, SPANS)
    apply_spans(script, [{"number": 1, "first_line": 1, "last_line": 5,
                          "description": "one picture now"}])

    shots = [seg["shots"][0] for seg in script["segments"]]
    assert [s.get("share_with") for s in shots] == [None, "1a", "1a", "1a", "1a"]
    assert len(picture_owning_shots(script)) == 1


def test_the_report_says_what_was_applied():
    script = _script(5)
    stats = apply_spans(script, SPANS)
    assert stats == {"pictures": 2, "segments": 5}

from unittest.mock import patch


def test_auto_mode_lets_the_story_decide_the_count():
    from app import SmartStudioAPI

    script = _script(20)
    fake = [{"number": 1, "first_line": 1, "last_line": 12, "description": "a"},
            {"number": 2, "first_line": 13, "last_line": 20, "description": "b"}]

    with patch("pipeline.picture_plan.plan_pictures", return_value=fake):
        res = SmartStudioAPI().plan_pictures_for_script(script, image_count=None)

    assert res["success"] is True
    assert res["images_after"] == 2
    assert len(picture_owning_shots(script)) == 2


def test_manual_mode_passes_the_count_straight_through():
    from app import SmartStudioAPI

    script = _script(20)
    seen = {}

    def _capture(script_lines, seconds, **kw):
        seen.update(kw)
        return [{"number": 1, "first_line": 1, "last_line": 20, "description": "one"}]

    with patch("pipeline.picture_plan.plan_pictures", side_effect=_capture):
        SmartStudioAPI().plan_pictures_for_script(script, image_count=1)

    assert seen["exact_count"] == 1