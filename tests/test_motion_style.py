"""
The motion style: how much the camera moves, and which move follows which.

`MOTION_EFFECTS` and `resolve_motion_effect` have always existed, so every shot
had a move. Nothing let the user say how *much* movement they wanted, and the
cycle was applied per segment — at one shot per segment that meant every segment
opened on the same move, which is the same film again.

These tests assert on rendered pixels where the claim is about movement, because
a filtergraph string that reads correctly can still produce a still frame.
"""

import os
import subprocess

import numpy as np
import pytest
from PIL import Image

from pipeline.composer import _get_shot_cache_key, render_shot_clip
from pipeline.ffmpeg_locate import find_ffmpeg
from pipeline.motion import (
    DEFAULT_MOTION_STYLE,
    MOTION_STYLES,
    assign_effects,
    pad_factor_for,
    resolve_motion_style,
    style_of,
    styles_for_ui,
    travel_for,
)
from pipeline.text_parser import apply_shot_rhythm, plan_image_budget


# ── Resolving a style ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    ("static", "static"),
    ("gentle_drift", "gentle_drift"),
    ("ken_burns", "ken_burns"),
    ("dynamic", "dynamic"),
    ("Gentle drift", "gentle_drift"),          # the label, not the key
    ("KEN_BURNS", "ken_burns"),
    ("none", "static"),
    ("", DEFAULT_MOTION_STYLE),
    (None, DEFAULT_MOTION_STYLE),
    ("nonsense", DEFAULT_MOTION_STYLE),
])
def test_resolve_motion_style(value, expected):
    assert resolve_motion_style(value) == expected


def test_every_style_is_offered_to_the_ui():
    keys = [s["key"] for s in styles_for_ui()]
    assert keys == list(MOTION_STYLES)
    assert sum(1 for s in styles_for_ui() if s["default"]) == 1


# ── Travel ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("duration", [1.0, 3.0, 4.8, 7.0, 12.0, 19.0, 45.0])
def test_ken_burns_still_travels_exactly_what_it_used_to(duration):
    """
    The old behaviour was a flat 0.05/s clamped to 0.06-0.24. Projects planned
    before the styles existed resolve to ken_burns and must render identically,
    or every film quietly changes under the owner.
    """
    assert travel_for("ken_burns", duration) == pytest.approx(max(0.06, min(0.24, 0.05 * duration)))


def test_static_does_not_travel_at_all():
    assert travel_for("static", 12.0) == 0.0


@pytest.mark.parametrize("duration", [3.0, 7.0, 19.0])
def test_the_styles_are_ordered_by_how_much_they_move(duration):
    gentle = travel_for("gentle_drift", duration)
    classic = travel_for("ken_burns", duration)
    strong = travel_for("dynamic", duration)
    assert 0 < gentle < classic < strong


def test_travel_stays_inside_its_clamps():
    for key, prof in MOTION_STYLES.items():
        for duration in (0.5, 2.0, 8.0, 60.0, 600.0):
            travel = travel_for(key, duration)
            assert prof["min"] <= travel <= prof["max"], key


def test_a_bad_duration_does_not_blow_up_the_render():
    assert travel_for("ken_burns", None) == MOTION_STYLES["ken_burns"]["min"]
    assert travel_for("ken_burns", -4) == MOTION_STYLES["ken_burns"]["min"]


def test_the_padding_can_hold_the_widest_move():
    """
    zoompan crops out of the padded frame. A zoom of 1 + travel has to stay
    inside it, or the crop walks off the edge of the picture.
    """
    for key, prof in MOTION_STYLES.items():
        assert pad_factor_for(key) >= 1.0 + prof["max"], key


# ── Dealing the moves out ─────────────────────────────────────────────────────

def _script(shots_per_segment, segments=4, style="ken_burns"):
    return {
        "project": {"motion_style": style},
        "segments": [
            {
                "segment_id": s + 1,
                "narration": "One sentence here. Then a second one. And a third to split on.",
                "shots": [
                    {"shot_id": f"{s + 1}{chr(97 + i)}", "query": "q", "source": "library"}
                    for i in range(shots_per_segment)
                ],
            }
            for s in range(segments)
        ],
    }


