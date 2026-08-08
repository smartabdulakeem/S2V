import json
import urllib.request
import urllib.error
from typing import Optional, Dict, Any
from pipeline.llm.interface import BaseLLMProvider

class AnthropicProvider(BaseLLMProvider):
    def __init__(self, api_key: str, model: str = "claude-sonnet-5"):
        self.api_key = api_key
        self.model = model
        self.endpoint = "https://api.anthropic.com/v1/messages"

    def complete(
        self,
        system: str,
        user: str,
        json_schema: Optional[Dict[str, Any]] = None,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        payload: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [
                {"role": "user", "content": user}
            ]
        }

        if max_tokens > 16000:
            payload["stream"] = True

        if json_schema:
            payload["output_config"] = {
                "format": {
                    "type": "json_schema",
                    "schema": json_schema
                }
            }

        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=90) as response:
            if payload.get("stream"):
                chunks = []
                for line in response:
                    line_str = line.decode("utf-8").strip()
                    if line_str.startswith("data: "):
                        data_part = line_str[6:]
                        if data_part != "[DONE]":
                            try:
                                chunk_json = json.loads(data_part)
                                if chunk_json.get("type") == "content_block_delta":
                                    chunks.append(chunk_json["delta"].get("text", ""))
                            except Exception:
                                pass
                full_text = "".join(chunks)
                return json.loads(full_text)
            else:
                res_data = json.loads(response.read().decode("utf-8"))
                for block in res_data.get("content", []):
                    if block.get("type") == "text":
                        return json.loads(block["text"])
                    elif block.get("type") == "json":
                        return block["json"]
                raise ValueError("No text or JSON block in Anthropic response")
