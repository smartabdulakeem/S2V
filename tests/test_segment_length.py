"""
Segments must stay watchable in length, whatever the paste looks like.

split_into_segments honoured blank-line paragraphs exactly and applied max_words
only in its unformatted-text fallback. A script pasted as a title line, a blank
line, and one solid block therefore produced two segments — one of 5,414 words,
about forty minutes of narration on a single shot. The real 52-segment film runs
a median segment of 25 seconds.
"""

import pytest

from pipeline.text_parser import split_into_segments, drop_title_segment


def _words(segments):
    return [len(s.split()) for s in segments]


def test_one_enormous_paragraph_is_broken_up():
    body = " ".join(f"This is sentence number {i} of the narration." for i in range(200))
    text = f"S1E2 — The House of Wisdom\n\n{body}"

    segments = split_into_segments(text, max_words=60)

    assert len(segments) > 20, "a 1,600-word paragraph must not stay as one segment"
    assert max(_words(segments)) <= 90, f"segment far over the cap: {max(_words(segments))} words"


def test_no_words_are_lost_when_splitting():
    body = " ".join(f"Sentence {i} carries meaning that must survive." for i in range(120))
    text = f"Title Line Here\n\n{body}"

    segments = split_into_segments(text, max_words=60)

    original = (("Title Line Here " + body).split())
    rebuilt = " ".join(segments).split()
    assert rebuilt == original, "splitting dropped or reordered content"


def test_reasonable_paragraphs_are_still_respected():
    """Paragraph boundaries remain segment boundaries when they are sane."""
    paras = [
        "The water is gone and the mountain is dry after many days of waiting.",
        "Eighty people stand in a village of eighty houses on the slopes.",
        "The earth has been returned to something close to its original condition.",
    ]
    segments = split_into_segments("\n\n".join(paras), max_words=60)

    assert segments == paras


def test_single_line_paragraphs_are_capped_too():
    long_line = " ".join(f"word{i}" for i in range(300))
    text = f"A short opening line.\n{long_line}\nA short closing line."

    segments = split_into_segments(text, max_words=60)

    assert max(_words(segments)) <= 90


# ── The title line ────────────────────────────────────────────────────────────

def test_title_line_is_dropped_as_a_segment():
    """
    The title is already project metadata. Narrating it wastes a shot on an
    unmatchable query and puts an episode heading in the voiceover.
    """
    segments = ['S1E2 Part 1 — The House of Wisdom', "The water is gone. The mountain is dry."]

    kept = drop_title_segment(segments, "S1E2 Part 1 — The House of Wisdom")

    assert kept == ["The water is gone. The mountain is dry."]


def test_title_match_ignores_punctuation_and_case():
    segments = ['s2e2 "the weight of the mantle"', "Abu Bakr stood before them."]
    kept = drop_title_segment(segments, 'S2E2 — "The Weight of the Mantle"')
    assert len(kept) == 1


def test_real_narration_is_never_dropped():
    segments = ["The water is gone. The mountain is dry.", "Eighty people stand there."]
    kept = drop_title_segment(segments, "S1E2 — The House of Wisdom")
    assert kept == segments


def test_a_long_opening_segment_is_kept_even_if_it_mentions_the_title():
    opening = (
        "The House of Wisdom was not built in a day, and the story of how it rose "
        "from nothing begins long before any of the names we know were written down."
    )
    kept = drop_title_segment([opening, "Second segment."], "The House of Wisdom")
    assert len(kept) == 2, "a real opening segment must survive"


def test_dropping_never_empties_the_script():
    kept = drop_title_segment(["S1E2 — The House of Wisdom"], "S1E2 — The House of Wisdom")
    assert kept == ["S1E2 — The House of Wisdom"], "the only segment must not be removed"