def _effects(script):
    return [
        (shot["motion"].get("effect") or shot["motion"]["kind"])
        for seg in script["segments"]
        for shot in seg["shots"]
    ]


def test_no_two_shots_in_a_row_share_a_move():
    script = _script(3)
    assert assign_effects(script, "ken_burns") == 12
    effects = _effects(script)
    for a, b in zip(effects, effects[1:]):
        assert a != b, "two shots in a row use the same camera move"


def test_the_cycle_crosses_segment_boundaries():
    """
    One shot per segment is the case the old per-segment cycle got wrong: index
    0 of every segment meant the same move every time.
    """
    script = _script(1, segments=6)
    assign_effects(script, "ken_burns")
    effects = _effects(script)
    assert len(set(effects)) > 1, "every segment opened on the same move"
    for a, b in zip(effects, effects[1:]):
        assert a != b


def test_every_move_gets_used_over_a_long_film():
    script = _script(2, segments=8)
    assign_effects(script, "dynamic")
    assert set(_effects(script)) == set(MOTION_STYLES["dynamic"]["effects"])


def test_static_writes_the_shape_the_compositor_reads_as_a_held_frame():
    script = _script(2)
    assign_effects(script, "static")
    for seg in script["segments"]:
        for shot in seg["shots"]:
            assert shot["motion"] == {"kind": "static"}


def test_style_of_reads_the_project():
    assert style_of({"project": {"motion_style": "dynamic"}}) == "dynamic"
    assert style_of({"project": {}}) == DEFAULT_MOTION_STYLE
    assert style_of({}) == DEFAULT_MOTION_STYLE


# ── The two places shots get re-cut ───────────────────────────────────────────

def test_a_rhythm_change_honours_the_project_style():
    script = _script(1, segments=3, style="static")
    apply_shot_rhythm(script, 3)
    for seg in script["segments"]:
        for shot in seg["shots"]:
            assert shot["motion"] == {"kind": "static"}


def test_a_rhythm_change_still_alternates():
    script = _script(1, segments=3)
    apply_shot_rhythm(script, 3)
    effects = _effects(script)
    assert len(effects) > 3
    for a, b in zip(effects, effects[1:]):
        assert a != b


def test_an_image_budget_honours_the_project_style():
    script = _script(2, segments=5, style="gentle_drift")
    plan_image_budget(script, 5)
    effects = _effects(script)
    assert effects, "the budget left the script with no shots"
    for a, b in zip(effects, effects[1:]):
        assert a != b


# ── The cache ─────────────────────────────────────────────────────────────────

_SHOT = {
    "query": "a citadel at dawn",
    "motion": {"kind": "ken_burns", "effect": "zoom_in"},
    "treatment": {"filter": "none"},
}


def test_changing_the_style_re_renders_the_shot():
    """
    Same shot, same duration, different travel. A shared key would serve the old
    clip back and the new style would look like it had done nothing.
    """
    keys = {
        _get_shot_cache_key(_SHOT, 6.0, 1280, 720, 30, motion_style=style)
        for style in MOTION_STYLES
    }
    assert len(keys) == len(MOTION_STYLES)


def test_an_unset_style_keys_the_same_as_ken_burns():
    assert (_get_shot_cache_key(_SHOT, 6.0, 1280, 720, 30, motion_style=None)
            == _get_shot_cache_key(_SHOT, 6.0, 1280, 720, 30, motion_style="ken_burns"))


# ── Rendered pixels ───────────────────────────────────────────────────────────
#
# The obvious metric — mean absolute difference between the first frame and the
# last — is useless here. On a detailed frame any displacement past a few pixels
# decorrelates the two images completely, so gentle drift and dynamic both score
# ~72/255 and the test cannot tell them apart. Measuring the zoom directly can:
# a marker of known size grows by exactly the travel the style asked for.

@pytest.fixture(scope="module")
def marker_image(tmp_path_factory):
    """Black, with one white square at the centre — a thing whose size can be
    measured in the output frame."""
    p = tmp_path_factory.mktemp("motion_style") / "marker.jpg"
    img = Image.new("RGB", (1600, 900), (0, 0, 0))
    for x in range(700, 900):
        for y in range(350, 550):
            img.putpixel((x, y), (255, 255, 255))
    img.save(p)
    return str(p)


