"""
Every picture must reach the prompt builder with a description.

Splitting a span to meet an exact count gave the description to the first piece
and nothing to the rest. `compose_gap_prompt` falls back to the shot's raw
search keywords when a description is missing, so those pictures came out as
noun piles - "Iblis Allah Adam", "Qur'an Adam's Adam".

Measured on the owner's real export: he asked for 30 pictures, the model
returned 3 spans, and the file held 3 written prompts and 27 keyword piles. It
got worse the more pictures he asked for, and Auto looked fine because Auto
never splits.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.picture_plan import (
    describe_missing_spans, fill_undescribed, parse_plan_reply, plan_pictures,
    repair_spans, strip_negations,
)

LINES = [f"line {i} of the narration, saying something" for i in range(1, 31)]
SECONDS = [4.0] * 30


class _Provider:
    """A stand-in model. Records what it was asked, returns what it was given."""

    def __init__(self, reply=""):
        self.reply = reply
        self.asked = None

    def complete_text(self, system="", user="", max_tokens=0):
        self.asked = system
        return self.reply


def _spans(*triples):
    return [{"first_line": a, "last_line": b, "description": d} for a, b, d in triples]


def test_splitting_to_an_exact_count_is_what_empties_the_descriptions():
    """The defect itself, held still so it cannot come back unnoticed."""
    model_gave = _spans((1, 16, "a wide untouched earth"),
                        (17, 25, "a cosmic wide shot"),
                        (26, 30, "a desolate rocky landscape"))
    out = repair_spans(model_gave, 30, SECONDS, 8.0, 75.0, exact_count=30)

    blank = [s for s in out if not (s.get("description") or "").strip()]
    assert len(out) == 30
    assert len(blank) == 27, "3 described, 27 left blank - this is the bug"


def test_only_the_pictures_left_blank_are_asked_about():
    spans = _spans((1, 10, "already written"), (11, 20, ""), (21, 30, ""))
    prov = _Provider("2: the second picture\n3: the third picture")

    describe_missing_spans(spans, LINES, "INSTRUCTION", prov)

    assert "already written" not in prov.asked
    assert "Picture 2" in prov.asked
    assert "Picture 3" in prov.asked
    assert "Picture 1" not in prov.asked


def test_a_reply_fills_the_blanks_and_leaves_the_written_one_alone():
    spans = _spans((1, 10, "already written"), (11, 20, ""), (21, 30, ""))
    prov = _Provider("2: the second picture\n3: the third picture")

    describe_missing_spans(spans, LINES, "INSTRUCTION", prov)

    assert [s["description"] for s in spans] == [
        "already written", "the second picture", "the third picture"]


def test_descriptions_are_matched_by_picture_number_not_by_order():
    """A reply answering out of order must not shift every description by one."""
    spans = _spans((1, 10, ""), (11, 20, ""), (21, 30, ""))
    prov = _Provider("3: the third\n1: the first\n2: the second")

    describe_missing_spans(spans, LINES, "INSTRUCTION", prov)

    assert [s["description"] for s in spans] == ["the first", "the second", "the third"]


def test_the_narration_a_picture_carries_is_what_the_model_is_shown():
    spans = _spans((1, 2, ""))
    prov = _Provider("1: anything")

    describe_missing_spans(spans, LINES, "INSTRUCTION", prov)

    assert LINES[0] in prov.asked
    assert LINES[1] in prov.asked
    assert LINES[5] not in prov.asked


def test_a_dead_model_still_leaves_no_picture_without_a_description():
    """
    A neighbour's description repeated is a worse picture.
    A pile of search keywords is not a picture at all.
    """
    class _Dead:
        def complete_text(self, **kw):
            raise RuntimeError("no provider")

    spans = _spans((1, 10, "a desolate rocky landscape"), (11, 20, ""), (21, 30, ""))
    describe_missing_spans(spans, LINES, "INSTRUCTION", _Dead())
    fill_undescribed(spans)

    assert all((s.get("description") or "").strip() for s in spans)
    assert spans[1]["description"] == "a desolate rocky landscape"


def test_a_blank_before_any_written_one_borrows_from_the_picture_after_it():
    spans = _spans((1, 10, ""), (11, 20, ""), (21, 30, "the only written one"))
    fill_undescribed(spans)
    assert [s["description"] for s in spans] == ["the only written one"] * 3


def test_nothing_written_at_all_is_left_alone_rather_than_faked():
    """With no description anywhere there is nothing honest to borrow."""
    spans = _spans((1, 30, ""))
    fill_undescribed(spans)
    assert spans[0]["description"] == ""


def test_the_whole_pass_leaves_every_picture_described():
    """plan_pictures is what the app calls; the guarantee must hold end to end."""
    reply = "\n".join(f"{i}-{i}: picture {i} shows something" for i in range(1, 31))
    out = plan_pictures(LINES, SECONDS, provider=_Provider(reply), exact_count=30)

    assert len(out) == 30
    assert all((s.get("description") or "").strip() for s in out)


def test_a_model_that_returns_three_spans_for_thirty_pictures_still_describes_all_thirty():
    """The owner's real run: 3 spans came back, 30 pictures were asked for."""
    class _ThenDescribes:
        """Returns 3 spans to the planning call, then answers the describe call."""

        def __init__(self):
            self.calls = 0

        def complete_text(self, system="", user="", max_tokens=0):
            self.calls += 1
            if self.calls == 1:
                return ("1-16: a wide untouched earth\n"
                        "17-25: a cosmic wide shot\n"
                        "26-30: a desolate rocky landscape")
            return "\n".join(f"{i}: written picture {i}" for i in range(1, 31))

    out = plan_pictures(LINES, SECONDS, provider=_ThenDescribes(), exact_count=30)

    assert len(out) == 30
    blank = [s for s in out if not (s.get("description") or "").strip()]
    assert blank == [], f"{len(blank)} pictures would fall back to raw keywords"


