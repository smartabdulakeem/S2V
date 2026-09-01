"""
Camera motion, tested with the shape the app actually writes.

The schema splits motion into `kind` (ken_burns | static | generative) and
`effect` (zoom_in | zoom_out | pan_left | pan_right). The compositor compared
`kind` against the effect names, so every Ken Burns shot rendered as a fixed
frame — every film was a slideshow.

The earlier test suite missed it entirely because it passed {"kind": "zoom_in"},
which nothing in the app produces. These tests use real schema shapes, and assert
on rendered pixels rather than on the filtergraph string.
"""

import glob
import os
import subprocess

import numpy as np
import pytest
from PIL import Image

from pipeline.composer import resolve_motion_effect, render_shot_clip, _find_ffmpeg


# ── The resolver ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("motion,expected", [
    ({"kind": "ken_burns", "effect": "zoom_in"}, "zoom_in"),
    ({"kind": "ken_burns", "effect": "zoom_out"}, "zoom_out"),
    ({"kind": "ken_burns", "effect": "pan_left"}, "pan_left"),
    ({"kind": "ken_burns", "effect": "pan_right"}, "pan_right"),
    ({"kind": "static"}, "static"),
    ({"kind": "generative", "effect": "zoom_in"}, "static"),
    ({"kind": "ken_burns"}, "zoom_in"),            # effect omitted -> sane default
    ({"kind": "ken_burns", "effect": "nonsense"}, "zoom_in"),
    ({"kind": "zoom_in"}, "zoom_in"),              # tolerated legacy shape
    ("pan_left", "pan_left"),                      # schema v1 string
    (None, "zoom_in"),
])
def test_resolve_motion_effect(motion, expected):
    assert resolve_motion_effect(motion) == expected


def test_the_real_schema_shape_is_not_treated_as_static():
    """The exact regression: kind='ken_burns' must not mean 'no movement'."""
    assert resolve_motion_effect({"kind": "ken_burns", "effect": "pan_right"}) != "static"


# ── Rendered pixels ───────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def source_image(tmp_path_factory):
    """A detailed image — a flat one would show no movement however it panned."""
    p = tmp_path_factory.mktemp("motion") / "src.jpg"
    img = Image.new("RGB", (1600, 900))
    px = img.load()
    for x in range(1600):
        for y in range(900):
            px[x, y] = ((x * 3) % 256, (y * 7) % 256, ((x ^ y) * 5) % 256)
    img.save(p)
    return str(p)


def _frame(video, t, out_png):
    subprocess.run([_find_ffmpeg(), "-y", "-ss", str(t), "-i", video, "-frames:v", "1", out_png],
                   capture_output=True, text=True)
    return out_png


def _difference(a, b):
    ia, ib = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
    return float(np.mean(np.abs(np.asarray(ia, float) - np.asarray(ib, float))))


@pytest.mark.parametrize("effect", ["zoom_in", "zoom_out", "pan_left", "pan_right"])
def test_each_effect_actually_moves_the_picture(effect, source_image, tmp_path):
    shot = {
        "shot_id": "1a",
        "motion": {"kind": "ken_burns", "effect": effect},
        "treatment": {"filter": "none"},
    }
    out = str(tmp_path / f"{effect}.mp4")
    render_shot_clip(shot=shot, visual_path=source_image, duration=3.0,
                     width=640, height=360, output_mp4_path=out, fps=24)

    first = _frame(out, 0.2, str(tmp_path / f"{effect}_a.png"))
    last = _frame(out, 2.6, str(tmp_path / f"{effect}_b.png"))

    assert _difference(first, last) > 1.0, f"{effect} rendered as a still frame"


def test_static_really_is_static(source_image, tmp_path):
    shot = {"shot_id": "1a", "motion": {"kind": "static"}, "treatment": {"filter": "none"}}
    out = str(tmp_path / "static.mp4")
    render_shot_clip(shot=shot, visual_path=source_image, duration=2.0,
                     width=640, height=360, output_mp4_path=out, fps=24)

    a = _frame(out, 0.2, str(tmp_path / "s_a.png"))
    b = _frame(out, 1.6, str(tmp_path / "s_b.png"))
    assert _difference(a, b) < 0.5


def test_a_picture_held_for_minutes_barely_moves():
    """
    The owner's concern, in his words: "This may affect the image editing, I
    mean the moving, zooming in, zooming out ... but I know there's always a
    way around that where we're not zooming that much."

    Travel is clamped, so an image held ten minutes travels no further than one
    held five seconds — the same distance over 120x the time, which is 120x
    slower. Nothing needs adding; this is here so nothing removes it.
    """
    from pipeline.motion import travel_for, MOTION_STYLES

    ceiling = MOTION_STYLES["ken_burns"]["max"]

    assert travel_for("ken_burns", 600.0) == ceiling
    assert travel_for("ken_burns", 75.0) == ceiling
    # Sample at 3.0s: rate 0.05 * 3.0s = 0.15 < max 0.24 (at 5.0s rate*5.0=0.25 hits max clamp)
    assert travel_for("ken_burns", 3.0) < ceiling


def test_the_static_style_still_holds_perfectly_still_at_any_length():
    from pipeline.motion import travel_for

    assert travel_for("static", 600.0) == 0.0
    assert travel_for("static", 8.0) == 0.0