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
#: a shot is described; these lines decide what a description has to resolve
#: before it counts as finished, that the reply can be parsed, and that nothing
#: unreadable ends up drawn into the picture.
#:
#: The completeness list is the part that earns its length. A recipe describes
#: the *world* — the look of the whole film — and a model can satisfy every word
#: of it while still returning "two figures in an ancient setting, dramatic
#: light". Nothing was asking each individual description to resolve who is in
#: the frame, what they are doing, where the camera stands and where the light
#: comes from, so nothing did.
RECIPE_OUTPUT_CONTRACT = """Write ONE image description for each numbered picture below,
following the directives above.

Each description is the entire brief for one picture. Nothing else will be
added to say what the picture shows, so whatever you leave out will not be
there. Resolve every one of these that the moment calls for:

- the main subject, and the one action visible in the frame
- the place, and the period's own buildings, tools, clothing and materials
- what stands near the camera, and what lies behind
- the composition and the viewpoint: how near the camera is, where it stands,
  what fills the frame
- the light: where it comes from, its direction and its quality
- what hangs in the air, and the emotional weight of the moment

Do not recite those categories one by one. Use them to check that someone who
has read nothing else could draw this picture and get it right.

You choose the camera for every picture, and you vary it across the film. Do
not stand the same distance from every subject.

These requirements override anything above that conflicts with them:
- Describe only what a camera could see. Never restate the narration, and never
  address the viewer.
- Each description is ONE still frame that stands on its own. No camera
  movement - no pan, zoom, tracking, dolly, cut or sequence - and never refer
  to another shot, to "the previous scene", or to what came before. The
  picture is made in isolation by someone who has seen nothing else. "The same
  landscape, but now with embers" describes nothing: whoever draws it has never
  seen the first one. Name the landscape again, in full, every time.
- Do not name a medium, an art style or a named artist. The look of the film is
  applied afterwards and is not yours to choose.
- Say what IS in the picture, never what is absent. Image models do not read
  negation - writing "no wings" makes wings more likely, not less - so a
  description that lists what it excludes produces the very thing it excluded.
  Where something must not be seen, build the picture so that it cannot be: a
  face that must not show becomes "seen from behind" or "a back-lit
  silhouette"; a modern building becomes "an untouched primordial landscape";
  wings and horns become "a column of amber heat-shimmer above bare rock".
  Never write "no", "not", "without", "avoid", "free of", "devoid of", "empty
  of", "absent", "lacking" or "there are none" - in any phrasing. "Devoid of
  human figures" and "with no discernible figures" are the same mistake as "no
  people": name a thing and the model draws it. Describe only what the camera
  sees. A picture that has to say what it leaves out has not been composed yet.
- Nothing written may appear in the scene: no text, letters, captions, numbers,
  signage or inscriptions.
- Output exactly one line per picture, formatted as:
  <number>. <description>
  where <number> is the picture number it was given below.
- Return nothing else - no preamble, no blank lines, no commentary."""

#: A recipe may ask for a paragraph. It may not ask for a runaway.
#:
#: Raised from 150 when the output contract began requiring each description to
#: resolve subject, action, place, material culture, foreground, background,
#: composition, viewpoint, light and atmosphere. A description that answers all
#: of that runs past 150 words, and a description over the cap is not trimmed —
#: it is discarded, and the shot silently drops to two-word keyword search. It
#: would have been the new contract quietly undoing itself.
RICH_WORD_CAP = 220

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
                provider: str = "", span: str = "", total_pictures: int = 0) -> str:
    """
    Stable hash of the scene, the niche configuration, model, provider, the film
    it is in, and the stretch of that film the picture has to carry.

    The span belongs in the key because it is now most of the brief. The same
    opening sentence covering six script lines and covering one is two different
    pictures, and it changes whenever the image budget is moved — so a re-plan at
    a different budget has to re-describe rather than serve the old answer.
    """
    cleaned_scene = " ".join((scene or "").strip().split())
    recipe_hash = hashlib.sha256((prompt_recipe or "").strip().encode("utf-8")).hexdigest()[:12] if prompt_recipe else ""
    slug_part = (series_slug or "").strip().lower()
    era_part = " ".join((era_block or "").strip().split())
    prov_part = (provider or "gemini").strip().lower()
    model_part = (model or "gemini-2.5-flash").strip().lower()
    span_part = f"{(span or '').strip()}/{int(total_pictures or 0)}"
    # v7: the span of script the picture covers, and the film's picture count,
    # join provider, model, niche, recipe, era and script in the key.
    raw = (f"v7|{prov_part}|{model_part}|{slug_part}|{recipe_hash}|{era_part}|{_script_fingerprint(script_context)}"
           f"|{span_part}|{cleaned_scene}")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _never_depict_rule(series_cfg: Optional[dict]) -> str:
    """
    The niche's `never_depict` names, phrased as a rule for the model.

    A figure reaches a picture two ways: named in the brief the composer appends
    to every prompt, or written into a description by the model. Both have to
    honour the list, or it is only half a rule.
    """
    from pipeline.library import never_depict_names
    names = never_depict_names(series_cfg)
    if not names:
        return ""
    listed = ", ".join(sorted(n.title() for n in names))
    return ("- Never depict, and never describe the appearance of: " + listed +
            ". Show the scene around them - what others do, where the light "
            "falls, what is left behind - never their form, face, hands or figure.")