# -- what is not in the picture never reaches the picture ---------------------

def test_a_trailing_clause_about_what_is_absent_is_removed():
    """
    The opening picture of the owner's film read "...under a vast sky, devoid of
    any human presence or structures." A text encoder cannot subtract: it reads
    "human presence" and draws people into an empty landscape.
    """
    out = strip_negations("A wide untouched primordial landscape under a vast "
                          "sky, devoid of any human presence or structures.")
    assert out == "A wide untouched primordial landscape under a vast sky."


def test_a_negation_in_the_middle_closes_up_cleanly():
    out = strip_negations("A celestial sphere with volumetric shafts of light, "
                          "with no discernible figures, immense in scale.")
    assert out == "A celestial sphere with volumetric shafts of light, immense in scale."
    assert ",," not in out and " ," not in out


def test_a_description_with_nothing_to_remove_is_left_exactly_as_it_was():
    text = ("A canyon at dusk, jagged rock formations casting long shadows, "
            "heat-shimmer rising from bare stone.")
    assert strip_negations(text) == text


def test_a_description_that_is_only_a_negation_is_kept_rather_than_emptied():
    """A flawed description still beats an empty one."""
    assert strip_negations("no people") == "no people"


def test_the_scrub_runs_on_whatever_the_model_sends_back():
    got = parse_plan_reply("1-6: A wide landscape, devoid of any human figures.", 30)
    assert got[0]["description"] == "A wide landscape."


def test_the_scrub_runs_on_the_second_describe_pass_too():
    spans = [{"first_line": 1, "last_line": 10, "description": ""}]

    class _P:
        def complete_text(self, system="", user="", max_tokens=0):
            return "1: A still valley, without any sign of habitation."

    describe_missing_spans(spans, LINES, "INSTRUCTION", _P())
    assert spans[0]["description"] == "A still valley."

