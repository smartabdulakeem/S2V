"""
Planning used a word count to guess how long a line takes to say.

`WORDS_PER_SECOND = 2.6` is a decent average and wrong on every individual
line: a short line with a long pause after it, a name the voice labours over,
a rhetorical question read slowly. Boundaries placed on that estimate drift
from the audio the viewer actually hears.

The narration is generated anyway. Measuring it costs one ffprobe per segment.
"""

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.narration_timing import segment_seconds, measure_narration


def _script(*narrations):
    return {"segments": [{"segment_id": i + 1, "narration": n}
                         for i, n in enumerate(narrations)]}


def test_measured_seconds_are_used_when_they_are_there():
    script = _script("one two three", "four five six")
    script["segments"][0]["narration_seconds"] = 4.5
    script["segments"][1]["narration_seconds"] = 9.25

    assert segment_seconds(script) == [4.5, 9.25]


def test_the_word_estimate_stands_in_until_the_audio_exists():
    script = _script(" ".join(["word"] * 26))
    assert segment_seconds(script) == [10.0]


def test_one_measured_segment_does_not_make_the_others_zero():
    """A half-finished timing pass must not silently zero the rest."""
    script = _script("one two three four five", " ".join(["word"] * 26))
    script["segments"][0]["narration_seconds"] = 3.0

    assert segment_seconds(script) == [3.0, 10.0]


def test_an_empty_narration_takes_no_time():
    assert segment_seconds(_script("")) == [0.0]


def test_the_timing_pass_writes_real_seconds_onto_every_segment():
    script = _script("one two three", "four five six")

    with patch("pipeline.narration_timing.generate_voiceover",
               side_effect=lambda **kw: f"/fake/segment_{kw['segment_id']}_audio.mp3"), \
         patch("pipeline.narration_timing.probe_seconds",
               side_effect=lambda path: 4.5 if "segment_1" in path else 9.25):
        stats = measure_narration(script, cache_dir="/fake")

    assert [s["narration_seconds"] for s in script["segments"]] == [4.5, 9.25]
    assert stats["measured"] == 2
    assert stats["failed"] == 0


def test_a_segment_whose_audio_cannot_be_probed_keeps_its_estimate():
    """
    One unreadable mp3 must not zero a segment. A zero-length line collapses
    the boundary maths around it and takes the pacing with it.
    """
    script = _script(" ".join(["word"] * 26), "four five six")

    with patch("pipeline.narration_timing.generate_voiceover",
               side_effect=lambda **kw: f"/fake/segment_{kw['segment_id']}_audio.mp3"), \
         patch("pipeline.narration_timing.probe_seconds",
               side_effect=lambda path: None if "segment_1" in path else 9.25):
        stats = measure_narration(script, cache_dir="/fake")

    assert script["segments"][0].get("narration_seconds") is None
    assert segment_seconds(script) == [10.0, 9.25]
    assert stats["failed"] == 1


def test_a_dead_tts_engine_does_not_take_the_whole_pass_down():
    script = _script("one two three")

    with patch("pipeline.narration_timing.generate_voiceover",
               side_effect=RuntimeError("no engine")):
        stats = measure_narration(script, cache_dir="/fake")

    assert stats["failed"] == 1
    assert stats["measured"] == 0


def test_the_audio_path_is_kept_beside_the_seconds():
    """
    `write_wolfcut_project` takes an audio path per segment and a duration per
    segment, and measures neither itself. Its only caller today is inside the
    render, so a WolfCut timeline costs a full video encode. The timing pass
    produces both maps — keeping the path here is what lets WolfCut export
    without rendering anything.
    """
    script = _script("one two three", "four five six")

    with patch("pipeline.narration_timing.generate_voiceover",
               side_effect=lambda **kw: f"/fake/segment_{kw['segment_id']}_audio.mp3"), \
         patch("pipeline.narration_timing.probe_seconds", return_value=4.0):
        measure_narration(script, cache_dir="/fake")

    assert script["segments"][0]["narration_audio"] == "/fake/segment_1_audio.mp3"
    assert script["segments"][1]["narration_audio"] == "/fake/segment_2_audio.mp3"