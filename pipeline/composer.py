"""
Stage 5 — Segment composition.
Ultra-fast single-pass FFmpeg compositor.
Supports Schema v2 multi-shot segments, content-hash caching, encoder probing,
sound effect mixing, subtitles/captions, text overlays, and sprites.
"""

import os
import math
import shutil
import hashlib
import json
import subprocess
import time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from pipeline.captions import parse_srt
from pipeline.validator import resolve_shot_durations
from pipeline.motion import pad_factor_for, travel_for, resolve_motion_style

FPS = 30

# Global cached encoder probe result
_CACHED_ENCODER = None


from pipeline.ffmpeg_locate import find_ffmpeg, find_ffprobe


def _get_best_encoder(on_progress=None) -> tuple[str, list[str]]:
    """
    Select the optimal H.264 encoder and parameters for sharp, artifact-free delivery.
    Uses libx264 with medium preset, CRF 18 (near-transparent), and faststart flag.
    """
    global _CACHED_ENCODER
    if _CACHED_ENCODER is not None:
        return _CACHED_ENCODER

    # Selected standard CPU libx264 (medium preset, crf 18, faststart)
    best = ("libx264", ["-preset", "medium", "-crf", "18", "-movflags", "+faststart"])
    _CACHED_ENCODER = best
    if on_progress:
        on_progress("Encoder selected: libx264 (-preset medium -crf 18 -movflags +faststart)")
    return _CACHED_ENCODER


#: Font files are looked up under the *real* Windows directory. "C:/Windows"
#: was hardcoded, and Windows is not always installed on C:. The overlay filter
#: further down hardcoded a single file with no fallback at all, so a machine
#: without arialbd.ttf lost every text overlay to an FFmpeg error rather than
#: falling back to another face.
_FONT_NAMES = ("arialbd.ttf", "arial.ttf", "calibrib.ttf", "segoeui.ttf")


def _font_candidates():
    """Every font file worth trying on this machine, best first."""
    windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot") or "C:/Windows"
    return [os.path.join(windir, "Fonts", name) for name in _FONT_NAMES]


def _find_font_file():
    """The first font file that actually exists here, or None if there is none."""
    for path in _font_candidates():
        if os.path.isfile(path):
            return path
    return None


def _ffmpeg_font_arg(path: str) -> str:
    """A font path as an FFmpeg filter argument: forward slashes, escaped colon."""
    return path.replace(chr(92), "/").replace(":", chr(92) + ":")


def _get_font(size: int):
    """Load a TTF font; fall back to PIL default if no system font found."""
    for path in _font_candidates():
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


#: Single-image treatments, mapped to their magick_processor implementation.
SINGLE_IMAGE_TREATMENTS = {
    "vignette": "process_vignette",
    "vox_collage": "process_vox_collage",
    "documentary": "process_documentary",
    "illustration": "process_illustration",
    "silhouette": "process_silhouette",
}


#: What zoompan can actually perform.
MOTION_EFFECTS = ("zoom_in", "zoom_out", "pan_left", "pan_right")


def resolve_motion_effect(motion) -> str:
    """
    Work out which camera move a shot wants.

    The schema splits this in two: `kind` is ken_burns | static | generative, and
    `effect` is zoom_in | zoom_out | pan_left | pan_right. The compositor used to
    compare `kind` against the effect names — values it can never hold — so every
    Ken Burns shot fell through to a fixed z=1.0 frame. Every film this app has
    produced was a slideshow of still images, and no test caught it because the
    tests passed {"kind": "zoom_in"}, a shape nothing in the app ever writes.

    Accepts a plain string too, for schema-v1 segments that stored the effect
    directly in `ken_burns`.
    """
    if isinstance(motion, str):
        return motion if motion in MOTION_EFFECTS else "static"
    if not isinstance(motion, dict):
        return "zoom_in"

    kind = (motion.get("kind") or "ken_burns").strip().lower()
    if kind in ("static", "none"):
        return "static"
    if kind in MOTION_EFFECTS:
        # Tolerated: some callers put the effect straight into `kind`.
        return kind
    if kind == "generative":
        return "static"

    effect = (motion.get("effect") or "zoom_in").strip().lower()
    return effect if effect in MOTION_EFFECTS else "zoom_in"


