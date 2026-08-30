import json
import pytest
import urllib.request
import urllib.error
from io import BytesIO
from unittest.mock import patch, MagicMock

from pipeline.llm.interface import BaseLLMProvider
from pipeline.llm.anthropic import AnthropicProvider
from pipeline.llm.openai import OpenAIProvider
from pipeline.llm.gemini import GeminiProvider
from pipeline.llm.deepseek import DeepSeekProvider
from pipeline.llm.factory import (
    get_single_llm_provider,
    get_llm_provider,
    AutomaticLLMProvider,
    run_provider_test,
    get_last_provider_status,
    clear_provider_status,
)
from pipeline.shot_description import describe_shots, _scene_hash
from pipeline.text_parser import build_script_with_ai
from app import Api


def _mock_http_response(status=200, json_data=None, raw_data=b""):
    resp = MagicMock()
    resp.status = status
    if json_data is not None:
        payload = json.dumps(json_data).encode("utf-8")
    else:
        payload = raw_data
    resp.read.return_value = payload
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = None
    return resp


def test_factory_builds_all_providers_and_unknown_raises():
    """Each provider is built by the factory from its name; an unknown name raises."""
    p_anthropic = get_single_llm_provider("anthropic", model="claude-sonnet-5", api_key="test-key")
    assert isinstance(p_anthropic, AnthropicProvider)
    assert p_anthropic.model == "claude-sonnet-5"

    p_openai = get_single_llm_provider("openai", model="gpt-4o", api_key="test-key")
    assert isinstance(p_openai, OpenAIProvider)
    assert p_openai.model == "gpt-4o"

    p_gemini = get_single_llm_provider("gemini", model="gemini-2.5-flash", api_key="test-key")
    assert isinstance(p_gemini, GeminiProvider)
    assert p_gemini.model == "gemini-2.5-flash"

    p_deepseek = get_single_llm_provider("deepseek", model="deepseek-chat", api_key="test-key")
    assert isinstance(p_deepseek, DeepSeekProvider)
    assert p_deepseek.model == "deepseek-chat"

    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_single_llm_provider("invalid_provider")


def test_openai_provider_structured_completion_matches_gemini_and_deepseek_shape():
    """The OpenAI provider returns structured dict matching Gemini and DeepSeek shape."""
    expected = {
        "batch_results": [
            {
                "segment_id": 1,
                "shots": [{"query": "desert fortress", "visual_description": "A stone fortress under blazing sun"}]
            }
        ]
    }
    openai_raw_reply = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(expected)
                }
            }
        ]
    }

    provider = OpenAIProvider(api_key="sk-mock-key", model="gpt-4o")
    with patch("urllib.request.urlopen", return_value=_mock_http_response(json_data=openai_raw_reply)):
        res = provider.complete(system="System prompt", user="User prompt")

    assert res == expected
    assert "batch_results" in res
    assert res["batch_results"][0]["shots"][0]["query"] == "desert fortress"


def test_provider_switched_off_is_never_called_under_automatic():
    """A provider switched off is never called, even by Automatic."""
    mock_settings = {
        "prompt_writer_mode": "auto",
        "prompt_writer_providers": {
            "anthropic": {"enabled": False, "model": "claude-sonnet-5"},
            "openai": {"enabled": False, "model": "gpt-4o"},
            "gemini": {"enabled": True, "model": "gemini-2.5-flash"},
            "deepseek": {"enabled": False, "model": "deepseek-chat"},
        },
        "google_api_key": "dummy-google-key",
    }

    auto_provider = AutomaticLLMProvider(settings=mock_settings)
    chain = auto_provider._get_enabled_chain()

    assert len(chain) == 1
    assert chain[0][0] == "gemini"

    gemini_reply = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "1. A lone rider cresting a desert sand dune."}]
                }
            }
        ]
    }
    with patch("urllib.request.urlopen", return_value=_mock_http_response(json_data=gemini_reply)):
        reply = auto_provider.complete_text(system="Describe scene")

    assert "lone rider" in reply


