"""
Stage 5 — Segment composition.
Combines image + audio + Ken Burns motion + burned-in captions + text overlay + transitions.
Outputs an MP4 per segment with dynamic width/height aspect ratios.
"""

import os
import math
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from pipeline.captions import parse_srt

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

def _load_and_fit(img_path: str, width: int, height: int) -> Image.Image:
    """Load image and resize/crop to exactly fill width x height (cover, not letterbox)."""
    img = Image.open(img_path).convert("RGB")
    iw, ih = img.size

    scale = max(width / iw, height / ih)
    new_w = math.ceil(iw * scale)
    new_h = math.ceil(ih * scale)
    img = img.resize((new_w, new_h), Image.BILINEAR)

    left = (new_w - width) // 2
    top = (new_h - height) // 2
    img = img.crop((left, top, left + width, top + height))
    return img


# ── Ken Burns ─────────────────────────────────────────────────────────────────

def _ken_burns_crop(img: Image.Image, t: float, duration: float, effect: str, width: int, height: int) -> Image.Image:
    """
    Return the width x height crop of img at time t for the given Ken Burns effect.
    Works on an image already sized to at least width x height.
    """
    iw, ih = img.size
    progress = t / duration if duration > 0 else 0

    if effect == "zoom_in":
        scale_start, scale_end = 1.0, 0.85
        scale = scale_start + (scale_end - scale_start) * progress
        cw = int(width * scale)
        ch = int(height * scale)
        left = (iw - cw) // 2
        top = (ih - ch) // 2

    elif effect == "zoom_out":
        scale_start, scale_end = 0.85, 1.0
        scale = scale_start + (scale_end - scale_start) * progress
        cw = int(width * scale)
        ch = int(height * scale)
        left = (iw - cw) // 2
        top = (ih - ch) // 2

    elif effect == "pan_right":
        cw = int(width * 0.9)
        ch = int(height * 0.9)
        max_left = iw - cw
        left = int(max_left * progress)
        top = (ih - ch) // 2

    elif effect == "pan_left":
        cw = int(width * 0.9)
        ch = int(height * 0.9)
        max_left = iw - cw
        left = int(max_left * (1.0 - progress))
        top = (ih - ch) // 2

    else:  # "none"
        return img.crop((
            (iw - width) // 2, (ih - height) // 2,
            (iw + width) // 2, (ih + height) // 2
        )).resize((width, height), Image.BILINEAR)

    cropped = img.crop((left, top, left + cw, top + ch))
    return cropped.resize((width, height), Image.BILINEAR)


# ── Caption drawing ────────────────────────────────────────────────────────────

_CAPTION_FONT = None
_OVERLAY_FONT = None

def _draw_caption(draw: ImageDraw.Draw, text: str, font, width: int, height: int):
    """Draw white text with black outline at bottom-third position."""
    if not text.strip():
        return

    # Wrap long lines based on canvas width
    words = text.split()
    lines = []
    current = []
    max_line_w = width - 120
    for word in words:
        test = " ".join(current + [word])
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] > max_line_w:
            if current:
                lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))

    line_height = draw.textbbox((0, 0), "A", font=font)[3] + 8
    total_h = line_height * len(lines)
    
    # Adjust position slightly for vertical screens (9:16)
    vertical_ratio = height / width
    if vertical_ratio > 1.2:
        y_start = int(height * 0.72) - total_h // 2
    else:
        y_start = int(height * 0.78) - total_h // 2

    outline_offsets = [(-2, -2), (2, -2), (-2, 2), (2, 2), (0, -3), (0, 3), (-3, 0), (3, 0)]

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_w = bbox[2] - bbox[0]
        x = (width - line_w) // 2

        for dx, dy in outline_offsets:
            draw.text((x + dx, y_start + dy), line, font=font, fill=(0, 0, 0))
        draw.text((x, y_start), line, font=font, fill=(255, 255, 255))
        y_start += line_height


