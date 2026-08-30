"""
The description model must read the whole script before writing any shot.

`describe_shots` sent the instruction and then twenty bare narration fragments,
each on its own numbered line, with nothing around them. Asked to illustrate
"Before Adam ever walked upon the earth, something had already happened.", a
model has almost nothing to reason from: it cannot know what happened, who is in
the film, what came before that line or what follows it. It answers with the
only thing a lone clause supports — a vague landscape.

Every one of the owner's scripts fits in a few thousand tokens, so there is no
reason to withhold it. The whole narration now travels with every batch, each
excerpt is tagged with its line number inside that script, and the model is told
to place the moment before describing it.

The cache key carries the script too: the same sentence inside a different film
is a different picture, which is the entire point of sending the script.
"""

import os
import sys
import json
import re
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pipeline.shot_description as shot_desc_module
from pipeline.shot_description import describe_shots, _scene_hash, _build_batch_prompt
from pipeline.llm.gemini import GeminiProvider


SCRIPT = [
    "Before Adam ever walked upon the earth, something had already happened.",
    "The earth had been inhabited before humanity.",
    "And according to early reports, there had been corruption and bloodshed.",
    "Then Allah announced to the angels:",
    "I am going to place a khalifah on the earth.",
]

CFG = {
    "series_slug": "pre_islamic_prophetic___global_history",
    "prompt_recipe": "Write grounded historical descriptions.",
    "era_block": "",
}


@pytest.fixture(autouse=True)
def clean_cache(tmp_path, monkeypatch):
    shot_desc_module._MEMORY_CACHE.clear()
    monkeypatch.setattr(shot_desc_module, "CACHE_FILE", str(tmp_path / "shot_descriptions.json"))
    monkeypatch.setattr(shot_desc_module, "CACHE_DIR", str(tmp_path))


def _gemini_body(text):
    return json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}}]}).encode("utf-8")


def _mock_response(body):
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__.return_value = resp
    return resp


def test_the_whole_script_travels_with_the_batch():
    batch = [{"shot_id": "4a", "scene": SCRIPT[3]}]
    prompt = _build_batch_prompt("INSTRUCTION HERE", batch, script_context=SCRIPT)

    for line in SCRIPT:
        assert line in prompt, f"the model was not shown this line of the script: {line!r}"


def test_each_excerpt_is_placed_inside_the_script():
    batch = [{"shot_id": "4a", "scene": SCRIPT[3]}]
    prompt = _build_batch_prompt("INSTRUCTION HERE", batch, script_context=SCRIPT)

    # The excerpt must be locatable in the script the model was given, so it can
    # read what comes before and after it.
    assert re.search(r"line\s*4", prompt, re.I), (
        "the excerpt was not tied to its position in the script"
    )


def test_without_a_script_the_prompt_is_what_it_always_was():
    batch = [{"shot_id": "1a", "scene": SCRIPT[0]}]
    plain = _build_batch_prompt("INSTRUCTION HERE", batch, script_context=None)

    assert plain.startswith("INSTRUCTION HERE")
    assert "1. " + SCRIPT[0] in plain
    assert SCRIPT[2] not in plain, "context leaked in when none was given"


def test_the_same_line_in_a_different_film_is_a_different_picture():
    a = _scene_hash(SCRIPT[0], series_slug="n", prompt_recipe="r", script_context=SCRIPT)
    b = _scene_hash(SCRIPT[0], series_slug="n", prompt_recipe="r",
                    script_context=["A completely different film about bees."])
    assert a != b, "the cached description ignores the script it was written for"

    same = _scene_hash(SCRIPT[0], series_slug="n", prompt_recipe="r", script_context=SCRIPT)
    assert a == same, "the key is not stable for the same script"


def test_the_script_reaches_the_model_through_describe_shots():
    shots = [{"shot_id": "4a", "scene": SCRIPT[3]}]
    captured = {}

    def _capture(self, system, user="", max_tokens=2048):
        captured["prompt"] = system
        return "1. A hall of bowed figures beneath a shaft of pale light"

    # Gemini reaches the model through the provider seam now, not through a
    # private HTTP call inside this module. Same assertion, one layer over.
    with patch.object(GeminiProvider, "complete_text", _capture):
        res = describe_shots(shots, api_key="dummy", series_cfg=CFG, script_context=SCRIPT)

    assert res["4a"] == "A hall of bowed figures beneath a shaft of pale light"
    assert SCRIPT[0] in captured["prompt"], "describe_shots did not forward the script"
    assert SCRIPT[4] in captured["prompt"], "describe_shots forwarded only part of the script"
