"""
Plain-text script parser.
Splits a raw script into segments, extracts image search keywords automatically,
and returns a dict matching the S2V JSON schema — ready to pass straight to the
validator and orchestrator.

When a Google API key is provided, `build_script_with_ai()` uses Gemini to
intelligently split the script at natural narrative breaks, generate specific
b_roll_keywords, and optionally suggest a visual_style.  Falls back to the
rule-based `build_script()` if Gemini fails or no key is available.
"""

import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from typing import Optional, Dict, Any, List

# Common English words that make poor image search terms
STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "can", "that",
    "this", "these", "those", "it", "its", "they", "them", "their", "there",
    "then", "than", "so", "if", "when", "where", "who", "which", "what",
    "how", "not", "no", "nor", "up", "out", "about", "into", "through",
    "during", "before", "after", "above", "below", "between", "each",
    "him", "his", "her", "she", "he", "we", "our", "you", "your", "i",
    "my", "me", "us", "all", "also", "just", "more", "most", "one", "two",
    "three", "four", "five", "very", "any", "some", "such", "over", "under",
    "again", "while", "both", "few", "other", "than", "too", "only", "own",
    "same", "even", "never", "always", "often", "still", "now", "back",
    "since", "until", "every", "around", "without", "later", "however",
    "therefore", "because", "became", "become", "known", "called", "said",
    "many", "much", "new", "old", "great", "long", "little", "own", "right",
    "big", "high", "different", "small", "large", "next", "early", "young",
    "important", "public", "private", "real", "best", "free", "able",
}

# Ken Burns effects cycle — gives variety across scenes
from pipeline.motion import assign_effects, style_of

KEN_BURNS_CYCLE = ["zoom_in", "pan_right", "zoom_out", "pan_left", "zoom_in", "zoom_out"]

# Transition cycle
TRANSITION_CYCLE = ["fade", "crossfade", "fade", "crossfade"]


def sanitize_output_filename(filename: str) -> str:
    """Sanitize the output filename to be safe for filenames and end with .mp4."""
    stem = filename.strip()
    # Strip a supplied .mp4 before sanitising — otherwise the dot becomes an
    # underscore and "s2e6.mp4" comes back as "s2e6_mp4.mp4".
    if stem.lower().endswith('.mp4'):
        stem = stem[:-4]
    safe_name = re.sub(r'[^\w\-]', '_', stem)
    safe_name = re.sub(r'_+', '_', safe_name).strip('_')
    if not safe_name:
        safe_name = "my_video"
    return safe_name + '.mp4'


# ── Sentence / paragraph splitter ──────────────────────────────────────────────

def _split_long_paragraph(paragraph: str, max_words: int) -> list:
    """Break one over-long paragraph at sentence boundaries, keeping every word."""
    raw_sentences = re.split(r'(?<=[.!?])\s+', paragraph)
    sentences = [s.strip() for s in raw_sentences if s.strip()]
    if not sentences:
        return [paragraph]

    chunks = []
    current, count = [], 0
    for sentence in sentences:
        wc = len(sentence.split())
        if count + wc > max_words and current:
            chunks.append(" ".join(current))
            current, count = [sentence], wc
        else:
            current.append(sentence)
            count += wc
    if current:
        chunks.append(" ".join(current))

    # Text with no sentence punctuation at all leaves one enormous "sentence".
    # A hard word-boundary split is ugly, but far better than a segment that
    # holds a single image for minutes.
    final = []
    for chunk in chunks:
        words = chunk.split()
        if len(words) > max_words * 1.5:
            for i in range(0, len(words), max_words):
                final.append(" ".join(words[i:i + max_words]))
        else:
            final.append(chunk)
    return final


def _cap_segment_length(segments: list, max_words: int) -> list:
    """
    Keep the writer's paragraph boundaries, but never let one run unwatchably long.

    The paragraph strategies used to return whatever they were given, applying
    max_words only in the unformatted-text fallback. A script pasted as one solid
    block after its title became a single 5,414-word segment — one shot held for
    the length of the film. Paragraph breaks still decide where segments start;
    this only subdivides a paragraph that is too long to be a scene.
    """
    capped = []
    for seg in segments:
        if len(seg.split()) > max_words:
            capped.extend(_split_long_paragraph(seg, max_words))
        else:
            capped.append(seg)
    return capped


#: Measured on this machine: Supertonic reads ~2.6 words per second.
WORDS_PER_SECOND = 2.6

