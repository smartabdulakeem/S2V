"""
Tests for plan_image_budget and share_with resolver support.

Covers:
1. N > S, N == S, N < S, N == 1 -> images_after == N in every case.
2. N < S produces exactly N distinct queries and non-first shots have share_with pointing to the run's first shot.
3. Pinned first shot survives a re-plan at a different N.
4. Segment durations drive the distribution when N > S.
5. The resolver reuses the shared image, triggering 1 search per run instead of 1 search per segment.
"""

import pytest
from pipeline import library
from pipeline.text_parser import plan_image_budget


def _make_script(num_segments=44, words_per_seg=45):
    """Generate a dummy script with num_segments and roughly words_per_seg words each."""
    segments = []
    for i in range(1, num_segments + 1):
        words = " ".join([f"word{j}" for j in range(words_per_seg)])
        narration = f"Segment {i} narration. " + words + "."
        segments.append({
            "segment_id": i,
            "narration": narration,
            "shots": [{
                "shot_id": f"{i}a",
                "query": f"segment {i} visual",
                "source": "library",
                "pin": None,
                "scene": narration,
            }],
        })
    return {
        "project": {"title": "Image Budget Test", "series_slug": "default"},
        "segments": segments,
    }


@pytest.mark.parametrize("n", [1, 5, 31, 44, 100])
def test_images_after_equals_n_on_44_segment_script(n):
    """images_after must equal N for all N (N < S, N == S, N > S, N == 1)."""
    script = _make_script(num_segments=44, words_per_seg=45)
    res = plan_image_budget(script, n)
    assert res["images_after"] == n

    distinct_images = 0
    total_shots = 0
    for seg in script["segments"]:
        for shot in seg["shots"]:
            total_shots += 1
            if not shot.get("share_with"):
                distinct_images += 1

    assert distinct_images == n


def test_n_less_than_s_sharing_structure():
    """When N < S, shots in a run share the run query and have share_with pointing to the first shot."""
    script = _make_script(num_segments=10, words_per_seg=30)
    N = 3
    res = plan_image_budget(script, N)
    assert res["images_after"] == 3
    assert res["shared_runs"] == 3

    runs_seen = {}
    for seg in script["segments"]:
        shot = seg["shots"][0]
        r_idx = shot.get("run_index")
        assert r_idx is not None
        if r_idx not in runs_seen:
            runs_seen[r_idx] = []
        runs_seen[r_idx].append(shot)

    assert len(runs_seen) == 3
    for r_idx, shots in runs_seen.items():
        first_shot = shots[0]
        assert first_shot.get("share_with") is None
        assert first_shot.get("run_position") == 0
        run_query = first_shot.get("query")
        assert run_query is not None

        for pos, shot in enumerate(shots[1:], 1):
            assert shot.get("share_with") == first_shot["shot_id"]
            assert shot.get("run_position") == pos
            assert shot.get("query") == run_query


def test_pinned_first_shot_survives_replan():
    """A user's deliberate pin on the first shot survives re-planning at different N values."""
    script = _make_script(num_segments=10, words_per_seg=30)
    script["segments"][0]["shots"][0]["pin"] = "images/custom_pin.jpg"
    script["segments"][0]["shots"][0]["source"] = "pin"
    script["segments"][0]["shots"][0]["resolved"] = "images/custom_pin.jpg"

    plan_image_budget(script, 3)
    first_shot_n3 = script["segments"][0]["shots"][0]
    assert first_shot_n3.get("pin") == "images/custom_pin.jpg"
    assert first_shot_n3.get("source") == "pin"

    plan_image_budget(script, 20)
    first_shot_n20 = script["segments"][0]["shots"][0]
    assert first_shot_n20.get("pin") == "images/custom_pin.jpg"
    assert first_shot_n20.get("source") == "pin"


