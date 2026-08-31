"""
Stage 4 — Visual sourcing.
Generates images at the selected aspect ratio: 16:9, 9:16, 1:1, or 4:3.

Routing logic:
  - visual_type == "ai_image"    → Hugging Face FLUX.1-schnell Serverless API
                                    (Falls back to Pollinations.ai FLUX if key is missing/failed)
  - visual_type == "stock_photo" → Pixabay API (requires API key)
  - anything else                → black frame fallback
"""

import os
import time
import json
import base64
import urllib.request
import urllib.parse
import re
import shutil
import unicodedata
from pathlib import Path

from pipeline.magick_processor import (
    process_vignette, process_diptych, process_collage, process_vox_collage,
    process_documentary, process_illustration, process_silhouette
)

PIXABAY_SEARCH_URL = "https://pixabay.com/api/"
POLLINATIONS_URL   = "https://image.pollinations.ai/prompt/{prompt}?width={width}&height={height}&nologo=true&seed={seed}&model=flux"

ASPECT_RATIOS = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:3": (1440, 1080)
}



# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_dimensions(aspect_ratio: str) -> tuple[int, int]:
    return ASPECT_RATIOS.get(aspect_ratio, ASPECT_RATIOS["16:9"])


# Typographic punctuation that NFKD does NOT decompose. An em-dash has no decomposition,
# so normalising alone left it to become "_" — and when the same title was read as cp1252
# instead of UTF-8 it arrived as "â€"" and became "___" instead. That mismatch is what
# produced three separate folders for one episode.
_PUNCT_MAP = str.maketrans({
    "—": "-", "–": "-", "‒": "-", "‐": "-", "‑": "-",
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"',
    "…": "...", " ": " ",
})


def slugify_title(title: str) -> str:
    """
    Stable folder name for a project title.

    Must produce the same slug whatever encoding the title arrived in, so a re-render
    finds the folder it created last time.
    """
    t = (title or "").strip()
    # Repair the classic UTF-8-read-as-cp1252 mojibake ("â€"" for an em-dash). Old titles
    # carry it, and without this the same episode slugs three different ways.
    if "â" in t or "Â" in t or "€" in t:
        try:
            t = t.encode("cp1252", "strict").decode("utf-8", "strict")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    t = unicodedata.normalize("NFKD", t)
    t = t.translate(_PUNCT_MAP)
    # Drop anything still non-ASCII (accents already split off by NFKD, mojibake bytes too)
    t = t.encode("ascii", "ignore").decode("ascii")
    t = re.sub(r"[^\w\-]+", "_", t)
    t = re.sub(r"_+", "_", t).strip("_")
    return t or "my_project"


def _create_black_frame(output_path: str, width: int, height: int):
    from PIL import Image
    img = Image.new("RGB", (width, height), color=(0, 0, 0))
    img.save(output_path, "JPEG", quality=95)







# ── Google Imagen API ─────────────────────────────────────────────────────────

def _fetch_google_imagen_image(
    segment_id: int,
    prompt: str,
    width: int,
    height: int,
    google_api_key: str,
    output_path: str,
    on_progress=None
) -> bool:
    """Generate an image via Google AI Studio Imagen API."""
    if not google_api_key:
        return False

    url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-4.0-generate-001:predict?key={google_api_key}"
    headers = {
        "Content-Type": "application/json"
    }
    
    # Map dimensions to the aspect ratios Imagen accepts. Match on the ratio, not on
    # exact pixel sizes — an exact-size table silently fell through to "1:1" and
    # returned square images the moment the 16:9 default moved from 720p to 1080p.
    ratio = width / height if height else 1.0
    aspect_ratio_str = min(
        (("16:9", 16 / 9), ("9:16", 9 / 16), ("1:1", 1.0), ("4:3", 4 / 3), ("3:4", 3 / 4)),
        key=lambda pair: abs(pair[1] - ratio),
    )[0]

    payload = {
        "instances": [
            {
                "prompt": prompt
            }
        ],
        "parameters": {
            "sampleCount": 1,
            "aspectRatio": aspect_ratio_str,
            "outputMimeType": "image/jpeg"
        }
    }
    body = json.dumps(payload).encode("utf-8")

    for attempt in range(5):
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=90) as resp:
                response_data = json.loads(resp.read().decode("utf-8"))
            
            if "predictions" not in response_data or not response_data["predictions"]:
                if on_progress:
                    on_progress(f"Segment {segment_id} — Google API response error: {response_data}")
                return False
                
            b64_data = response_data["predictions"][0]["bytesBase64Encoded"]
            image_bytes = base64.b64decode(b64_data)
            
            with open(output_path, "wb") as f:
                f.write(image_bytes)
            return True
            
        except urllib.error.HTTPError as he:
            err_body = he.read().decode("utf-8")
            if on_progress:
                on_progress(f"Segment {segment_id} — Google Imagen Attempt {attempt+1} HTTP error {he.code}: {err_body}")
            if attempt < 4:
                sleep_time = (attempt + 1) * 3
                time.sleep(sleep_time)
        except Exception as e:
            if on_progress:
                on_progress(f"Segment {segment_id} — Google Imagen Attempt {attempt+1} failed ({e})")
            if attempt < 4:
                sleep_time = (attempt + 1) * 3
                time.sleep(sleep_time)
            
    return False


# ── Pollinations.ai Fallback ──────────────────────────────────────────────────