def split_narration_for_shots(narration: str, n: int) -> list:
    """Split one segment's narration into n runs of whole sentences."""
    if n <= 1:
        return [narration]
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', narration) if s.strip()]

    # A shot boundary is visual only — the narration is one continuous take and
    # shot durations are split evenly across it. So when a segment has fewer
    # sentences than shots wanted, splitting mid-sentence costs nothing and is the
    # difference between a 12-second hold and a 5-second one.
    if len(sentences) < n:
        words = narration.split()
        if len(words) < n:
            return [narration] if len(sentences) <= 1 else sentences
        size = max(1, len(words) // n)
        chunks = [" ".join(words[i:i + size]) for i in range(0, len(words), size)]
        while len(chunks) > n:
            chunks[-2] = chunks[-2] + " " + chunks[-1]
            chunks.pop()
        return chunks

    total = sum(len(s.split()) for s in sentences)
    target = total / n
    chunks, current, count = [], [], 0
    for idx, sentence in enumerate(sentences):
        current.append(sentence)
        count += len(sentence.split())
        remaining_sentences = len(sentences) - 1 - idx
        needed_chunks = (n - 1) - len(chunks)
        if (count >= target or remaining_sentences == needed_chunks) and len(chunks) < n - 1:
            chunks.append(" ".join(current))
            current, count = [], 0
    if current:
        chunks.append(" ".join(current))

    # If sentence boundary grouping produced fewer chunks due to sentence size variation,
    # subdivide mid-sentence to satisfy the requested shot count.
    if len(chunks) < n:
        words = narration.split()
        if len(words) >= n:
            size = max(1, len(words) // n)
            chunks = [" ".join(words[i:i + size]) for i in range(0, len(words), size)]
            while len(chunks) > n:
                chunks[-2] = chunks[-2] + " " + chunks[-1]
                chunks.pop()

    return chunks


def _carryable_by_scene(old_shots) -> dict:
    """
    What a shot has already earned, keyed by the narration it covers.

    A re-cut rebuilds every shot from scratch. When a new chunk covers exactly
    the text an old shot covered it *is* that shot, and the description written
    for it and the query planned for it still describe it. Regenerating them
    from `extract_keyword` replaces a written sentence with a two-word guess and
    throws the planner's work away — which is what left one 347-shot film with
    no descriptions at all and queries like "fought defeated drove".

    Keyed on whitespace-normalised scene text, so a chunk that changed at all is
    treated as new and is re-planned exactly as before.
    """
    carry = {}
    for shot in old_shots:
        scene = " ".join((shot.get("scene") or "").split())
        if not scene:
            continue
        keep = {}
        described = (shot.get("visual_description") or "").strip()
        if described:
            keep["visual_description"] = described
        planned = (shot.get("query") or "").strip()
        if planned:
            keep["query"] = planned
        if keep:
            carry[scene] = keep
    return carry


def apply_shot_rhythm(script_data: dict, seconds_per_shot: float = 7.0) -> dict:
    """
    Cut each segment into several shots so the picture changes on a rhythm.

    A segment holds one image for its whole span. At the ~19s segments this app
    produces that is a slideshow, however good the Ken Burns move is — broadcast
    documentary cuts every 4-6 seconds. Splitting the narration into runs of whole
    sentences gives each shot its own search query, so the library supplies a
    different image per shot and diversity keeps them distinct.

    Existing pins are carried over positionally: a deliberate choice for the first
    shot survives a rhythm change, later ones are re-planned.

    The camera moves are dealt out afterwards, in one pass over the whole script,
    under the project's motion style. Assigning them here, per segment, meant
    every segment opened on the same move.

    Returns {"shots_before": int, "shots_after": int, "segments": int}.
    """
    seconds_per_shot = max(2.0, float(seconds_per_shot or 7.0))
    before = after = 0

    for seg in script_data.get("segments", []):
        seg_id = seg.get("segment_id", 1)
        narration = seg.get("narration", "") or ""
        old_shots = seg.get("shots") or []
        before += len(old_shots)

        words = len(narration.split())
        est_seconds = words / WORDS_PER_SECOND if words else 0.0
        wanted = max(1, int(round(est_seconds / seconds_per_shot))) if est_seconds else 1

        chunks = split_narration_for_shots(narration, wanted)

        # Carry over whatever the user had already settled, in order.
        carried = [
            {k: s[k] for k in ("source", "pin", "resolved", "resolved_score") if k in s}
            for s in old_shots
        ]
        template = old_shots[0] if old_shots else {}
        treatment = template.get("treatment") or {"filter": "none", "grade": None}
        carry_by_scene = _carryable_by_scene(old_shots)

        new_shots = []
        for i, chunk in enumerate(chunks):
            shot = {
                "shot_id": f"{seg_id}{chr(97 + i)}",
                "duration": None,
                "source": "library",
                "query": extract_keyword(chunk) or extract_keyword(narration) or "documentary shot",
                "pin": None,
                "min_score": template.get("min_score", 0.26),
                "motion": {"kind": "ken_burns", "effect": "zoom_in"},
                "treatment": dict(treatment),
                # The slice of narration this shot covers. Without it every shot
                # in a segment shares one description and gets the same prompt.
                "scene": chunk,
            }
            prior = carry_by_scene.get(" ".join(chunk.split()))
            if prior:
                shot.update(prior)
            if i < len(carried) and carried[i].get("pin"):
                shot.update(carried[i])
            new_shots.append(shot)

        seg["shots"] = new_shots
        after += len(new_shots)

    assign_effects(script_data, style_of(script_data))

    return {
        "shots_before": before,
        "shots_after": after,
        "segments": len(script_data.get("segments", [])),
    }


def _count_distinct_images(segments) -> int:
    """
    How many distinct images the plan actually uses.

    Counted from the shots themselves rather than returned from the number that
    was asked for. A budget that reports back its own input cannot tell you it
    missed, and `images_after == N` is the one assertion this feature rests on.
    """
    return sum(1 for seg in segments
               for shot in (seg.get("shots") or [])
               if not shot.get("share_with"))


def plan_image_budget(script_data: dict, image_count: int) -> dict:
    """
    Re-cut the whole script so it uses exactly image_count images.

    Unlike apply_shot_rhythm, which floors at one shot per segment, this plans
    across the whole script: when fewer images are asked for than there are
    segments, a run of consecutive segments shares one image.

    Returns {"images_before": int, "images_after": int, "segments": int,
             "shared_runs": int}.
    """
    import math

    N = max(1, min(500, int(image_count if image_count is not None else 1)))
    segments = script_data.get("segments", [])
    S = len(segments)

    if S == 0:
        return {"images_before": 0, "images_after": 0, "segments": 0, "shared_runs": 0}

    # Count distinct images before re-planning (non-sharing shots)
    before = 0
    for seg in segments:
        shots = seg.get("shots") or []
        if shots:
            before += sum(1 for s in shots if not s.get("share_with"))
        else:
            before += 1

    # Duration estimates per segment
    seg_seconds = []
    for seg in segments:
        narration = seg.get("narration", "") or ""
        words = len(narration.split())
        seg_seconds.append(words / WORDS_PER_SECOND if words else 0.0)

    total_seconds = sum(seg_seconds)
    if total_seconds <= 0.0:
        seg_seconds = [1.0] * S
        total_seconds = float(S)

    if N >= S:
        # Case A — N >= S (split segments proportional to duration)
        raw = [N * (sec / total_seconds) for sec in seg_seconds]
        base = [max(1, math.floor(r)) for r in raw]

        # While sum(base) > N: decrement the largest base[i] that is > 1
        while sum(base) > N:
            candidates = [i for i, b in enumerate(base) if b > 1]
            if not candidates:
                break
            best_idx = max(candidates, key=lambda i: (base[i], -(raw[i] - math.floor(raw[i]))))
            base[best_idx] -= 1

        # While sum(base) < N: increment the base[i] with largest fractional remainder
        while sum(base) < N:
            remainders = [(raw[i] - math.floor(raw[i]), i) for i in range(S)]
            remainders.sort(key=lambda x: x[0], reverse=True)
            for _, i in remainders:
                if sum(base) < N:
                    base[i] += 1

        for i, seg in enumerate(segments):
            seg_id = seg.get("segment_id", i + 1)
            narration = seg.get("narration", "") or ""
            old_shots = seg.get("shots") or []

            chunks = split_narration_for_shots(narration, base[i])

            carried = [
                {k: s[k] for k in ("source", "pin", "resolved", "resolved_score") if k in s}
                for s in old_shots
            ]
            template = old_shots[0] if old_shots else {}
            treatment = template.get("treatment") or {"filter": "none", "grade": None}
            carry_by_scene = _carryable_by_scene(old_shots)

            new_shots = []
            for j, chunk in enumerate(chunks):
                shot = {
                    "shot_id": f"{seg_id}{chr(97 + j)}",
                    "duration": None,
                    "source": "library",
                    "query": extract_keyword(chunk) or extract_keyword(narration) or "documentary shot",
                    "pin": None,
                    "min_score": template.get("min_score", 0.26),
                    "motion": {"kind": "ken_burns", "effect": "zoom_in"},
                    "treatment": dict(treatment),
                    "scene": chunk,
                    "share_with": None,
                }
                prior = carry_by_scene.get(" ".join(chunk.split()))
                if prior:
                    shot.update(prior)
                if j < len(carried) and carried[j].get("pin"):
                    shot.update(carried[j])
                new_shots.append(shot)

            seg["shots"] = new_shots

        assign_effects(script_data, style_of(script_data))

        return {
            "images_before": before,
            "images_after": _count_distinct_images(segments),
            "segments": S,
            "shared_runs": 0,
        }

    else:
        # Case B — N < S (share images across segments)
        target_dur = total_seconds / N
        runs = []
        current_run = []
        current_dur = 0.0

        for i, seg in enumerate(segments):
            current_run.append((i, seg))
            current_dur += seg_seconds[i]
            remaining_segs = S - 1 - i
            runs_needed = (N - 1) - len(runs)

            if len(runs) < N - 1:
                if current_dur >= target_dur or remaining_segs == runs_needed:
                    runs.append(current_run)
                    current_run = []
                    current_dur = 0.0

        if current_run:
            runs.append(current_run)

        for run_idx, run_items in enumerate(runs):
            run_narrations = [(seg.get("narration", "") or "").strip() for _, seg in run_items]
            full_run_narration = " ".join(n for n in run_narrations if n)
            run_query = extract_keyword(full_run_narration) or "documentary shot"

            first_seg_id = run_items[0][1].get("segment_id", run_items[0][0] + 1)
            first_shot_id = f"{first_seg_id}a"

            for pos, (i, seg) in enumerate(run_items):
                seg_id = seg.get("segment_id", i + 1)
                narration = seg.get("narration", "") or ""
                old_shots = seg.get("shots") or []
                template = old_shots[0] if old_shots else {}
                treatment = template.get("treatment") or {"filter": "none", "grade": None}

                shot_id = f"{seg_id}a"
                is_first = (pos == 0)

                shot = {
                    "shot_id": shot_id,
                    "duration": None,
                    "source": "library",
                    "query": run_query,
                    "pin": None,
                    "min_score": template.get("min_score", 0.26),
                    "motion": {"kind": "ken_burns", "effect": "zoom_in"},
                    "treatment": dict(treatment),
                    "scene": narration,
                    "share_with": None if is_first else first_shot_id,
                    "run_index": run_idx,
                    "run_position": pos,
                }

                # Only the description carries here. `query` is deliberately the
                # run's, not this segment's: several segments share one image and
                # it is retrieved for the run as a whole.
                prior = _carryable_by_scene(old_shots).get(" ".join(narration.split()))
                if prior and prior.get("visual_description"):
                    shot["visual_description"] = prior["visual_description"]

                if old_shots and old_shots[0].get("pin"):
                    for k in ("source", "pin", "resolved", "resolved_score"):
                        if k in old_shots[0]:
                            shot[k] = old_shots[0][k]

                seg["shots"] = [shot]

        assign_effects(script_data, style_of(script_data))

        return {
            "images_before": before,
            "images_after": _count_distinct_images(segments),
            "segments": S,
            "shared_runs": len(runs),
        }


def _normalise_title(value: str) -> str:
    """Lowercase, strip punctuation and collapse whitespace, for title comparison."""
    cleaned = unicodedata.normalize("NFKD", value or "").lower()
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def drop_title_segment(segments: list, title: str) -> list:
    """
    Remove a leading segment that is just the episode title.

    NOT USED BY THE PIPELINE. Everything in the script box is narrated, including
    a title line the writer chose to leave there — silently deleting a line of
    their script is worse than narrating a heading. The Title *field* never
    produced a segment in the first place; the segment came from the pasted text.

    Kept because the behaviour is still wanted for imported scripts that repeat
    their heading, and because the matching rules below were expensive to get
    right. Call it explicitly if you want it.
    """
    if not segments or len(segments) < 2 or not title:
        return segments

    first = _normalise_title(segments[0])
    wanted = _normalise_title(title)
    if not first or not wanted:
        return segments

    # A genuine opening paragraph is longer than a heading.
    if len(segments[0].split()) > 40:
        return segments

    if first == wanted:
        return segments[1:]

    # Prose that merely opens with the title phrase is still prose, and dropping
    # it would silently delete the first scene. A heading does not end in a full
    # stop; narration does. That is what separates
    #   "S1E2 — The House of Wisdom After the Flood: Nimrod, the Tower"   (heading)
    # from
    #   "The House of Wisdom was not built in a day, and the story ... down."
    if segments[0].rstrip().endswith((".", "!", "?")):
        return segments

    if first in wanted or wanted in first:
        return segments[1:]

    first_tokens, wanted_tokens = set(first.split()), set(wanted.split())
    if wanted_tokens and len(first_tokens & wanted_tokens) / len(wanted_tokens) >= 0.8:
        return segments[1:]

    return segments


def split_into_segments(text: str, max_words: int = 60) -> list:
    """
    Split a plain-text script into a list of narration strings.

    Strategy (in priority order)
    --------
    1. Blank-line paragraphs  — if the script has blank lines between sections,
       each section becomes one segment. The user's formatting is respected exactly.
    2. Single-line paragraphs — if every line is on its own line (no blank lines),
       each non-empty line becomes one segment.
    3. Sentence-group fallback — plain unformatted block of text, grouped into
       ~max_words chunks at sentence boundaries.

    In all cases, only truly empty lines are discarded. No content is ever
    dropped, summarised, or merged unless a paragraph is 2 words or fewer
    (too short to be a standalone scene).
    """
    text = text.strip()
    if not text:
        return []

    # ── Strategy 1: blank-line paragraph split ────────────────────────────────
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]

    if len(paragraphs) >= 2:
        # Collapse internal newlines within each paragraph to a single space
        paragraphs = [re.sub(r'\s*\n\s*', ' ', p) for p in paragraphs]
        # Only merge paragraphs that are truly tiny (≤ 2 words)
        merged = []
        buf = ""
        for p in paragraphs:
            if not buf:
                buf = p
            elif len(buf.split()) <= 2:
                buf = buf + " " + p
            else:
                merged.append(buf)
                buf = p
        if buf:
            merged.append(buf)
        return _cap_segment_length(merged, max_words)

    # ── Strategy 2: single-line paragraph split ───────────────────────────────
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    if len(lines) >= 2:
        # Only merge lines that are truly tiny (≤ 2 words)
        merged = []
        buf = ""
        for ln in lines:
            if not buf:
                buf = ln
            elif len(buf.split()) <= 2:
                buf = buf + " " + ln
            else:
                merged.append(buf)
                buf = ln
        if buf:
            merged.append(buf)
        return _cap_segment_length(merged, max_words)

    # ── Strategy 3: sentence-group fallback ───────────────────────────────────
    raw_sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in raw_sentences if s.strip()]

    segments = []
    current_words = 0
    current_sents = []

    for sentence in sentences:
        wc = len(sentence.split())
        if current_words + wc > max_words and current_sents:
            segments.append(" ".join(current_sents))
            current_sents = [sentence]
            current_words = wc
        else:
            current_sents.append(sentence)
            current_words += wc

    if current_sents:
        segments.append(" ".join(current_sents))

    return segments


