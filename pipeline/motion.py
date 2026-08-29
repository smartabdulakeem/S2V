"""
How the camera moves, as opposed to what it points at.

`MOTION_EFFECTS` in the compositor has always held four moves, and
`resolve_motion_effect` has always picked one. What was missing was any way for
the user to say how much movement they wanted, and any policy about which move
follows which — so a film ran one move at one strength from the first shot to
the last, whatever it was about.

A motion style is the part the compositor can act on:

  rate       how far the frame travels per second of shot, as a fraction
  min/max    the floor and ceiling on that travel, however long the shot runs
  pad        how much larger than the output the source is scaled before the
             crop moves across it
  effects    the moves this style is allowed to use, in the order it cycles them

The travel has to scale with duration or the *rate* changes with every cut: a
flat 15% reads as a push over 3 seconds and as a still frame over 19. The clamps
then stop a very short shot from lurching and a very long one from crawling.

`pad` is not a free parameter. zoompan crops out of the padded frame, so a zoom
of 1 + travel must stay inside it — travel of 0.34 needs the source at 1.36x, or
the crop walks off the edge of the picture.

The effect cycle is what stops a film repeating itself. It alternates zoom and
pan, and it is applied across the whole script rather than per segment, so the
last shot of one segment and the first of the next do not land on the same move.
"""

#: Every motion style the board can offer. `label` is what the dropdown shows,
#: `description` is its hover text.
MOTION_STYLES = {
    "static": {
        "label": "Static",
        "description": "No camera move at all. Every shot is a held frame.",
        "rate": 0.0,
        "min": 0.0,
        "max": 0.0,
        "pad": 1.25,
        "effects": (),
    },
    "gentle_drift": {
        "label": "Gentle drift",
        "description": "Barely-there movement. The frame breathes without pulling attention.",
        "rate": 0.020,
        "min": 0.03,
        "max": 0.10,
        "pad": 1.25,
        "effects": ("zoom_in", "pan_left", "zoom_out", "pan_right"),
    },
    "ken_burns": {
        "label": "Ken Burns",
        "description": "The documentary standard: a steady push or drift across every shot.",
        "rate": 0.050,
        "min": 0.06,
        "max": 0.24,
        "pad": 1.25,
        "effects": ("zoom_in", "pan_left", "zoom_out", "pan_right"),
    },
    "dynamic": {
        "label": "Dynamic",
        "description": "Strong, fast moves. Suits short cuts and urgent material.",
        "rate": 0.090,
        "min": 0.12,
        "max": 0.34,
        "pad": 1.36,
        "effects": ("zoom_in", "pan_left", "zoom_out", "pan_right"),
    },
}

DEFAULT_MOTION_STYLE = "ken_burns"

#: What projects planned before this existed resolve to. Their shots already
#: carry Ken Burns effects and rendered at the old flat 0.05/s with a 0.06-0.24
#: clamp, which is exactly the ken_burns profile — so an old project renders
#: identically rather than quietly changing.
_LEGACY_STYLES = {
    "": DEFAULT_MOTION_STYLE,
    "none": "static",
    "ken burns": "ken_burns",
    "kenburns": "ken_burns",
}


def resolve_motion_style(style) -> str:
    """The style key for whatever the project has stored in `motion_style`."""
    if not style:
        return DEFAULT_MOTION_STYLE
    key = str(style).strip()
    if key in MOTION_STYLES:
        return key
    lowered = key.lower()
    if lowered in _LEGACY_STYLES:
        return _LEGACY_STYLES[lowered]
    for skey, prof in MOTION_STYLES.items():
        if prof["label"].lower() == lowered:
            return skey
    return DEFAULT_MOTION_STYLE


def motion_style_for(style) -> dict:
    """The rate, clamps, padding and effect cycle for a style."""
    return MOTION_STYLES[resolve_motion_style(style)]


def styles_for_ui() -> list:
    """Every style, in the order the dropdown should offer them."""
    return [
        {
            "key": key,
            "label": prof["label"],
            "description": prof["description"],
            "default": key == DEFAULT_MOTION_STYLE,
        }
        for key, prof in MOTION_STYLES.items()
    ]


def travel_for(style, duration: float) -> float:
    """
    How far the frame travels over a shot of this length, as a fraction.

    Zero for the static style, which is what makes it hold still.
    """
    prof = motion_style_for(style)
    if prof["rate"] <= 0:
        return 0.0
    try:
        seconds = max(0.0, float(duration))
    except (TypeError, ValueError):
        seconds = 0.0
    return round(max(prof["min"], min(prof["max"], prof["rate"] * seconds)), 4)


def pad_factor_for(style) -> float:
    """How much larger than the output the source is scaled before cropping."""
    return motion_style_for(style)["pad"]


def assign_effects(script_data: dict, style=None) -> int:
    """
    Give every shot in the script its camera move, in one pass over the film.

    Returns the number of shots touched.

    The cycle runs across segment boundaries deliberately. Assigning per segment
    means every segment opens on the same move, and at one shot per segment that
    is no variety at all — it is the same film again.

    The static style writes `{"kind": "static"}`, which is the shape
    `resolve_motion_effect` reads as "hold this frame"; the other styles write
    the `ken_burns` kind with an effect, which is what the validator expects.
    """
    prof = motion_style_for(style)
    effects = prof["effects"]
    touched = 0
    position = 0

    for seg in script_data.get("segments", []) or []:
        for shot in seg.get("shots") or []:
            if not isinstance(shot, dict):
                continue
            if not effects:
                shot["motion"] = {"kind": "static"}
            else:
                shot["motion"] = {
                    "kind": "ken_burns",
                    "effect": effects[position % len(effects)],
                }
                position += 1
            touched += 1

    return touched


def style_of(script_data: dict) -> str:
    """The style a planned script was built with, for the renderer to honour."""
    project = (script_data or {}).get("project") or {}
    return resolve_motion_style(project.get("motion_style"))
