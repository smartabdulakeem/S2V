"""
Vocabulary tables for structured image prompts.

Each table is an ordered list of (regex, phrase) pairs. The first pattern that
matches the shot's text contributes its phrase to that slot; a slot that
matches nothing is left out of the prompt entirely rather than emitting filler.

These live in their own module because they are data the owner edits often,
and because pipeline/library.py is already long enough.
"""

import re

#: Camera distance and how the subject sits in the frame.
PROMPT_FRAMING = [
    (r"\b(close|detail|macro|tight)\b", "tight detail shot, shallow plane of focus"),
    (r"\b(aerial|overhead|bird's eye)\b", "high aerial shot looking down"),
    (r"\b(wide|establishing|vista|panorama)\b", "wide establishing shot, subject small in the frame"),
]

#: Used when the shot names no framing of its own.
DEFAULT_FRAMING = "wide establishing shot, subject small in the frame"

#: Whether the scene is moving or held.
PROMPT_MOTION = [
    (r"\b(rode|riding|rides|charge|charging|gallop|advance|advancing|march|marching|fled|fleeing|running)\b",
     "bodies and animals mid-movement, motion blur at the frame edges"),
    (r"\b(stood|standing|waiting|held|holding|watched|watching|silent|still)\b",
     "held still, weight settled, tension in the stance"),
]

#: What the ground underfoot looks like.
PROMPT_GROUND = [
    (r"\b(mire|mud|muddy|churned|flooded|marsh|swamp|bog)\b",
     "churned waterlogged ground, standing water breaking the surface"),
    (r"\b(dune|dunes|sand|desert|arid)\b",
     "wind-scoured sand, drifting grain across the foreground"),
    (r"\b(snow|ice|frozen|frost)\b",
     "snow and frozen ground, breath visible in the cold"),
    (r"\b(rubble|ruins|debris|wreckage)\b",
     "broken rubble underfoot, dust settling between stones"),
]

#: What hangs in the air.
PROMPT_ATMOSPHERE = [
    (r"\b(dust|smoke|smouldering|burning|fire|flame)\b",
     "hanging dust and smoke catching the light"),
    (r"\b(rain|storm|downpour|torrent)\b",
     "rain streaking the air, wet reflective surfaces"),
    (r"\b(mist|fog|haze)\b", "low mist clinging to the ground"),
]

#: Time of day expressed as light a camera would see.
PROMPT_LIGHT = [
    (r"\b(dawn|daybreak|first light|sunrise|before dawn)\b",
     "cold blue pre-dawn light, sun still below the ridge, long low shadows"),
    (r"\b(dusk|sunset|nightfall|evening|twilight)\b",
     "low golden dusk light, long raking shadows, warm highlights against cool shade"),
    (r"\b(night|midnight|moonlit|after dark|nocturnal)\b",
     "deep night, moonlight and torch flame the only sources, deep unlit shadow"),
    (r"\b(noon|midday|blazing sun|high sun)\b",
     "hard overhead midday sun, short black shadows, bleached highlights"),
]


def match_slot(table, text: str, default: str = None) -> str | None:
    """The phrase for the first pattern in `table` that `text` matches."""
    if not text:
        return default
    for pattern, phrase in table:
        if re.search(pattern, text, re.IGNORECASE):
            return phrase
    return default