def test_automatic_skips_402_and_moves_to_next_enabled_provider():
    """Automatic skips a provider returning 402 and uses next enabled one, recording message."""
    clear_provider_status()
    mock_settings = {
        "prompt_writer_mode": "auto",
        "prompt_writer_providers": {
            "anthropic": {"enabled": True, "model": "claude-sonnet-5"},
            "openai": {"enabled": True, "model": "gpt-4o"},
            "gemini": {"enabled": False, "model": "gemini-2.5-flash"},
            "deepseek": {"enabled": False, "model": "deepseek-chat"},
        },
        "anthropic_api_key": "sk-ant-exhausted",
        "openai_api_key": "sk-openai-valid",
    }

    auto_provider = AutomaticLLMProvider(settings=mock_settings)

    call_urls = []

    def mock_urlopen(req, *args, **kwargs):
        call_urls.append(req.full_url)
        if "anthropic" in req.full_url:
            raise urllib.error.HTTPError(req.full_url, 402, "Payment Required", {}, BytesIO(b"Out of credit"))
        elif "openai" in req.full_url:
            openai_reply = {
                "choices": [{"message": {"content": "1. A bustling harbor with wooden sailing vessels."}}]
            }
            return _mock_http_response(json_data=openai_reply)
        raise RuntimeError(f"Unexpected endpoint: {req.full_url}")

    with patch("urllib.request.urlopen", side_effect=mock_urlopen):
        res = auto_provider.complete_text(system="Describe scene")

    assert "bustling harbor" in res
    status = get_last_provider_status()
    assert "Anthropic refused the request: 402 Payment Required" in status["message"]
    assert "Automatic moved to OpenAI" in status["message"]
    assert status["answering_provider"] == "openai"


def test_description_pass_honours_selected_provider():
    """The description pass honours the selected provider — two providers, same scene, different text."""
    shots = [{"shot_id": "1a", "scene": "The morning sun rose over the ancient temple."}]

    class MockAnthropic(BaseLLMProvider):
        model = "claude-sonnet-5"
        def complete(self, *args, **kwargs): return {}
        def complete_text(self, *args, **kwargs):
            return "1. Warm sunlight illuminates the stone columns of a mountaintop temple."

    class MockOpenAI(BaseLLMProvider):
        model = "gpt-4o"
        def complete(self, *args, **kwargs): return {}
        def complete_text(self, *args, **kwargs):
            return "1. Golden rays break through morning mist across weathered temple steps."

    res_anthropic = describe_shots(shots, provider=MockAnthropic())
    res_openai = describe_shots(shots, provider=MockOpenAI())

    assert "Warm sunlight illuminates" in res_anthropic["1a"]
    assert "Golden rays break through" in res_openai["1a"]
    assert res_anthropic["1a"] != res_openai["1a"]


def test_llm_planning_off_segments_script_with_zero_llm_calls():
    """With LLM planning off, a script still segments correctly without making LLM calls."""
    script_text = (
        "Paragraph one describing the ancient ruins of Persepolis.\n\n"
        "Paragraph two detailing the inscriptions on the palace walls.\n\n"
        "Paragraph three concluding the historical journey."
    )

    class SpyFailingProvider(BaseLLMProvider):
        def complete(self, *args, **kwargs):
            raise AssertionError("LLM provider must NOT be called when planning is off")

    with patch("pipeline.library._setting", side_effect=lambda key, default=None: False if key == "llm_planning_enabled" else default):
        script_json = build_script_with_ai(
            text=script_text,
            title="Zero LLM Planning Test",
            llm_provider=None
        )

    segments = script_json["segments"]
    assert len(segments) == 3
    assert segments[0]["type"] == "hook"
    assert segments[1]["type"] == "body"
    assert segments[2]["type"] == "conclusion"
    assert all(len(s["shots"]) >= 1 for s in segments)
    assert all(s["shots"][0]["query"] for s in segments)


def test_api_get_settings_never_leaks_raw_keys():
    """No secret key value appears in any returned settings payload."""
    api = Api()
    api._settings["anthropic_api_key"] = "sk-ant-secret12345"
    api._settings["openai_api_key"] = "sk-proj-secret67890"
    api._settings["google_api_key"] = "AIzaSySecretGoogleKey"

    safe_settings = api.get_settings()

    assert "anthropic_api_key" not in safe_settings
    assert "openai_api_key" not in safe_settings
    assert "google_api_key" not in safe_settings

    assert safe_settings["anthropic_api_key_set"] is True
    assert safe_settings["openai_api_key_set"] is True
    assert safe_settings["google_api_key_set"] is True

    # Confirm key lengths are reported without leaking secrets
    assert safe_settings["anthropic_api_key_len"] == len("sk-ant-secret12345")


