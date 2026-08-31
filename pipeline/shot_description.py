"""
pipeline/shot_description.py

Planning-time pass that writes one visual sentence per shot, stored on the shot
as "visual_description", used as the prompt's subject.
"""

import os
import re
import sys
import json
import hashlib
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

    from pipeline.llm.factory import (get_llm_provider, get_single_llm_provider,
                                      is_permanent_error, set_last_provider_status,
                                      get_last_provider_status, PROVIDER_DISPLAY_NAMES)

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

    # The provider says who it is. Sniffing the class name and reading .model
    # off it worked for a single provider and quietly failed for Automatic,
    # which has neither — every description then cached under the same name
    # whichever provider had actually written it.
    prov_key, model_name = prov_instance.identity()

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
            # Every provider goes through the seam, Gemini included. Gemini used
            # to take a direct HTTP path here, so the one provider writing all
            # of the prompts was the one the seam never covered.
            # The reply carries one description per shot in the batch, so the
            # ceiling has to scale with the batch and with how long a recipe
            # lets a description run. At a flat 2048 a recipe-driven batch of
            # twenty was cut off mid-word after the third description, and the
            # other seventeen shots silently fell back to two-word keyword
            # search. Measured: 3 of 20 came back at 2048, all 20 at 8192.
            # The floor matters as much as the scaling: a final batch of seven
            # still came back with two at 2048. An unused ceiling costs nothing
            # — only generated tokens are billed — so there is no reason to be
            # tight here, and every reason not to be.
            per_shot = 250 if has_recipe else 80
            reply_budget = min(8192, max(4096, len(batch) * per_shot + 512))
            reply_text = prov_instance.complete_text(system=prompt_text, user="",
                                                     max_tokens=reply_budget)

            if not reply_text:
                continue

            # Parse lines: Match ^\s*(\d+)[.):]\s*(.+)$ per line
            line_pattern = re.compile(r"^\s*(\d+)[.):]\s*(.+)$")
            batch_before = len(results)
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

            # A batch that answers for fewer shots than it was asked about has
            # been cut off, and every shot it skipped drops to keyword search.
            # That is invisible unless it is counted, which is how seventeen
            # shots in twenty went unnoticed.
            got = len(results) - batch_before
            if got < len(batch):
                message = (f"{PROVIDER_DISPLAY_NAMES.get(prov_key, prov_key.title())} "
                           f"described {got} of {len(batch)} shots in one batch — "
                           f"the reply was cut short. The rest fall back to keyword search.")
                set_last_provider_status("error", message, answering_provider=prov_key)
                sys.stderr.write(f"[shot_description] {message}\n")
        except Exception as err:
            # A dead provider has to reach the screen. Classifying the error and
            # then writing it to stderr — where no user looks — before dropping
            # silently to keyword planning is exactly how a months-dead DeepSeek
            # key went unnoticed. Automatic reports its own chain failure in
            # more detail, so leave that message standing when it is there.
            is_perm, code, explanation = is_permanent_error(err)
            display = PROVIDER_DISPLAY_NAMES.get(prov_key, prov_key.title())
            if is_perm:
                message = (f"{display} refused the request: {explanation}. "
                           f"Shot descriptions fell back to keyword search.")
            else:
                message = (f"{display} could not be reached: {err}. "
                           f"Shot descriptions fell back to keyword search.")
            if prov_key != "auto" or get_last_provider_status().get("status") != "error":
                set_last_provider_status("error", message, answering_provider="")
            sys.stderr.write(f"[shot_description] {message}\n")
            continue

    if cache_updated:
        _save_disk_cache(_MEMORY_CACHE)

    return results