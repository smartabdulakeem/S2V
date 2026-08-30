"""
When a niche has a prompt recipe, the recipe governs the shot descriptions.

The recipe was only ever read by the batch planner in `text_parser`, which runs
when a script is built with AI. The board's plan calls `plan_shots`, which never
touches it — descriptions came from `shot_description.INSTRUCTION`, a fixed
"documentary shot designer" brief capped at "12 to 25 words" that also bans the
word "cinematic".

So an owner could write five thousand words of recipe, watch it save correctly,
and still get seventeen plain words per shot. Making the pass merely *aware* of
the niche was not enough: the hardcoded rules were still the ones in charge.

With a recipe present the recipe becomes the instruction, and the generated text
is judged against what the recipe asked for rather than against the built-in
length and style limits. With no recipe, nothing changes.
"""

import os
import sys
import json
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pipeline.shot_description as shot_desc_module
from pipeline.shot_description import (
    describe_shots,
    is_valid_description,
    _build_instruction,
    INSTRUCTION,
)


RECIPE = (
    "You are the visual storyboard planner for ancient and pre-Islamic sacred history.\n"
    "Write rich, specific, cinematic descriptions grounded in material culture.\n"
    "Name the light, the materials, and what people are physically doing."
)

CFG_WITH_RECIPE = {
    "series_slug": "pre_islamic_prophetic___global_history",
    "prompt_recipe": RECIPE,
    "era_block": "mud brick, palm and undressed stone, oil lamp and open fire light",
}

CFG_NO_RECIPE = {"series_slug": "islamic_history", "prompt_recipe": "", "era_block": ""}

# 47 words, and it says "cinematic" — everything the built-in rules reject.
RICH_SENTENCE = (
    "A cinematic wide view of labourers hauling reed baskets of wet silt up the ramp of a "
    "half-built mud-brick granary, the irrigation channels below catching the last copper "
    "light of the day while dust hangs in the warm air above the floodplain"
)


@pytest.fixture(autouse=True)
def clean_cache(tmp_path, monkeypatch):
    shot_desc_module._MEMORY_CACHE.clear()
    monkeypatch.setattr(shot_desc_module, "CACHE_FILE", str(tmp_path / "shot_descriptions.json"))
    monkeypatch.setattr(shot_desc_module, "CACHE_DIR", str(tmp_path))


def _gemini_body(text: str) -> bytes:
    return json.dumps(
        {"candidates": [{"content": {"parts": [{"text": text}]}}]}
    ).encode("utf-8")


def _mock_response(body: bytes):
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__.return_value = resp
    return resp


def test_the_recipe_becomes_the_instruction():
    built = _build_instruction(CFG_WITH_RECIPE)
    assert RECIPE.splitlines()[0] in built, "the recipe does not govern the instruction"
    assert "12 to 25 words" not in built, "the built-in length cap still governs the recipe"
    assert CFG_WITH_RECIPE["era_block"] in built, "the era was not carried into the instruction"
    # The output contract must survive, or the reply cannot be parsed back.
    assert "<number>." in built


def test_no_recipe_leaves_the_instruction_exactly_as_it_was():
    assert _build_instruction(None) == INSTRUCTION
    assert _build_instruction(CFG_NO_RECIPE).startswith(INSTRUCTION)
    assert "12 to 25 words" in _build_instruction(CFG_NO_RECIPE)


def test_a_rich_generated_description_survives_when_a_recipe_governs():
    shots = [{"shot_id": "s1", "scene": "They built the granaries beside the river"}]
    reply = f"1. {RICH_SENTENCE}"

    with patch("urllib.request.urlopen", return_value=_mock_response(_gemini_body(reply))):
        result = describe_shots(shots, api_key="dummy", series_cfg=CFG_WITH_RECIPE)

    assert result.get("s1") == RICH_SENTENCE, (
        "the recipe asked for a rich cinematic description and the pass threw it away"
    )


def test_the_same_description_is_still_rejected_when_no_recipe_governs():
    shots = [{"shot_id": "s1", "scene": "They built the granaries beside the river"}]
    reply = f"1. {RICH_SENTENCE}"

    with patch("urllib.request.urlopen", return_value=_mock_response(_gemini_body(reply))):
        result = describe_shots(shots, api_key="dummy", series_cfg=CFG_NO_RECIPE)

    assert "s1" not in result, "the built-in gates stopped applying to a niche with no recipe"


def test_is_valid_description_keeps_its_original_meaning_by_default():
    assert is_valid_description(RICH_SENTENCE) is False
    assert is_valid_description(RICH_SENTENCE, allow_rich=True) is True
    assert is_valid_description("", allow_rich=True) is False
    assert is_valid_description("   ", allow_rich=True) is False
    # Even a rich description has an upper bound; runaway output is still junk.
    assert is_valid_description("word " * 400, allow_rich=True) is False
