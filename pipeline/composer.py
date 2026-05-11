"""
Stage 5 — Segment composition.
Combines image + audio + Ken Burns motion + burned-in captions + text overlay + transitions.
Outputs a 1920x1080 30fps H.264 MP4 per segment.
"""

import os
import math
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from pipeline.captions import parse_srt

OUTPUT_W = 1920
OUTPUT_H = 1080
FPS = 30

# ── Font loading ───────────────────────────────────────────────────────────────

def _get_font(size: int):
    """Load a TTF font; fall back to PIL default if no system font found."""
    font_candidates = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
    ]
    for path in font_candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


# ── Image preparation ──────────────────────────────────────────────────────────

def _load_and_fit(img_path: str) -> Image.Image:
    """Load image and resize/crop to exactly fill 1920x1080 (cover, not letterbox)."""
    img = Image.open(img_path).convert("RGB")
    iw, ih = img.size

    scale = max(OUTPUT_W / iw, OUTPUT_H / ih)
    new_w = math.ceil(iw * scale)
    new_h = math.ceil(ih * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    left = (new_w - OUTPUT_W) // 2
    top = (new_h - OUTPUT_H) // 2
    img = img.crop((left, top, left + OUTPUT_W, top + OUTPUT_H))
    return img


# ── Ken Burns ─────────────────────────────────────────────────────────────────

def _ken_burns_crop(img: Image.Image, t: float, duration: float, effect: str) -> Image.Image:
    """
    Return the 1920x1080 crop of img at time t for the given Ken Burns effect.
    Works on an image already sized to at least 1920x1080 (use _load_and_fit first).
    """
    iw, ih = img.size
    progress = t / duration if duration > 0 else 0

    if effect == "zoom_in":
        # Crop shrinks from 100% to 85% — creates zoom-in illusion
        scale_start, scale_end = 1.0, 0.85
        scale = scale_start + (scale_end - scale_start) * progress
        cw = int(OUTPUT_W * scale)
        ch = int(OUTPUT_H * scale)
        left = (iw - cw) // 2
        top = (ih - ch) // 2

    elif effect == "zoom_out":
        scale_start, scale_end = 0.85, 1.0
        scale = scale_start + (scale_end - scale_start) * progress
        cw = int(OUTPUT_W * scale)
        ch = int(OUTPUT_H * scale)
        left = (iw - cw) // 2
        top = (ih - ch) // 2

    elif effect == "pan_right":
        cw = int(OUTPUT_W * 0.9)
        ch = int(OUTPUT_H * 0.9)
        max_left = iw - cw
        left = int(max_left * progress)
        top = (ih - ch) // 2

    elif effect == "pan_left":
        cw = int(OUTPUT_W * 0.9)
        ch = int(OUTPUT_H * 0.9)
        max_left = iw - cw
        left = int(max_left * (1.0 - progress))
        top = (ih - ch) // 2

    else:  # "none"
        return img.crop((
            (iw - OUTPUT_W) // 2, (ih - OUTPUT_H) // 2,
            (iw + OUTPUT_W) // 2, (ih + OUTPUT_H) // 2
        )).resize((OUTPUT_W, OUTPUT_H), Image.LANCZOS)

    cropped = img.crop((left, top, left + cw, top + ch))
    return cropped.resize((OUTPUT_W, OUTPUT_H), Image.LANCZOS)


# ── Caption drawing ────────────────────────────────────────────────────────────

_CAPTION_FONT = None
_OVERLAY_FONT = None

def _draw_caption(draw: ImageDraw.Draw, text: str, font):
    """Draw white text with black outline at bottom-third position."""
    if not text.strip():
        return

    # Wrap long lines
    words = text.split()
    lines = []
    current = []
    for word in words:
        test = " ".join(current + [word])
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] > OUTPUT_W - 120:
            if current:
                lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))

    line_height = draw.textbbox((0, 0), "A", font=font)[3] + 8
    total_h = line_height * len(lines)
    y_start = int(OUTPUT_H * 0.78) - total_h // 2

    outline_offsets = [(-2, -2), (2, -2), (-2, 2), (2, 2), (0, -3), (0, 3), (-3, 0), (3, 0)]

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_w = bbox[2] - bbox[0]
        x = (OUTPUT_W - line_w) // 2

        for dx, dy in outline_offsets:
            draw.text((x + dx, y_start + dy), line, font=font, fill=(0, 0, 0))
        draw.text((x, y_start), line, font=font, fill=(255, 255, 255))
        y_start += line_height