def _add_ambient_bed(narration_path: str, segment_dict: dict, duration: float,
                     cache_dir: str, segment_id, on_progress=None) -> str:
    """
    Lay an ambient bed under this segment's narration, if one suits it.

    Silence is the correct answer when nothing matches — an unrelated bed is worse
    than none. Controlled by config/settings.json → ambient_beds (default on).
    Any failure returns the narration untouched.
    """
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        settings_file = os.path.join(root, "config", "settings.json")
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                if not json.load(f).get("ambient_beds", True):
                    return narration_path
        except Exception:
            pass

        from pipeline import sound

        beds = sound.load_beds()
        if not beds:
            return narration_path

        seg = segment_dict or {}
        shots = seg.get("shots") or []
        scene_text = " ".join(
            [seg.get("narration", "")] + [str(s.get("query", "")) for s in shots]
        )
        bed = sound.pick_bed(scene_text, beds)
        if not bed:
            return narration_path

        ffmpeg = find_ffmpeg()
        bed_track = os.path.join(cache_dir, f"segment_{segment_id}_bed.wav")
        sound.build_bed_track(bed["abs_path"], duration, bed_track, ffmpeg)

        mixed = os.path.join(cache_dir, f"segment_{segment_id}_with_bed.mp3")
        result = sound.mix_bed_under_narration(narration_path, bed_track, mixed, ffmpeg)
        if result != narration_path and on_progress:
            on_progress(f"Segment {segment_id} — ambient bed: {os.path.basename(bed['path'])}")
        return result
    except Exception as e:
        if on_progress:
            on_progress(f"Segment {segment_id} — no ambient bed ({e})")
        return narration_path


def treatment_for_style(visual_style: str, preset: dict = None,
                        visual_type: str = None) -> str | None:
    """
    Map the project's look onto a post-processing treatment.

    Order matters: a preset that names its own treatment is authoritative, then
    a preset key that is itself a treatment name, and only then the loose prose
    match that was here before. This is what finally makes the prompt and the
    picture agree - picking courtroom_sketch now yields an illustration prompt
    *and* the illustration treatment.
    """
    if preset and preset.get("treatment") in SINGLE_IMAGE_TREATMENTS:
        return preset["treatment"]

    if visual_type and visual_type in SINGLE_IMAGE_TREATMENTS:
        return visual_type

    if not visual_style:
        return None
    s = visual_style.lower()
    for key, name in (
        ("vox", "vox_collage"), ("collage", "vox_collage"), ("paper", "vox_collage"),
        ("silhouette", "silhouette"),
        ("illustrat", "illustration"), ("drawn", "illustration"), ("painted", "illustration"),
        ("documentary", "documentary"), ("archival", "documentary"), ("vintage", "documentary"),
    ):
        if key in s:
            return name
    return None


def resolve_default_treatment(visual_style: str, visual_type: str = "",
                              series_slug: str = None) -> str | None:
    """
    The treatment a render should fall back to, given the project's choices.

    Looks the picked visual type up in its series pack so the preset's declared
    treatment wins, then defers to treatment_for_style for the older prose
    match. Import is function-local because pipeline.library is heavy and the
    compositor is imported by processes that never need it.
    """
    preset = None
    if visual_type:
        try:
            from pipeline.library import get_series_config, resolve_style_preset
            preset = resolve_style_preset(
                get_series_config(series_slug=series_slug), visual_type
            )
        except Exception:
            preset = None
    return treatment_for_style(visual_style, preset=preset, visual_type=visual_type)


def _apply_treatment(shot: dict, visual_path: str, output_mp4_path: str,
                     width: int, height: int, on_progress=None,
                     default_filter: str | None = None) -> str:
    """
    Render the shot's treatment onto a copy of the image and return its path.

    Falls back to the untreated image on any failure — a look is never worth
    losing the shot over. The treated file is cached beside the shot clip, so the
    Pillow work happens once per shot rather than once per render.
    """
    treatment = shot.get("treatment") or {}
    if not isinstance(treatment, dict):
        return visual_path
    name = (treatment.get("filter") or "none").strip().lower()

    # "vignette" is what the upconverter writes when nobody chose anything, so a
    # project style is allowed to override it. A deliberately chosen treatment
    # still wins.
    if default_filter and name in ("none", "vignette"):
        name = default_filter

    func_name = SINGLE_IMAGE_TREATMENTS.get(name)
    if not func_name or not visual_path or not os.path.exists(visual_path):
        return visual_path

    treated = f"{os.path.splitext(output_mp4_path)[0]}_{name}.jpg"
    if os.path.exists(treated) and os.path.getsize(treated) > 0:
        return treated

    try:
        from pipeline import magick_processor
        getattr(magick_processor, func_name)(visual_path, treated, width, height)
        if os.path.exists(treated) and os.path.getsize(treated) > 0:
            if on_progress:
                on_progress(f"Applied {name} treatment")
            return treated
    except Exception as e:
        if on_progress:
            on_progress(f"Treatment '{name}' failed ({e}); using the untreated image")
    return visual_path


