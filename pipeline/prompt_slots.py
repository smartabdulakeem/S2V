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
    (r"\b(aerial|overhead|bird's eye)\b", "high aerial shot looking down"),
    (r"\b(wide|establishing|vista|panorama)\b",
     "wide establishing shot, subject clearly readable against the setting"),
    (r"\b(close[- ]?up|macro|extreme close|tight (?:shot|crop|framing)|detail (?:of|shot))\b",
     "tight detail shot, shallow plane of focus"),
]

#: Used when the shot names no framing of its own.
#:
#: This was one phrase — "wide establishing shot, subject small in the frame" —
#: applied to nearly every shot in every film, because most shot text names no
#: framing. Two things came of it. Every picture sat the same distance from its
#: subject, so a 47-image film had one camera position. And every picture was
#: told to make its subject *small*, which is a direct instruction to the image
#: model to fill the frame with background. Detail near the camera is what reads
#: as expensive; a small subject reads as cheap however good the generator is.
#:
#: The cycle varies distance across a film instead. The caller passes the shot's
#: position; without one it takes the first entry, which is the safest single
#: choice rather than the widest.
DEFAULT_FRAMING_CYCLE = (
    "cinematic medium shot, subject filling much of the frame",
    "close shot, subject large in the frame, background falling away",
    "wide establishing shot, subject clearly readable against the setting",
    "three-quarter shot, subject off centre, depth receding behind",
)

DEFAULT_FRAMING = DEFAULT_FRAMING_CYCLE[0]


def default_framing_for(position=None) -> str:
    """
    The framing for a shot at this position in the film.

    Position is the shot's index across the whole script, so the variety
    crosses segment boundaries rather than resetting at each one.
    """
    if position is None:
        return DEFAULT_FRAMING
    try:
        return DEFAULT_FRAMING_CYCLE[int(position) % len(DEFAULT_FRAMING_CYCLE)]
    except (TypeError, ValueError):
        return DEFAULT_FRAMING

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
    (r"\b(snow|snowfall|frost|frostbite|glacier|permafrost)\b"
     r"|\bice(?:[- ](?:sheet|field|floe))?\b"
     r"|\bfrozen (?:ground|earth|river|lake|sea|mud|field|road)\b",
     "snow and frozen ground, breath visible in the cold"),
    (r"\b(rubble|ruins|debris|wreckage)\b",
     "broken rubble underfoot, dust settling between stones"),
]

#: What hangs in the air.
PROMPT_ATMOSPHERE = [
    (r"\b(dust|dusty|smoke|smoky|smouldering|ablaze|bonfire|wildfire)\b"
     r"|\bburning (?:village|city|town|building|ship|field|forest|wreck)\b",
     "hanging dust and smoke catching the light"),
    (r"\b(rain|storm|downpour|torrent)\b",
     "rain streaking the air, wet reflective surfaces"),
    (r"\b(mist|fog|haze)\b", "low mist clinging to the ground"),
]

#: Time of day expressed as light a camera would see.
PROMPT_LIGHT = [
    (r"\b(daybreak|first light|sunrise)\b|\bdawn\b(?! of\b)",
     "cold blue pre-dawn light, sun still below the ridge, long low shadows"),
    (r"\b(dusk|sunset|nightfall|evening)\b|\btwilight\b(?! of\b)",
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
