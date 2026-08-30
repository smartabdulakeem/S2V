import os
import re
import json
import urllib.error
from typing import Optional, Dict, Any, List, Tuple
from pipeline.llm.interface import BaseLLMProvider
from pipeline.llm.deepseek import DeepSeekProvider
from pipeline.llm.gemini import GeminiProvider
from pipeline.llm.anthropic import AnthropicProvider
from pipeline.llm.openai import OpenAIProvider

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SETTINGS_PATH = os.path.join(_ROOT, "config", "settings.json")

# Module-level state for reporting permanent provider events and active answers to the UI
_LAST_PROVIDER_STATUS: Dict[str, Any] = {
    "status": "idle",
    "message": "",
    "answering_provider": "",
    "timestamp": 0
}

PROVIDER_DISPLAY_NAMES = {
    "anthropic": "Anthropic",
    "openai": "OpenAI",
    "gemini": "Google",
    "deepseek": "DeepSeek",
    "google": "Google"
}

DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4",
    "openai": "gpt-4o",
    "gemini": "gemini-2.5-flash",
    "deepseek": "deepseek-chat"
}

DEFAULT_PROVIDERS_ORDER = ["anthropic", "openai", "gemini", "deepseek"]

def load_settings() -> dict:
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def get_last_provider_status() -> dict:
    global _LAST_PROVIDER_STATUS
    return dict(_LAST_PROVIDER_STATUS)

def set_last_provider_status(status: str, message: str, answering_provider: str = ""):
    global _LAST_PROVIDER_STATUS
    import time
    _LAST_PROVIDER_STATUS = {
        "status": status,
        "message": message,
        "answering_provider": answering_provider,
        "timestamp": time.time()
    }

def clear_provider_status():
    global _LAST_PROVIDER_STATUS
    _LAST_PROVIDER_STATUS = {
        "status": "idle",
        "message": "",
        "answering_provider": "",
        "timestamp": 0
    }