def _resolve_pin_path(pin_file: str, project_dir: str, root: str = None) -> str:
    """
    Resolve a shot's pin to a real file, or None.

    Pins come from two places and are written differently. The storyboard writes
    library-relative paths ("library/images/x.jpg"); the schema-v1 fallback writes
    project-local names ("1.jpg"). Only the project-local form used to be tried, so
    an image chosen on the board silently lost to the retrieved one at render time.
    """
    if not pin_file or not isinstance(pin_file, str):
        return None
    cleaned = pin_file.strip().replace("\\", "/")
    if not cleaned:
        return None

    if os.path.isabs(cleaned) and os.path.exists(cleaned):
        return os.path.normpath(cleaned)

    if root is None:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    for candidate in (os.path.join(project_dir, cleaned), os.path.join(root, cleaned)):
        if os.path.exists(candidate):
            return os.path.normpath(candidate)
    return None


def _get_shot_cache_key(shot: dict, resolved_duration: float, width: int, height: int, fps: int = 30,
                        default_treatment: str = None, motion_style: str = None) -> str:
    """Generate a SHA-1 hash for shot content cache lookup."""
    query_or_pin = str(shot.get("prompt_override") or shot.get("pin") or shot.get("query") or "")
    motion = json.dumps(shot.get("motion", {}), sort_keys=True)
    treatment = json.dumps(shot.get("treatment", {}), sort_keys=True)
    dur_str = f"{resolved_duration:.3f}"
    res_str = f"{width}x{height}"
    
    # Bump when the rendered result changes for identical inputs, or every cached
    # clip from the old behaviour is served back and the fix looks like a no-op.
    # v2: motion effect is honoured (shots used to render as fixed frames) and
    #     treatments are applied to the image.
    # v3: default_treatment (from the resolved visual type/preset) is part of
    #     the key, so changing the picked visual type invalidates the cache.
    # v4: the motion style sets how far the frame travels, so the same shot at
    #     the same duration renders differently under Gentle drift and Dynamic.
    # v5: lanczos scaling flags, medium/crf 18 encoder preset, faststart, and 192k audio.
    # v6: prompt_override support, apply_era separation, medium/palette/era split.
    # v7: prompt_recipe support, external prompt binding, and numbered slot matching.
    # v8: empty visual_type resolves to top style preset; style_presets override whitelist.
    # v9: visual_description in shot description pass obeys niche prompt_recipe, era, and cache.
    style_key = resolve_motion_style(motion_style)
    raw = (f"v9|{query_or_pin}|{dur_str}|{motion}|{treatment}|{res_str}|{fps}|"
           f"{default_treatment or ''}|{style_key}")
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _overlay_sound_effects(narration_path: str, sfx_list: list, output_audio_path: str, cache_dir: str, on_progress=None) -> str:
    """
    Mix narration audio and multiple sound effects at specified millisecond offsets using FFmpeg.
    """
    if not sfx_list:
        return narration_path

    project_dir = os.path.dirname(os.path.dirname(narration_path))
    sfx_search_paths = [
        os.path.join(project_dir, "assets", "sfx"),
        os.path.join(os.path.dirname(project_dir), "assets", "sfx")
    ]
    
    valid_sfx = []
    for item in sfx_list:
        name = item.get("name")
        if not name:
            continue
        if not name.endswith(".wav") and not name.endswith(".mp3"):
            name += ".wav"
            
        found_path = None
        for base in sfx_search_paths:
            candidate = os.path.join(base, name)
            if os.path.exists(candidate):
                found_path = candidate
                break
                
        if found_path:
            valid_sfx.append((found_path, item.get("offset_ms", 0)))
            
    if not valid_sfx:
        return narration_path
        
    if on_progress:
        on_progress(f"Mixing {len(valid_sfx)} sound effects into voiceover")
        
    ffmpeg_bin = find_ffmpeg()
    cmd = [ffmpeg_bin, "-y", "-i", narration_path]
    for path, _ in valid_sfx:
        cmd.extend(["-i", path])
        
    filter_parts = []
    mix_inputs = 1 + len(valid_sfx)
    
    for i, (_, offset_ms) in enumerate(valid_sfx, start=1):
        filter_parts.append(f"[{i}:a]adelay={offset_ms}:all=1[sfx_{i}]")
        
    mix_str = "[0:a]" + "".join(f"[sfx_{i}]" for i in range(1, len(valid_sfx) + 1))
    mix_str += f"amix=inputs={mix_inputs}:duration=first[aout]"
    filter_parts.append(mix_str)
    
    filter_complex = ";".join(filter_parts)
    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[aout]",
        "-c:a", "pcm_s16le",
        output_audio_path
    ])
    
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and os.path.exists(output_audio_path):
            return output_audio_path
        elif on_progress:
            on_progress(f"Warning: SFX mixing failed, using clean audio: {res.stderr}")
    except Exception as e:
        if on_progress:
            on_progress(f"Warning: SFX mixing encountered error: {e}")
            
    return narration_path