def test_provider_test_diagnostics():
    """test_provider reports true diagnosis: working, bad key (401), out of credit (402), not found (404)."""
    # 1. Missing key
    res_no_key = run_provider_test("anthropic", api_key="")
    assert res_no_key["status"] == "error"
    assert res_no_key["code"] == 401
    assert "not set" in res_no_key["message"]

    # 2. 402 Out of credit
    def mock_402(req, *args, **kwargs):
        raise urllib.error.HTTPError(req.full_url, 402, "Payment Required", {}, BytesIO(b"Credit exhausted"))

    with patch("urllib.request.urlopen", side_effect=mock_402):
        res_402 = run_provider_test("deepseek", api_key="sk-test")
        assert res_402["status"] == "error"
        assert res_402["code"] == 402
        assert "402 Payment Required" in res_402["message"]

    # 3. 404 Model Not Found
    def mock_404(req, *args, **kwargs):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, BytesIO(b"Model not found"))

    with patch("urllib.request.urlopen", side_effect=mock_404):
        res_404 = run_provider_test("gemini", model="gemini-2.5-pro", api_key="AIzaSyTest")
        assert res_404["status"] == "error"
        assert res_404["code"] == 404
        assert "404 Not Found" in res_404["message"]

    # 4. Working (200 OK)
    openai_ok = {"choices": [{"message": {"content": "OK"}}]}
    with patch("urllib.request.urlopen", return_value=_mock_http_response(json_data=openai_ok)):
        res_200 = run_provider_test("openai", api_key="sk-valid")
        assert res_200["status"] == "ok"
        assert res_200["message"] == "working"

# ---------------------------------------------------------------------------
# Regressions for four faults found reviewing the first pass of this feature.
# ---------------------------------------------------------------------------

_CHAIN_SETTINGS = {
    "prompt_writer_mode": "auto",
    "prompt_writer_providers": {
        "anthropic": {"enabled": True, "model": "claude-sonnet-5"},
        "openai": {"enabled": True, "model": "gpt-4o"},
        "gemini": {"enabled": False, "model": "gemini-2.5-flash"},
        "deepseek": {"enabled": False, "model": "deepseek-chat"},
    },
    "anthropic_api_key": "sk-ant-x",
    "openai_api_key": "sk-oa-x",
}


def test_automatic_identity_names_the_chain_not_a_hardcoded_gemini():
    """
    Automatic has no single model. Reading `.model` off it found nothing and
    fell back to "gemini-2.5-flash", so every description cached under that name
    whichever provider had actually answered.
    """
    auto = AutomaticLLMProvider(settings=_CHAIN_SETTINGS)
    prov_key, model = auto.identity()

    assert prov_key == "auto"
    assert model == "anthropic:claude-sonnet-5>openai:gpt-4o"
    assert "gemini" not in model, "Automatic still reports a provider that is switched off"


def test_changing_the_chain_changes_the_description_cache_key():
    """A different chain must not be served the previous chain's descriptions."""
    scene = "The army stood motionless on the ridge at dawn."

    both = AutomaticLLMProvider(settings=_CHAIN_SETTINGS).identity()

    openai_only = dict(_CHAIN_SETTINGS)
    openai_only["prompt_writer_providers"] = dict(_CHAIN_SETTINGS["prompt_writer_providers"])
    openai_only["prompt_writer_providers"]["anthropic"] = {"enabled": False, "model": "claude-sonnet-5"}
    one = AutomaticLLMProvider(settings=openai_only).identity()

    remodelled = dict(_CHAIN_SETTINGS)
    remodelled["prompt_writer_providers"] = dict(_CHAIN_SETTINGS["prompt_writer_providers"])
    remodelled["prompt_writer_providers"]["openai"] = {"enabled": True, "model": "gpt-4o-mini"}
    other_model = AutomaticLLMProvider(settings=remodelled).identity()

    keys = {
        _scene_hash(scene, provider=both[0], model=both[1]),
        _scene_hash(scene, provider=one[0], model=one[1]),
        _scene_hash(scene, provider=other_model[0], model=other_model[1]),
    }
    assert len(keys) == 3, "two different chains share one cache key"


