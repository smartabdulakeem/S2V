"""
Plain-text script parser.
Splits a raw script into segments, extracts image search keywords automatically,
and returns a dict matching the S2V JSON schema — ready to pass straight to the
validator and orchestrator.
"""

import re

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

def split_into_segments(text: str, max_words: int = 45) -> list:
    """
    Split a plain-text script into a list of narration strings.

    Strategy
    --------
    1. If the text has clear paragraph breaks (blank lines), use those as scene
       boundaries — but merge any paragraph under 8 words into the next one so
       we don't create micro-clips.
    2. If the text is one big block, split by sentences and group every
       ~max_words words into a segment.
    """
    text = text.strip()
    if not text:
        return []

    # ── Paragraph split ──
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]

    if len(paragraphs) >= 2:
        merged = []
        buf = ""
        for p in paragraphs:
            if not buf:
                buf = p
            else:
                if len(buf.split()) < 8:
                    # too short — merge forward
                    buf = buf + " " + p
                else:
                    merged.append(buf)
                    buf = p
        if buf:
            merged.append(buf)
        return merged

    # ── Sentence-group split ──
    # Split on . ! ? but keep the punctuation
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
    max_words: int = 45,
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
        },
        "segments": segments,
    }