def _create_static_overlay_png(level1_overlay: dict, width: int, height: int, output_png_path: str) -> bool:
    """
    Render static level1_overlay elements (highlights, labels, arrows) onto a transparent PNG overlay.
    Returns True if an overlay PNG was created, False otherwise.
    """
    if not level1_overlay:
        return False

    highlights = level1_overlay.get("highlights", [])
    labels = level1_overlay.get("labels", [])
    arrows = level1_overlay.get("arrows", [])

    if not highlights and not labels and not arrows:
        return False

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    for h in highlights:
        cx = h.get("x", 0)
        cy = h.get("y", 0)
        if isinstance(cx, float) and cx <= 1.0: cx = int(cx * width)
        if isinstance(cy, float) and cy <= 1.0: cy = int(cy * height)
        r = h.get("radius", 30)
        color_str = h.get("color", "red")
        fill = h.get("fill", True)
        
        c_map = {
            "red": (255, 50, 50, 180),
            "yellow": (255, 230, 50, 180),
            "blue": (50, 150, 255, 180),
            "white": (255, 255, 255, 180)
        }
        col = c_map.get(color_str, (255, 50, 50, 180))
        fill_col = col if fill else None
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill_col, outline=col, width=3)

    font_size = max(24, int(width * 0.033))
    font = _get_font(font_size)

    for lbl in labels:
        txt = lbl.get("text", "")
        if not txt:
            continue
        lx = lbl.get("x", 0)
        ly = lbl.get("y", 0)
        if isinstance(lx, float) and lx <= 1.0: lx = int(lx * width)
        if isinstance(ly, float) and ly <= 1.0: ly = int(ly * height)
        color_str = lbl.get("color", "yellow")
        c_map = {"yellow": (255, 230, 100), "white": (255, 255, 255), "red": (255, 80, 80)}
        col = c_map.get(color_str, (255, 230, 100))
        
        bbox = draw.textbbox((0, 0), txt, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx, ty = lx - tw // 2, ly - th // 2
        for dx, dy in [(-2, -2), (2, -2), (-2, 2), (2, 2)]:
            draw.text((tx + dx, ty + dy), txt, font=font, fill=(0, 0, 0))
        draw.text((tx, ty), txt, font=font, fill=col)

    for arr in arrows:
        x1, y1 = arr.get("x1", 0), arr.get("y1", 0)
        x2, y2 = arr.get("x2", 0), arr.get("y2", 0)
        if isinstance(x1, float) and x1 <= 1.0: x1 = int(x1 * width)
        if isinstance(y1, float) and y1 <= 1.0: y1 = int(y1 * height)
        if isinstance(x2, float) and x2 <= 1.0: x2 = int(x2 * width)
        if isinstance(y2, float) and y2 <= 1.0: y2 = int(y2 * height)
        color_str = arr.get("color", "blue")
        c_map = {"blue": (50, 150, 255), "red": (255, 50, 50), "yellow": (255, 230, 50)}
        col = c_map.get(color_str, (50, 150, 255))
        draw.line([(x1, y1), (x2, y2)], fill=col, width=4)

    img.save(output_png_path, "PNG")
    return True


def _convert_srt_to_ass(srt_path: str, width: int, height: int) -> str:
    """
    Convert SRT file to an ASS subtitle file with exact PlayResX/Y header, font size,
    and baseline position matching the original renderer.
    """
    captions = parse_srt(srt_path)
    font_size = max(24, int(width * 0.027))
    is_vertical = (height / width) > 1.2
    margin_v = int(height * 0.28) if is_vertical else int(height * 0.22)
    
    ass_path = os.path.splitext(srt_path)[0] + ".ass"
    
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,Arial,{font_size},&H00FFFFFF,&H00000000,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,2,0,2,60,60,{margin_v},1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    
    def fmt_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        cs = int(round((seconds - int(seconds)) * 100))
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    for start_s, end_s, text in captions:
        t_start = fmt_time(start_s)
        t_end = fmt_time(end_s)
        clean_text = text.replace("\n", "\\N")
        lines.append(f"Dialogue: 0,{t_start},{t_end},Default,,0,0,0,,{clean_text}")

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return ass_path


def render_shot_clip(
    shot: dict,
    visual_path: str,
    duration: float,
    width: int,
    height: int,
    output_mp4_path: str,
    srt_path: str | None = None,
    audio_path: str | None = None,
    fps: int = 30,
    on_progress=None,
    default_treatment: str | None = None,
    motion_style: str | None = None,
) -> str:
    """
    Render a single shot into an MP4 clip using an FFmpeg filtergraph.
    """
    if os.path.exists(output_mp4_path) and os.path.getsize(output_mp4_path) > 0:
        return output_mp4_path

    num_frames = int(round(duration * fps))
    if num_frames < 1:
        num_frames = 1

    motion_kind = resolve_motion_effect(shot.get("motion"))
    text_overlay = shot.get("text_overlay")
    transition_in = shot.get("transition_in", "cut")
    transition_out = shot.get("transition_out", "cut")
    level1_overlay = shot.get("level1_overlay")

    # Base scale & zoompan. The padding is the style's, because the crop of a
    # Dynamic move travels further than a 1.25x frame can hold.
    pad = pad_factor_for(motion_style)
    pad_w = int(width * pad)
    pad_h = int(height * pad)

    # Treatment (the "grade" look). magick_processor has implemented vignette,
    # vox_collage, documentary, illustration and silhouette all along, but the
    # compositor only ever used `treatment` to build a cache key and rendered the
    # raw image — so every shot in every film came out untreated.
    visual_path = _apply_treatment(shot, visual_path, output_mp4_path, pad_w, pad_h,
                                   on_progress, default_treatment)

    filters = [f"scale={pad_w}:{pad_h}:flags=lanczos"]

    # Motion (Ken Burns).
    #
    # The travel used to be a flat 15% however long the shot ran. Over a 3s shot
    # that reads as a push; over the ~19s segments this app now produces it is
    # 0.8% per second — indistinguishable from a still frame. It scales with
    # duration so the *rate* stays constant, and the project's motion style sets
    # that rate and the clamps around it. Static returns zero, which collapses
    # every expression below to a held frame whatever move the shot asked for.
    travel = travel_for(motion_style, duration)
    pan_zoom = 1.0 + travel

    if motion_kind == "zoom_in":
        filters.append(f"zoompan=z='1.0+{travel:.4f}*(on/{num_frames})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={num_frames}:s={width}x{height}:fps={fps}")
    elif motion_kind == "zoom_out":
        filters.append(f"zoompan=z='{1.0 + travel:.4f}-{travel:.4f}*(on/{num_frames})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={num_frames}:s={width}x{height}:fps={fps}")
    elif motion_kind == "pan_right":
        filters.append(f"zoompan=z='{pan_zoom:.4f}':x='(iw-iw/zoom)*(on/{num_frames})':y='(ih-ih/zoom)/2':d={num_frames}:s={width}x{height}:fps={fps}")
    elif motion_kind == "pan_left":
        filters.append(f"zoompan=z='{pan_zoom:.4f}':x='(iw-iw/zoom)*(1-on/{num_frames})':y='(ih-ih/zoom)/2':d={num_frames}:s={width}x{height}:fps={fps}")
    else:
        filters.append(f"zoompan=z='1.0':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d={num_frames}:s={width}x{height}:fps={fps}")

    # Text overlay. Skipped rather than attempted when the machine has none of
    # the candidate fonts: drawtext with a missing fontfile fails the whole
    # render, which would lose the picture as well as the caption.
    overlay_font = _find_font_file()
    if text_overlay and text_overlay.get("text") and not overlay_font and on_progress:
        on_progress("No usable system font found - skipping the text overlay.")
    if text_overlay and text_overlay.get("text") and overlay_font:
        ov_text = text_overlay.get("text", "").replace("'", "'\\''").replace(":", "\\:")
        pos = text_overlay.get("position", "bottom_center")
        ov_dur = text_overlay.get("duration_seconds", duration)
        
        ov_positions = {
            "top_left":      ("60", "60"),
            "top_center":    ("(w-text_w)/2", "60"),
            "top_right":     ("w-text_w-60", "60"),
            "bottom_left":   ("60", "h-120"),
            "bottom_center": ("(w-text_w)/2", "h-120"),
            "bottom_right":  ("w-text_w-60", "h-120"),
            "center":        ("(w-text_w)/2", "(h-text_h)/2"),
        }
        x_expr, y_expr = ov_positions.get(pos, ov_positions["bottom_center"])
        font_path = _ffmpeg_font_arg(overlay_font)
        ov_font_size = max(24, int(width * 0.033))
        
        drawtext_str = (
            f"drawtext=fontfile='{font_path}':text='{ov_text}':fontsize={ov_font_size}:"
            f"fontcolor=0xFFE664:borderw=2:bordercolor=black:box=1:boxcolor=black@0.65:boxborderw=12:"
            f"x={x_expr}:y={y_expr}:enable='between(t,0,{ov_dur})'"
        )
        filters.append(drawtext_str)

    # Subtitles / Captions via ASS file
    if srt_path and os.path.exists(srt_path):
        ass_path = _convert_srt_to_ass(srt_path, width, height)
        clean_ass = ass_path.replace("\\", "/").replace(":", "\\:")
        filters.append(f"subtitles=filename='{clean_ass}'")

    # Fade transitions
    if transition_in in ("fade", "crossfade"):
        filters.append("fade=t=in:st=0:d=0.5")
    if transition_out in ("fade", "crossfade") and duration > 0.5:
        filters.append(f"fade=t=out:st={duration - 0.5:.2f}:d=0.5")

    additional_inputs = []
    
    # Check for static level1_overlay PNG
    cache_dir = os.path.dirname(output_mp4_path)
    static_overlay_png = os.path.join(cache_dir, f"static_ov_{os.path.basename(output_mp4_path)}.png")
    has_static_overlay = _create_static_overlay_png(level1_overlay, width, height, static_overlay_png)
    if has_static_overlay:
        additional_inputs.extend(["-loop", "1", "-i", static_overlay_png])

    # Check for moving sprites
    sprite_inputs = []
    if level1_overlay and "sprites" in level1_overlay:
        project_dir = os.path.dirname(visual_path)
        for sp in level1_overlay["sprites"]:
            m_type = sp.get("motion", "none").lower()
            sp_name = sp.get("image")
            if not sp_name or m_type in ("none", "static"):
                continue
            sp_path = os.path.join(project_dir, sp_name)
            if not os.path.exists(sp_path):
                sp_path = os.path.join(os.path.dirname(project_dir), "assets", "sprites", sp_name)
            if os.path.exists(sp_path):
                additional_inputs.extend(["-loop", "1", "-i", sp_path])
                sprite_inputs.append({
                    "target_x": sp.get("x", 0),
                    "target_y": sp.get("y", 0),
                    "scale": sp.get("scale", 1.0),
                    "motion": m_type
                })

    ffmpeg_bin = find_ffmpeg()
    encoder, enc_args = _get_best_encoder(on_progress)

    cmd = [ffmpeg_bin, "-y", "-loop", "1", "-i", visual_path]
    if audio_path and os.path.exists(audio_path):
        cmd.extend(["-i", audio_path])
    cmd.extend(additional_inputs)

    if not has_static_overlay and not sprite_inputs:
        # Simple filtergraph
        vf_str = ",".join(filters)
        cmd.extend(["-vf", vf_str])
    else:
        # Complex multi-input filtergraph
        base_chain = ",".join(filters)
        fc_parts = [f"[0:v]{base_chain}[v_current]"]
        curr_stream = "v_current"
        in_idx = 2 if (audio_path and os.path.exists(audio_path)) else 1

        if has_static_overlay:
            next_stream = f"v_over_{in_idx}"
            fc_parts.append(f"[{curr_stream}][{in_idx}:v]overlay=x=0:y=0:shortest=1[{next_stream}]")
            curr_stream = next_stream
            in_idx += 1

        for sp in sprite_inputs:
            m_type = sp["motion"]
            tx = sp["target_x"]
            ty = sp["target_y"]
            if isinstance(tx, float) and tx <= 1.0: tx = int(tx * width)
            if isinstance(ty, float) and ty <= 1.0: ty = int(ty * height)
            scale = sp["scale"]

            scaled_stream = f"sp_scale_{in_idx}"
            if scale != 1.0:
                fc_parts.append(f"[{in_idx}:v]scale=iw*{scale}:ih*{scale}[{scaled_stream}]")
            else:
                scaled_stream = f"{in_idx}:v"

            if m_type == "slide_in_left":
                x_expr = f"if(lt(t,1), -w+({tx}+w)*t/1, {tx})"
                y_expr = f"{ty}"
            elif m_type == "slide_in_right":
                x_expr = f"if(lt(t,1), {width}-({width}-{tx})*t/1, {tx})"
                y_expr = f"{ty}"
            elif m_type == "bounce":
                x_expr = f"{tx}"
                y_expr = f"{ty}-abs(sin(t*PI*2.5))*40"
            elif m_type == "slide_in_left_bounce":
                x_expr = f"if(lt(t,1), -w+({tx}+w)*t/1, {tx})"
                y_expr = f"{ty}-abs(sin(t*PI*2.5))*40"
            else:
                x_expr = f"{tx}"
                y_expr = f"{ty}"

            next_stream = f"v_over_{in_idx}"
            fc_parts.append(f"[{curr_stream}][{scaled_stream}]overlay=x='{x_expr}':y='{y_expr}':eval=frame[{next_stream}]")
            curr_stream = next_stream
            in_idx += 1

        fc_parts.append(f"[{curr_stream}]copy[outv]")
        cmd.extend(["-filter_complex", ";".join(fc_parts), "-map", "[outv]"])
        if audio_path and os.path.exists(audio_path):
            cmd.extend(["-map", "1:a"])

    cmd.extend(["-t", f"{duration:.3f}", "-c:v", encoder])
    cmd.extend(enc_args)
    cmd.extend(["-pix_fmt", "yuv420p"])

    if audio_path and os.path.exists(audio_path):
        cmd.extend(["-c:a", "aac", "-b:a", "192k", "-shortest"])

    cmd.append(output_mp4_path)

    res = subprocess.run(cmd, capture_output=True, text=True)
    if has_static_overlay and os.path.exists(static_overlay_png):
        try:
            os.remove(static_overlay_png)
        except Exception:
            pass

    if res.returncode == 0 and os.path.exists(output_mp4_path):
        return output_mp4_path
    else:
        raise RuntimeError(f"FFmpeg render shot clip failed:\nCommand: {' '.join(cmd)}\nError: {res.stderr}")


def compose_segment(
    segment_id: int,
    visual_path: str,
    audio_path: str,
    srt_path: str,
    ken_burns: str = "zoom_in",
    text_overlay: dict | None = None,
    transition_in: str = "cut",
    transition_out: str = "cut",
    cache_dir: str = "",
    width: int = 1280,
    height: int = 720,
    on_progress=None,
    sfx: list = None,
    level1_overlay: dict = None,
    segment_dict: dict = None,
    visual_style: str = "",
    visual_type: str = "",
    series_slug: str = None,
    motion_style: str = None,
) -> str:
    """
    Compose a single segment into an MP4 of resolution width x height.
    Supports Schema v2 multi-shot lists and content-hash caching per shot.
    """
    output_path = os.path.join(cache_dir, f"segment_{segment_id}_final.mp4")

    # Fast-path check: if final segment MP4 is already cached
    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        if on_progress:
            on_progress(f"Segment {segment_id} — video already cached, skipping")
        return output_path

    if on_progress:
        on_progress(f"Segment {segment_id} — composing video ({width}x{height})")

    # Mix SFX if provided
    mixed_audio_path = os.path.join(cache_dir, f"segment_{segment_id}_mixed_audio.wav")
    final_audio_path = _overlay_sound_effects(audio_path, sfx, mixed_audio_path, cache_dir, on_progress)

    # Calculate total segment audio duration strictly using ffprobe
    ffprobe_bin = find_ffprobe()
    probe_cmd = [
        ffprobe_bin, "-i", final_audio_path,
        "-show_entries", "format=duration",
        "-v", "quiet", "-of", "csv=p=0"
    ]
    dur_res = subprocess.run(probe_cmd, capture_output=True, text=True)
    if dur_res.returncode != 0 or not dur_res.stdout.strip():
        raise RuntimeError(f"ffprobe failed to probe audio duration for '{final_audio_path}'. Error: {dur_res.stderr.strip()}")

    try:
        total_audio_duration = float(dur_res.stdout.strip())
    except ValueError as e:
        raise RuntimeError(f"ffprobe returned non-numeric audio duration '{dur_res.stdout.strip()}' for '{final_audio_path}'") from e

    final_audio_path = _add_ambient_bed(
        final_audio_path, segment_dict, total_audio_duration,
        cache_dir, segment_id, on_progress,
    )

    # Extract shot list from segment_dict (Schema v2) or build single shot (Schema v1)
    shots = []
    if segment_dict and "shots" in segment_dict and segment_dict["shots"]:
        shots = segment_dict["shots"]
    else:
        # Schema v1 single-shot fallback
        shots = [{
            "shot_id": 1,
            "duration": None,
            "pin": visual_path if not visual_path.endswith("_placeholder.jpg") else None,
            "query": "segment visual",
            "source": "pin" if visual_path and not visual_path.endswith("_placeholder.jpg") else "library",
            "motion": {"kind": ken_burns},
            "treatment": {"filter": "none"},
            "text_overlay": text_overlay,
            "transition_in": transition_in,
            "transition_out": transition_out,
            "level1_overlay": level1_overlay,
        }]

    # Resolve shot durations
    resolved_durations = resolve_shot_durations(shots, total_audio_duration)

    # Resolved once per segment, not once per shot: it hits the series pack.
    default_treatment = resolve_default_treatment(visual_style, visual_type, series_slug)

    # Render each shot clip
    shot_clip_paths = []
    for i, shot in enumerate(shots):
        dur = resolved_durations[i]
        cache_key = _get_shot_cache_key(shot, dur, width, height, FPS, default_treatment=default_treatment,
                                        motion_style=motion_style)
        shot_mp4 = os.path.join(cache_dir, f"shot_{cache_key}.mp4")

        # Determine visual path for shot
        shot_visual = visual_path
        if shot.get("pin"):
            resolved_pin = _resolve_pin_path(shot["pin"], os.path.dirname(visual_path))
            if resolved_pin:
                shot_visual = resolved_pin
            elif on_progress:
                on_progress(
                    f"Segment {segment_id} — pinned image not found: {shot['pin']} "
                    f"(falling back to the retrieved image)"
                )

        # Burn subtitles only on first shot of segment if SRT present
        shot_srt = srt_path if i == 0 else None

        if not os.path.exists(shot_mp4) or os.path.getsize(shot_mp4) == 0:
            if on_progress:
                on_progress(f"Segment {segment_id} — rendering shot {i+1}/{len(shots)} ({dur:.2f}s)")
            render_shot_clip(
                shot=shot,
                visual_path=shot_visual,
                duration=dur,
                width=width,
                height=height,
                output_mp4_path=shot_mp4,
                srt_path=shot_srt,
                fps=FPS,
                on_progress=on_progress,
                default_treatment=default_treatment,
                motion_style=motion_style,
            )

        shot_clip_paths.append(shot_mp4)

    # If single shot segment, combine visual + audio directly
    ffmpeg_bin = find_ffmpeg()
    if len(shot_clip_paths) == 1:
        combine_cmd = [
            ffmpeg_bin, "-y",
            "-i", shot_clip_paths[0],
            "-i", final_audio_path,
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            output_path
        ]
        res = subprocess.run(combine_cmd, capture_output=True, text=True)
        if res.returncode == 0 and os.path.exists(output_path):
            return output_path

    # Multi-shot segment: concat visual shots then combine audio
    concat_txt_path = os.path.join(cache_dir, f"segment_{segment_id}_shots.txt")
    with open(concat_txt_path, "w", encoding="utf-8") as f:
        for p in shot_clip_paths:
            escaped_p = p.replace("\\", "/")
            f.write(f"file '{escaped_p}'\n")

    combined_visual_mp4 = os.path.join(cache_dir, f"segment_{segment_id}_visual_concat.mp4")
    concat_cmd = [
        ffmpeg_bin, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_txt_path,
        "-c", "copy",
        combined_visual_mp4
    ]
    res_concat = subprocess.run(concat_cmd, capture_output=True, text=True)

    # Add audio
    combine_cmd = [
        ffmpeg_bin, "-y",
        "-i", combined_visual_mp4 if os.path.exists(combined_visual_mp4) else shot_clip_paths[0],
        "-i", final_audio_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_path
    ]
    res_comb = subprocess.run(combine_cmd, capture_output=True, text=True)
    if res_comb.returncode == 0 and os.path.exists(output_path):
        return output_path

    raise RuntimeError(f"Segment composition failed for segment {segment_id}.")
