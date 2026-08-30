"""
tests/test_shot_description.py

Unit tests for AI-powered visual shot descriptions with mocked HTTP layer.
Ensures zero live network calls during tests.
"""

import json
import pytest
import urllib.request
import urllib.error
from unittest.mock import patch, MagicMock

import pipeline.shot_description as shot_desc_module
from pipeline.shot_description import (
    describe_shots,
    is_valid_description,
    _scene_hash,
    _MEMORY_CACHE,
)
from pipeline.library import compose_gap_prompt


@pytest.fixture(autouse=True)
def clean_cache(tmp_path, monkeypatch):
    """Ensure a pristine cache state for each test."""
    shot_desc_module._MEMORY_CACHE.clear()
    fake_cache_file = tmp_path / "shot_descriptions.json"
    monkeypatch.setattr(shot_desc_module, "CACHE_FILE", str(fake_cache_file))
    monkeypatch.setattr(shot_desc_module, "CACHE_DIR", str(tmp_path))


def _make_gemini_response(text: str) -> bytes:
    payload = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": text}]
                }
            }
        ]
    }
    return json.dumps(payload).encode("utf-8")


def _create_mock_response(body_bytes: bytes):
    mock_resp = MagicMock()
    mock_resp.read.return_value = body_bytes
    mock_resp.__enter__.return_value = mock_resp
    return mock_resp