# ── Keyword extractor ──────────────────────────────────────────────────────────

def extract_keyword(text: str) -> str:
    """
    Pull a 2-3 word image search keyword from a segment.

    Priority
    --------
    1. Proper nouns (capitalised words not at sentence start) — these are usually
       place names, people, or organisations: the best image search terms.
    2. Any non-stopword word longer than 3 characters.
    """
    # Collect proper nouns (not the first word of a sentence)
    proper = []
    sentences = re.split(r'(?<=[.!?])\s+', text)
    for sent in sentences:
        words = sent.split()
        for i, raw_word in enumerate(words):
            word = raw_word.strip("'\".,!?;:()")
            if (i > 0
                    and word
                    and word[0].isupper()
                    and word.lower() not in STOPWORDS
                    and len(word) > 2):
                proper.append(word)

    # Collect all meaningful words
    all_words = re.findall(r"[A-Za-z']+", text)
    meaningful = [
        w for w in all_words
        if w.lower() not in STOPWORDS and len(w) > 3
    ]

    # Build keyword: proper nouns first, pad with meaningful
    result = []
    seen = set()
    for w in proper + meaningful:
        low = w.lower()
        if low not in seen:
            result.append(w)
            seen.add(low)
        if len(result) >= 3:
            break

    if not result:
        # absolute fallback
        for w in all_words:
            if w.lower() not in STOPWORDS:
                return w
        return "history"

    return " ".join(result[:3])