def _never_show_face_rule(series_cfg: Optional[dict]) -> str:
    """
    The niche's `never_show_face` names, phrased as a rule for the model.

    Distinct from `never_depict`, which removes a figure entirely. These belong
    in the picture; what they must never be is identifiable. Without the rule
    the model reached for the nearest stock idea of a person — a cloaked figure,
    a furrowed brow, cold eyes — and an image generator turns that into a
    photographic human model.
    """
    from pipeline.library import never_show_face_names
    names = never_show_face_names(series_cfg)
    if not names:
        return ""
    listed = ", ".join(sorted(n.title() for n in names))
    return ("- These may appear in a picture but must never be identifiable: " + listed +
            ". Show them far from the camera, from behind, or as a silhouette against "
            "stronger light. No face, no facial features, no eyes, no read of an "
            "expression, and never anything that would render as a photographed human "
            "model. Give them no wings, no horns, no coloured skin and no "
            "fantasy-creature form. Carry their state through the scene instead - the "
            "light, the ground, the distance, what everyone else is doing.")


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
        # The niche's standing exclusions. The app has always held these in
        # `negative_block` and never showed them to the model — it appended them
        # to the finished prompt, and only when a setting was on. So a request
        # asking for a complete, production-ready prompt was asking for one with
        # no exclusions in it, and all sixty came back with none. The owner's own
        # prompts carry them on every line; that is most of the visible gap.
        negative = (series_cfg.get("negative_block") or "").strip()
        if negative:
            parts.append("Standing exclusions for this film. Do not write these "
                         "into the description - compose each picture so that "
                         f"none of them could appear in it: {negative}")

        contract = RECIPE_OUTPUT_CONTRACT
        rules = [r for r in (_never_depict_rule(series_cfg),
                             _never_show_face_rule(series_cfg)) if r]
        if rules:
            contract = contract.replace(
                "- Nothing written may appear in the scene:",
                "\n".join(rules) + "\n- Nothing written may appear in the scene:")
        parts.append(contract)
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


def _numbered_script(script_context) -> list:
    """The whole narration, one numbered line each, trimmed if it runs away."""
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
    return numbered


def _span_label(entry: dict) -> str:
    """`02:14 to 02:33 (script lines 7-13)`, or line numbers alone when untimed."""
    first, last = entry.get("first_line"), entry.get("last_line")
    if not first:
        return "position unknown"
    lines = (f"script line {first}" if not last or last == first
             else f"script lines {first}-{last}")

    start, end = entry.get("starts_at"), entry.get("ends_at")
    if start is None or end is None:
        return lines

    def _mmss(value):
        minutes, secs = divmod(int(round(float(value))), 60)
        return f"{minutes:02d}:{secs:02d}"

    return f"{_mmss(start)} to {_mmss(end)} ({lines})"


def _build_batch_prompt(instruction: str, batch: list, script_context=None,
                        picture_plan=None) -> str:
    """
    The text sent for one batch of pictures.

    The model is shown three things and nothing else: the whole script, how many
    pictures the film is made of, and where each one falls in that script. It is
    never handed a narration excerpt as the thing to illustrate.

    That was the defect. A picture stands for a *run* of script lines — in the
    owner's film, 5.8 of them on average — but the request pasted the run's first
    sentence underneath the instruction as if it were the brief. Asked to
    illustrate "Before Adam, there was no human being.", a model returns a vague
    landscape, and it is right to: that is all the sentence supports. The six
    lines the picture actually has to carry were sitting in the script block
    above, unattached to it.

    So the excerpt is gone. A picture is identified by its number and its span,
    both of which point back into the script the model has already read. The
    plan of all the film's pictures travels with every batch, so a model writing
    pictures 21-40 still knows that 1-20 and 41-60 exist and what they cover.

    With no plan the old excerpt form is kept, for callers that have only a bare
    list of scenes to describe.
    """
    if picture_plan and script_context:
        return _build_picture_prompt(instruction, batch, script_context, picture_plan)

    if not script_context:
        lines = [instruction, ""]
        for idx, s in enumerate(batch, 1):
            lines.append(f"{idx}. {s.get('scene', '').strip()}")
        return "\n".join(lines)

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
    lines.extend(_numbered_script(script_context))
    lines.extend(["", "THE MOMENTS TO DESCRIBE", ""])
    for idx, s in enumerate(batch, 1):
        scene = " ".join((s.get("scene") or "").split())
        at = position.get(scene)
        where = f" (script line {at})" if at else ""
        lines.append(f"{idx}.{where} {scene}")
    return "\n".join(lines)


