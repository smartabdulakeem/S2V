"""
How a script is *read*, as opposed to what it says.

The Tone dropdown used to be three fixed strings that reached only the LLM
planner: they changed the visual keywords it invented and nothing about the
audio. A motivational speech and a war documentary came out of Supertonic
sounding identical.

A delivery profile is the part a text-to-speech engine can actually act on:

  speed          how fast the words come
  silence        the gap left at a sentence end, in seconds
  block_silence  the gap left between paragraphs, in seconds

Those three carry most of what separates a grave documentary from a
motivational speech. A motivational read is not faster - it is slower, with
long holds between short blocks. A news read is the opposite.

Supertonic takes `silence_duration` natively and chunks the text itself.
Kokoro has no such parameter, so `split_blocks` and `join_with_silence` here
stitch real silence between separately synthesised blocks. Neither engine
supports SSML, so this is the whole available vocabulary - which is why the
profiles are three numbers rather than a markup language.
"""

import re

#: Every tone the board can offer. `label` is what the dropdown shows,
#: `steering` is the sentence handed to the LLM planner, which is what the
#: three original tone strings were doing and still need to do.
DELIVERY_PROFILES = {
    "grave_documentary": {
        "label": "Grave documentary",
        "speed": 0.94,
        "silence": 0.42,
        "block_silence": 0.85,
        "steering": "Grave, measured documentary narration. Unhurried, weighty, "
                    "letting hard facts land without embellishment.",
    },
    "warm_storytelling": {
        "label": "Warm storytelling",
        "speed": 1.00,
        "silence": 0.34,
        "block_silence": 0.70,
        "steering": "Warm, companionable storytelling. Natural rhythm, as though "
                    "recounting something remembered rather than reciting it.",
    },
    "reverent_measured": {
        "label": "Reverent and measured",
        "speed": 0.90,
        "silence": 0.50,
        "block_silence": 1.00,
        "steering": "Reverent, careful narration. Slow and respectful, every name "
                    "and date given its full weight.",
    },
    "urgent_news": {
        "label": "Urgent news",
        "speed": 1.12,
        "silence": 0.16,
        "block_silence": 0.32,
        "steering": "Urgent broadcast-news delivery. Brisk, clipped, forward-leaning, "
                    "very little air between sentences.",
    },
    "motivational_punch": {
        "label": "Motivational — short blocks, long holds",
        "speed": 0.96,
        "silence": 0.60,
        "block_silence": 1.60,
        "steering": "Motivational speech. Short declarative blocks separated by long "
                    "silences. Each line lands on its own and is allowed to sit.",
    },
    "dramatic_reveal": {
        "label": "Dramatic reveal",
        "speed": 0.95,
        "silence": 0.55,
        "block_silence": 1.20,
        "steering": "Suspenseful narration that withholds. Deliberate pacing with long "
                    "holds before a turn in the story.",
    },
    "wonder_awe": {
        "label": "Wonder and scale",
        "speed": 0.92,
        "silence": 0.46,
        "block_silence": 0.95,
        "steering": "Quiet awe at scale and beauty. Spacious, unhurried, letting the "
                    "images breathe.",
    },
    "conversational_explainer": {
        "label": "Conversational explainer",
        "speed": 1.05,
        "silence": 0.24,
        "block_silence": 0.48,
        "steering": "Clear conversational explanation. Friendly and efficient, keeping "
                    "momentum without rushing.",
    },
}

#: The order the board offers them in, per niche. The first entry is the default
#: for that niche. Tones not listed still appear, below a separator.
NICHE_TONES = {
    "biography": ["warm_storytelling", "reverent_measured", "grave_documentary"],
    "business_money": ["conversational_explainer", "urgent_news", "warm_storytelling"],
    "default": ["warm_storytelling", "conversational_explainer", "grave_documentary"],
    "islamic_history": ["reverent_measured", "grave_documentary", "warm_storytelling"],
    "motivational": ["motivational_punch", "warm_storytelling", "conversational_explainer"],
    "mythology_folklore": ["dramatic_reveal", "warm_storytelling", "grave_documentary"],
    "nature_wildlife": ["wonder_awe", "warm_storytelling", "conversational_explainer"],
    "space_science": ["wonder_awe", "conversational_explainer", "grave_documentary"],
    "true_crime": ["grave_documentary", "dramatic_reveal", "urgent_news"],
    "world_military_history": ["grave_documentary", "urgent_news", "reverent_measured"],
}