# ── Script builder ─────────────────────────────────────────────────────────────

def build_script(
    text: str,
    title: str,
    voice: str,
    output_filename: str,
    visual_style: str = "",
    max_words: int = 60,
) -> dict:
    """
    Convert a plain-text script into a full S2V script dict.

    Parameters
    ----------
    text            : the raw narration text
    title           : project title (shown in the app summary)
    voice           : edge-tts voice ID, e.g. "en-US-GuyNeural"
    output_filename : desired MP4 filename (with or without .mp4)
    max_words       : max words per segment when using sentence-group mode

    Returns
    -------
    A dict that matches the S2V JSON schema and can be passed to validate_script()
    and RenderOrchestrator.render().
    """
    raw_segments = split_into_segments(text, max_words)

    if not raw_segments:
        raise ValueError("No text found — please paste your script and try again.")

    safe_name = sanitize_output_filename(output_filename)

    total = len(raw_segments)
    segments = []

    for i, narration in enumerate(raw_segments):
        if i == 0:
            seg_type = "hook"
        elif i == total - 1:
            seg_type = "conclusion"
        else:
            seg_type = "body"

        segments.append({
            "segment_id": i + 1,
            "type": seg_type,
            "narration": narration,
            "b_roll_keyword": extract_keyword(narration),
            "visual_type": "ai_image",
            "ken_burns": KEN_BURNS_CYCLE[i % len(KEN_BURNS_CYCLE)],
            "text_overlay": None,
            "transition_in": TRANSITION_CYCLE[i % len(TRANSITION_CYCLE)],
            "transition_out": TRANSITION_CYCLE[i % len(TRANSITION_CYCLE)],
        })

    return {
        "project": {
            "title": title.strip() or "My Video",
            "output_filename": safe_name,
            "voice": voice,
            "voice_rate": "+0%",
            "voice_pitch": "+0Hz",
            "background_music": None,
            "visual_style": visual_style.strip(),
        },
        "segments": segments,
    }