def _marker_size(video, t, out_png):
    subprocess.run([find_ffmpeg(), "-y", "-ss", str(t), "-i", video, "-frames:v", "1", out_png],
                   capture_output=True, text=True)
    frame = np.asarray(Image.open(out_png).convert("L"))
    cols = np.where(frame.max(axis=0) > 128)[0]
    assert len(cols), f"the marker is not in the frame at t={t}"
    return int(cols[-1] - cols[0] + 1)


def _zoom_ratio(style, marker_image, tmp_path):
    """How much larger the marker is at the end of the shot than at the start."""
    shot = {
        "shot_id": "1a",
        "motion": {"kind": "ken_burns", "effect": "zoom_in"},
        "treatment": {"filter": "none"},
    }
    out = str(tmp_path / f"{style}.mp4")
    render_shot_clip(shot=shot, visual_path=marker_image, duration=3.0,
                     width=640, height=360, output_mp4_path=out, fps=24,
                     motion_style=style)
    assert os.path.exists(out)
    first = _marker_size(out, 0.0, str(tmp_path / f"{style}_a.png"))
    last = _marker_size(out, 2.95, str(tmp_path / f"{style}_b.png"))
    return last / first


@pytest.mark.parametrize("style", ["gentle_drift", "ken_burns", "dynamic"])
def test_the_frame_travels_as_far_as_the_style_says_it_does(style, marker_image, tmp_path):
    """Not "it moved" — it moved by the declared amount. Measured over a 3s
    shot: gentle 1.0625, ken_burns 1.1500, dynamic 1.2625 against declared
    1.06, 1.15 and 1.27."""
    ratio = _zoom_ratio(style, marker_image, tmp_path)
    expected = 1.0 + travel_for(style, 3.0)
    assert ratio == pytest.approx(expected, abs=0.03), f"{style}: rendered {ratio:.4f}, asked for {expected:.4f}"


def test_the_styles_do_not_overlap_on_screen(marker_image, tmp_path):
    """Three styles that measure the same are one style with three names."""
    gentle = _zoom_ratio("gentle_drift", marker_image, tmp_path)
    classic = _zoom_ratio("ken_burns", marker_image, tmp_path)
    strong = _zoom_ratio("dynamic", marker_image, tmp_path)
    assert 1.0 < gentle < classic < strong, f"{gentle:.4f} {classic:.4f} {strong:.4f}"


def test_the_static_style_holds_the_frame_even_when_the_shot_asks_to_zoom(marker_image, tmp_path):
    """
    A project switched to Static holds still without re-planning every shot: the
    style sets the travel to zero, which collapses the move.
    """
    assert _zoom_ratio("static", marker_image, tmp_path) == 1.0


# ── SLICE B TESTS: Camera Amount & Window Memory ──────────────────────────────

@pytest.mark.parametrize("style", ["static", "gentle_drift", "ken_burns", "dynamic"])
@pytest.mark.parametrize("amount", list(range(0, 105, 5)))
def test_the_clamp_holds_at_every_amount(style, amount):
    """1. The clamp holds at every amount: travel_for(style, 600.0) never exceeds max * (amount/100)."""
    prof = MOTION_STYLES[style]
    scaled_max = round(prof["max"] * (amount / 100.0), 4)
    result = travel_for(style, 600.0, amount=amount)
    assert result <= scaled_max + 1e-4


@pytest.mark.parametrize("style", ["static", "gentle_drift", "ken_burns", "dynamic"])
@pytest.mark.parametrize("amount", list(range(0, 105, 5)))
@pytest.mark.parametrize("duration", [0.5, 2.0, 5.0, 12.0, 60.0])
def test_the_pad_invariant(style, amount, duration):
    """2. The pad invariant: 1 + travel_for(style, duration, amount) <= pad_factor_for(style)."""
    travel = travel_for(style, duration, amount=amount)
    pad = pad_factor_for(style)
    assert 1.0 + travel <= pad + 1e-4


