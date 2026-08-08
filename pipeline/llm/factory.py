import os
import json
from typing import Optional
from pipeline.llm.interface import BaseLLMProvider
from pipeline.llm.deepseek import DeepSeekProvider
from pipeline.llm.gemini import GeminiProvider
from pipeline.llm.anthropic import AnthropicProvider

SETTINGS_PATH = os.path.abspath("config/settings.json")

def load_settings() -> dict:
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def get_llm_provider(provider_name: Optional[str] = None, model: Optional[str] = None) -> BaseLLMProvider:
    settings = load_settings()
    
    prov = (provider_name or settings.get("llm_provider") or "deepseek").lower()
    
    if prov == "deepseek":
        api_key = settings.get("deepseek_api_key") or os.getenv("DEEPSEEK_API_KEY", "")
        model_name = model or settings.get("llm_model") or "deepseek-chat"
        return DeepSeekProvider(api_key=api_key, model=model_name)
    elif prov == "gemini":
        api_key = settings.get("google_api_key") or os.getenv("GOOGLE_API_KEY", "")
        model_name = model or settings.get("llm_model") or "gemini-2.5-flash"
        return GeminiProvider(api_key=api_key, model=model_name)
    elif prov in ["anthropic", "claude"]:
        api_key = settings.get("anthropic_api_key") or os.getenv("ANTHROPIC_API_KEY", "")
        model_name = model or settings.get("llm_model") or "claude-sonnet-5"
        return AnthropicProvider(api_key=api_key, model=model_name)
    else:
        raise ValueError(f"Unknown LLM provider '{prov}'. Supported: deepseek, gemini, anthropic.")