def test_a_single_provider_still_keys_on_its_own_model():
    """The single-provider key is unchanged — same writer, same text, reusable."""
    assert GeminiProvider(api_key="k", model="gemini-2.5-flash").identity() == (
        "gemini", "gemini-2.5-flash")
    assert AnthropicProvider(api_key="k", model="claude-sonnet-5").identity() == (
        "anthropic", "claude-sonnet-5")
    assert OpenAIProvider(api_key="k", model="gpt-4o").identity() == ("openai", "gpt-4o")
    assert DeepSeekProvider(api_key="k", model="deepseek-chat").identity() == (
        "deepseek", "deepseek-chat")


def test_gemini_reaches_the_model_through_the_provider_seam():
    """
    Gemini took a private HTTP path inside shot_description, so the one provider
    writing every prompt was the one the seam did not cover.
    """
    import pipeline.shot_description as sd
    sd._MEMORY_CACHE.clear()

    seen = {}

    def _spy(self, system, user="", max_tokens=2048):
        seen["called"] = True
        seen["model"] = self.model
        return "1. A hall of bowed figures beneath a shaft of pale light"

    shots = [{"shot_id": "1a", "scene": "The hall fell silent as the envoy entered."}]
    with patch.object(GeminiProvider, "complete_text", _spy),          patch.object(sd, "_load_disk_cache", return_value={}),          patch.object(sd, "_save_disk_cache"):
        res = describe_shots(shots, provider=GeminiProvider(api_key="k", model="gemini-2.5-flash"))

    assert seen.get("called") is True, "Gemini bypassed the provider seam"
    assert res["1a"].startswith("A hall of bowed figures")


def test_a_dead_provider_reaches_the_ui_instead_of_stderr():
    """
    A 402 was classified, written to stderr where no user looks, and dropped
    silently to keyword planning. That is how a dead key went unnoticed.
    """
    import pipeline.shot_description as sd
    sd._MEMORY_CACHE.clear()
    clear_provider_status()

    def _dead(self, system, user="", max_tokens=2048):
        raise urllib.error.HTTPError("https://x", 402, "Payment Required", {}, BytesIO(b"no credit"))

    shots = [{"shot_id": "1a", "scene": "A refused batch must leave no description behind."}]
    with patch.object(GeminiProvider, "complete_text", _dead),          patch.object(sd, "_load_disk_cache", return_value={}),          patch.object(sd, "_save_disk_cache"):
        res = describe_shots(shots, provider=GeminiProvider(api_key="k", model="gemini-2.5-flash"))

    assert res == {}, "a refused request must not invent descriptions"
    status = get_last_provider_status()
    assert status["status"] == "error"
    assert "Google" in status["message"]
    assert "402 Payment Required" in status["message"]


def test_automatic_keeps_the_documented_order_whatever_the_settings_list():
    """
    The order was derived from which keys happened to be present, so a settings
    file naming only DeepSeek tried the provider known to be dead first.
    """
    keys = {"anthropic_api_key": "a", "openai_api_key": "o",
            "deepseek_api_key": "d", "google_api_key": "g"}
    on = {"enabled": True}

    def chain(cfg):
        s = {"prompt_writer_mode": "auto", "prompt_writer_providers": cfg}
        s.update(keys)
        return [c[0] for c in AutomaticLLMProvider(settings=s)._get_enabled_chain()]

    assert chain({"anthropic": on, "openai": on, "gemini": on, "deepseek": on}) == [
        "anthropic", "openai", "gemini", "deepseek"]
    assert chain({"deepseek": on, "gemini": on, "openai": on, "anthropic": on}) == [
        "anthropic", "openai", "gemini", "deepseek"]
    assert chain({"deepseek": on})[0] != "deepseek", "the dead provider is tried first"


def test_the_default_anthropic_model_is_a_real_model_id():
    """`claude-sonnet-4` 404s. A wrong default reads as a dead provider."""
    from pipeline.llm.factory import DEFAULT_MODELS
    assert DEFAULT_MODELS["anthropic"] == "claude-sonnet-5"
    assert get_single_llm_provider("anthropic", api_key="k").model == "claude-sonnet-5"