DEFAULT_TONE = "warm_storytelling"

#: The three strings the dropdown used to hold, so projects saved before this
#: existed still resolve to something sensible instead of the default.
_LEGACY_TONES = {
    "grave documentary": "grave_documentary",
    "warm storytelling": "warm_storytelling",
    "urgent": "urgent_news",
}


def resolve_tone(tone: str) -> str:
    """The profile key for whatever the project has stored in `narrative_tone`."""
    if not tone:
        return DEFAULT_TONE
    key = str(tone).strip()
    if key in DELIVERY_PROFILES:
        return key
    lowered = key.lower()
    if lowered in _LEGACY_TONES:
        return _LEGACY_TONES[lowered]
    # A label rather than a key ("Urgent news")
    for pkey, prof in DELIVERY_PROFILES.items():
        if prof["label"].lower() == lowered:
            return pkey
    return DEFAULT_TONE


def delivery_for(tone: str) -> dict:
    """The speed and silences for a tone. Always returns a usable profile."""
    return DELIVERY_PROFILES[resolve_tone(tone)]


def tones_for_niche(series_slug: str = None) -> list:
    """
    Every tone, recommended ones first, each flagged for the dropdown.

    Nothing is hidden: a motivational read on a wildlife film is a legitimate
    choice, it is just not the one offered first.
    """
    recommended = NICHE_TONES.get(series_slug or "", NICHE_TONES["default"])
    ordered = [k for k in recommended if k in DELIVERY_PROFILES]
    ordered += [k for k in DELIVERY_PROFILES if k not in ordered]
    return [
        {
            "key": key,
            "label": DELIVERY_PROFILES[key]["label"],
            "recommended": key in recommended,
            "steering": DELIVERY_PROFILES[key]["steering"],
        }
        for key in ordered
    ]


def steering_for(tone: str) -> str:
    """The sentence handed to the LLM planner for this tone."""
    return delivery_for(tone)["steering"]


def apply_rate(base_speed: float, voice_rate: str) -> float:
    """
    Fold the user's own rate adjustment into the tone's speed.

    The rate box holds strings like "+10%" and "-5%", and it has always been a
    relative nudge, so it stays relative to whatever the tone chose.
    """
    speed = float(base_speed)
    if voice_rate:
        text = str(voice_rate).strip()
        if text.endswith("%"):
            try:
                speed = speed + (float(text[:-1]) / 100.0)
            except ValueError:
                pass
    return round(max(0.7, min(2.0, speed)), 3)


#: A blank line, or a single newline, is the author saying "hold here".
_BLOCK_SPLIT = re.compile(r"\n\s*\n|\n")
#: Sentence ends, keeping the punctuation with the sentence it closes.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def split_blocks(text: str) -> list:
    """
    Break narration into the units a pause can sit between.

    Returns a list of (chunk, gap_kind) where gap_kind is "sentence" or
    "block". The last chunk carries no trailing gap - that is the caller's to
    decide, and a segment should not end on dead air.
    """
    if not text or not text.strip():
        return []

    out = []
    blocks = [b.strip() for b in _BLOCK_SPLIT.split(text) if b.strip()]
    for b_i, block in enumerate(blocks):
        sentences = [s.strip() for s in _SENTENCE_SPLIT.split(block) if s.strip()]
        for s_i, sentence in enumerate(sentences):
            last_in_block = s_i == len(sentences) - 1
            last_overall = last_in_block and b_i == len(blocks) - 1
            if last_overall:
                gap = None
            elif last_in_block:
                gap = "block"
            else:
                gap = "sentence"
            out.append((sentence, gap))
    return out


def join_with_silence(pieces, sample_rate: int, profile: dict):
    """
    Concatenate synthesised audio with the profile's silences between pieces.

    `pieces` is a list of (samples, gap_kind) as produced alongside
    split_blocks. Used by the Kokoro path, which has no silence parameter of
    its own; Supertonic takes `silence_duration` natively and does not need this.
    """
    import numpy as np

    chunks = []
    for samples, gap in pieces:
        if samples is None or len(samples) == 0:
            continue
        chunks.append(np.asarray(samples))
        if gap:
            seconds = profile["block_silence"] if gap == "block" else profile["silence"]
            pad = int(max(0.0, float(seconds)) * sample_rate)
            if pad:
                chunks.append(np.zeros(pad, dtype=np.asarray(samples).dtype))
    if not chunks:
        return None
    return np.concatenate(chunks)