def test_segment_durations_drive_distribution_when_n_greater_than_s():
    """A segment twice as long gets roughly twice the images when N > S."""
    script = {
        "project": {"title": "Duration Test"},
        "segments": [
            {
                "segment_id": 1,
                "narration": "Short segment. " + " ".join(["short"] * 20) + ".",
                "shots": [{"shot_id": "1a"}],
            },
            {
                "segment_id": 2,
                "narration": "Long segment with double words. " + " ".join(["long"] * 40) + ".",
                "shots": [{"shot_id": "2a"}],
            },
        ],
    }

    res = plan_image_budget(script, 6)
    assert res["images_after"] == 6
    seg1_shots = len(script["segments"][0]["shots"])
    seg2_shots = len(script["segments"][1]["shots"])
    assert seg1_shots + seg2_shots == 6
    assert seg2_shots >= seg1_shots * 1.5


def test_resolver_reuses_shared_image_with_minimal_searches(monkeypatch):
    """The resolver reuses the shared image so a 5-segment run triggers 1 search, not 5."""
    script = _make_script(num_segments=5, words_per_seg=30)
    plan_image_budget(script, 1)

    search_calls = []

    def mock_search(query, k=5, exclude=None, min_score=0.0, folder="", allow_reuse=True):
        search_calls.append(query)
        return [("library/images/shared_test.jpg", 0.35)]

    monkeypatch.setattr(library, "search", mock_search)
    monkeypatch.setattr(library, "resolve_library_path", lambda p: p if p else None)
    monkeypatch.setattr(library, "optimal_assignment", lambda **kwargs: {})

    report = library.plan_shots(script, min_score=0.26, weak_band=0.06)

    assert len(search_calls) == 1
    assert report["total_shots"] == 5
    assert report["matched"] == 5

    first_image = report["shot_reports"][0]["best_path"]
    assert first_image == "library/images/shared_test.jpg"
    for r in report["shot_reports"]:
        assert r["best_path"] == first_image
        assert r["state"] == "matched"


def test_resolver_44_segments_at_n_3_triggers_exactly_3_searches(monkeypatch):
    """For a 44-segment script at N = 3, plan_shots runs exactly 3 searches."""
    script = _make_script(num_segments=44, words_per_seg=45)
    plan_image_budget(script, 3)

    search_calls = []

    def mock_search(query, k=5, exclude=None, min_score=0.0, folder="", allow_reuse=True):
        search_calls.append(query)
        return [(f"library/images/result_{len(search_calls)}.jpg", 0.35)]

    monkeypatch.setattr(library, "search", mock_search)
    monkeypatch.setattr(library, "resolve_library_path", lambda p: p if p else None)

    report = library.plan_shots(script, min_score=0.26, weak_band=0.06)

    assert len(search_calls) == 3
    assert report["total_shots"] == 44
    assert report["matched"] == 44


def test_a_pin_on_a_follower_segment_survives_the_budget(monkeypatch):
    """
    A pin outranks sharing, wherever in the run it sits.

    The run leader is trivially safe - it never carries share_with. The shot that
    breaks is a *follower*: plan_image_budget copies the pin onto it and also
    marks it share_with, and the resolver used to check share_with first and
    `continue` past the pin branch, discarding the user's choice.
    """
    script = _make_script(num_segments=10, words_per_seg=30)

    # Segment 2 is a follower of segment 1 at N=3. Pin it deliberately.
    script["segments"][1]["shots"][0]["pin"] = "library/images/MY_PIN.jpg"
    script["segments"][1]["shots"][0]["source"] = "pin"

    plan_image_budget(script, 3)

    pinned = script["segments"][1]["shots"][0]
    assert pinned.get("pin") == "library/images/MY_PIN.jpg"
    assert pinned.get("share_with"), "segment 2 must be a follower for this test to mean anything"

    monkeypatch.setattr(library, "search",
                        lambda q, **kw: [("library/images/from_search.jpg", 0.35)])
    monkeypatch.setattr(library, "resolve_library_path", lambda p: p if p else None)
    monkeypatch.setattr(library, "optimal_assignment", lambda **kwargs: {})

    report = library.plan_shots(script, min_score=0.26, weak_band=0.06)

    rep = next(r for r in report["shot_reports"] if r["shot_id"] == pinned["shot_id"])
    assert rep["best_path"] == "library/images/MY_PIN.jpg", (
        "the run's shared image overwrote a deliberate pin"
    )
    assert rep["state"] == "pinned"
