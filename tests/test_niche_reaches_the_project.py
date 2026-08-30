"""
The niche picked on the Script screen must reach the project.

`build_script_with_deepseek_and_gemini` has always accepted `series_slug`, with
a hardcoded default of "islamic_history". Nothing above it ever passed one:
`generate_storyboard_plan` had no such parameter, and neither did
`parse_plain_text`. The Script screen read the dropdown into a `seriesSlug`
variable and then used it only in the web-mode fallback.

So every project built through the app was stamped `islamic_history` whatever
the user chose. A niche could be written, saved, and selected, and none of it
reached a single prompt — which is why an owner could paste a 5,277-character
recipe, watch it save, switch the dropdown, and still get generic pictures.

The evidence that finally named it: a project saved
`visual_type: "editorial_illustration"` with the label "Historical Cinematic
Still" — a preset that exists only in the owner's own niche — while its
`series_slug` said `islamic_history`. The visual type was attached from the
dropdown; the niche was not.
"""

import os
import re
import sys
import inspect
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pipeline.ai_agent as ai_agent
from pipeline.ai_agent import generate_storyboard_plan


NICHE = "pre_islamic_prophetic___global_history"

FRONTEND = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "app.js"
)
APP_PY = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py"
)


def _fake_script():
    return {
        "project": {"title": "T", "series_slug": "islamic_history"},
        "segments": [{"segment_id": 1, "narration": "A short line of narration.", "shots": []}],
    }


def test_generate_storyboard_plan_takes_a_series_slug():
    params = inspect.signature(generate_storyboard_plan).parameters
    assert "series_slug" in params, (
        "the planner cannot receive the niche the user picked"
    )


def test_parse_plain_text_takes_a_series_slug():
    """Checked on the source, so the test does not need a pywebview window."""
    src = open(APP_PY, encoding="utf-8").read()
    sig = re.search(r"def parse_plain_text\((.*?)\) -> dict:", src, re.S)
    assert sig, "parse_plain_text signature not found"
    assert "series_slug" in sig.group(1), (
        "the API the Script screen calls cannot receive the niche"
    )


def test_the_chosen_niche_lands_on_the_project():
    with patch.object(ai_agent, "initialize_project_sourcing", create=True), \
         patch("pipeline.visuals.initialize_project_sourcing"), \
         patch("pipeline.text_parser.build_script_with_deepseek_and_gemini",
               return_value=_fake_script()):
        res = generate_storyboard_plan(
            text="A short line of narration.",
            title="T",
            voice="local:kokoro-bm_george",
            output_filename="t.mp4",
            google_api_key="dummy",
            series_slug=NICHE,
        )
    assert res["success"]
    assert res["script"]["project"]["series_slug"] == NICHE, (
        "the project was stamped with a niche the user did not choose"
    )


def test_the_chosen_niche_survives_the_rules_fallback():
    """When AI planning throws, the fallback must still carry the niche."""
    with patch("pipeline.visuals.initialize_project_sourcing"), \
         patch("pipeline.text_parser.build_script_with_deepseek_and_gemini",
               side_effect=RuntimeError("planner down")), \
         patch("pipeline.ai_agent.build_script", return_value=_fake_script()):
        res = generate_storyboard_plan(
            text="A short line of narration.",
            title="T",
            voice="local:kokoro-bm_george",
            output_filename="t.mp4",
            google_api_key="dummy",
            series_slug=NICHE,
        )
    assert res["success"] and res.get("fallback") is True
    assert res["script"]["project"]["series_slug"] == NICHE, (
        "the fallback path dropped the niche"
    )


def test_no_slug_given_changes_nothing():
    with patch("pipeline.visuals.initialize_project_sourcing"), \
         patch("pipeline.text_parser.build_script_with_deepseek_and_gemini",
               return_value=_fake_script()):
        res = generate_storyboard_plan(
            text="A short line of narration.",
            title="T",
            voice="local:kokoro-bm_george",
            output_filename="t.mp4",
            google_api_key="dummy",
        )
    assert res["script"]["project"]["series_slug"] == "islamic_history"


def test_the_script_screen_actually_sends_the_dropdown():
    """
    The bug was never in the backend — it was a variable read and then not
    passed. A signature test alone would still have passed while the Script
    screen dropped it on the floor.
    """
    src = open(FRONTEND, encoding="utf-8").read()
    call = re.search(r"api\.parse_plain_text\((.*?)\);", src, re.S)
    assert call, "the parse_plain_text call site was not found"
    assert "seriesSlug" in call.group(1), (
        "the Script screen reads the niche dropdown but never sends it"
    )