_OVERLAY_POSITIONS = {
    "top_left":     (60, 60),
    "top_center":   (OUTPUT_W // 2, 60),
    "top_right":    (OUTPUT_W - 60, 60),
    "bottom_left":  (60, OUTPUT_H - 120),
    "bottom_center":(OUTPUT_W // 2, OUTPUT_H - 120),
    "bottom_right": (OUTPUT_W - 60, OUTPUT_H - 120),
    "center":       (OUTPUT_W // 2, OUTPUT_H // 2),
}

def _draw_text_overlay(draw: ImageDraw.Draw, overlay: dict, t: float, font):
    """Draw text overlay if t is within its duration."""
    if not overlay or t > overlay.get("duration_seconds", 0):
        return
    text = overlay.get("text", "")
    position_key = overlay.get("position", "bottom_center")
    x, y = _OVERLAY_POSITIONS.get(position_key, _OVERLAY_POSITIONS["bottom_center"])

    # Semi-transparent background pill — drawn as a filled rectangle
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pad = 16
    rx = x - tw // 2 - pad
    ry = y - th // 2 - pad
    draw.rectangle([rx, ry, rx + tw + pad * 2, ry + th + pad * 2], fill=(0, 0, 0, 160))

    outline_offsets = [(-2, -2), (2, -2), (-2, 2), (2, 2)]
    for dx, dy in outline_offsets:
        draw.text((x - tw // 2 + dx, y - th // 2 + dy), text, font=font, fill=(0, 0, 0))
    draw.text((x - tw // 2, y - th // 2), text, font=font, fill=(255, 230, 100))


# ── Transition helpers ─────────────────────────────────────────────────────────

def _fade_factor(t: float, duration: float, transition_in: str, transition_out: str,
                 fade_duration: float = 0.5) -> float:
    """Return a brightness multiplier [0.0, 1.0] for fade transitions."""
    factor = 1.0
    if transition_in in ("fade", "crossfade") and t < fade_duration:
        factor = min(factor, t / fade_duration)
    if transition_out in ("fade", "crossfade") and t > (duration - fade_duration):
        factor = min(factor, (duration - t) / fade_duration)
    return max(0.0, factor)


# ── Main composition function ──────────────────────────────────────────────────

def compose_segment(
    segment_id: int,
    visual_path: str,
    audio_path: str,
    srt_path: str,
    ken_burns: str,
    text_overlay: dict | None,
    transition_in: str,
    transition_out: str,
    cache_dir: str,
    on_progress=None,
) -> str:
    """
    Compose a single segment into a 1080p MP4.
    Returns the path to the rendered MP4.
    Skips if already cached.
    """
    output_path = os.path.join(cache_dir, f"segment_{segment_id}_final.mp4")

    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        if on_progress:
            on_progress(f"Segment {segment_id} — video already cached, skipping")
        return output_path

    if on_progress:
        on_progress(f"Segment {segment_id} — composing video")

    from moviepy.editor import AudioFileClip, VideoClip

    audio = AudioFileClip(audio_path)
    duration = audio.duration

    # Load base image (fitted to 1920x1080)
    base_img = _load_and_fit(visual_path)
    # Enlarge slightly so Ken Burns crops don't go out of bounds
    pad_w = int(OUTPUT_W * 1.25)
    pad_h = int(OUTPUT_H * 1.25)
    base_img = base_img.resize((pad_w, pad_h), Image.LANCZOS)

    captions = parse_srt(srt_path) if srt_path and os.path.exists(srt_path) else []

    global _CAPTION_FONT, _OVERLAY_FONT
    if _CAPTION_FONT is None:
        _CAPTION_FONT = _get_font(52)
    if _OVERLAY_FONT is None:
        _OVERLAY_FONT = _get_font(64)

    cap_font = _CAPTION_FONT
    ovl_font = _OVERLAY_FONT

    def make_frame(t):
        frame = _ken_burns_crop(base_img, t, duration, ken_burns)

        # Draw captions and overlay onto a PIL Image
        frame_rgba = frame.convert("RGBA")
        overlay_layer = Image.new("RGBA", frame_rgba.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay_layer)

        # Active caption at time t
        active_caption = ""
        for start, end, text in captions:
            if start <= t <= end:
                active_caption = text
                break
        if active_caption:
            _draw_caption(draw, active_caption, cap_font)

        # Text overlay (timed)
        if text_overlay:
            _draw_text_overlay(draw, text_overlay, t, ovl_font)

        # Composite caption layer onto frame
        frame_rgba = Image.alpha_composite(frame_rgba, overlay_layer)
        frame_rgb = frame_rgba.convert("RGB")

        # Apply fade transition brightness
        factor = _fade_factor(t, duration, transition_in, transition_out)
        if factor < 1.0:
            arr = np.array(frame_rgb, dtype=np.float32)
            arr = arr * factor
            frame_rgb = Image.fromarray(arr.astype(np.uint8))

        return np.array(frame_rgb)

    video = VideoClip(make_frame, duration=duration)
    video = video.set_audio(audio)

    Path(cache_dir).mkdir(parents=True, exist_ok=True)

    video.write_videofile(
        output_path,
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        ffmpeg_params=["-crf", "23"],
        logger=None,
        temp_audiofile=os.path.join(cache_dir, f"segment_{segment_id}_temp_audio.m4a"),
    )

    audio.close()
    video.close()

    return output_path
