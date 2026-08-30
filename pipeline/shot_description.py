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
from typing import Dict, List, Optional, Any

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

#: Kept when a niche's recipe takes over the instruction. The recipe decides how
#: a shot is described; these four lines decide only that the reply can be parsed
#: and that nothing unreadable ends up drawn into the picture.
RECIPE_OUTPUT_CONTRACT = """Write ONE image description for each numbered narration excerpt below,
following the directives above.

These requirements override anything above that conflicts with them:
- Describe only what a camera could see. Never restate the narration, and never
  address the viewer.
- Nothing written may appear in the scene: no text, letters, captions, numbers,
  signage or inscriptions.
- Output exactly one line per excerpt, formatted as:
  <number>. <description>
- Return nothing else - no preamble, no blank lines, no commentary."""

#: A recipe may ask for a paragraph. It may not ask for a runaway.
RICH_WORD_CAP = 150

BANNED_PATTERN = re.compile(
    r"\b(cinematic|illustration|photograph|painting|render|35mm|close-up|close\s+up|wide\s+shot|caption|title|text|sign|signs|signage)\b",
    re.IGNORECASE
)


def _script_fingerprint(script_context) -> str:
    """A stable short hash of the whole narration this shot sits inside."""
    if not script_context:
        return ""
    joined = " ".join(" ".join((line or "").split()) for line in script_context)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:12]


def _scene_hash(scene: str, series_slug: str = "", prompt_recipe: str = "",
                era_block: str = "", script_context=None, model: str = "",
                provider: str = "") -> str:
    """Stable hash of the scene, the niche configuration, model, provider, and the film it is in."""
    cleaned_scene = " ".join((scene or "").strip().split())
    recipe_hash = hashlib.sha256((prompt_recipe or "").strip().encode("utf-8")).hexdigest()[:12] if prompt_recipe else ""
    slug_part = (series_slug or "").strip().lower()
    era_part = " ".join((era_block or "").strip().split())
    prov_part = (provider or "gemini").strip().lower()
    model_part = (model or "gemini-2.5-flash").strip().lower()
    # v6: provider and model are part of the key alongside niche, recipe, era and script.
    raw = (f"v6|{prov_part}|{model_part}|{slug_part}|{recipe_hash}|{era_part}|{_script_fingerprint(script_context)}"
           f"|{cleaned_scene}")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _build_instruction(series_cfg: Optional[dict] = None) -> str:
    """
    The instruction sent to the description model.
    """
    if not series_cfg:
        return INSTRUCTION

    recipe = (series_cfg.get("prompt_recipe") or "").strip()
    if recipe:
        parts = [recipe]
        era = (series_cfg.get("era_block") or "").strip()
        if era:
            parts.append(f"Period and material culture: {era}")
        parts.append(RECIPE_OUTPUT_CONTRACT)
        return "\n\n".join(parts)

    context_parts = []
    anchor = (series_cfg.get("brief_subject") or series_cfg.get("display_name") or "").strip()
    era = (series_cfg.get("era_block") or "").strip()
    recipe = (series_cfg.get("prompt_recipe") or "").strip()

    if anchor:
        context_parts.append(f"- Setting / Subject Anchor: {anchor}")
    if era:
        context_parts.append(f"- Historical Era / Period: {era}")
    if recipe:
        recipe_lines = [line.strip() for line in recipe.splitlines() if line.strip()]
        recipe_lead = "\n  ".join(recipe_lines[:6])
        if recipe_lead:
            context_parts.append(f"- Style & Content Directives:\n  {recipe_lead}")

    if not context_parts:
        return INSTRUCTION

    context_section = "\n".join(context_parts)
    return f"{INSTRUCTION}\n\nProject Context:\n{context_section}"


MAX_SCRIPT_CONTEXT_CHARS = 60000


def _build_batch_prompt(instruction: str, batch: list, script_context=None) -> str:
    """The text sent for one batch of shots."""
    if not script_context:
        lines = [instruction, ""]
        for idx, s in enumerate(batch, 1):
            lines.append(f"{idx}. {s.get('scene', '').strip()}")
        return "\n".join(lines)

    numbered, total = [], 0
    for i, line in enumerate(script_context, 1):
        text = " ".join((line or "").split())
        if not text:
            continue
        total += len(text)
        if total > MAX_SCRIPT_CONTEXT_CHARS:
            numbered.append("[...script trimmed...]")
            break
        numbered.append(f"[{i}] {text}")

    position = {}
    for i, line in enumerate(script_context, 1):
        position.setdefault(" ".join((line or "").split()), i)

    lines = [
        instruction,
        "",
        "THE FULL SCRIPT",
        "Read all of it before you write anything. Each excerpt below is one",
        "moment inside this film. Place the moment in the story first — what has",
        "just happened, what is about to — and describe that moment, not the",
        "sentence on its own.",
        "",
    ]
    lines.extend(numbered)
    lines.extend(["", "THE MOMENTS TO DESCRIBE", ""])
    for idx, s in enumerate(batch, 1):
        scene = " ".join((s.get("scene") or "").split())
        at = position.get(scene)
        where = f" (script line {at})" if at else ""
        lines.append(f"{idx}.{where} {scene}")
    return "\n".join(lines)


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


