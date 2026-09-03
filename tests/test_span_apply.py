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


# ── the whole chain ───────────────────────────────────────────────────────────

def test_planning_after_spans_does_not_ask_the_model_to_describe_again():
    """
    `apply_spans` writes a description onto every owning shot. `plan_shots`
    then runs `describe_shots`, which must recognise them as already written.

    If it does not, every re-plan pays for the descriptions twice and — worse —
    the second answer is written for a shot rather than for the span, which is
    the exact defect this whole plan exists to remove.
    """
    from pipeline.shot_description import describe_shots

    script = _script(5)
    apply_spans(script, SPANS)

    owning = [shot for _seg, shot in picture_owning_shots(script)]
    shots_for_desc = [{"shot_id": s["shot_id"], "scene": s["scene"],
                       "picture_number": i + 1, "first_line": i + 1, "last_line": i + 1,
                       "visual_description": s.get("visual_description")}
                      for i, s in enumerate(owning)]

    class _MustNotBeCalled:
        def identity(self):
            return "gemini", "gemini-2.5-flash"

        def complete_text(self, system, user="", max_tokens=2048):
            raise AssertionError("describe_shots asked the model for descriptions it already had")

    out = describe_shots(shots_for_desc, series_cfg={"prompt_recipe": "r"},
                         provider=_MustNotBeCalled())

    assert out["1a"] == "the first picture"
    assert out["4a"] == "the second picture"


def test_a_numbered_folder_image_still_binds_to_the_picture_it_names():
    """
    The numbering contract, across the new boundaries. `3.jpg` is the third
    picture the film makes — whoever decided where that picture starts.
    """
    from pipeline.library import match_folder_images_by_slot

    script = _script(9)
    apply_spans(script, [
        {"number": 1, "first_line": 1, "last_line": 4, "description": "first"},
        {"number": 2, "first_line": 5, "last_line": 6, "description": "second"},
        {"number": 3, "first_line": 7, "last_line": 9, "description": "third"},
    ])

    owners = picture_owning_shots(script)
    assert len(owners) == 3

    matched, fell_back = match_folder_images_by_slot(
        ["/imgs/1_a.jpg", "/imgs/2_b.jpg", "/imgs/3_c.jpg"], len(owners))
    assert fell_back is False
    assert matched[2].endswith("3_c.jpg"), "picture 3 did not receive 3.jpg"