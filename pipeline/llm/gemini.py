import json
import sys
import urllib.request
import urllib.error
from typing import Optional, Dict, Any
from pipeline.llm.interface import BaseLLMProvider
from pipeline.llm.http import urlopen_with_backoff

#: Room for the model's own reasoning, on top of the answer the caller asked for.
#
# On Gemini 2.5, thinking is on by default and its tokens are billed against
# maxOutputTokens — so a caller asking for 4096 tokens of answer was not getting
# 4096 tokens of answer. Measured on the owner's real description batches:
# thinking took 1683, 1911 and 2895 tokens of the 4096, leaving as little as
# 1201 for the reply. That is why the board reported "described 3 of 8 shots in
# one batch — the reply was cut short" on one run and described all eight on the
# next, with nothing changed in between: whether the answer fitted was decided
# by how long the model happened to think.
#
# Unused output tokens are not billed, so headroom is free. 4096 clears the
# worst measured run with room to spare.
THINKING_HEADROOM = 4096

#: gemini-2.5-flash accepts 65536 output tokens; stay inside that after padding.
MAX_OUTPUT_TOKENS = 65536


def _read_timeout(budget: int) -> int:
    """
    How long to wait for a reply of this size.

    A flat 60 seconds was fine when the biggest ask was a few hundred tokens.
    `PLAN_REPLY_CEILING` is 32768 - boundaries and a description for every
    picture of an eighteen-minute film in one reply - and that cannot arrive in
    a minute. It did not: asking for a 60-picture plan of the owner's real film
    timed out three times in one run, and each time the plan "fell back to one
    image" and the descriptions fell back to keyword search. Nothing was wrong
    with the request; the app simply stopped listening before the answer came.

    Roughly a minute per thousand tokens of budget, floored at the old 60 and
    capped so a hung connection still ends.
    """
    return max(60, min(600, 30 + int(budget) // 60))


def _with_thinking_headroom(max_tokens: int) -> int:
    """The budget to ask for so `max_tokens` survives for the answer itself."""
    try:
        wanted = int(max_tokens)
    except (TypeError, ValueError):
        wanted = 2048
    return max(1, min(MAX_OUTPUT_TOKENS, wanted + THINKING_HEADROOM))


def _warn_if_truncated(candidate: dict, usage: dict, asked: int, where: str):
    """
    Say when a reply was cut off.

    Silence here is expensive. `complete_text` returned the truncated string —
    or "" when thinking consumed everything and no part came back at all — and
    the caller could not tell that from a genuinely short answer, so shots
    dropped to two-word keyword search without anything reaching the screen.
    """
    if (candidate or {}).get("finishReason") != "MAX_TOKENS":
        return
    thoughts = (usage or {}).get("thoughtsTokenCount")
    sys.stderr.write(
        f"[gemini] {where}: reply hit the {asked}-token ceiling and was cut off"
        + (f" (thinking used {thoughts} of it)" if thoughts else "")
        + ". Raise the caller's max_tokens.\n"
    )


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
            "maxOutputTokens": _with_thinking_headroom(max_tokens)
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

        res_data = json.loads(urlopen_with_backoff(
            req, timeout=_read_timeout(config["maxOutputTokens"])).decode("utf-8"))
        _warn_if_truncated((res_data.get("candidates") or [{}])[0],
                           res_data.get("usageMetadata") or {},
                           config["maxOutputTokens"], "complete")
        raw_text = res_data["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(raw_text)

    def complete_text(
        self,
        system: str,
        user: str = "",
        max_tokens: int = 2048
    ) -> str:
        headers = {"Content-Type": "application/json"}
        full_text = f"{system}\n\nUSER INPUT:\n{user}" if user and user.strip() else system
        payload = {
            "contents": [
                {
                    "parts": [{"text": full_text}]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": _with_thinking_headroom(max_tokens)
            }
        }
        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        raw = urlopen_with_backoff(
            req, timeout=_read_timeout(payload["generationConfig"]["maxOutputTokens"]))
        res_data = json.loads(raw.decode("utf-8")) if raw else {}
        candidates = res_data.get("candidates") or []
        if not candidates:
            return ""
        _warn_if_truncated(candidates[0], res_data.get("usageMetadata") or {},
                           payload["generationConfig"]["maxOutputTokens"], "complete_text")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        if not parts:
            return ""
        return parts[0].get("text", "")

