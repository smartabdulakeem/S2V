"""
Editing the words of a line did not re-record it.

`generate_voiceover` writes `segment_<id>_audio.mp3` and decides the cached file
is still good from the segment number and the narrative tone. The narration
itself was never part of that decision, so rewording a line and re-rendering
returned the previous recording of the previous words - silently, with no error
and nothing in the progress log.

From the narration timing pass onward this stopped being only an audio problem:
the stale recording's duration is written onto the script and decides where a
picture starts and ends, so a stale mp3 becomes a stale picture boundary.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pipeline.voiceover as vo


@pytest.fixture
def cache(tmp_path):
    return str(tmp_path)


def _record(cache_dir, calls, text):
    """Call generate_voiceover with the engine stubbed, returning the mp3 path."""
    def _fake_kokoro(narration, voice, voice_rate, output_path, on_progress=None, segment_id=0, narrative_tone=""):
        calls.append(narration)
        with open(output_path, "wb") as fh:
            fh.write(b"ID3fake-audio")

    original = vo._generate_with_local_kokoro
    vo._generate_with_local_kokoro = _fake_kokoro
    try:
        return vo.generate_voiceover(
            segment_id=1, narration=text, voice=vo.FALLBACK_VOICE,
            voice_rate="+0%", voice_pitch="+0Hz", cache_dir=cache_dir,
        )
    finally:
        vo._generate_with_local_kokoro = original


def test_the_same_words_are_not_recorded_twice(cache):
    calls = []
    _record(cache, calls, "the same words")
    _record(cache, calls, "the same words")

    assert len(calls) == 1, "an unchanged line must still come from the cache"


def test_rewording_a_line_re_records_it(cache):
    """The defect: the second call returned the first recording."""
    calls = []
    _record(cache, calls, "the original words")
    _record(cache, calls, "the words after an edit")

    assert calls == ["the original words", "the words after an edit"]


def test_audio_cached_before_this_fix_is_adopted_rather_than_re_recorded(cache):
    """
    Existing projects have an mp3 and a tone marker but no text marker. Treating
    that as a miss would re-record every segment of every film he has made. It is
    adopted and fingerprinted instead, so the next edit is the one that is caught.
    """
    calls = []
    path = _record(cache, calls, "words from before the fix")
    os.unlink(path + ".text")

    _record(cache, calls, "words from before the fix")
    assert len(calls) == 1, "a pre-fix cache must not trigger a re-record"

    _record(cache, calls, "words edited after the fix")
    assert len(calls) == 2, "but an edit after adoption must re-record"
