import json
import urllib.request
import urllib.error
from typing import Optional, Dict, Any
from pipeline.llm.interface import BaseLLMProvider

class GeminiProvider(BaseLLMProvider):
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.model = model
        self.endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    def complete(
        self,
        system: str,
        user: str,
        json_schema: Optional[Dict[str, Any]] = None,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        headers = {"Content-Type": "application/json"}

        config = {
            "responseMimeType": "application/json",
            "temperature": 0.3,
            "maxOutputTokens": max_tokens
        }
        if json_schema:
            config["responseSchema"] = json_schema

        payload = {
            "contents": [
                {
                    "parts": [{"text": f"{system}\n\nUSER INPUT:\n{user}"}]
                }
            ],
            "generationConfig": config
        }

        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=60) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            raw_text = res_data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(raw_text)
