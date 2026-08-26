"""
pipeline/shot_description.py

Planning-time pass that writes one visual sentence per shot, stored on the shot
as "visual_description", used as the prompt's subject.
"""

import os
import re
import sys
import json
import time
import hashlib
import urllib.request
import urllib.error
from typing import Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(ROOT, "cache", "planning")
CACHE_FILE = os.path.join(CACHE_DIR, "shot_descriptions.json")

# In-memory cache keyed by scene hash
_MEMORY_CACHE: Dict[str, str] = {}

INSTRUCTION = """You are a documentary shot designer. For each numbered narration excerpt below,
write ONE sentence describing what the camera sees.

Rules:
- Describe only what a camera could photograph: people, objects, place, light, action.
- Never restate the narration and never use its voice. Drop "imagine", "you have",
  "picture this" and every second-person address.
- An abstract idea must become a concrete image. "A command that seems simple"
  becomes "a raised hand held still above a bowed assembly".
- No style, medium, camera or lens words. Never write cinematic, illustration,
  photograph, painting, 35mm, wide shot, close-up.
- Nothing written may appear in the scene: no text, letters, captions, titles,
  numbers, signage, banners or inscriptions.
- 12 to 25 words. One sentence. No trailing full stop needed.
- Keep a proper noun only when it names a person or place that recurs in the film.

Output exactly one line per excerpt, formatted as:
<number>. <sentence>

Return nothing else - no preamble, no blank lines, no commentary."""

BANNED_PATTERN = re.compile(
    r"\b(cinematic|illustration|photograph|painting|render|35mm|close-up|close\s+up|wide\s+shot|caption|title|text|sign|signs|signage)\b",
    re.IGNORECASE
)


def _scene_hash(scene: str) -> str:
    """Stable hash of normalized scene text."""
    cleaned = " ".join((scene or "").strip().split())
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:16]


def _load_disk_cache() -> Dict[str, str]:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_disk_cache(cache: Dict[str, str]):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def is_valid_description(sentence: str) -> bool:
    """Validate sentence according to shot description rules."""
    if not sentence or not sentence.strip():
        return False
    words = sentence.strip().split()
    if len(words) > 40:
        return False
    if BANNED_PATTERN.search(sentence):
        return False
    return True


def _http_request_with_backoff(req: urllib.request.Request, timeout: int = 60, max_retries: int = 3) -> bytes:
    """Make HTTP request with exponential backoff on 429/503."""
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                if isinstance(data, (bytes, bytearray)):
                    return data
                elif isinstance(data, str):
                    return data.encode("utf-8")
                return bytes(data) if data else b""
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
    return b""


def _call_gemini_batch(prompt_text: str, api_key: str, model: str = "gemini-2.5-flash") -> Optional[str]:
    """Execute Gemini request for one batch."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [
            {
                "parts": [{"text": prompt_text}]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 2048,
        }
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    resp_bytes = _http_request_with_backoff(req, timeout=60)
    if isinstance(resp_bytes, (bytes, bytearray)):
        raw_text = resp_bytes.decode("utf-8")
    elif isinstance(resp_bytes, str):
        raw_text = resp_bytes
    else:
        raw_text = "{}"

    data = json.loads(raw_text)
    candidates = data.get("candidates") or []
    if not candidates:
        return None
    parts = (candidates[0].get("content") or {}).get("parts") or []
    if not parts:
        return None
    return parts[0].get("text", "")


def describe_shots(shots: list, api_key: str, model: str = "gemini-2.5-flash") -> dict:
    """
    One visual sentence per shot, keyed by shot_id.

    `shots` is a list of {"shot_id": str, "scene": str} - `scene` is the slice of
    narration that shot covers. Returns {shot_id: description}. Shots that come
    back empty or unparseable are simply absent from the result; the caller falls
    back to the search query for those.
    """
    global _MEMORY_CACHE
    if not shots:
        return {}

    # Initialize disk cache if memory cache is empty
    if not _MEMORY_CACHE:
        _MEMORY_CACHE.update(_load_disk_cache())

    results = {}
    uncached_shots = []

    # 1. Check existing shot visual_description and cache
    for shot in shots:
        shot_id = shot.get("shot_id")
        scene = (shot.get("scene") or "").strip()
        if not shot_id or not scene:
            continue

        h = _scene_hash(scene)
        existing_desc = shot.get("visual_description")
        if existing_desc and is_valid_description(existing_desc):
            results[shot_id] = existing_desc.strip().rstrip(".")
            _MEMORY_CACHE[h] = results[shot_id]
        elif h in _MEMORY_CACHE and is_valid_description(_MEMORY_CACHE[h]):
            results[shot_id] = _MEMORY_CACHE[h]
        else:
            uncached_shots.append(shot)

    if not uncached_shots:
        return results

    if not api_key or not str(api_key).strip():
        sys.stderr.write("[shot_description] No Google API key configured, falling back to query\n")
        return results

    # 2. Batch 20 shots per request
    BATCH_SIZE = 20
    cache_updated = False

    for batch_start in range(0, len(uncached_shots), BATCH_SIZE):
        batch = uncached_shots[batch_start:batch_start + BATCH_SIZE]
        prompt_lines = [INSTRUCTION, ""]
        for idx, s in enumerate(batch, 1):
            prompt_lines.append(f"{idx}. {s.get('scene', '').strip()}")
        prompt_text = "\n".join(prompt_lines)

        try:
            reply_text = _call_gemini_batch(prompt_text, api_key=api_key.strip(), model=model)
            if not reply_text:
                continue

            # Parse lines: Match ^\s*(\d+)[.):]\s*(.+)$ per line
            line_pattern = re.compile(r"^\s*(\d+)[.):]\s*(.+)$")
            for line in reply_text.splitlines():
                m = line_pattern.match(line.strip())
                if not m:
                    continue
                try:
                    num = int(m.group(1))
                    sentence = m.group(2).strip()
                except (ValueError, IndexError):
                    continue

                # Map back to shot at that position in the batch sent (1-indexed)
                if 1 <= num <= len(batch):
                    matched_shot = batch[num - 1]
                    s_id = matched_shot.get("shot_id")
                    s_scene = matched_shot.get("scene", "")

                    if is_valid_description(sentence):
                        clean_sentence = sentence.rstrip(" .")
                        results[s_id] = clean_sentence
                        _MEMORY_CACHE[_scene_hash(s_scene)] = clean_sentence
                        cache_updated = True
        except urllib.error.HTTPError as err:
            sys.stderr.write(f"[shot_description] HTTP error {err.code} calling Gemini: {err}, falling back to query\n")
            continue
        except urllib.error.URLError as err:
            sys.stderr.write(f"[shot_description] URL error calling Gemini: {err}, falling back to query\n")
            continue
        except Exception as err:
            sys.stderr.write(f"[shot_description] Error calling Gemini: {err}, falling back to query\n")
            continue

    if cache_updated:
        _save_disk_cache(_MEMORY_CACHE)

    return results