# ── AI-powered script builder (Gemini) ────────────────────────────────────────

_GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent?key={key}"
)

_SPLIT_PROMPT = """\
You are a video script editor. Your job is to split a narration script into \
individual scenes for a documentary-style YouTube video.

Rules:
1. Narration Dialect & Verbatim: If the requested voice dialect is NOT "Standard English", you MUST adapt and rewrite the narration script text to match the sentence structure, rhythm, spellings, and vocabulary of "{voice_dialect}" (with custom guidelines: "{ai_guideline}"). Otherwise, keep the text verbatim. Do not omit any core information or add filler sentences.
2. Split at natural narrative or topic breaks. Each segment should be \
   30-60 words (one clear idea or moment).
3. For each segment, write a "b_roll_keyword": a highly-detailed, rich 15-25 word \
   visual prompt describing concrete scene imagery, lighting, mood, atmosphere, and subjects in detail. \
   Ensure the visual style and keywords match the requested tone "{narrative_tone}". Avoid generic keywords.
4. Narration SSML Formatting: Wrap the narration segment text in `<speak>...</speak>`. You must inject subtle SSML markup tags to make the speech sound natural, dramatic, and expressive. Use single quotes for all SSML attributes (e.g. use `<break time='300ms'/>` or `<break time='500ms'/>` for dramatic pauses at punctuation, and `<emphasis level='moderate'>...</emphasis>` to emphasize important proper nouns, actions, or names). This is crucial to prevent JSON syntax errors from unescaped double quotes.
5. Voice Steering: Write a "voice_steering" instruction prompt for each segment to steer the Gemini 3.1 Flash Text-to-Speech engine. This guides the speed, emotional tone, and pronunciation.
   - User's Tone Guideline: {ai_guideline} (If empty, use a natural dramatic documentary tone)
   - Ensure the voice_steering matches the user's guideline.
6. Conversational Speaker Switching: The speaker mode is "{speaker_mode}". If it is "conversational", structure the narration to switch between different speakers/voices (using tags `[M1]` through `[M5]` for male speakers, and `[F1]` through `[F5]` for female speakers) mid-sentence or mid-segment to create a natural back-and-forth conversation or dynamic dual-narrative. Insert these tags inline in the narration text (e.g. `[M1] In the beginning, [F1] there was only light.`). If the mode is "single", do not insert any inline speaker tags.
7. Arabic Storytelling: If the narration language is Arabic or the dialect is "Arabic Storytelling", you MUST fully add diacritical marks (Tashkeel) to all Arabic words in the narration text.
8. If the user did not supply a visual_style, suggest one that fits the topic \
   (e.g. "Islamic golden age, warm cinematic tones, oil painting style").

Return ONLY a valid JSON object -- no markdown fences, no commentary -- in this \
exact shape:
{{
  "visual_style": "<suggested style or the user-supplied one unchanged>",
  "segments": [
    {{"narration": "...", "b_roll_keyword": "...", "voice_steering": "..."}},
    ...
  ]
}}

Script title: {title}
User-supplied visual_style (empty = please suggest): {visual_style}

Script to split:
{script}"""

