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
from pathlib import Path

PIXABAY_SEARCH_URL = "https://pixabay.com/api/"
POLLINATIONS_URL   = "https://image.pollinations.ai/prompt/{prompt}?width={width}&height={height}&nologo=true&seed={seed}&model=flux"

ASPECT_RATIOS = {
    "16:9": (1280, 720),
    "9:16": (720, 1280),
    "1:1": (1080, 1080),
    "4:3": (1440, 1080)
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_dimensions(aspect_ratio: str) -> tuple[int, int]:
    return ASPECT_RATIOS.get(aspect_ratio, ASPECT_RATIOS["16:9"])


def _create_black_frame(output_path: str, width: int, height: int):
    from PIL import Image
    img = Image.new("RGB", (width, height), color=(0, 0, 0))
    img.save(output_path, "JPEG", quality=95)


def _build_final_prompt(keyword: str, narration: str, video_title: str, visual_style: str, aspect_ratio: str) -> str:
    """Builds a rich prompt string by combining keyword, narration context, style, and ratio details."""
    context = narration.strip()
    if len(context) > 120:
        context = context[:120].rsplit(" ", 1)[0]

    style = visual_style.strip() if visual_style.strip() else (
        "cinematic documentary photography, dramatic natural lighting, "
        "highly detailed, sharp focus, photorealistic, historical realism"
    )

    parts = []
    if video_title:
        parts.append(f"Scene for '{video_title}'")
    parts.append(keyword)
    if context:
        parts.append(f"depicting: {context}")
    parts.append(style)
    parts.append(f"{aspect_ratio} aspect ratio")
    return ", ".join(parts)




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
    
    # Map S2V dimensions to strict Imagen supported aspect ratios
    aspect_ratio_str = "1:1"
    if width == 1280 and height == 720:
        aspect_ratio_str = "16:9"
    elif width == 720 and height == 1280:
        aspect_ratio_str = "9:16"
    elif width == 1080 and height == 1080:
        aspect_ratio_str = "1:1"
    elif width == 1440 and height == 1080:
        aspect_ratio_str = "4:3"

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


# ── Public Entry Point ─────────────────────────────────────────────────────────

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
) -> str:
    """
    Fetch or generate a visual for this segment at the correct aspect ratio.
    Looks inside the local manual projects directory projects/<title_slug>/.
    Generates structured Pillow placeholders if no manual images exist yet.
    """
    output_path = os.path.join(cache_dir, f"segment_{segment_id}_visual.jpg")
    width, height = _get_dimensions(aspect_ratio)

    project_slug = re.sub(r'[^\w\-]', '_', video_title.strip()).strip('_')
    if not project_slug:
        project_slug = "my_project"

    project_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "projects", project_slug)
    os.makedirs(project_dir, exist_ok=True)

    # Check if a manual image has been placed by the user
    jpg_path = os.path.join(project_dir, f"{segment_id}.jpg")
    png_path = os.path.join(project_dir, f"{segment_id}.png")

    manual_path = None
    if os.path.exists(jpg_path):
        manual_path = jpg_path
    elif os.path.exists(png_path):
        manual_path = png_path

    # If no manual visual exists yet, generate the placeholder at jpg_path
    if not manual_path:
        if on_progress:
            on_progress(f"Segment {segment_id} — Generating placeholder at projects/{project_slug}/{segment_id}.jpg")
        _generate_placeholder_image(jpg_path, segment_id, keyword, narration, width, height)
        manual_path = jpg_path

    # Copy to cache directory if cached file size is different (i.e. user replaced placeholder or it's new)
    if not os.path.exists(output_path) or os.path.getsize(manual_path) != os.path.getsize(output_path):
        if on_progress:
            on_progress(f"Segment {segment_id} — Syncing image to cache")
        shutil.copy2(manual_path, output_path)

    # Create/update the project-specific visual prompts text file
    prompts_file = os.path.join(project_dir, "image_prompts.txt")
    prompt_desc = _build_final_prompt(
        keyword=keyword,
        narration=narration,
        video_title=video_title,
        visual_style=visual_style,
        aspect_ratio=aspect_ratio
    )
    
    existing_lines = {}
    if os.path.exists(prompts_file):
        try:
            with open(prompts_file, "r", encoding="utf-8") as pf:
                for line in pf:
                    match = re.match(r"^Segment\s+(\d+)\s*:", line)
                    if match:
                        existing_lines[int(match.group(1))] = line.strip()
        except Exception:
            pass
            
    existing_lines[segment_id] = f"Segment {segment_id}: {prompt_desc}"
    
    try:
        with open(prompts_file, "w", encoding="utf-8") as pf:
            for seg_id in sorted(existing_lines.keys()):
                pf.write(existing_lines[seg_id] + "\n")
    except Exception as e:
        if on_progress:
            on_progress(f"Failed to write prompts file: {e}")

    return output_path


def initialize_project_sourcing(script_dict: dict) -> str:
    """
    Initialize the project folder, write/update image_prompts.txt, and create placeholder images.
    This is called during the planning and save phases to support offline manual visuals generation.
    """
    proj = script_dict.get("project", {})
    title = proj.get("title", "My Video")
    aspect_ratio = proj.get("aspect_ratio", "16:9")
    visual_style = proj.get("visual_style", "")
    
    project_slug = re.sub(r'[^\w\-]', '_', title.strip()).strip('_')
    if not project_slug:
        project_slug = "my_project"
        
    project_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "projects", project_slug)
    os.makedirs(project_dir, exist_ok=True)
    
    width, height = _get_dimensions(aspect_ratio)
    
    prompts_file = os.path.join(project_dir, "image_prompts.txt")
    lines = []
    
    for seg in script_dict.get("segments", []):
        segment_id = seg["segment_id"]
        keyword = seg.get("b_roll_keyword", "")
        narration = seg.get("narration", "")
        
        # 1. Generate placeholder if neither jpg nor png exists
        jpg_path = os.path.join(project_dir, f"{segment_id}.jpg")
        png_path = os.path.join(project_dir, f"{segment_id}.png")
        if not os.path.exists(jpg_path) and not os.path.exists(png_path):
            _generate_placeholder_image(jpg_path, segment_id, keyword, narration, width, height)
            
        # 2. Build rich prompt for image_prompts.txt
        prompt_desc = _build_final_prompt(
            keyword=keyword,
            narration=narration,
            video_title=title,
            visual_style=visual_style,
            aspect_ratio=aspect_ratio
        )
        lines.append(f"Segment {segment_id}: {prompt_desc}")
        
    # Write image_prompts.txt
    try:
        with open(prompts_file, "w", encoding="utf-8") as pf:
            for line in lines:
                pf.write(line + "\n")
    except Exception as e:
        print(f"Failed to write image_prompts.txt: {e}")
        
    return project_dir

