"""
The world anchor follows the niche a project is set to now, not the one it was
first planned under.

The pack's anchor used to be copied onto the project at parse time, and an
explicit anchor always beats the pack's, so the first niche a script saw
followed it forever. Every niche demanded seventh century Arabia, and the era
was stated twice over because the brief carried it too.
"""

import pytest

from pipeline.library import project_world_anchor, compose_gap_prompt


def test_a_pack_anchor_stored_on_a_project_defers_to_the_pack():
    """The stale copy is recognised by matching a pack verbatim, and ignored."""
    planned_under_islamic_history = {
        "series_slug": "nature_wildlife",
        "world_anchor": "7th century Arabian Peninsula, early Islamic era",
    }
    assert project_world_anchor(planned_under_islamic_history) is None


def test_a_pack_anchor_is_matched_regardless_of_case_and_padding():
    messy = {"world_anchor": "  7TH CENTURY ARABIAN PENINSULA, EARLY ISLAMIC ERA  "}
    assert project_world_anchor(messy) is None


def test_a_hand_written_anchor_is_honoured():
    """An override is the user's own words and must survive."""
    own = {"series_slug": "nature_wildlife",
           "world_anchor": "the Serengeti in the long dry season"}
    assert project_world_anchor(own) == "the Serengeti in the long dry season"


def test_visual_style_is_never_read_as_an_anchor():
    """
    visual_style holds the label of the picked look ("Stylised Illustration").

    It used to be the fallback when no anchor was stored, which put the name of
    a style into the prompt's setting slot.
    """
    assert project_world_anchor({"visual_style": "Stylised Illustration"}) is None
    assert project_world_anchor({"visual_style": "vintage_documentary"}) is None


def test_a_missing_or_empty_anchor_is_fine():
    assert project_world_anchor({}) is None
    assert project_world_anchor({"world_anchor": "   "}) is None
    assert project_world_anchor(None) is None


def test_a_wildlife_prompt_carries_no_seventh_century_arabia():
    """The whole point, end to end."""
    stale = {"series_slug": "nature_wildlife",
             "world_anchor": "7th century Arabian Peninsula, early Islamic era"}
    prompt = compose_gap_prompt(
        shot_query="a lioness on a ridge at dawn",
        world_anchor=project_world_anchor(stale),
        series_slug="nature_wildlife",
        visual_type="photoreal",
        project_title="Big Cats",
        project_brief="A documentary photograph of wildlife and the natural world",
    )
    lowered = prompt.lower()
    assert "arabia" not in lowered
    assert "islamic" not in lowered
    assert "lioness" in lowered
