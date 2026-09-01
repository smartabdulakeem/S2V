"""
pipeline/narration_timing.py

How long each line of narration actually takes to say.

Planning guessed from a word count. That average is fine across a film and
wrong on every individual line, and picture boundaries placed on a guess drift
from the audio the viewer hears. The narration is generated anyway, so the
real number is one ffprobe away.
"""

import os
import sys

from pipeline.text_parser import WORDS_PER_SECOND


def estimated_seconds(narration: str) -> float:
    """The word-count stand-in, used until the audio exists."""
    words = len((narration or "").split())
    return round(words / WORDS_PER_SECOND, 3) if words else 0.0


def segment_seconds(script_data: dict) -> list:
    """
    Seconds per segment, in script order.

    Measured where a timing pass has run, estimated everywhere else, so a
    half-finished pass degrades to the old behaviour rather than to zeros.
    """
    out = []
    for seg in (script_data.get("segments") or []):
        measured = seg.get("narration_seconds")
        try:
            measured = float(measured)
        except (TypeError, ValueError):
            measured = None
        if measured and measured > 0:
            out.append(measured)
        else:
            out.append(estimated_seconds(seg.get("narration") or ""))
    return out