def is_permanent_error(e: Exception) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Classifies whether an exception represents a permanent HTTP error (401, 402, 403, 404).
    Returns (is_permanent, error_code, reason_explanation).
    """
    err_str = str(e)
    code = None
    if isinstance(e, urllib.error.HTTPError):
        code = str(e.code)
    else:
        for c in ("401", "402", "403", "404"):
            if c in err_str:
                code = c
                break

    if not code:
        return False, None, None

    explanations = {
        "401": ("401 Unauthorized", "Check that your API key is correct"),
        "402": ("402 Payment Required", "Your account is out of credit"),
        "403": ("403 Forbidden", "Check key permissions or regional availability"),
        "404": ("404 Not Found", "The model is not supported or accessible on this account"),
    }
    reason, explanation = explanations.get(code, (f"HTTP {code}", "Permanent error"))
    return True, code, f"{reason}. {explanation}"

class AutomaticLLMProvider(BaseLLMProvider):
    """
    Tries enabled providers in order (Anthropic -> OpenAI -> Google -> DeepSeek).
    On permanent error (401, 402, 403, 404), fails over to the next enabled provider
    and records the transition message for the UI.
    """
    def __init__(self, settings: Optional[dict] = None):
        self.settings = settings if settings is not None else load_settings()

    def _get_enabled_chain(self) -> List[Tuple[str, str, BaseLLMProvider]]:
        """Returns list of (provider_key, display_name, provider_instance) for enabled providers."""
        chain = []
        providers_cfg = self.settings.get("prompt_writer_providers") or {}

        # Look in order
        configured_keys = list(providers_cfg.keys())
        order = [k for k in DEFAULT_PROVIDERS_ORDER if k in configured_keys] + [k for k in DEFAULT_PROVIDERS_ORDER if k not in configured_keys]
        # Also include any custom keys from providers_cfg in order
        for k in configured_keys:
            if k not in order:
                order.append(k)

        for p_key in order:
            p_info = providers_cfg.get(p_key) or {}
            # Check enabled flag
            is_enabled = p_info.get("enabled")
            if is_enabled is None:
                if p_key in ("anthropic", "gemini"):
                    is_enabled = True
                else:
                    is_enabled = False

            if not is_enabled:
                continue

            model_name = p_info.get("model") or DEFAULT_MODELS.get(p_key)
            try:
                provider = get_single_llm_provider(p_key, model=model_name, settings=self.settings)
                if getattr(provider, "api_key", None) or p_key in ("gemini", "google"):
                    chain.append((p_key, PROVIDER_DISPLAY_NAMES.get(p_key, p_key.title()), provider))
            except Exception:
                continue
        return chain

    def complete(
        self,
        system: str,
        user: str,
        json_schema: Optional[Dict[str, Any]] = None,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        chain = self._get_enabled_chain()
        if not chain:
            raise RuntimeError("No enabled prompt writer providers available in Automatic mode.")

        errors = []
        fallback_msg = None
        for idx, (p_key, p_display, provider) in enumerate(chain):
            try:
                res = provider.complete(system=system, user=user, json_schema=json_schema, max_tokens=max_tokens)
                if fallback_msg:
                    set_last_provider_status("fallback", fallback_msg, answering_provider=p_key)
                else:
                    set_last_provider_status("ok", f"{p_display} answered successfully.", answering_provider=p_key)
                return res
            except Exception as e:
                is_perm, code, explanation = is_permanent_error(e)
                if is_perm and idx + 1 < len(chain):
                    next_p_display = chain[idx + 1][1]
                    fallback_msg = f"{p_display} refused the request: {explanation}. Automatic moved to {next_p_display}."
                    set_last_provider_status("fallback", fallback_msg, answering_provider=chain[idx + 1][0])
                    errors.append(fallback_msg)
                    continue
                elif is_perm:
                    msg = f"{p_display} refused the request: {explanation}."
                    set_last_provider_status("error", msg, answering_provider="")
                    errors.append(msg)
                else:
                    errors.append(f"{p_display} error: {e}")

        raise RuntimeError("; ".join(errors))

    def complete_text(
        self,
        system: str,
        user: str = "",
        max_tokens: int = 2048
    ) -> str:
        chain = self._get_enabled_chain()
        if not chain:
            raise RuntimeError("No enabled prompt writer providers available in Automatic mode.")

        errors = []
        fallback_msg = None
        for idx, (p_key, p_display, provider) in enumerate(chain):
            try:
                res = provider.complete_text(system=system, user=user, max_tokens=max_tokens)
                if fallback_msg:
                    set_last_provider_status("fallback", fallback_msg, answering_provider=p_key)
                else:
                    set_last_provider_status("ok", f"{p_display} answered successfully.", answering_provider=p_key)
                return res
            except Exception as e:
                is_perm, code, explanation = is_permanent_error(e)
                if is_perm and idx + 1 < len(chain):
                    next_p_display = chain[idx + 1][1]
                    fallback_msg = f"{p_display} refused the request: {explanation}. Automatic moved to {next_p_display}."
                    set_last_provider_status("fallback", fallback_msg, answering_provider=chain[idx + 1][0])
                    errors.append(fallback_msg)
                    continue
                elif is_perm:
                    msg = f"{p_display} refused the request: {explanation}."
                    set_last_provider_status("error", msg, answering_provider="")
                    errors.append(msg)
                else:
                    errors.append(f"{p_display} error: {e}")

        raise RuntimeError("; ".join(errors))

def get_single_llm_provider(
    provider_name: str,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    settings: Optional[dict] = None
) -> BaseLLMProvider:
    st = settings if settings is not None else load_settings()
    prov = (provider_name or "").lower().strip()

    if prov in ("gemini", "google"):
        key = api_key if api_key is not None else (st.get("google_api_key") or os.getenv("GOOGLE_API_KEY", ""))
        model_name = model or st.get("google_model") or st.get("gemini_model") or DEFAULT_MODELS["gemini"]
        return GeminiProvider(api_key=key, model=model_name)

    elif prov in ("anthropic", "claude"):
        key = api_key if api_key is not None else (st.get("anthropic_api_key") or os.getenv("ANTHROPIC_API_KEY", ""))
        model_name = model or st.get("anthropic_model") or DEFAULT_MODELS["anthropic"]
        return AnthropicProvider(api_key=key, model=model_name)

    elif prov in ("openai", "gpt"):
        key = api_key if api_key is not None else (st.get("openai_api_key") or os.getenv("OPENAI_API_KEY", ""))
        model_name = model or st.get("openai_model") or DEFAULT_MODELS["openai"]
        return OpenAIProvider(api_key=key, model=model_name)

    elif prov == "deepseek":
        key = api_key if api_key is not None else (st.get("deepseek_api_key") or os.getenv("DEEPSEEK_API_KEY", ""))
        model_name = model or st.get("deepseek_model") or DEFAULT_MODELS["deepseek"]
        return DeepSeekProvider(api_key=key, model=model_name)

    else:
        raise ValueError(f"Unknown LLM provider '{prov}'. Supported: deepseek, gemini, anthropic, openai.")

def get_llm_provider(
    provider_name: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None
) -> BaseLLMProvider:
    settings = load_settings()
    mode = (provider_name or settings.get("prompt_writer_mode") or settings.get("llm_provider") or "gemini").lower()

    if mode in ("auto", "automatic"):
        return AutomaticLLMProvider(settings=settings)

    return get_single_llm_provider(mode, model=model, api_key=api_key, settings=settings)

def run_provider_test(provider_name: str, model: Optional[str] = None, api_key: Optional[str] = None) -> dict:
    """
    Executes a minimal test completion for a single provider and returns diagnosis.
    """
    try:
        provider = get_single_llm_provider(provider_name, model=model, api_key=api_key)
        if not getattr(provider, "api_key", None) or not str(provider.api_key).strip():
            return {
                "status": "error",
                "code": 401,
                "reason": "key not set",
                "message": f"API key for {PROVIDER_DISPLAY_NAMES.get(provider_name, provider_name)} is not set."
            }

        res = provider.complete_text(system="Respond with the exact word 'OK'.", user="", max_tokens=10)
        if res and ("OK" in res.upper() or len(res.strip()) > 0):
            return {
                "status": "ok",
                "code": 200,
                "message": "working",
                "provider": provider_name,
                "model": getattr(provider, "model", model)
            }
        return {
            "status": "ok",
            "code": 200,
            "message": "working",
            "provider": provider_name,
            "model": getattr(provider, "model", model)
        }
    except Exception as e:
        is_perm, code, explanation = is_permanent_error(e)
        display_name = PROVIDER_DISPLAY_NAMES.get(provider_name, provider_name.title())
        if is_perm:
            int_code = int(code) if code and code.isdigit() else 400
            return {
                "status": "error",
                "code": int_code,
                "reason": explanation,
                "message": f"{display_name} refused the request: {explanation}."
            }
        return {
            "status": "error",
            "code": getattr(e, "code", None),
            "reason": str(e),
            "message": f"{display_name} test failed: {e}"
        }