_OVERSIGHT_PROMPT = """\
You are a Quality Control and Voice Narration Editor. Your job is to verify and enrich a proposed storyboard.

Original Script:
{original_script}

Proposed Storyboard (JSON):
{storyboard_json}

Your tasks:
1. Dialect & Accuracy Verification: If a custom voice dialect "{voice_dialect}" is requested, verify that the narration matches the target dialect while retaining 100% of the meaning/flow of the original script. Otherwise, verify that the concatenated "narration" fields of all segments in the storyboard contain EXACTLY the original script verbatim. No words added, changed, or deleted. Correct the "narration" fields immediately if there is a mismatch.
2. Tone Steering: Ensure that the visual descriptions (b_roll_keyword) and voice steering for all segments fit the narrative tone "{narrative_tone}" and user guidelines "{ai_guideline}".
3. Conversational Speaker Switching: The speaker mode is "{speaker_mode}". If it is "conversational", verify that the narration segments contain inline speaker tags like `[M1]`, `[F1]`, etc. at appropriate mid-sentence or mid-segment switch points to create conversational dialogue. If the mode is "single", ensure there are no speaker tags in the narration.
4. Arabic Storytelling: If the language is Arabic, ensure all narration text has full diacritical marks (Tashkeel) added.
5. Wrap each segment's narration in `<speak>...</speak>` and add subtle SSML markup tags (like `<break time='300ms'/>` or `<emphasis level='moderate'>...</emphasis>`) to make it sound natural and dramatic. You must use single quotes for all SSML attributes to prevent JSON format errors.

Return ONLY a valid JSON object in this exact shape:
{{
  "visual_style": "<visual style>",
  "segments": [
    {{
      "narration": "<narration wrapped in speak tag with SSML>",
      "b_roll_keyword": "<visual prompt from the storyboard>",
      "voice_steering": "<voice steering guidance tailored to the segment and tone guideline>"
    }},
    ...
  ]
}}
"""
import hashlib
import random
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _resolve_cache_dir() -> str:
    """
    Planning cache lives under the configured cache_dir, never under config/ —
    that directory holds settings.json with live API keys.
    """
    cache_dir = "cache"
    settings_file = os.path.join(_ROOT, "config", "settings.json")
    if os.path.exists(settings_file):
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                configured = json.load(f).get("cache_dir", "").strip()
                if configured:
                    cache_dir = configured
        except Exception:
            pass
    if not os.path.isabs(cache_dir):
        cache_dir = os.path.join(_ROOT, cache_dir)
    return os.path.join(cache_dir, "planning")


CACHE_DIR = _resolve_cache_dir()


def _http_request_with_backoff(req, timeout=90, max_retries=3):
    """
    Execute HTTP request with exponential backoff and jitter on 429 and 503 errors.
    Caps at max_retries=3.
    """
    delay = 1.0
    for attempt in range(1, max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as err:
            if err.code in (429, 503) and attempt < max_retries:
                jitter = random.uniform(0.1, 0.5)
                sleep_time = delay + jitter
                sys.stderr.write(f"HTTP {err.code} rate limited/busy on attempt {attempt}/{max_retries}. Backing off {sleep_time:.2f}s...\n")
                time.sleep(sleep_time)
                delay *= 2.0
            else:
                raise err
        except urllib.error.URLError as err:
            if attempt < max_retries:
                jitter = random.uniform(0.1, 0.5)
                sleep_time = delay + jitter
                sys.stderr.write(f"URL error on attempt {attempt}/{max_retries}: {err}. Backing off {sleep_time:.2f}s...\n")
                time.sleep(sleep_time)
                delay *= 2.0
            else:
                raise err


# Bump when segmentation changes shape, so cached plans built by the old rules are
# not served back. Without this, re-planning the same script returns the stale plan
# and a segmentation fix looks like it did nothing.
PLANNER_VERSION = 2


def _get_planning_cache_key(text: str, title: str, voice: str, visual_style: str, ai_guideline: str, voice_dialect: str, narrative_tone: str, speaker_mode: str,
                            series_slug: str = "", prompt_recipe: str = "") -> str:
    """
    The key for a cached plan.

    The niche and its prompt recipe belong in here. Without them, editing the
    recipe and re-planning the same script returned the plan the old recipe
    produced - the whole point of the feature, silently doing nothing. The same
    was true of the niche itself: planning one script under two niches gave one
    answer.

    The recipe is hashed rather than concatenated because it is a document, not
    a setting - the owner's runs to tens of kilobytes.
    """
    recipe_fingerprint = hashlib.sha256((prompt_recipe or "").encode("utf-8")).hexdigest()[:16]
    raw = (f"v{PLANNER_VERSION}:{text}:{title}:{voice}:{visual_style}:{ai_guideline}:"
           f"{voice_dialect}:{narrative_tone}:{speaker_mode}:{series_slug or ''}:{recipe_fingerprint}")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _get_cached_plan(cache_key: str) -> dict | None:
    cache_path = os.path.join(CACHE_DIR, f"planning_{cache_key}.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def _save_cached_plan(cache_key: str, plan_data: dict):
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, f"planning_{cache_key}.json")
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(plan_data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

from pipeline.llm.factory import get_llm_provider
from pipeline.llm.interface import BaseLLMProvider
from pipeline.library import get_series_config, validate_series_pack

BATCH_PLANNING_SYSTEM_PROMPT = """You are S2V's visual director and shot planner.
You receive a batch of narration segments from a video script.
Your job is to propose B-roll shot queries, shot counts, and voice steering per segment.

STRICT CONSTRAINTS:
1. Do NOT rewrite, alter, or regenerate narration text. Narration is handled externally.
2. For each segment, output 1-3 shot queries describing specific, historically/visually accurate B-roll visuals.
3. Keep shot queries concise and visually descriptive (5-12 words).
"""

BATCH_PLANNING_SCHEMA = {
    "type": "object",
    "properties": {
        "batch_results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "segment_id": {"type": "integer"},
                    "voice_steering": {"type": "string"},
                    "shots": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string"},
                                "visual_description": {"type": "string"},
                                "source": {"type": "string", "enum": ["library", "generate", "pin"]}
                            },
                            "required": ["query"]
                        }
                    }
                },
                "required": ["segment_id", "shots"]
            }
        }
    },
    "required": ["batch_results"]
}


