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

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.narration_timing import segment_seconds


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