def is_valid_description(sentence: str, allow_rich: bool = False) -> bool:
    """Validate a sentence against the rules that produced it."""
    if not sentence or not sentence.strip():
        return False
    words = sentence.strip().split()
    if allow_rich:
        return len(words) <= RICH_WORD_CAP
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


def describe_shots(shots: list, api_key: Optional[str] = None, model: str = "",
                   series_cfg: Optional[dict] = None, script_context=None,
                   provider: Optional[Any] = None, provider_name: Optional[str] = None) -> dict:
    """
    One visual sentence per shot, keyed by shot_id.
    """
    global _MEMORY_CACHE
    if not shots:
        return {}

    # Initialize disk cache if memory cache is empty
    if not _MEMORY_CACHE:
        _MEMORY_CACHE.update(_load_disk_cache())

    from pipeline.llm.factory import get_llm_provider, get_single_llm_provider, is_permanent_error, set_last_provider_status

    # Resolve LLM provider
    prov_instance = provider
    if prov_instance is None:
        if api_key is not None and not str(api_key).strip():
            # Explicit empty key passed
            sys.stderr.write("[shot_description] No Google API key configured, falling back to query\n")
            return {}
        elif api_key:
            # Explicit non-empty key passed
            p_name = provider_name or "gemini"
            m_name = model or "gemini-2.5-flash"
            prov_instance = get_single_llm_provider(p_name, model=m_name, api_key=api_key)
        else:
            # Resolve from settings / Automatic mode
            prov_instance = get_llm_provider(provider_name=provider_name, model=model)

    prov_type = getattr(prov_instance, "__class__", type(prov_instance)).__name__.lower()
    prov_key = "gemini" if "gemini" in prov_type else ("anthropic" if "anthropic" in prov_type else ("openai" if "openai" in prov_type else ("deepseek" if "deepseek" in prov_type else prov_type)))
    model_name = getattr(prov_instance, "model", model or "gemini-2.5-flash")

    series_slug = (series_cfg or {}).get("series_slug", "")
    prompt_recipe = (series_cfg or {}).get("prompt_recipe", "")
    era_block = (series_cfg or {}).get("era_block", "")
    has_recipe = bool((prompt_recipe or "").strip())

    results = {}
    uncached_shots = []

    # 1. Check existing shot visual_description and cache
    for shot in shots:
        shot_id = shot.get("shot_id")
        scene = (shot.get("scene") or "").strip()
        if not shot_id or not scene:
            continue

        h = _scene_hash(scene, series_slug=series_slug, prompt_recipe=prompt_recipe,
                        era_block=era_block, script_context=script_context,
                        model=model_name, provider=prov_key)
        existing_desc = shot.get("visual_description")
        if existing_desc:
            if has_recipe or is_valid_description(existing_desc):
                clean_desc = existing_desc.strip().rstrip(".")
                results[shot_id] = clean_desc
                _MEMORY_CACHE[h] = clean_desc
        elif h in _MEMORY_CACHE and (has_recipe or is_valid_description(_MEMORY_CACHE[h])):
            results[shot_id] = _MEMORY_CACHE[h]
        else:
            uncached_shots.append(shot)

    if not uncached_shots:
        return results

    # 2. Batch 20 shots per request
    BATCH_SIZE = 20
    cache_updated = False
    instruction_prompt = _build_instruction(series_cfg)

    for batch_start in range(0, len(uncached_shots), BATCH_SIZE):
        batch = uncached_shots[batch_start:batch_start + BATCH_SIZE]
        prompt_text = _build_batch_prompt(instruction_prompt, batch, script_context=script_context)

        try:
            if prov_key == "gemini":
                key_to_use = getattr(prov_instance, "api_key", api_key or "")
                reply_text = _call_gemini_batch(prompt_text, api_key=key_to_use, model=model_name)
            else:
                reply_text = prov_instance.complete_text(system=prompt_text, user="", max_tokens=2048)

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

                    if is_valid_description(sentence, allow_rich=has_recipe):
                        clean_sentence = sentence.rstrip(" .")
                        results[s_id] = clean_sentence
                        _MEMORY_CACHE[_scene_hash(s_scene, series_slug=series_slug,
                                                  prompt_recipe=prompt_recipe, era_block=era_block,
                                                  script_context=script_context, model=model_name,
                                                  provider=prov_key)] = clean_sentence
                        cache_updated = True
        except urllib.error.HTTPError as err:
            is_perm, code, explanation = is_permanent_error(err)
            sys.stderr.write(f"[shot_description] HTTP error {err.code} calling LLM provider: {err}, falling back to query\n")
            continue
        except urllib.error.URLError as err:
            sys.stderr.write(f"[shot_description] URL error calling LLM provider: {err}, falling back to query\n")
            continue
        except Exception as err:
            is_perm, code, explanation = is_permanent_error(err)
            sys.stderr.write(f"[shot_description] Error calling LLM provider: {err}, falling back to query\n")
            continue

    if cache_updated:
        _save_disk_cache(_MEMORY_CACHE)

    return results