def _build_picture_prompt(instruction: str, batch: list, script_context,
                          picture_plan: list) -> str:
    """The script, the picture count, and where every picture falls in it."""
    total = len(picture_plan)
    wanted = [s.get("picture_number") for s in batch if s.get("picture_number")]

    lines = [
        instruction,
        "",
        "THE FULL SCRIPT",
        "Read all of it before you write anything. This is the whole film, one",
        "numbered line per narration beat.",
        "",
    ]
    lines.extend(_numbered_script(script_context))

    lines.extend([
        "",
        "THE PICTURE PLAN",
        f"This film is made of exactly {total} pictures, numbered 1 to {total}.",
        "Each picture stands for a run of consecutive script lines and has to",
        "carry that whole run — everything those lines say, the turn they take,",
        "where the story has got to by then — not the first sentence in it.",
        "The plan is fixed. Do not add a picture, drop one, or move one.",
        "",
    ])
    for entry in picture_plan:
        lines.append(f"Picture {entry['number']} — {_span_label(entry)}")

    lines.extend([
        "",
        "WRITE THESE PICTURES NOW",
        "Write one description for each of these picture numbers, and no others.",
        "Number each line with the picture number exactly as given here:",
        "",
        ", ".join(str(n) for n in wanted),
    ])
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

    # The plan is the shot list itself. A caller that knows which pictures the
    # film makes tags every shot it sends with its picture number and the run of
    # script lines that picture has to carry; the plan is then exactly those
    # shots, in order, and cannot drift out of step with what gets described.
    picture_plan = []
    if shots and all(s.get("picture_number") for s in shots):
        picture_plan = [
            {"number": s["picture_number"], "shot_id": s.get("shot_id"),
             "first_line": s.get("first_line"), "last_line": s.get("last_line")}
            for s in shots
        ]
    total_pictures = len(picture_plan)

    def _hash_for(shot: dict, scene: str) -> str:
        entry = {"first_line": shot.get("first_line"), "last_line": shot.get("last_line")}
        return _scene_hash(scene, series_slug=series_slug, prompt_recipe=prompt_recipe,
                           era_block=era_block, script_context=script_context,
                           model=model_name, provider=prov_key,
                           span=_span_label(entry) if picture_plan else "",
                           total_pictures=total_pictures)

    results = {}
    uncached_shots = []

    # 1. Check existing shot visual_description and cache
    for shot in shots:
        shot_id = shot.get("shot_id")
        scene = (shot.get("scene") or "").strip()
        if not shot_id or not scene:
            continue

        h = _hash_for(shot, scene)
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
        prompt_text = _build_batch_prompt(instruction_prompt, batch,
                                          script_context=script_context,
                                          picture_plan=picture_plan)
        # With a plan the model answers by picture number, which is a number in
        # the whole film, not a position inside this batch. Batch three answers
        # 41, 42, 43 and there is no shot at index 41 of a twenty-shot batch.
        by_number = {s.get("picture_number"): s for s in batch} if picture_plan else {}

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
            # 320 covers a description written to the full completeness list at
            # the 220-word cap. 20 x 320 + 512 stays under the 8192 ceiling, so
            # the ceiling still holds and no provider is asked for more than it
            # allows.
            per_shot = 320 if has_recipe else 80
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

                # Map back to the shot the number names: its picture number when
                # a plan was sent, otherwise its 1-indexed place in the batch.
                if picture_plan:
                    matched_shot = by_number.get(num)
                else:
                    matched_shot = batch[num - 1] if 1 <= num <= len(batch) else None

                if matched_shot is not None:
                    s_id = matched_shot.get("shot_id")
                    s_scene = matched_shot.get("scene", "")

                    if is_valid_description(sentence, allow_rich=has_recipe):
                        clean_sentence = sentence.rstrip(" .")
                        results[s_id] = clean_sentence
                        _MEMORY_CACHE[_hash_for(matched_shot, s_scene)] = clean_sentence
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