def _draw_text_overlay(draw: ImageDraw.Draw, overlay: dict, t: float, font, width: int, height: int):
    """Draw text overlay if t is within its duration."""
    if not overlay or t > overlay.get("duration_seconds", 0):
        return
    text = overlay.get("text", "")
    position_key = overlay.get("position", "bottom_center")

    # Calculate dynamic overlay coordinates based on current width/height
    overlay_positions = {
        "top_left":      (60, 60),
        "top_center":    (width // 2, 60),
        "top_right":     (width - 60, 60),
        "bottom_left":   (60, height - 120),
        "bottom_center": (width // 2, height - 120),
        "bottom_right":  (width - 60, height - 120),
        "center":        (width // 2, height // 2),
    }
    
    x, y = overlay_positions.get(position_key, overlay_positions["bottom_center"])

    # Draw background pill
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pad = 16

    # Constrain positioning so text doesn't flow off screen
    if "center" in position_key:
        rx = x - tw // 2 - pad
        tx = x - tw // 2
    elif "left" in position_key:
        rx = x - pad
        tx = x
    else: # right
        rx = x - tw - pad
        tx = x - tw

    ry = y - th // 2 - pad
    ty = y - th // 2

    # Draw rounded rectangle behind overlay
    draw.rounded_rectangle([rx, ry, rx + tw + pad * 2, ry + th + pad * 2], radius=8, fill=(0, 0, 0, 160))

    outline_offsets = [(-2, -2), (2, -2), (-2, 2), (2, 2)]
    for dx, dy in outline_offsets:
        draw.text((tx + dx, ty + dy), text, font=font, fill=(0, 0, 0))
    draw.text((tx, ty), text, font=font, fill=(255, 230, 100))


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


def _overlay_sound_effects(narration_path: str, sfx_list: list, output_audio_path: str, cache_dir: str, on_progress=None) -> str:
    """
    Mix narration audio and multiple sound effects (e.g. whoosh, pop) at specified millisecond offsets.
    Uses a very fast local FFmpeg command.
    """
    if not sfx_list:
        return narration_path

    import subprocess
    import shutil
    
    # Identify SFX search directories
    project_dir = os.path.dirname(os.path.dirname(narration_path))
    sfx_search_paths = [
        os.path.join(project_dir, "assets", "sfx"),
        os.path.join(os.path.dirname(project_dir), "assets", "sfx")
    ]
    
    # Parse inputs and verify which files actually exist
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
        
    # Build single FFmpeg amix command delaying inputs
    cmd = ["ffmpeg", "-y", "-i", narration_path]
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
        else:
            if on_progress:
                on_progress(f"Warning: SFX mixing failed, using clean audio: {res.stderr}")
    except Exception as e:
        if on_progress:
            on_progress(f"Warning: SFX mixing encountered error: {e}")
            
    return narration_path


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
    width: int = 1920,
    height: int = 1080,
    on_progress=None,
    sfx: list = None,
    level1_overlay: dict = None,
) -> str:
    """
    Compose a single segment into an MP4 of resolution width x height.
    Returns the path to the rendered MP4.
    Skips if already cached.
    """
    output_path = os.path.join(cache_dir, f"segment_{segment_id}_final.mp4")

    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        # Check if the cached file has the correct video dimensions
        # Simple safeguard to re-render if ratio changed in settings
        try:
            from moviepy.editor import VideoFileClip
            with VideoFileClip(output_path) as clip:
                if clip.size[0] == width and clip.size[1] == height:
                    if on_progress:
                        on_progress(f"Segment {segment_id} — video already cached with correct dimensions, skipping")
                    return output_path
        except Exception:
            pass

    if on_progress:
        on_progress(f"Segment {segment_id} — composing video ({width}x{height})")

    # Mix sound effects on the audio track if present
    mixed_audio_path = os.path.join(cache_dir, f"segment_{segment_id}_mixed_audio.wav")
    audio_path = _overlay_sound_effects(audio_path, sfx, mixed_audio_path, cache_dir, on_progress)

    from moviepy.editor import AudioFileClip, VideoClip

    audio = AudioFileClip(audio_path)
    duration = audio.duration

    # Check for Static Frame Fast-Path
    has_moving_sprites = False
    if level1_overlay and "sprites" in level1_overlay:
        for sprite in level1_overlay["sprites"]:
            motion = sprite.get("motion", "none")
            if motion and motion.lower() not in ("none", "static"):
                has_moving_sprites = True
                break

    has_no_motion = (ken_burns == "none") or (not ken_burns)
    if has_moving_sprites:
        has_no_motion = False

    has_no_captions = not srt_path or not os.path.exists(srt_path)
    has_no_overlay = not text_overlay
    has_no_transitions = (transition_in in ("none", "cut", "", None)) and (transition_out in ("none", "cut", "", None))

    if has_no_motion and has_no_captions and has_no_overlay and has_no_transitions:
        if on_progress:
            on_progress(f"Segment {segment_id} — Fast-path static frame detected. Running direct FFmpeg compile...")
        
        # Fit image to width/height to make sure aspect ratio is respected
        fit_img_path = os.path.join(cache_dir, f"segment_{segment_id}_fit.jpg")
        fitted_img = _load_and_fit(visual_path, width, height)
        fitted_img.save(fit_img_path, "JPEG", quality=98)

        # Build FFmpeg command to compile static video
        # We will attempt h264_nvenc (NVIDIA) first, then fall back to libx264
        import subprocess
        success = False
        for codec in ["h264_nvenc", "libx264"]:
            if on_progress:
                on_progress(f"Segment {segment_id} — Compiling static frame via FFmpeg with codec: {codec}")
            
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", fit_img_path,
                "-i", audio_path,
                "-c:v", codec,
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-shortest",
                output_path
            ]
            if codec == "h264_nvenc":
                cmd.insert(-1, "-b:v")
                cmd.insert(-1, "4M")
            
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                success = True
                break
            else:
                if on_progress:
                    on_progress(f"Segment {segment_id} — FFmpeg {codec} failed: {res.stderr.strip()[:100]}... falling back.")
        
        audio.close()
        if success:
            if os.path.exists(fit_img_path):
                try:
                    os.remove(fit_img_path)
                except Exception:
                    pass
            return output_path
        else:
            if on_progress:
                on_progress(f"Segment {segment_id} — FFmpeg fast-path failed. Falling back to MoviePy.")
            audio = AudioFileClip(audio_path)

    # Load base image (fitted to target canvas size)
    base_img = _load_and_fit(visual_path, width, height)
    # Enlarge slightly so Ken Burns crops don't go out of bounds
    pad_w = int(width * 1.25)
    pad_h = int(height * 1.25)
    base_img = base_img.resize((pad_w, pad_h), Image.BILINEAR)

    captions = parse_srt(srt_path) if srt_path and os.path.exists(srt_path) else []

    # Dynamic font size based on width (e.g. 52px for 1920w, smaller for vertical/squares)
    caption_font_size = max(24, int(width * 0.027))
    overlay_font_size = max(28, int(width * 0.033))

    cap_font = _get_font(caption_font_size)
    ovl_font = _get_font(overlay_font_size)

    # Load moving sprites once to avoid opening them frame-by-frame (which is slow)
    loaded_sprites = []
    if level1_overlay and "sprites" in level1_overlay:
        project_dir = os.path.dirname(visual_path)
        for sprite in level1_overlay["sprites"]:
            motion = sprite.get("motion", "none")
            if motion and motion.lower() not in ("none", "static"):
                sprite_filename = sprite.get("image")
                if sprite_filename:
                    sprite_path = os.path.join(project_dir, sprite_filename)
                    if not os.path.exists(sprite_path):
                        sprite_path = os.path.join(os.path.dirname(project_dir), "assets", "sprites", sprite_filename)
                    if os.path.exists(sprite_path):
                        try:
                            sprite_img = Image.open(sprite_path).convert("RGBA")
                            scale = sprite.get("scale", 1.0)
                            if scale != 1.0:
                                sw = int(sprite_img.width * scale)
                                sh = int(sprite_img.height * scale)
                                sprite_img = sprite_img.resize((sw, sh), Image.Resampling.LANCZOS)
                            loaded_sprites.append({
                                "image": sprite_img,
                                "target_x": sprite.get("x", 0),
                                "target_y": sprite.get("y", 0),
                                "motion": motion.lower()
                            })
                        except Exception as e:
                            print(f"Error loading moving sprite: {e}")

    def make_frame(t):
        frame = _ken_burns_crop(base_img, t, duration, ken_burns, width, height)

        # Draw captions, overlays, and moving sprites onto a PIL Image
        frame_rgba = frame.convert("RGBA")
        overlay_layer = Image.new("RGBA", frame_rgba.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay_layer)

        # 0. Draw moving sprites
        for s in loaded_sprites:
            m_type = s["motion"]
            tx = s["target_x"]
            ty = s["target_y"]
            s_img = s["image"]
            
            # Resolve coordinates (if percentage float, scale to target canvas)
            if isinstance(tx, float) and tx <= 1.0:
                tx = int(tx * width)
            if isinstance(ty, float) and ty <= 1.0:
                ty = int(ty * height)
                
            cur_x = tx
            cur_y = ty
            
            # Calculate dynamic coordinates based on motion behaviors
            if m_type == "slide_in_left":
                start_x = - (s_img.width // 2)
                duration_sec = min(1.0, duration)
                if t < duration_sec:
                    cur_x = int(start_x + (tx - start_x) * (t / duration_sec))
                else:
                    cur_x = tx
            elif m_type == "slide_in_right":
                start_x = width + (s_img.width // 2)
                duration_sec = min(1.0, duration)
                if t < duration_sec:
                    cur_x = int(start_x + (tx - start_x) * (t / duration_sec))
                else:
                    cur_x = tx
            elif m_type == "bounce":
                bounce_height = 40
                hop = abs(math.sin(t * math.pi * 2.5)) * bounce_height
                cur_y = int(ty - hop)
            elif m_type == "slide_in_left_bounce":
                start_x = - (s_img.width // 2)
                duration_sec = min(1.0, duration)
                if t < duration_sec:
                    cur_x = int(start_x + (tx - start_x) * (t / duration_sec))
                else:
                    cur_x = tx
                bounce_height = 40
                hop = abs(math.sin(t * math.pi * 2.5)) * bounce_height
                cur_y = int(ty - hop)
                
            px = cur_x - s_img.width // 2
            py = cur_y - s_img.height // 2
            
            overlay_layer.paste(s_img, (px, py), s_img)

        # Active caption at time t
        active_caption = ""
        for start, end, text in captions:
            if start <= t <= end:
                active_caption = text
                break
        if active_caption:
            _draw_caption(draw, active_caption, cap_font, width, height)

        # Text overlay (timed)
        if text_overlay:
            _draw_text_overlay(draw, text_overlay, t, ovl_font, width, height)

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

    try:
        if on_progress:
            on_progress(f"Segment {segment_id} — encoding with h264_nvenc GPU acceleration")
        video.write_videofile(
            output_path,
            fps=FPS,
            codec="h264_nvenc",
            audio_codec="aac",
            ffmpeg_params=["-b:v", "4M"],
            logger=None,
            temp_audiofile=os.path.join(cache_dir, f"segment_{segment_id}_temp_audio.m4a"),
        )
    except Exception as e:
        if on_progress:
            on_progress(f"Segment {segment_id} — GPU encoding failed: {e}. Retrying with CPU libx264...")
        video.write_videofile(
            output_path,
            fps=FPS,
            codec="libx264",
            audio_codec="aac",
            preset="ultrafast",
            ffmpeg_params=["-crf", "23", "-threads", "8"],
            logger=None,
            temp_audiofile=os.path.join(cache_dir, f"segment_{segment_id}_temp_audio.m4a"),
        )

    audio.close()
    video.close()

    return output_path
