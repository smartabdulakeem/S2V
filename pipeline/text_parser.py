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
import re
import urllib.error
import urllib.request

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
KEN_BURNS_CYCLE = ["zoom_in", "pan_right", "zoom_out", "pan_left", "zoom_in", "zoom_out"]

# Transition cycle
TRANSITION_CYCLE = ["fade", "crossfade", "fade", "crossfade"]


# ── Sentence / paragraph splitter ──────────────────────────────────────────────

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
        return merged

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
        return merged

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

    # Sanitise output filename
    safe_name = re.sub(r'[^\w\-]', '_', output_filename.strip())
    safe_name = re.sub(r'_+', '_', safe_name).strip('_')
    if not safe_name:
        safe_name = "my_video"
    if not safe_name.lower().endswith('.mp4'):
        safe_name += '.mp4'

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
    "gemini-2.0-flash:generateContent?key={key}"
)

_SPLIT_PROMPT = """\
You are a video script editor. Your job is to split a narration script into \
individual scenes for a documentary-style YouTube video.

Rules:
1. NEVER rewrite, paraphrase, summarise, or omit any of the narrator's words. \
   Every word in the original script must appear in exactly one segment's \
   "narration" field, verbatim. Do not add filler sentences.
2. Split at natural narrative or topic breaks. Each segment should be \
   30-60 words (one clear idea or moment).
3. For each segment write a "b_roll_keyword": a specific 2-4 word visual \
   search term that describes what viewers should SEE on screen (not a quote \
   from the narration -- a concrete visual noun phrase).
4. If the user did not supply a visual_style, suggest one that fits the topic \
   (e.g. "Islamic golden age, warm cinematic tones, oil painting style").

Return ONLY a valid JSON object -- no markdown fences, no commentary -- in this \
exact shape:
{{
  "visual_style": "<suggested style or the user-supplied one unchanged>",
  "segments": [
    {{"narration": "...", "b_roll_keyword": "..."}},
    ...
  ]
}}

Script title: {title}
User-supplied visual_style (empty = please suggest): {visual_style}

Script to split:
{script}"""


def build_script_with_ai(
    text: str,
    title: str,
    voice: str,
    output_filename: str,
    visual_style: str = "",
    google_api_key: str = "",
) -> dict:
    """
    Use Gemini to intelligently split the script into scenes.

    Falls back to build_script() automatically if:
    - no google_api_key is provided
    - Gemini returns an invalid response
    - any network or parsing error occurs

    Returns the same dict structure as build_script().
    """
    if not google_api_key:
        return build_script(text, title, voice, output_filename, visual_style)

    prompt = _SPLIT_PROMPT.format(
        title=title.strip() or "My Video",
        visual_style=visual_style.strip(),
        script=text.strip(),
    )

    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 8192,
        },
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            _GEMINI_URL.format(key=google_api_key),
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read())

        raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()

        # Strip markdown fences if Gemini wrapped the JSON anyway
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```[a-z]*\n?", "", raw_text)
            raw_text = re.sub(r"\n?```$", "", raw_text.strip())

        parsed = json.loads(raw_text)
        ai_segments = parsed.get("segments", [])
        ai_style    = parsed.get("visual_style", visual_style).strip()

        if not ai_segments:
            raise ValueError("Gemini returned empty segments list")

        # Validate every segment has narration
        for s in ai_segments:
            if not s.get("narration", "").strip():
                raise ValueError("Gemini returned a segment with empty narration")

        # ── Build the full script dict from Gemini's output ────────────────────
        safe_name = re.sub(r'[^\w\-]', '_', output_filename.strip())
        safe_name = re.sub(r'_+', '_', safe_name).strip('_')
        if not safe_name:
            safe_name = "my_video"
        if not safe_name.lower().endswith('.mp4'):
            safe_name += '.mp4'

        total = len(ai_segments)
        segments = []

        for i, seg in enumerate(ai_segments):
            if i == 0:
                seg_type = "hook"
            elif i == total - 1:
                seg_type = "conclusion"
            else:
                seg_type = "body"

            narration = seg.get("narration", "").strip()
            keyword = seg.get("b_roll_keyword", "").strip()
            if not keyword:
                keyword = extract_keyword(narration)

            segments.append({
                "segment_id": i + 1,
                "type": seg_type,
                "narration": narration,
                "b_roll_keyword": keyword,
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
                "visual_style": ai_style or visual_style.strip(),
            },
            "segments": segments,
        }

    except Exception:
        # Any failure → fall back silently to rule-based splitter
        return build_script(text, title, voice, output_filename, visual_style)
