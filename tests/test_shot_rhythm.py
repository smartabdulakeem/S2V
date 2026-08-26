"""
The shot rhythm slider.

It shipped wired to nothing: `oninput` rewrote its own label and no code ever read
the value, so every segment held one image for its whole span — a slideshow at the
~19s segments this app produces, where documentary cuts every 4-6 seconds.
"""

import pytest

from pipeline.text_parser import apply_shot_rhythm, split_narration_for_shots


def _script(narration, segments=1):
    return {
        "project": {"title": "Rhythm"},
        "segments": [
            {"segment_id": i + 1, "narration": narration,
             "shots": [{"shot_id": f"{i + 1}a", "query": "old query",
                        "treatment": {"filter": "documentary", "grade": None}}]}
            for i in range(segments)
        ],
    }


LONG = (
    "The water is gone and the mountain is dry. Eighty people stand in a village. "
    "Everything that was before the flood is gone now. The earth has been returned "
    "to something close to its original condition. Clean and waiting for what comes. "
    "The question that hangs over everything is simple enough to ask."
)


def test_shorter_rhythm_produces_more_shots():
    slow = _script(LONG)
    fast = _script(LONG)
    slow_stats = apply_shot_rhythm(slow, 12)
    fast_stats = apply_shot_rhythm(fast, 3)

    assert fast_stats["shots_after"] > slow_stats["shots_after"]
    assert slow_stats["shots_after"] >= 1


def test_each_shot_gets_its_own_query():
    script = _script(LONG)
    apply_shot_rhythm(script, 4)
    shots = script["segments"][0]["shots"]

    assert len(shots) > 1
    queries = [s["query"] for s in shots]
    assert len(set(queries)) > 1, "every shot got the same query, so every shot gets the same image"
    assert all(q and q.strip() for q in queries)


def test_shot_ids_are_unique_and_ordered():
    script = _script(LONG)
    apply_shot_rhythm(script, 4)
    ids = [s["shot_id"] for s in script["segments"][0]["shots"]]
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)


def test_consecutive_shots_do_not_repeat_the_same_move():
    script = _script(LONG)
    apply_shot_rhythm(script, 3)
    effects = [s["motion"]["effect"] for s in script["segments"][0]["shots"]]
    for a, b in zip(effects, effects[1:]):
        assert a != b, "two shots in a row use the same camera move"


def test_a_pinned_shot_survives_a_rhythm_change():
    script = _script(LONG)
    script["segments"][0]["shots"][0].update({"source": "pin", "pin": "library/images/mine.jpg"})
    apply_shot_rhythm(script, 4)

    first = script["segments"][0]["shots"][0]
    assert first["pin"] == "library/images/mine.jpg"
    assert first["source"] == "pin"


def test_the_segment_treatment_is_preserved():
    script = _script(LONG)
    apply_shot_rhythm(script, 4)
    assert all(s["treatment"]["filter"] == "documentary" for s in script["segments"][0]["shots"])


def test_a_one_sentence_segment_still_splits_when_it_is_long():
    """Shot boundaries are visual, so a long single sentence may still be cut."""
    one = "word " * 60
    chunks = split_narration_for_shots(one.strip(), 4)
    assert len(chunks) == 4
    assert " ".join(chunks).split() == one.split()


def test_a_very_short_segment_is_left_as_one_shot():
    script = _script("Two words.")
    apply_shot_rhythm(script, 3)
    assert len(script["segments"][0]["shots"]) == 1


def test_no_narration_word_is_lost_when_splitting():
    chunks = split_narration_for_shots(LONG, 5)
    assert " ".join(chunks).split() == LONG.split()
