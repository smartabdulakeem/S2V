"""
The shot count has a floor the user cannot get under.

`apply_shot_rhythm` cuts *within* a segment and takes `max(1, ...)`, so a script
with 47 segments produces at least 47 images however slowly the rhythm is set.
Measured on the real project THE_BATTLE_OF_THE_MUD: 47 segments, 1404 words,
~9.4 minutes, and the slider bottoms out at 48 images. The user wants 15-21.

These tests record that floor. The first two must keep passing. The third is the
target and is expected to fail until shots are allowed to span segments — it is
marked xfail(strict) so that *fixing* it forces this file to be updated, and so
that nobody can report the job done while the floor is still there.
"""

import pytest

from pipeline.text_parser import WORDS_PER_SECOND, apply_shot_rhythm


def _script(segment_count: int, words_per_segment: int = 30) -> dict:
    """A script shaped like the real one: ~30 words a segment, ~11.5s of narration."""
    return {
        "project": {"title": "Floor"},
        "segments": [
            {
                "segment_id": i + 1,
                "narration": " ".join(["word"] * words_per_segment),
                "shots": [],
            }
            for i in range(segment_count)
        ],
    }


def test_a_slow_rhythm_still_cannot_go_below_one_image_per_segment():
    script = _script(47)
    stats = apply_shot_rhythm(script, seconds_per_shot=60.0)
    assert stats["shots_after"] == 47, (
        "60s per shot on a 9.4 minute film should be far fewer than 47 images; "
        "the per-segment max(1, ...) is the floor"
    )


def test_the_floor_is_the_segment_count_whatever_the_slider_says():
    script = _script(47)
    counts = {
        secs: apply_shot_rhythm(_script(47), seconds_per_shot=secs)["shots_after"]
        for secs in (12, 20, 30, 40, 60, 120)
    }
    assert set(counts.values()) == {47}, (
        f"every slow setting collapses to the segment count: {counts}"
    )
    # And a fast rhythm does still increase the count, so the control is not dead.
    assert apply_shot_rhythm(script, seconds_per_shot=3.0)["shots_after"] > 47


def test_a_faster_rhythm_yields_more_images_not_fewer():
    """Guards the direction itself: shorter shots must mean more of them."""
    fast = apply_shot_rhythm(_script(20), seconds_per_shot=3.0)["shots_after"]
    slow = apply_shot_rhythm(_script(20), seconds_per_shot=12.0)["shots_after"]
    assert fast > slow


@pytest.mark.xfail(
    strict=True,
    reason="Not built: shots cannot span segments, so 15-21 images over 9.4 minutes "
           "is unreachable. See ROADMAP.md C1.",
)
def test_a_long_rhythm_can_reach_the_count_the_user_actually_wants():
    """~31s of screen time per image across 47 segments is 18 images."""
    script = _script(47)
    stats = apply_shot_rhythm(script, seconds_per_shot=31.0)
    assert 15 <= stats["shots_after"] <= 21, (
        f"wanted 15-21 images, got {stats['shots_after']}"
    )


def test_the_words_per_second_assumption_is_the_one_the_measurement_used():
    """If this changes, every shot-count number in ROADMAP.md needs re-measuring."""
    assert WORDS_PER_SECOND == 2.6