def build_script_with_ai(
    text: str,
    title: str = "My Video",
    voice: str = "google:en-US-Neural2-D",
    output_filename: str = "",
    visual_style: str = "vintage_documentary",
    series_slug: str = "islamic_history",
    ai_guideline: str = "",
    voice_dialect: str = "",
    narrative_tone: str = "",
    speaker_mode: str = "single",
    llm_provider: Optional[BaseLLMProvider] = None,
    batch_size: int = 6
) -> dict:
    """
    Builds an S2V v2 script JSON using chunked LLM planning.

    Strategy:
    1. Splits input text into narration segments in Python (zero LLM calls).
    2. Narration strings are COPIED VERBATIM into the JSON.
    3. Calls LLM provider per batch of 5-8 segments to plan shot queries.
    4. Failed batch retries that batch alone.
    """
    text_clean = text.strip()
    if not text_clean:
        return build_script("", title, voice, visual_style)

    # 1. Split script in Python — zero LLM calls
    segments_narration = split_into_segments(text_clean)
    if not segments_narration:
        return build_script(text_clean, title, voice, visual_style)

    # 2. Resolve series pack config defaults
    series_cfg = get_series_config(series_slug=series_slug, project_title=title)
    pack_voice = series_cfg.get("voice", {})
    resolved_voice = voice or pack_voice.get("id", "google:en-US-Neural2-D")

    # 3. Check planning cache (only if default provider is used)
    cache_key = _get_planning_cache_key(
        text_clean, title, resolved_voice, visual_style, ai_guideline, voice_dialect,
        narrative_tone, speaker_mode,
        series_slug=series_slug,
        prompt_recipe=series_cfg.get("prompt_recipe") or "",
    )
    if llm_provider is None:
        cached_plan = _get_cached_plan(cache_key)
        if cached_plan:
            return cached_plan

    # 4. Check if LLM planning is enabled (defaults to False).
    # If disabled and no explicit provider was injected, use rule-based planning.
    from pipeline.library import _setting
    llm_planning_enabled = _setting("llm_planning_enabled", False)
    if llm_provider is None and not llm_planning_enabled:
        total_segments = len(segments_narration)
        planned_segments = []
        for i, seg_text in enumerate(segments_narration):
            seg_id = i + 1
            shots_list = [{
                "shot_id": f"{seg_id}a",
                "duration": None,
                "source": "library",
                "query": extract_keyword(seg_text),
                "min_score": 0.26,
                "motion": {
                    "kind": "ken_burns",
                    "effect": KEN_BURNS_CYCLE[seg_id % len(KEN_BURNS_CYCLE)]
                },
                "treatment": {
                    "filter": series_cfg.get("grade", "none"),
                    "grade": None
                }
            }]
            planned_segments.append({
                "segment_id": seg_id,
                "type": "hook" if seg_id == 1 else ("conclusion" if seg_id == total_segments else "body"),
                "narration": seg_text,
                "voice_steering": None,
                "shots": shots_list
            })

        safe_name = sanitize_output_filename(output_filename or title)
        result = {
            "project": {
                "title": title.strip() or "My Video",
                "output_filename": safe_name,
                "voice": resolved_voice,
                "voice_rate": "+0%",
                "voice_pitch": "+0Hz",
                "background_music": None,
                "visual_style": visual_style.strip(),
                "series_slug": series_slug,
                "ai_guideline": ai_guideline,
                "voice_dialect": voice_dialect,
                "narrative_tone": narrative_tone,
                "speaker_mode": speaker_mode
            },
            "segments": planned_segments
        }
        return result

    # 5. Resolve LLM provider
    provider = llm_provider or get_llm_provider()

    # Stable system prompt prefix for prompt caching
    recipe = (series_cfg.get("prompt_recipe") or "").strip()
    if recipe:
        system_prefix = f"""{recipe}

RETRIEVAL QUERY REQUIREMENT:
For each shot, in addition to visual_description, you must always provide a concise 'query' of 5-12 words summarizing the core visual subject for library retrieval and file matching.
"""
    else:
        system_prefix = f"""{BATCH_PLANNING_SYSTEM_PROMPT}

SERIES PACK CONSTRAINTS ({series_slug}):
World Anchor: {series_cfg.get('world_anchor', '')}
Style Instructions: {series_cfg.get('style_block', '')}
Negative Constraints: {series_cfg.get('negative_block', '')}
"""

    total_segments = len(segments_narration)
    planned_segments = []
    
    # 5. Process in batches of 5-8 segments
    for start_idx in range(0, total_segments, batch_size):
        end_idx = min(start_idx + batch_size, total_segments)
        batch_narrations = segments_narration[start_idx:end_idx]
        
        batch_input = [
            {
                "segment_id": start_idx + i + 1,
                "narration": seg_text
            }
            for i, seg_text in enumerate(batch_narrations)
        ]

        user_payload = json.dumps({"segments": batch_input}, ensure_ascii=False)

        # Batch execution with isolated retry
        batch_data = None
        for attempt in range(1, 4):
            try:
                batch_data = provider.complete(
                    system=system_prefix,
                    user=user_payload,
                    json_schema=BATCH_PLANNING_SCHEMA,
                    max_tokens=2048
                )
                if batch_data and "batch_results" in batch_data:
                    break
            except Exception as e:
                # Auth, billing and not-found are permanent — retrying them just makes
                # the user wait through three backoffs before the same failure. An
                # exhausted API key showed up as three rounds of "402 Payment Required"
                # and looked like the app had hung.
                permanent = any(code in str(e) for code in ("401", "402", "403", "404"))
                sys.stderr.write(
                    f"LLM batch planning error on segments {start_idx+1}-{end_idx} "
                    f"(attempt {attempt}/3): {e}\n"
                )
                if permanent:
                    sys.stderr.write(
                        "  Permanent provider error — not retrying. "
                        "Falling back to keyword-based planning; check your API key and credit.\n"
                    )
                    break
                time.sleep(1.0 * attempt)

        # Parse batch results or fall back to rule-based defaults for this batch
        results_map = {}
        if batch_data and isinstance(batch_data.get("batch_results"), list):
            for res in batch_data["batch_results"]:
                results_map[res.get("segment_id")] = res

        for i, seg_text in enumerate(batch_narrations):
            seg_id = start_idx + i + 1
            res = results_map.get(seg_id, {})
            
            shots_list = []
            res_shots = res.get("shots", [])
            if res_shots and isinstance(res_shots, list):
                for s_idx, s_obj in enumerate(res_shots):
                    query_str = s_obj.get("query", "").strip() or extract_keyword(seg_text)
                    vdesc_str = (s_obj.get("visual_description") or "").strip()
                    shot_item = {
                        "shot_id": f"{seg_id}{chr(97 + s_idx)}",
                        "duration": None,
                        "source": s_obj.get("source", "library"),
                        "query": query_str,
                        "min_score": 0.26,
                        "motion": {
                            "kind": "ken_burns",
                            "effect": KEN_BURNS_CYCLE[(seg_id + s_idx) % len(KEN_BURNS_CYCLE)]
                        },
                        "treatment": {
                            "filter": series_cfg.get("grade", "none"),
                            "grade": None
                        }
                    }
                    if vdesc_str:
                        shot_item["visual_description"] = vdesc_str
                    shots_list.append(shot_item)
            
            if not shots_list:
                shots_list.append({
                    "shot_id": f"{seg_id}a",
                    "duration": None,
                    "source": "library",
                    "query": extract_keyword(seg_text),
                    "min_score": 0.26,
                    "motion": {
                        "kind": "ken_burns",
                        "effect": KEN_BURNS_CYCLE[seg_id % len(KEN_BURNS_CYCLE)]
                    },
                    "treatment": {
                        "filter": series_cfg.get("grade", "none"),
                        "grade": None
                    }
                })

            planned_segments.append({
                "segment_id": seg_id,
                "type": "hook" if seg_id == 1 else ("conclusion" if seg_id == total_segments else "body"),
                "narration": seg_text,  # VERBATIM COPY FROM INPUT SPLIT
                "voice": None,
                "voice_steering": res.get("voice_steering", ""),
                "shots": shots_list,
                "text_overlay": None,
                "transition_in": "fade" if seg_id == 1 else "cut",
                "transition_out": "fade" if seg_id == total_segments else "cut",
                "sfx": []
            })

    # Assemble full script
    final_script = {
        "schema_version": 2,
        "project": {
            "title": title.strip() or "My Video",
            "series_slug": series_slug,
            # The user's chosen filename wins; fall back to the title only when none was given.
            "output_filename": sanitize_output_filename(output_filename or title),
            "aspect_ratio": "16:9",
            "resolution": "1920x1080",
            "fps": 30,
            "voice": resolved_voice,
            "voice_rate": "+0%",
            "voice_pitch": "+0Hz",
            "voice_dialect": voice_dialect,
            "narrative_tone": narrative_tone or series_cfg.get("voice", {}).get("tone", "Dramatic Documentary"),
            "speaker_mode": speaker_mode,
            "captions": {"enabled": True, "source": "tts_timings"},
            "background_music": None,
            "music_volume_db": -20,
            "visual_style": visual_style,
            # The pack's world_anchor is deliberately NOT copied here. An anchor
            # stored on the project is honoured over the pack's, so freezing it
            # at parse time meant the niche a script was first planned under
            # followed it forever - every later niche still demanded seventh
            # century Arabia. The pack supplies it live at prompt time instead;
            # this key is now reserved for a genuine override typed by the user.
            "character_bible": {},
            "budget": {"max_generated_clips": 0, "max_spend_usd": 0.0}
        },
        "segments": planned_segments
    }

    _save_cached_plan(cache_key, final_script)
    return final_script


def build_script_with_deepseek_and_gemini(
    text: str,
    title: str = "My Video",
    voice: str = "google:en-US-Neural2-D",
    output_filename: str = "video.mp4",
    visual_style: str = "",
    google_api_key: str = "",
    deepseek_api_key: str = "",
    ai_guideline: str = "",
    deepseek_model: str = "deepseek-chat",
    voice_dialect: str = "",
    narrative_tone: str = "",
    speaker_mode: str = "single",
    series_slug: str = "islamic_history"
) -> dict:
    """
    Legacy wrapper routing directly to chunked LLM provider seam.
    """
    return build_script_with_ai(
        text=text,
        title=title,
        voice=voice,
        output_filename=output_filename,
        visual_style=visual_style,
        series_slug=series_slug,
        ai_guideline=ai_guideline,
        voice_dialect=voice_dialect,
        narrative_tone=narrative_tone,
        speaker_mode=speaker_mode
    )