def _fetch_pollinations_image(
    segment_id: int,
    prompt: str,
    width: int,
    height: int,
    output_path: str,
    seed: int,
    on_progress=None
) -> bool:
    """Generate a custom-size AI image via Pollinations.ai as a free fallback."""
    encoded = urllib.parse.quote(prompt)
    url = POLLINATIONS_URL.format(prompt=encoded, width=width, height=height, seed=seed)

    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "S2V/1.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()

            if len(data) < 2048:
                if on_progress:
                    on_progress(f"Segment {segment_id} — Pollinations image size too small, retrying…")
                time.sleep(2)
                continue

            with open(output_path, "wb") as f:
                f.write(data)
            return True
        except Exception as e:
            if attempt < 2:
                time.sleep(3)
            else:
                if on_progress:
                    on_progress(f"Segment {segment_id} — Pollinations failed after 3 attempts: {e}")
                return False
    return False

def _generate_placeholder_image(output_path: str, segment_id: int, keyword: str, narration: str, width: int, height: int):
    """Generate a clean dark-themed placeholder card using Pillow."""
    from PIL import Image, ImageDraw, ImageFont
    
    # Create dark grey canvas
    img = Image.new("RGB", (width, height), color=(30, 30, 35))
    draw = ImageDraw.Draw(img)
    
    # Draw simple border
    border_color = (70, 70, 80)
    draw.rectangle([20, 20, width - 20, height - 20], outline=border_color, width=3)
    
    title_text = f"SEGMENT #{segment_id}"
    keyword_text = f"Visual Prompt: {keyword}"
    
    # Clip narration text for preview
    narr_preview = narration.strip()
    if len(narr_preview) > 100:
        narr_preview = narr_preview[:97] + "..."
    narr_text = f"Narration: {narr_preview}"
    
    # We draw text using basic default fonts to avoid font loading failures on Windows
    try:
        font_large = ImageFont.truetype("arial.ttf", 60)
        font_medium = ImageFont.truetype("arial.ttf", 40)
        font_small = ImageFont.truetype("arial.ttf", 28)
    except IOError:
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_small = ImageFont.load_default()
        
    # Draw Segment ID
    draw.text((80, 80), title_text, fill=(240, 196, 25), font=font_large) # gold color
    
    # Draw B-roll Keyword
    draw.text((80, 200), keyword_text, fill=(255, 255, 255), font=font_medium)
    
    # Draw Narration Preview wrapped
    words = narr_text.split()
    lines = []
    current_line = []
    for word in words:
        current_line.append(word)
        if len(" ".join(current_line)) > 60:
            lines.append(" ".join(current_line))
            current_line = []
    if current_line:
        lines.append(" ".join(current_line))
        
    y_offset = 350
    for line in lines[:8]:
        draw.text((80, y_offset), line, fill=(180, 180, 190), font=font_small)
        y_offset += 45
        
    # Draw footer instruction
    footer_text = "[ Replace this file with your generated image ]"
    draw.text((width // 2 - 250, height - 80), footer_text, fill=(100, 100, 110), font=font_small)
    
    img.save(output_path, "JPEG", quality=95)


def _apply_level1_overlay(input_path: str, output_path: str, overlay: dict, width: int, height: int, crop: dict = None):
    """
    Apply Pillow drawing overlays (labels, highlights, arrows) and crops/sprites on top of the input image.
    This enables reusing base assets (like maps or character portraits) and manipulating them programmatically.
    """
    import os
    import math
    from PIL import Image, ImageDraw
    from pipeline.composer import _get_font
    
    # 0. Load raw source image
    raw_img = Image.open(input_path)
    img_w, img_h = raw_img.size
    
    # 0.1 Apply Crop if specified
    if crop:
        # Resolve coordinates (support both fractions 0.0-1.0 and absolute pixels)
        cx = crop.get("x", 0)
        cy = crop.get("y", 0)
        cw = crop.get("w", img_w)
        ch = crop.get("h", img_h)
        
        # If fraction/percentage is used, scale to actual pixel dimensions
        if isinstance(cx, float) and cx <= 1.0:
            cx = int(cx * img_w)
        if isinstance(cy, float) and cy <= 1.0:
            cy = int(cy * img_h)
        if isinstance(cw, float) and cw <= 1.0:
            cw = int(cw * img_w)
        if isinstance(ch, float) and ch <= 1.0:
            ch = int(ch * img_h)
            
        # Ensure values don't exceed boundaries
        cx = max(0, min(cx, img_w - 1))
        cy = max(0, min(cy, img_h - 1))
        cw = max(1, min(cw, img_w - cx))
        ch = max(1, min(ch, img_h - cy))
        
        raw_img = raw_img.crop((cx, cy, cx + cw, cy + ch))
    
    # 0.2 Fit cropped/raw image to target canvas size using "cover" cropping
    img = raw_img.copy()
    target_ratio = width / height
    current_w, current_h = img.size
    current_ratio = current_w / current_h
    
    if current_ratio > target_ratio:
        # Image is too wide
        new_w = int(target_ratio * current_h)
        left = (current_w - new_w) // 2
        img = img.crop((left, 0, left + new_w, current_h))
    elif current_ratio < target_ratio:
        # Image is too tall
        new_h = int(current_w / target_ratio)
        top = (current_h - new_h) // 2
        img = img.crop((0, top, current_w, top + new_h))
        
    img = img.resize((width, height), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(img)
    
    # Helper for drawing text outlines for high readability
    def draw_text_with_outline(text, x, y, font, fill_color, outline_color="black"):
        outline_offsets = [(-1, -1), (1, -1), (-1, 1), (1, 1)]
        for dx, dy in outline_offsets:
            draw.text((x + dx, y + dy), text, font=font, fill=outline_color)
        draw.text((x, y), text, font=font, fill=fill_color)

    # 1. Draw Highlights (Circles)
    for hl in overlay.get("highlights", []):
        x = hl.get("x", 0)
        y = hl.get("y", 0)
        r = hl.get("radius", 15)
        color = hl.get("color", "red")
        fill_opt = hl.get("fill", False)
        
        color_map = {
            "red": (255, 0, 0, 180),
            "blue": (0, 0, 255, 180),
            "green": (0, 255, 0, 180),
            "yellow": (255, 255, 0, 180),
            "white": (255, 255, 255, 180),
            "black": (0, 0, 0, 180)
        }
        c = color_map.get(color.lower(), color)
        
        if fill_opt:
            overlay_img = Image.new("RGBA", img.size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay_img)
            overlay_draw.ellipse([x - r, y - r, x + r, y + r], fill=c)
            img = Image.alpha_composite(img.convert("RGBA"), overlay_img).convert("RGB")
            draw = ImageDraw.Draw(img)
        else:
            draw.ellipse([x - r, y - r, x + r, y + r], outline=c, width=4)

    # 2. Draw Arrows / Lines (Troop movements or focus paths)
    for line in overlay.get("arrows", []):
        x1 = line.get("x1", 0)
        y1 = line.get("y1", 0)
        x2 = line.get("x2", 0)
        y2 = line.get("y2", 0)
        color = line.get("color", "blue")
        
        color_map = {"red": (255, 0, 0), "blue": (0, 0, 255), "green": (0, 255, 0), "yellow": (255, 255, 0)}
        c = color_map.get(color.lower(), color)
        
        draw.line([x1, y1, x2, y2], fill=c, width=5)
        
        # Draw arrow head
        angle = math.atan2(y2 - y1, x2 - x1)
        arrow_len = 15
        arrow_angle = math.pi / 6
        ax1 = x2 - arrow_len * math.cos(angle - arrow_angle)
        ay1 = y2 - arrow_len * math.sin(angle - arrow_angle)
        ax2 = x2 - arrow_len * math.cos(angle + arrow_angle)
        ay2 = y2 - arrow_len * math.sin(angle + arrow_angle)
        draw.polygon([x2, y2, ax1, ay1, ax2, ay2], fill=c)

    # 3. Draw Sprites (Transparent character images pasted on base)
    for sprite in overlay.get("sprites", []):
        sprite_filename = sprite.get("image")
        if not sprite_filename:
            continue
            
        motion = sprite.get("motion", "none")
        if motion and motion.lower() not in ("none", "static"):
            continue
            
        # Sprites can be in project_dir or assets/sprites/ or cache/
        project_dir = os.path.dirname(input_path)
        sprite_path = os.path.join(project_dir, sprite_filename)
        
        if not os.path.exists(sprite_path):
            sprite_path = os.path.join(os.path.dirname(project_dir), "assets", "sprites", sprite_filename)
            
        if os.path.exists(sprite_path):
            try:
                sprite_img = Image.open(sprite_path).convert("RGBA")
                
                # Dynamic scaling
                scale = sprite.get("scale", 1.0)
                if scale != 1.0:
                    sw = int(sprite_img.width * scale)
                    sh = int(sprite_img.height * scale)
                    sprite_img = sprite_img.resize((sw, sh), Image.Resampling.LANCZOS)
                    
                # Calculate coordinates (placed relative to center of the sprite)
                sx = sprite.get("x", 0)
                sy = sprite.get("y", 0)
                
                # If percentages (floats between 0.0 and 1.0) are used, scale to target canvas
                if isinstance(sx, float) and sx <= 1.0:
                    sx = int(sx * width)
                if isinstance(sy, float) and sy <= 1.0:
                    sy = int(sy * height)
                    
                # Align sprite center to sx, sy
                px = sx - sprite_img.width // 2
                py = sy - sprite_img.height // 2
                
                # Paste with transparency alpha channel
                img_rgba = img.convert("RGBA")
                img_rgba.paste(sprite_img, (px, py), sprite_img)
                img = img_rgba.convert("RGB")
                draw = ImageDraw.Draw(img) # Reinitialize draw for subsequent overlays
            except Exception as e:
                print(f"Error drawing sprite {sprite_filename}: {e}")

    # 4. Draw Labels (Character names, locations)
    for lbl in overlay.get("labels", []):
        text = lbl.get("text", "")
        x = lbl.get("x", 0)
        y = lbl.get("y", 0)
        color = lbl.get("color", "white")
        size = lbl.get("size", 24)
        font = _get_font(size)
        
        color_map = {"white": (255, 255, 255), "yellow": (255, 230, 100), "red": (255, 100, 100), "blue": (100, 100, 255)}
        c = color_map.get(color.lower(), color)
        
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        tx = x - tw // 2
        ty = y - (bbox[3] - bbox[1]) // 2
        draw_text_with_outline(text, tx, ty, font, c)

    img.convert("RGB").save(output_path, "JPEG", quality=95)


def _convert_white_to_transparent(input_path: str, output_path: str):
    """
    Convert an image with a solid white background into a transparent PNG.
    """
    from PIL import Image
    try:
        img = Image.open(input_path).convert("RGBA")
        datas = img.getdata()
        
        new_data = []
        for item in datas:
            # If color is close to pure white, convert alpha to 0
            if item[0] > 230 and item[1] > 230 and item[2] > 230:
                new_data.append((255, 255, 255, 0))
            else:
                new_data.append(item)
                
        img.putdata(new_data)
        img.save(output_path, "PNG")
        return True
    except Exception as e:
        print(f"Error keying background for {input_path}: {e}")
        return False


# ── Public Entry Point ─────────────────────────────────────────────────────────

def segment_keyword(seg: dict) -> str:
    """
    The image subject for a segment, from either schema version.

    v2 scripts carry it on shots[0].query; only v1 has b_roll_keyword. Reading
    one field alone produced prompts with no subject at all — "Segment 1: , 7th
    century Arabian Peninsula, ..." — and a bare seg["b_roll_keyword"] in the
    orchestrator failed every segment of every AI-planned script outright.
    """
    shots = seg.get("shots") or []
    return (
        seg.get("b_roll_keyword")
        or (shots[0].get("query") if shots else "")
        or ""
    ).strip()


def segment_pin(seg: dict):
    """
    The image the user chose for this segment, or None.

    The storyboard writes pins to shots[0].pin; v1 scripts use use_base_image.
    Without this the visuals stage re-searched for a shot the user had already
    settled, and a pinned gap still failed the render.
    """
    shots = seg.get("shots") or []
    if shots:
        if shots[0].get("source") == "pin":
            pinned = (shots[0].get("pin") or "").strip()
            if pinned:
                return pinned
        # What the storyboard displayed for this shot. Honouring it keeps the
        # render identical to the board the user approved; re-running retrieval
        # here could quietly pick a different image than the one they saw.
        resolved = (shots[0].get("resolved") or "").strip()
        if resolved:
            return resolved
    return seg.get("use_base_image")


def fetch_visual(
    segment_id: int,
    keyword: str,
    narration: str,
    cache_dir: str,
    google_api_key: str = "",
    aspect_ratio: str = "16:9",
    render_id: str = "",
    video_title: str = "",
    visual_style: str = "",
    on_progress=None,
    visual_type: str = "ai_image",
    magick_filter: str = "vignette",
    use_base_image: str = None,
    use_base_image_a: str = None,
    use_base_image_b: str = None,
    character_bible: dict = None,
    level1_overlay: dict = None,
    crop: dict = None,
    auto_generate: bool = False,
    min_score: float = None,
    exclude_paths: set = None,
    series_slug: str = None,
    on_library_hit=None,
    style_preset: str = "",
    project_brief: str = "",
    visual_description: str = None,
    #: The project's chosen working folder, when it has one. Without this the
    #: render searched the whole library while the board searched the folder,
    #: so a picture the board found was unreachable at render time.
    work_folder: str = None,
    #: The project's own world anchor, or None to let the series pack supply
    #: it. Never visual_style - that is the label of the picked look.
    world_anchor: str = None,
    prompt_override: str = None,
    apply_era: bool = True,
) -> str:
    """
    Fetch or generate a visual for this segment at the correct aspect ratio.
    Looks inside the local manual projects directory projects/<title_slug>/.
    Generates structured Pillow placeholders if no manual images exist yet.

    on_library_hit: optional callable(library_relative_path). Called when a library
    image is retrieved for this segment, or when a newly generated image joins the
    library. The caller decides whether the render completed; this only reports use.
    """
    from pipeline import library

    # Fall back to the pack's calibrated floor, not a literal. A hardcoded 0.26 here
    # made the renderer accept images the storyboard had already called gaps —
    # islamic_history calibrates to 0.2796, so anything scoring 0.26–0.2796 was a
    # gap on screen and a match on disk.
    if min_score is None:
        min_score = library.get_calibrated_min_score(series_slug=series_slug)

    output_path = os.path.join(cache_dir, f"segment_{segment_id}_visual.jpg")
    width, height = _get_dimensions(aspect_ratio)

    project_slug = slugify_title(video_title)

    project_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "projects", project_slug)
    os.makedirs(project_dir, exist_ok=True)

    # Check and generate any missing sprites in the level1_overlay
    if level1_overlay and "sprites" in level1_overlay:
        for sprite in level1_overlay["sprites"]:
            sprite_filename = sprite.get("image")
            if not sprite_filename:
                continue
            
            sprite_path = os.path.join(project_dir, sprite_filename)
            if not os.path.exists(sprite_path):
                # Search for it in character bible
                desc = sprite_filename.rsplit(".", 1)[0]
                bible_match = None
                if character_bible:
                    for k, v in character_bible.items():
                        if k.lower() in desc.lower() or desc.lower() in k.lower():
                            bible_match = v
                            break
                
                char_prompt = f"flat vector stickman cartoon icon of {bible_match if bible_match else desc.replace('_', ' ')}, isolated on a pure white background"
                if on_progress:
                    on_progress(f"Segment {segment_id} — Auto-generating missing sprite asset: {sprite_filename}")
                
                # Fetch temporary JPG from Pollinations or Google Imagen
                temp_jpg = os.path.join(cache_dir, f"temp_{sprite_filename.replace('.png', '.jpg')}")
                
                success = False
                if google_api_key:
                    success = _fetch_google_imagen_image(segment_id + 900, char_prompt, 512, 512, google_api_key, temp_jpg, on_progress)
                if not success:
                    success = _fetch_pollinations_image(segment_id + 900, char_prompt, 512, 512, temp_jpg, seed=segment_id*45, on_progress=on_progress)
                
                if success and os.path.exists(temp_jpg):
                    # Convert to transparent PNG
                    key_success = _convert_white_to_transparent(temp_jpg, sprite_path)
                    try:
                        os.remove(temp_jpg)
                    except:
                        pass
                    if key_success and on_progress:
                        on_progress(f"Segment {segment_id} — Successfully converted {sprite_filename} to transparent PNG")
                else:
                    # Fallback: create a small transparent placeholder
                    if on_progress:
                        on_progress(f"Segment {segment_id} — Warning: failed to generate sprite, creating dummy shape")
                    try:
                        from PIL import ImageDraw
                        dummy = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
                        d_draw = ImageDraw.Draw(dummy)
                        d_draw.rectangle([10, 10, 90, 90], fill=(255, 0, 0, 180), outline="white", width=2)
                        dummy.save(sprite_path)
                    except Exception as e:
                        print(f"Error creating dummy sprite: {e}")

    # Check if a manual image has been placed by the user
    if magick_filter in ["diptych", "collage"]:
        base_a = use_base_image_a if use_base_image_a else f"{segment_id}a.jpg"
        base_b = use_base_image_b if use_base_image_b else f"{segment_id}b.jpg"
        path_a = os.path.join(project_dir, base_a)
        path_b = os.path.join(project_dir, base_b)
        
        if not os.path.exists(path_a) and not os.path.exists(path_a.replace(".jpg", ".png")):
            if visual_type == "ai_image":
                prompt_a = library.compose_gap_prompt(
                    shot_query=f"{keyword} (Left part)",
                    world_anchor=world_anchor,
                    character_bible=character_bible,
                    script_context=narration,
                    series_slug=series_slug,
                    project_title=video_title,
                    visual_type=style_preset,
                    project_brief=project_brief,
                    visual_description=f"{visual_description} (Left part)" if visual_description else None,
                )
                success = False
                if google_api_key:
                    if on_progress: on_progress(f"Segment {segment_id} — Fetching AI image A via Google Imagen")
                    success = _fetch_google_imagen_image(segment_id, prompt_a, width, height, google_api_key, path_a, on_progress)
                if not success:
                    if on_progress: on_progress(f"Segment {segment_id} — Fetching AI image A via Pollinations")
                    success = _fetch_pollinations_image(segment_id, prompt_a, width, height, path_a, seed=segment_id*10, on_progress=on_progress)
                if not success:
                    if on_progress: on_progress(f"Segment {segment_id} — Generating placeholder A")
                    _generate_placeholder_image(path_a, f"{segment_id}a", keyword, narration, width, height)
            else:
                if on_progress: on_progress(f"Segment {segment_id} — Generating placeholder A")
                _generate_placeholder_image(path_a, f"{segment_id}a", keyword, narration, width, height)
        if not os.path.exists(path_b) and not os.path.exists(path_b.replace(".jpg", ".png")):
            if visual_type == "ai_image":
                prompt_b = library.compose_gap_prompt(
                    shot_query=f"{keyword} (Right part)",
                    world_anchor=world_anchor,
                    character_bible=character_bible,
                    script_context=narration,
                    series_slug=series_slug,
                    project_title=video_title,
                    visual_type=style_preset,
                    project_brief=project_brief,
                    visual_description=f"{visual_description} (Right part)" if visual_description else None,
                )
                success = False
                if google_api_key:
                    if on_progress: on_progress(f"Segment {segment_id} — Fetching AI image B via Google Imagen")
                    success = _fetch_google_imagen_image(segment_id, prompt_b, width, height, google_api_key, path_b, on_progress)
                if not success:
                    if on_progress: on_progress(f"Segment {segment_id} — Fetching AI image B via Pollinations")
                    success = _fetch_pollinations_image(segment_id, prompt_b, width, height, path_b, seed=segment_id*11, on_progress=on_progress)
                if not success:
                    if on_progress: on_progress(f"Segment {segment_id} — Generating placeholder B")
                    _generate_placeholder_image(path_b, f"{segment_id}b", keyword, narration, width, height)
            else:
                if on_progress: on_progress(f"Segment {segment_id} — Generating placeholder B")
                _generate_placeholder_image(path_b, f"{segment_id}b", keyword, narration, width, height)
            
        actual_a = path_a.replace(".jpg", ".png") if os.path.exists(path_a.replace(".jpg", ".png")) else path_a
        actual_b = path_b.replace(".jpg", ".png") if os.path.exists(path_b.replace(".jpg", ".png")) else path_b

        needs_update = True
        if os.path.exists(output_path):
            if os.path.getmtime(output_path) > max(os.path.getmtime(actual_a), os.path.getmtime(actual_b)):
                needs_update = False

        if needs_update:
            if on_progress:
                on_progress(f"Segment {segment_id} — Applying ImageMagick filter: {magick_filter}")
            if magick_filter == "diptych":
                process_diptych(actual_a, actual_b, output_path, width, height)
            else:
                process_collage(actual_a, actual_b, output_path, width, height)
    else:
        # A storyboard pin names a file in the library, not in the project folder.
        # Stage it under the segment's own name so everything below is unchanged,
        # and so the shot the user chose is the shot that renders.
        pinned_abs = library.resolve_library_path(use_base_image) if use_base_image else None
        if pinned_abs:
            Path(project_dir).mkdir(parents=True, exist_ok=True)
            staged = os.path.join(project_dir, f"{segment_id}.jpg")
            shutil.copy(pinned_abs, staged)
            if on_progress:
                on_progress(f"Segment {segment_id} — using your chosen image: {use_base_image}")
            if on_library_hit:
                on_library_hit(str(use_base_image).replace("\\", "/"))
            # Fall through with the staged filename so the retrieval branch is
            # skipped and the usual treatment still applies.
            use_base_image = f"{segment_id}.jpg"

        base_img = use_base_image if use_base_image else f"{segment_id}.jpg"
        if not base_img.endswith(".jpg") and not base_img.endswith(".png"):
            base_img += ".jpg"

        jpg_path = os.path.join(project_dir, base_img)
        base_img_png = base_img.rsplit(".", 1)[0] + ".png" if "." in base_img else base_img + ".png"
        png_path = os.path.join(project_dir, base_img_png)
        manual_path = png_path if os.path.exists(png_path) else jpg_path

        if not os.path.exists(manual_path):
            # Library-first lookup.
            #
            # Search on the planner's sentence when there is one. The keyword is
            # two or three nouns pulled out by extract_keyword — measured, five
            # consecutive shots in one project all searched "Adam Muslim human",
            # which scored 0.2439 against a 0.2796 floor and matched nothing. The
            # visual description is a sentence about the picture, which is what
            # the image embeddings were built from.
            search_query = (visual_description or "").strip() or keyword

            # A working folder is a decision, not a filter. When the user has put
            # the pictures for this film in one folder, the question is "which of
            # these fits best", not "is this good enough against a library of
            # 700". The floor is calibrated for the second question: it rejected
            # a murmuration image that had correctly ranked first for a shot
            # about a flock of birds, scoring 0.2358 against 0.2796.
            using_work_folder = bool(work_folder) and os.path.isdir(str(work_folder))
            effective_min = 0.0 if using_work_folder else min_score

            lib_results = library.search(
                search_query, k=1, exclude=exclude_paths or set(),
                min_score=effective_min,
                folder=work_folder if using_work_folder else None,
            )
            best_path, best_score = lib_results[0] if lib_results else (None, 0.0)

            if best_path and best_score >= effective_min:
                abs_lib_path = os.path.join(library.ROOT, best_path)
                if os.path.exists(abs_lib_path):
                    shutil.copy(abs_lib_path, jpg_path)
                    manual_path = jpg_path
                    if on_library_hit:
                        on_library_hit(best_path)
                    if on_progress:
                        on_progress(f"Segment {segment_id} — Found library match: {best_path} (score: {best_score:.2f})")
            
            if not os.path.exists(manual_path):
                if prompt_override and prompt_override.strip():
                    composed_prompt = prompt_override.strip()
                else:
                    composed_prompt = library.compose_gap_prompt(
                        shot_query=keyword,
                        world_anchor=world_anchor,
                        character_bible=character_bible,
                        script_context=narration,
                        series_slug=series_slug,
                        project_title=video_title,
                        visual_type=style_preset,
                        project_brief=project_brief,
                        visual_description=visual_description,
                        apply_era=apply_era,
                    )
                if not auto_generate:
                    raise ValueError(
                        f"Library miss for segment {segment_id} query '{search_query[:60]}' "
                        f"(best score: {best_score:.2f} < {effective_min}). "
                        f"Composed prompt:\n{composed_prompt}"
                    )
                else:
                    if visual_type == "ai_image":
                        prompt = composed_prompt
                        success = False
                        if google_api_key:
                            if on_progress: on_progress(f"Segment {segment_id} — Fetching AI image via Google Imagen")
                            success = _fetch_google_imagen_image(segment_id, prompt, width, height, google_api_key, jpg_path, on_progress)
                        if not success:
                            if on_progress: on_progress(f"Segment {segment_id} — Fetching AI image via Pollinations")
                            success = _fetch_pollinations_image(segment_id, prompt, width, height, jpg_path, seed=segment_id*100, on_progress=on_progress)
                        if not success:
                            if on_progress: on_progress(f"Segment {segment_id} — Generating placeholder")
                            _generate_placeholder_image(jpg_path, segment_id, keyword, narration, width, height)
                    else:
                        if on_progress: on_progress(f"Segment {segment_id} — Generating placeholder")
                        _generate_placeholder_image(jpg_path, segment_id, keyword, narration, width, height)

                    # Newly generated image joins the library, manifest, and index
                    if os.path.exists(jpg_path):
                        import hashlib
                        with open(jpg_path, "rb") as f:
                            img_data = f.read()
                        fname = hashlib.sha1(img_data).hexdigest()[:12] + ".jpg"
                        lib_target = os.path.join(library.IMAGES_DIR, fname)
                        if not os.path.exists(lib_target):
                            os.makedirs(library.IMAGES_DIR, exist_ok=True)
                            shutil.copy(jpg_path, lib_target)
                            
                        # Record in manifest
                        manifest_record = {
                            "path": f"library/images/{fname}",
                            "prompt": keyword,
                            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")
                        }
                        with open(library.MANIFEST_PATH, "a", encoding="utf-8") as mf:
                            mf.write(json.dumps(manifest_record) + "\n")

                        if on_library_hit:
                            on_library_hit(f"library/images/{fname}")

                        library.reindex(force=True)

                    manual_path = jpg_path
            
        needs_update = True
        if os.path.exists(output_path):
            if os.path.getmtime(output_path) > os.path.getmtime(manual_path):
                needs_update = False

        if needs_update:
            if level1_overlay or crop:
                if on_progress:
                    on_progress(f"Segment {segment_id} — Applying Level 1 overlays & crops on base image")
                _apply_level1_overlay(manual_path, output_path, level1_overlay or {}, width, height, crop)
            elif magick_filter in ["none", None, "null"]:
                if on_progress:
                    on_progress(f"Segment {segment_id} — Skipping filter, copying file")
                shutil.copy(manual_path, output_path)
            elif magick_filter == "diptych":
                if on_progress:
                    on_progress(f"Segment {segment_id} — Applying Diptych filter")
                process_diptych(manual_path, output_path, width, height)
            elif magick_filter == "collage":
                if on_progress:
                    on_progress(f"Segment {segment_id} — Applying Collage filter")
                process_collage(manual_path, output_path, width, height)
            elif magick_filter in ["vox_collage", "vox_paper_collage", "vox"] or (visual_style and "vox" in visual_style.lower()):
                if on_progress:
                    on_progress(f"Segment {segment_id} — Applying Vox Paper-Collage filter")
                try:
                    process_vox_collage(manual_path, output_path, width, height)
                except Exception as e:
                    if on_progress:
                        on_progress(f"Segment {segment_id} — Vox filter failed ({e}), falling back to copy")
                    shutil.copy(manual_path, output_path)
            elif magick_filter == "documentary":
                if on_progress:
                    on_progress(f"Segment {segment_id} — Applying Documentary filter")
                process_documentary(manual_path, output_path, width, height)
            elif magick_filter == "illustration":
                if on_progress:
                    on_progress(f"Segment {segment_id} — Applying Illustration filter")
                process_illustration(manual_path, output_path, width, height)
            elif magick_filter == "silhouette":
                if on_progress:
                    on_progress(f"Segment {segment_id} — Applying Silhouette filter")
                process_silhouette(manual_path, output_path, width, height)
            else:
                if on_progress:
                    on_progress(f"Segment {segment_id} — Applying filter: {magick_filter}")
                try:
                    process_vignette(manual_path, output_path, width, height)
                except Exception:
                    shutil.copy(manual_path, output_path)

    # `image_prompts.txt` is written by `initialize_project_sourcing`, once, at
    # plan and save time — one line per picture, numbered in film order. This
    # function used to rewrite the same file per segment as it rendered,
    # numbering by segment. Two writers with two different numbering schemes
    # cannot both be right, and the render-time one overwrote the numbering the
    # manual route depends on.

    return output_path


def initialize_project_sourcing(script_dict: dict) -> str:
    """
    Initialize the project folder, write/update image_prompts.txt, and create placeholder images.
    This is called during the planning and save phases to support offline manual visuals generation.
    """
    from pipeline import library  # only imported inside fetch_visual before, so this raised NameError

    proj = script_dict.get("project", {})
    title = proj.get("title", "My Video")
    aspect_ratio = proj.get("aspect_ratio", "16:9")
    visual_style = proj.get("visual_style", "")
    apply_era = proj.get("apply_era", True)
    # visual_style is the label of the picked look, never a setting. Passing it
    # as the anchor printed the style name into the prompt's setting slot.
    from pipeline.library import project_world_anchor
    world_anchor = project_world_anchor(proj)
    character_bible = proj.get("character_bible", {})
    
    project_slug = slugify_title(title)
        
    project_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "projects", project_slug)
    os.makedirs(project_dir, exist_ok=True)
    
    width, height = _get_dimensions(aspect_ratio)
    
    prompts_file = os.path.join(project_dir, "image_prompts.txt")
    lines = []
    
    for seg in script_dict.get("segments", []):
        segment_id = seg["segment_id"]
        keyword = segment_keyword(seg)
        narration = seg.get("narration", "")
        magick_filter = seg.get("magick_filter", "vignette")

        # 1. Generate placeholder if neither jpg nor png exists
        if magick_filter in ["diptych", "collage"]:
            base_a = seg.get("use_base_image_a", f"{segment_id}a.jpg")
            if not base_a.endswith(".jpg") and not base_a.endswith(".png"):
                base_a += ".jpg"
            path_a_jpg = os.path.join(project_dir, base_a)
            base_a_png = base_a.rsplit(".", 1)[0] + ".png"
            path_a_png = os.path.join(project_dir, base_a_png)
            if not os.path.exists(path_a_jpg) and not os.path.exists(path_a_png):
                _generate_placeholder_image(path_a_jpg, f"Base A ({base_a})", keyword, narration, width, height)
                
            base_b = seg.get("use_base_image_b", f"{segment_id}b.jpg")
            if not base_b.endswith(".jpg") and not base_b.endswith(".png"):
                base_b += ".jpg"
            path_b_jpg = os.path.join(project_dir, base_b)
            base_b_png = base_b.rsplit(".", 1)[0] + ".png"
            path_b_png = os.path.join(project_dir, base_b_png)
            if not os.path.exists(path_b_jpg) and not os.path.exists(path_b_png):
                _generate_placeholder_image(path_b_jpg, f"Base B ({base_b})", keyword, narration, width, height)
        else:
            base_img = seg.get("use_base_image", f"{segment_id}.jpg")
            if not base_img.endswith(".jpg") and not base_img.endswith(".png"):
                base_img += ".jpg"
            jpg_path = os.path.join(project_dir, base_img)
            base_img_png = base_img.rsplit(".", 1)[0] + ".png"
            png_path = os.path.join(project_dir, base_img_png)
            if not os.path.exists(jpg_path) and not os.path.exists(png_path):
                _generate_placeholder_image(jpg_path, f"Base ({base_img})", keyword, narration, width, height)
            
    # 2. One line per picture the film actually makes, numbered from 1 in film
    #    order. It used to be one line per segment, so a 200-segment script cut
    #    to 40 images produced 200 prompts for 40 pictures and the numbering
    #    meant nothing. Same list `apply_external_prompts` binds from, so
    #    prompt n, n.jpg and the nth picture are the same shot.
    series_slug = proj.get("series_slug")
    for idx, (seg, shot) in enumerate(library.picture_owning_shots(script_dict)):
        narration = seg.get("narration", "") or ""
        prompt_override = (shot.get("prompt_override")
                           or seg.get("prompt_override"))
        if prompt_override and prompt_override.strip():
            prompt_desc = prompt_override.strip()
        else:
            prompt_desc = library.compose_gap_prompt(
                shot_query=shot.get("query") or segment_keyword(seg),
                world_anchor=world_anchor,
                character_bible=character_bible,
                script_context=narration,
                series_slug=series_slug,
                project_title=title,
                visual_type=proj.get("visual_type", ""),
                project_brief=proj.get("project_brief", ""),
                # The shot's own description leads the prompt. Reading it off
                # the segment found nothing on the shots that carry it.
                visual_description=shot.get("visual_description"),
                # The picture's index across the whole film, so the framing
                # cycle varies instead of returning entry one every time.
                shot_position=idx,
                apply_era=apply_era,
            )
        lines.append(f"{idx + 1}. {prompt_desc}")

    # Write image_prompts.txt
    try:
        with open(prompts_file, "w", encoding="utf-8") as pf:
            for line in lines:
                pf.write(line + "\n")
    except Exception as e:
        print(f"Failed to write image_prompts.txt: {e}")
        
    return project_dir



def write_prompt_request(script_dict: dict) -> str:
    """
    The request to hand an outside AI, so it writes the prompts this film needs.

    The owner's fear, in his words: the app segments the script the way it
    understands, and an outside AI asked to write prompts from the same script
    has no idea how it was cut up. He is right, and the answer is that the AI
    does not have to guess — the app already knows, and already builds exactly
    this request when it calls a model itself. This writes it to a file instead
    of sending it, so the whole route works with no API key at all:

        plan  ->  prompt_request.txt  ->  any AI chat  ->  paste the reply back
              ->  make the images, numbered  ->  point the app at the folder

    Numbering is the contract. Moment n here is prompt n in the paste box, is
    n.jpg in the folder, is the nth picture in the film.
    """
    from pipeline import library
    from pipeline.shot_description import _build_instruction

    proj = script_dict.get("project", {})
    title = proj.get("title", "My Video")
    project_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "projects", slugify_title(title))
    os.makedirs(project_dir, exist_ok=True)

    series_slug = proj.get("series_slug")
    try:
        cfg = library.get_series_config(series_slug=series_slug, project_title=title)
    except Exception:
        cfg = {}

    owning = library.picture_owning_shots(script_dict)
    count = len(owning)

    # The look the app would have added itself, stated once so the outside AI
    # can put it on every prompt and the pictures match the niche.
    preset = library.resolve_style_preset(cfg, proj.get("visual_type") or "")
    look = (preset or {}).get("prompt") or (cfg.get("style_block") or "").strip()

    lines = [
        "HOW TO USE THIS FILE",
        "",
        f"1. Copy everything below the line and paste it into any AI chat.",
        f"2. It will reply with {count} numbered image prompts.",
        f"3. Paste that reply into Smart Studio -> Storyboard -> Paste External Prompts.",
        f"4. Make one image per prompt. Name them 1.jpg, 2.jpg ... {count}.jpg.",
        f"5. Put them in one folder and point the app at it.",
        "",
        f"This film needs exactly {count} pictures. Keep the numbering — prompt 7,",
        f"7.jpg and the 7th picture in the film are the same moment.",
        "",
        "=" * 70,
        "",
    ]

    # The recipe, and the rules that keep a reply usable, exactly as the app
    # would send them to a model.
    lines.append(_build_instruction(cfg))
    if look:
        lines += ["", f"End every prompt with this look, word for word: {look}"]

    narrations = [(seg.get("narration") or "").strip()
                  for seg in (script_dict.get("segments") or [])]
    position = {}
    for i, text in enumerate(narrations, 1):
        position.setdefault(" ".join(text.split()), i)

    lines += ["", "THE FULL SCRIPT", ""]
    lines += [f"[{i}] {' '.join(t.split())}" for i, t in enumerate(narrations, 1) if t.strip()]
    lines += ["", f"THE {count} MOMENTS TO DESCRIBE", ""]
    for idx, (seg, shot) in enumerate(owning, 1):
        moment = " ".join(((shot.get("scene") or seg.get("narration") or "")).split())
        at = position.get(moment)
        where = f" (script line {at})" if at else ""
        lines.append(f"{idx}.{where} {moment}")

    path = os.path.join(project_dir, "prompt_request.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path
