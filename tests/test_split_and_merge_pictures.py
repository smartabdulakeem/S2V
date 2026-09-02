"""
Moving one boundary by hand, without re-planning the film.

The model places the boundaries and is usually right, but re-planning a whole
film to move one of them costs two model calls, rewrites every other picture,
and throws away descriptions that were already good. That is exactly how the
owner lost 26 of his 30 written descriptions.

A boundary is `share_with` on the segment where a picture starts, so splitting
and merging is flipping that one field and nothing else.
"""

import pytest

from pipeline.picture_plan import (apply_spans, merge_picture, picture_boundaries,
                                   split_picture)


def script(lines=12):
    return {
        "project": {"title": "Boundaries"},
        "segments": [
            {"segment_id": i, "narration": f"line {i}",
             "shots": [{"shot_id": f"{i}a", "query": "q", "scene": f"line {i}"}]}
            for i in range(1, lines + 1)
        ],
    }


def planned():
    """Three pictures: 1-4, 5-8, 9-12."""
    s = script()
    apply_spans(s, [
        {"number": 1, "first_line": 1, "last_line": 4, "description": "the first"},
        {"number": 2, "first_line": 5, "last_line": 8, "description": "the second"},
        {"number": 3, "first_line": 9, "last_line": 12, "description": "the third"},
    ])
    return s


def descriptions(s):
    return {i: (seg["shots"][0].get("visual_description") or "")
            for i, seg in enumerate(s["segments"], 1)}


def test_the_plan_starts_where_expected():
    assert picture_boundaries(planned()) == [1, 5, 9]


# ── splitting ────────────────────────────────────────────────────────────────

def test_a_split_starts_a_new_picture_there():
    s = planned()
    out = split_picture(s, 7)

    assert out["success"] is True
    assert out["pictures"] == 4
    assert picture_boundaries(s) == [1, 5, 7, 9]


def test_the_lines_after_a_split_follow_the_new_picture():
    """Line 8 belonged to picture 2. After splitting at 7 it belongs to the new one."""
    s = planned()
    split_picture(s, 7)

    assert s["segments"][7]["shots"][0]["share_with"] == "7a", "line 8 kept the old owner"
    assert s["segments"][8]["shots"][0]["share_with"] is None, "picture 3 was disturbed"


def test_a_split_leaves_the_other_pictures_alone():
    """The whole point: one boundary moves, nothing else is rewritten."""
    s = planned()
    split_picture(s, 7)
    d = descriptions(s)

    assert d[1] == "the first", "picture 1 lost its description"
    assert d[5] == "the second", "picture 2 lost its description"
    assert d[9] == "the third", "picture 3 lost its description"


def test_the_new_picture_is_left_to_be_described():
    """
    Borrowing the old picture's words would describe the wrong half of the scene,
    so the new picture is left blank for the description pass to fill.
    """
    s = planned()
    split_picture(s, 7)

    assert descriptions(s)[7] == ""


def test_a_picture_cannot_start_twice():
    s = planned()
    assert split_picture(s, 5)["success"] is False
    assert picture_boundaries(s) == [1, 5, 9], "a refused split still changed the plan"


def test_the_first_line_is_already_a_boundary():
    s = planned()
    out = split_picture(s, 1)
    assert out["success"] is False
    assert "line of the script" in out["error"]


@pytest.mark.parametrize("line", [0, -3, 13, 999])
def test_a_split_off_the_end_of_the_script_is_refused(line):
    s = planned()
    assert split_picture(s, line)["success"] is False
    assert picture_boundaries(s) == [1, 5, 9]


# ── merging ──────────────────────────────────────────────────────────────────

def test_a_merge_folds_a_picture_into_the_one_before():
    s = planned()
    out = merge_picture(s, 5)

    assert out["success"] is True
    assert out["pictures"] == 2
    assert picture_boundaries(s) == [1, 9]


def test_everything_that_followed_comes_with_it():
    """Lines 5-8 all pointed at 5a. They must now point at 1a, not be orphaned."""
    s = planned()
    merge_picture(s, 5)

    for line in (5, 6, 7, 8):
        assert s["segments"][line - 1]["shots"][0]["share_with"] == "1a", \
            f"line {line} was left pointing at a picture that no longer exists"


def test_the_absorbed_description_does_not_linger():
    """
    A description written for a stretch of narration that no longer exists is
    the exact shape of the bug that lost 26 of the owner's 30 descriptions:
    words sitting on a shot no prompt can ever reach.
    """
    s = planned()
    merge_picture(s, 5)

    assert descriptions(s)[5] == ""
    assert descriptions(s)[1] == "the first", "the surviving picture lost its own words"


def test_a_merge_leaves_later_pictures_alone():
    s = planned()
    merge_picture(s, 5)

    assert s["segments"][8]["shots"][0]["share_with"] is None
    assert descriptions(s)[9] == "the third"


def test_the_first_picture_has_nothing_before_it():
    s = planned()
    out = merge_picture(s, 1)
    assert out["success"] is False
    assert picture_boundaries(s) == [1, 5, 9]


def test_a_line_that_starts_no_picture_cannot_be_merged():
    s = planned()
    out = merge_picture(s, 6)
    assert out["success"] is False
    assert "No picture starts" in out["error"]


def test_the_last_picture_standing_is_kept():
    """One picture for a whole film is legitimate. Zero is not."""
    s = planned()
    merge_picture(s, 9)
    merge_picture(s, 5)
    assert picture_boundaries(s) == [1]

    out = merge_picture(s, 1)
    assert out["success"] is False
    assert picture_boundaries(s) == [1], "the film was left with no pictures at all"


# ── the two together ─────────────────────────────────────────────────────────

def test_a_split_then_a_merge_returns_the_plan_it_started_from():
    s = planned()
    split_picture(s, 7)
    merge_picture(s, 7)

    assert picture_boundaries(s) == [1, 5, 9]
    for line in (5, 6, 7, 8):
        assert s["segments"][line - 1]["shots"][0]["share_with"] == (None if line == 5 else "5a")


def test_a_segment_with_no_shots_at_all_is_survivable():
    """
    Schema v1 segments carry no shot list, and must not crash the board.

    A segment with no shots has no `share_with`, so the plan already counts it
    as the start of a picture — `plan_shots` materialises exactly this shot when
    it meets one. Splitting there is therefore a no-op, and is refused rather
    than pretended to have worked.
    """
    s = planned()
    s["segments"][6]["shots"] = []
    assert picture_boundaries(s) == [1, 5, 7, 9], "a shot-less segment already starts a picture"

    out = split_picture(s, 7)

    assert out["success"] is False
    assert "already starts" in out["error"]
    assert picture_boundaries(s) == [1, 5, 7, 9]


def test_a_shot_less_segment_can_still_be_merged_away():
    """The refusal above must not leave it unfixable."""
    s = planned()
    s["segments"][6]["shots"] = []

    assert merge_picture(s, 7)["success"] is True
    assert picture_boundaries(s) == [1, 5, 9]