def test_1_batch_mapping_and_offset_guard():
    """
    A well-formed reply maps to the right shots, including on the second batch
    (guards the batch-offset bug where line 1 in batch 2 would overwrite shot 1).
    """
    # 25 shots: 1..20 in batch 1, 21..25 in batch 2
    shots = [{"shot_id": f"shot_{i}", "scene": f"Narration slice {i} describing events"} for i in range(1, 26)]

    batch1_reply = "\n".join([f"{i}. Visual description for shot {i} showing action" for i in range(1, 21)])
    batch2_reply = "\n".join([f"{i}. Second batch visual description for shot {i + 20}" for i in range(1, 6)])

    call_count = 0

    def mock_urlopen(req, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        body = req.data.decode("utf-8")
        if "Narration slice 21" in body:
            return _create_mock_response(_make_gemini_response(batch2_reply))
        else:
            return _create_mock_response(_make_gemini_response(batch1_reply))

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        result = describe_shots(shots, api_key="dummy-gemini-key")

    assert call_count == 2, f"Expected 2 batches, got {call_count}"
    assert len(result) == 25

    # Check batch 1 mappings
    assert result["shot_1"] == "Visual description for shot 1 showing action"
    assert result["shot_20"] == "Visual description for shot 20 showing action"

    # Crucial guard: Shot 21 (which was numbered 1 in batch 2) must map to shot_21, NOT shot_1
    assert result["shot_21"] == "Second batch visual description for shot 21"
    assert result["shot_25"] == "Second batch visual description for shot 25"


def test_2_missing_and_extra_numbered_lines():
    """
    A reply with missing or extra numbered lines drops the bad ones and keeps the good ones.
    """
    shots = [{"shot_id": f"shot_{i}", "scene": f"Narration slice {i}"} for i in range(1, 6)]

    # Returns lines 1, 3, 99 (invalid index), random unnumbered text, and 4
    mixed_reply = """
    1. A stone fountain bubbling in an ancient courtyard
    Some unwanted preamble text
    3. A lone traveler walking along a winding mountain path
    99. Hallucinated extra shot line outside bounds
    4. Two elders discussing a parchment document under an archway
    """

    mock_resp = _create_mock_response(_make_gemini_response(mixed_reply))

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = describe_shots(shots, api_key="dummy-gemini-key")

    assert "shot_1" in result
    assert result["shot_1"] == "A stone fountain bubbling in an ancient courtyard"
    assert "shot_3" in result
    assert result["shot_3"] == "A lone traveler walking along a winding mountain path"
    assert "shot_4" in result
    assert result["shot_4"] == "Two elders discussing a parchment document under an archway"

    # Missing line 2 and 5 should be absent
    assert "shot_2" not in result
    assert "shot_5" not in result
    # Out of bounds 99 should not create anything
    assert "shot_99" not in result


def test_3_banned_style_words_and_length_rejection():
    """
    A reply containing a banned style word is rejected for that shot only.
    Sentences longer than 40 words are also rejected.
    """
    shots = [
        {"shot_id": "shot_cinematic", "scene": "Narration one"},
        {"shot_id": "shot_wide", "scene": "Narration two"},
        {"shot_id": "shot_text", "scene": "Narration three"},
        {"shot_id": "shot_too_long", "scene": "Narration four"},
        {"shot_id": "shot_valid", "scene": "Narration five"},
    ]

    long_sentence = "A man walking through an endless desert under the blazing sun " * 8  # > 40 words

    reply = f"""
    1. A cinematic view of a ruined castle at sunset
    2. A wide shot of horses galloping across an open field
    3. A stone tablet with bold text and letters engraved upon it
    4. {long_sentence}
    5. A flock of white birds flying over a quiet calm lake
    """

    mock_resp = _create_mock_response(_make_gemini_response(reply))

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = describe_shots(shots, api_key="dummy-gemini-key")

    # Banned words rejected
    assert "shot_cinematic" not in result
    assert "shot_wide" not in result
    assert "shot_text" not in result
    assert "shot_too_long" not in result

    # Valid shot kept
    assert result["shot_valid"] == "A flock of white birds flying over a quiet calm lake"


def test_4_cache_skips_unchanged_scene():
    """
    A shot with an unchanged `scene` and an existing `visual_description` triggers no API call.
    """
    shots = [
        {
            "shot_id": "shot_1",
            "scene": "The army stood waiting on the ridge at dawn",
            "visual_description": "A line of armored spearmen standing motionless on a sandy ridge at dawn"
        },
        {
            "shot_id": "shot_2",
            "scene": "The horses charged across the valley floor"
        }
    ]

    # Pre-populate memory cache for shot 2's scene
    shot_desc_module._MEMORY_CACHE[_scene_hash(shots[1]["scene"])] = "Horses galloping in formation across a dry riverbed"

    mock_urlopen = MagicMock()
    with patch("urllib.request.urlopen", mock_urlopen):
        result = describe_shots(shots, api_key="dummy-gemini-key")

    # No HTTP call should have been made
    assert mock_urlopen.call_count == 0
    assert result["shot_1"] == "A line of armored spearmen standing motionless on a sandy ridge at dawn"
    assert result["shot_2"] == "Horses galloping in formation across a dry riverbed"


def test_5_fallback_on_no_api_key_and_network_error():
    """
    No API key, and a raised network error, both fall back to the query and still return a prompt.
    """
    shots = [{"shot_id": "shot_1", "scene": "Narration without key"}]

    # Case A: No API key
    res_no_key = describe_shots(shots, api_key="")
    assert res_no_key == {}
    prompt_a = compose_gap_prompt(shot_query="Allah Bow Adam", visual_description=res_no_key.get("shot_1"))
    assert "Allah Bow Adam" in prompt_a

    # Case B: Network error (e.g. URLError / HTTPError)
    def mock_error(*args, **kwargs):
        raise urllib.error.URLError("Connection refused")

    with patch("urllib.request.urlopen", side_effect=mock_error):
        res_error = describe_shots(shots, api_key="dummy-key")

    assert res_error == {}
    prompt_b = compose_gap_prompt(shot_query="Allah Bow Adam", visual_description=res_error.get("shot_1"))
    assert "Allah Bow Adam" in prompt_b


def test_6_compose_gap_prompt_subject_slot():
    """
    `compose_gap_prompt` puts `visual_description` in the subject slot when given,
    and the query when not.
    """
    shot_query = "Allah Bow Adam"
    visual_description = "a raised hand held still above a bowed assembly"

    # With visual description: subject slot uses visual_description
    prompt_with_desc = compose_gap_prompt(
        shot_query=shot_query,
        visual_description=visual_description,
        project_title="Islamic History",
    )
    assert visual_description in prompt_with_desc
    assert shot_query not in prompt_with_desc

    # Without visual description: subject slot uses shot_query
    prompt_without_desc = compose_gap_prompt(
        shot_query=shot_query,
        visual_description=None,
        project_title="Islamic History",
    )
    assert shot_query in prompt_without_desc

    # With empty visual description: falls back to shot_query
    prompt_empty_desc = compose_gap_prompt(
        shot_query=shot_query,
        visual_description="   ",
        project_title="Islamic History",
    )
    assert shot_query in prompt_empty_desc


def test_7_recipe_authored_long_cinematic_description_survives():
    """
    When the niche has a non-empty prompt_recipe, an existing visual_description on a shot
    survives untouched even if it is over 40 words and contains banned words like 'cinematic'.
    """
    long_cinematic_desc = (
        "A cinematic panoramic vista showing ancient warriors in ornate armor marching across "
        "the desert dunes under a dramatic sunset, cinematic lighting casting deep shadows over "
        "the caravan, highly detailed documentary photography style with magnificent atmospheric "
        "haze and historical accuracy throughout the majestic ancient landscape."
    )
    assert len(long_cinematic_desc.split()) > 40
    assert "cinematic" in long_cinematic_desc.lower()

    shots = [{
        "shot_id": "shot_recipe_1",
        "scene": "The soldiers crossed the vast empty quarter.",
        "visual_description": long_cinematic_desc,
    }]

    series_cfg = {
        "series_slug": "pre_islamic_prophetic___global_history",
        "prompt_recipe": "Produce epic historical documentary descriptions emphasizing authenticity.",
        "era_block": "Ancient Near East and Arabia",
    }

    mock_urlopen = MagicMock()
    with patch("urllib.request.urlopen", mock_urlopen):
        result = describe_shots(shots, api_key="dummy-key", series_cfg=series_cfg)

    # Must NOT call API and must preserve the recipe's exact description
    assert mock_urlopen.call_count == 0
    assert result["shot_recipe_1"] == long_cinematic_desc.strip().rstrip(".")


def test_8_same_narration_under_different_niches_produces_different_cache_entries():
    """
    The same scene text under two different niches produces two distinct cache keys,
    verifying that the cache key is niche-aware.
    """
    scene = "A lone horseman approaches the gates of the city at dusk"

    cfg_islamic = {
        "series_slug": "islamic_history",
        "prompt_recipe": "7th century Arabian historical visuals",
        "era_block": "7th century Arabian Peninsula",
    }
    cfg_space = {
        "series_slug": "space_science",
        "prompt_recipe": "Deep space scientific visualization",
        "era_block": "Modern space exploration",
    }

    hash_islamic = _scene_hash(
        scene,
        series_slug=cfg_islamic["series_slug"],
        prompt_recipe=cfg_islamic["prompt_recipe"],
        era_block=cfg_islamic["era_block"],
    )
    hash_space = _scene_hash(
        scene,
        series_slug=cfg_space["series_slug"],
        prompt_recipe=cfg_space["prompt_recipe"],
        era_block=cfg_space["era_block"],
    )

    assert hash_islamic != hash_space
    assert len(hash_islamic) == 16
    assert len(hash_space) == 16

    # Verify memory cache differentiation
    shot_desc_module._MEMORY_CACHE[hash_islamic] = "A rider in wool robes dismounting before mudbrick walls"
    shot_desc_module._MEMORY_CACHE[hash_space] = "An astronaut walking toward an airlock module"

    shots = [{"shot_id": "shot_s", "scene": scene}]
    res_islamic = describe_shots(shots, api_key="dummy", series_cfg=cfg_islamic)
    res_space = describe_shots(shots, api_key="dummy", series_cfg=cfg_space)

    assert res_islamic["shot_s"] == "A rider in wool robes dismounting before mudbrick walls"
    assert res_space["shot_s"] == "An astronaut walking toward an airlock module"


def test_9_editing_prompt_recipe_invalidates_cache():
    """
    Changing the niche's prompt_recipe produces a new hash, invalidating old cached descriptions.
    """
    scene = "The scholar writes on parchment in a candlelit room"
    h1 = _scene_hash(scene, series_slug="biography", prompt_recipe="Recipe version A", era_block="")
    h2 = _scene_hash(scene, series_slug="biography", prompt_recipe="Recipe version B with edits", era_block="")

    assert h1 != h2


def test_10_series_cfg_none_backward_compatible():
    """
    Passing series_cfg=None produces identical behavior and hashes as default legacy calls.
    """
    scene = "A caravan passing through mountain pass"
    h_none = _scene_hash(scene)
    h_explicit_empty = _scene_hash(scene, series_slug="", prompt_recipe="", era_block="")
    assert h_none == h_explicit_empty

    shots = [{
        "shot_id": "shot_leg",
        "scene": scene,
        "visual_description": "A train of camels traversing a rocky mountain defile",
    }]
    result = describe_shots(shots, api_key="dummy", series_cfg=None)
    assert result["shot_leg"] == "A train of camels traversing a rocky mountain defile"


def test_11_niche_with_no_recipe_still_generates_and_enforces_gates():
    """
    When a niche has no recipe, newly generated descriptions still undergo the 40-word and banned-word gates.
    """
    shots = [
        {"shot_id": "shot_banned", "scene": "Narration with banned word"},
        {"shot_id": "shot_ok", "scene": "Narration valid"},
    ]
    reply = """
    1. A cinematic wide view of the ancient valley
    2. A line of pack mules resting near an oasis spring
    """
    mock_resp = _create_mock_response(_make_gemini_response(reply))

    series_cfg_no_recipe = {
        "series_slug": "nature_wildlife",
        "prompt_recipe": "",
        "era_block": "",
    }

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = describe_shots(shots, api_key="dummy-key", series_cfg=series_cfg_no_recipe)

    assert "shot_banned" not in result
    assert result["shot_ok"] == "A line of pack mules resting near an oasis spring"


def test_12_user_created_niche_style_presets_is_override():
    """
    A user-created niche sets style_presets_is_override=True so deleted universal types stay deleted.
    """
    from pipeline.library import (
        create_user_niche,
        delete_user_niche,
        get_series_config,
        save_series_override,
        style_presets_for,
    )
    user_slug = "test_custom_desc_niche"
    try:
        create_user_niche(user_slug, "Test Custom Desc Niche", base_slug="biography")
        cfg = get_series_config(series_slug=user_slug)
        assert cfg.get("style_presets_is_override") is True

        # Delete photoreal and verify it is not re-merged
        presets = style_presets_for(cfg)
        assert "photoreal" in presets
        del presets["photoreal"]

        save_series_override(user_slug, {"style_presets": presets})
        reloaded_cfg = get_series_config(series_slug=user_slug)
        reloaded_presets = style_presets_for(reloaded_cfg)

        assert "photoreal" not in reloaded_presets
        assert reloaded_cfg.get("style_presets_is_override") is True
    finally:
        delete_user_niche(user_slug)