def test_the_amount_actually_scales():
    """3. Ken Burns at 50% travels half as far as at 100% at the same duration, and 0% travels zero on every style."""
    t50 = travel_for("ken_burns", 3.0, amount=50)
    t100 = travel_for("ken_burns", 3.0, amount=100)
    assert t50 == pytest.approx(t100 * 0.5, abs=1e-4)

    for style in ["static", "gentle_drift", "ken_burns", "dynamic"]:
        assert travel_for(style, 5.0, amount=0) == 0.0
        assert travel_for(style, 600.0, amount=0) == 0.0


def test_the_cache_key_changes_with_the_amount():
    """4. The cache key changes with the amount: same shot, same duration, two amounts -> two keys."""
    from pipeline.composer import _get_shot_cache_key
    shot = {"shot_id": 1, "query": "a scene"}
    k60 = _get_shot_cache_key(shot, 5.0, 1280, 720, 30, motion_style="ken_burns", motion_amount=60)
    k40 = _get_shot_cache_key(shot, 5.0, 1280, 720, 30, motion_style="ken_burns", motion_amount=40)
    assert k60 != k40


def test_existing_callers_are_unchanged():
    """5. Existing callers are unchanged: calling travel_for without amount returns exactly what it returns today."""
    for style in ["static", "gentle_drift", "ken_burns", "dynamic"]:
        for dur in [1.0, 3.0, 7.0, 15.0, 60.0]:
            assert travel_for(style, dur) == travel_for(style, dur, amount=None)


def test_the_camera_choice_round_trips(tmp_path, monkeypatch):
    """6. The camera choice round-trips: save_ui_defaults with motion_style and motion_amount returns both."""
    from app import Api
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("{}", encoding="utf-8")
    monkeypatch.setattr("app.SETTINGS_PATH", str(settings_file))

    api = Api()
    saved = api.save_ui_defaults({"motion_style": "dynamic", "motion_amount": 45})
    assert saved["success"] is True
    assert saved["ui_defaults"]["motion_style"] == "dynamic"
    assert saved["ui_defaults"]["motion_amount"] == 45

    res = api.get_ui_defaults()
    assert res["success"] is True
    assert res["ui_defaults"]["motion_style"] == "dynamic"
    assert res["ui_defaults"]["motion_amount"] == 45


def test_window_geometry_is_validated_not_trusted():
    """7. Window geometry is validated, not trusted: offscreen rect and below-minimum size fall back to safe defaults."""
    from pipeline.window_geometry import validate_window_geometry, DEFAULT_WIDTH, DEFAULT_HEIGHT, MIN_WIDTH, MIN_HEIGHT

    # Mock screen: 1920x1080 at (0, 0)
    mock_screens = [{"x": 0, "y": 0, "width": 1920, "height": 1080}]

    # Below-minimum size falls back to default_size
    tiny = validate_window_geometry({"width": 400, "height": 300, "x": 100, "y": 100}, screens=mock_screens)
    assert tiny["width"] == DEFAULT_WIDTH
    assert tiny["height"] == DEFAULT_HEIGHT

    # Negative offscreen coordinates fall back to centering/OS placement (x=None, y=None)
    offscreen_neg = validate_window_geometry({"width": 1000, "height": 900, "x": -2500, "y": -1500}, screens=mock_screens)
    assert offscreen_neg["x"] is None
    assert offscreen_neg["y"] is None
    assert offscreen_neg["width"] == DEFAULT_WIDTH

    # Far beyond virtual screen coordinates fall back
    offscreen_far = validate_window_geometry({"width": 1000, "height": 900, "x": 10000, "y": 8000}, screens=mock_screens)
    assert offscreen_far["x"] is None
    assert offscreen_far["y"] is None

    # Valid geometry is preserved
    valid = validate_window_geometry({"width": 1200, "height": 850, "x": 100, "y": 80, "maximized": False}, screens=mock_screens)
    assert valid["width"] == 1200
    assert valid["height"] == 850
    assert valid["x"] == 100
    assert valid["y"] == 80
    assert valid["maximized"] is False

