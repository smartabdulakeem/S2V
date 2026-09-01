"""
Whatever a model returns, the plan that leaves here is legal.

The model chooses where pictures go, which means it can return spans that
overlap, skip lines, arrive out of order, run past the end of the script, or
miss the count it was given. None of that may reach the script: a gap means
narration with no picture at all, and an overlap means two pictures claiming
the same line and a numbering contract that no longer holds.

Repair is deterministic and always succeeds. There is no failure mode where
the app refuses to plan.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.picture_plan import repair_spans, span_seconds

# Ten lines, four seconds each.
SECONDS = [4.0] * 10
N = 10


def _spans(*pairs):
    return [{"first_line": a, "last_line": b, "description": f"picture at {a}"}
            for a, b in pairs]


def _bounds(spans):
    return [(s["first_line"], s["last_line"]) for s in spans]


def test_a_legal_plan_passes_through_unchanged():
    spans = _spans((1, 4), (5, 7), (8, 10))
    assert _bounds(repair_spans(spans, N, SECONDS, 4.0, 60.0)) == [(1, 4), (5, 7), (8, 10)]


def test_a_gap_is_closed_by_extending_the_span_before_it():
    """Lines 5 and 6 belong to no picture. That is narration over nothing."""
    spans = _spans((1, 4), (7, 10))
    assert _bounds(repair_spans(spans, N, SECONDS, 4.0, 60.0)) == [(1, 6), (7, 10)]


def test_an_overlap_is_resolved_in_favour_of_the_earlier_span():
    spans = _spans((1, 6), (4, 10))
    assert _bounds(repair_spans(spans, N, SECONDS, 4.0, 60.0)) == [(1, 6), (7, 10)]


def test_spans_out_of_order_are_sorted_before_anything_else():
    spans = _spans((8, 10), (1, 4), (5, 7))
    assert _bounds(repair_spans(spans, N, SECONDS, 4.0, 60.0)) == [(1, 4), (5, 7), (8, 10)]


def test_the_plan_always_starts_at_line_one_and_ends_at_the_last_line():
    spans = _spans((3, 7))
    assert _bounds(repair_spans(spans, N, SECONDS, 4.0, 60.0)) == [(1, 10)]


def test_nothing_usable_still_produces_one_picture_over_the_whole_film():
    assert _bounds(repair_spans([], N, SECONDS, 4.0, 60.0)) == [(1, 10)]
    assert _bounds(repair_spans(_spans((99, 200)), N, SECONDS, 4.0, 60.0)) == [(1, 10)]


def test_a_span_shorter_than_the_floor_is_merged_into_a_neighbour():
    """One line is 4s. With a floor of 10s it cannot stand on its own."""
    spans = _spans((1, 4), (5, 5), (6, 10))
    out = repair_spans(spans, N, SECONDS, 10.0, 60.0)
    assert all(span_seconds(s, SECONDS) >= 10.0 for s in out), _bounds(out)
    assert _bounds(out)[0][0] == 1 and _bounds(out)[-1][1] == 10


def test_a_span_longer_than_the_ceiling_is_split():
    """One span of 40s against a 20s ceiling has to become two."""
    out = repair_spans(_spans((1, 10)), N, SECONDS, 4.0, 20.0)
    assert len(out) >= 2
    assert all(span_seconds(s, SECONDS) <= 20.0 + 1e-6 for s in out), _bounds(out)


def test_repair_never_loses_or_duplicates_a_line():
    """The invariant everything else rests on."""
    for spans in (_spans((1, 4), (7, 10)), _spans((1, 6), (4, 10)),
                  _spans((8, 10), (1, 4)), []):
        out = repair_spans(spans, N, SECONDS, 4.0, 60.0)
        covered = [line for s in out for line in range(s["first_line"], s["last_line"] + 1)]
        assert covered == list(range(1, N + 1)), f"{_bounds(out)} does not tile 1..{N}"


def test_the_description_travels_with_its_span():
    out = repair_spans(_spans((1, 4), (5, 10)), N, SECONDS, 4.0, 60.0)
    assert out[0]["description"] == "picture at 1"
    assert out[1]["description"] == "picture at 5"


# ── manual override ───────────────────────────────────────────────────────────

def test_one_picture_can_carry_the_entire_film():
    """
    The owner's words: "I also want flexibility enough that I can decide to
    choose one or two images for a 20-minute video, maybe if that may speak to
    the whole video."
    """
    out = repair_spans(_spans((1, 3), (4, 6), (7, 10)), N, SECONDS,
                       10.0, 20.0, exact_count=1)
    assert _bounds(out) == [(1, 10)]


def test_two_pictures_split_the_film_near_the_middle_by_time():
    out = repair_spans(_spans((1, 10)), N, SECONDS, 10.0, 20.0, exact_count=2)
    assert len(out) == 2
    a, b = (span_seconds(s, SECONDS) for s in out)
    assert abs(a - b) <= 4.0, _bounds(out)


def test_the_exact_count_beats_the_holding_range():
    """
    One picture over a 40s film breaks a 20s ceiling. The owner asked for one
    picture, so he gets one picture — the range is advisory in manual mode and
    the ceiling must not quietly split it back into two.
    """
    out = repair_spans(_spans((1, 10)), N, SECONDS, 4.0, 20.0, exact_count=1)
    assert len(out) == 1
    assert span_seconds(out[0], SECONDS) == 40.0


def test_asking_for_more_pictures_than_lines_stops_at_one_per_line():
    out = repair_spans(_spans((1, 10)), N, SECONDS, 4.0, 20.0, exact_count=25)
    assert len(out) == N
    assert _bounds(out) == [(i, i) for i in range(1, N + 1)]


def test_the_count_is_met_exactly_at_every_size_in_between():
    for wanted in range(1, N + 1):
        out = repair_spans(_spans((1, 4), (5, 7), (8, 10)), N, SECONDS,
                           4.0, 20.0, exact_count=wanted)
        assert len(out) == wanted, f"asked {wanted}, got {len(out)}"
        covered = [ln for s in out for ln in range(s["first_line"], s["last_line"] + 1)]
        assert covered == list(range(1, N + 1))


def test_pictures_are_numbered_from_one_in_film_order():
    out = repair_spans(_spans((1, 4), (5, 7), (8, 10)), N, SECONDS, 4.0, 60.0)
    assert [s["number"] for s in out] == [1, 2, 3]