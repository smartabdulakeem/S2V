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
import urllib.request
import urllib.parse
from pathlib import Path

PIXABAY_SEARCH_URL = "https://pixabay.com/api/"
HF_FLUX_URL        = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"
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


# ── Hugging Face FLUX API ──────────────────────────────────────────────────────

def _fetch_hf_flux_image(
    segment_id: int,
    prompt: str,
    width: int,
    height: int,
    hf_token: str,
    output_path: str,
    on_progress=None
) -> bool:
    """Generate an image via Hugging Face Serverless FLUX.1-schnell API."""
    if not hf_token:
        return False

    headers = {
        "Authorization": f"Bearer {hf_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "inputs": prompt,
        "parameters": {
            "width": width,
            "height": height
        },
        "options": {
            "wait_for_model": True
        }
    }
    body = json.dumps(payload).encode("utf-8")

    for attempt in range(2):
        try:
            req = urllib.request.Request(HF_FLUX_URL, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = resp.read()

            # Verify response is an image, not JSON error
            content_type = resp.headers.get("Content-Type", "")
            if "application/json" in content_type:
                err_txt = data.decode("utf-8")
                if on_progress:
                    on_progress(f"Segment {segment_id} — HF image API returned JSON error: {err_txt}")
                return False

            if len(data) < 5000:
                if on_progress:
                    on_progress(f"Segment {segment_id} — HF image too small, retrying...")
                time.sleep(2)
                continue

            with open(output_path, "wb") as f:
                f.write(data)
            return True

        except Exception as e:
            if on_progress:
                on_progress(f"Segment {segment_id} — HF Image Attempt {attempt+1} failed ({e})")
            time.sleep(2)

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


# ── Stock photo (Pixabay) ──────────────────────────────────────────────────────

def _fetch_stock_photo(
    segment_id: int,
    keyword: str,
    api_key: str,
    output_path: str,
    on_progress=None,
) -> bool:
    if not api_key:
        if on_progress:
            on_progress(f"Segment {segment_id} — no Pixabay API key, using black frame fallback")
        return False

    import requests

    params = {
        "key": api_key,
        "q": keyword,
        "image_type": "photo",
        "orientation": "horizontal",
        "per_page": 3,
        "safesearch": "true",
    }

    for attempt in range(2):
        try:
            resp = requests.get(PIXABAY_SEARCH_URL, params=params, timeout=15)
        except Exception as e:
            if on_progress:
                on_progress(f"Segment {segment_id} — Pixabay error: {e}, using black frame")
            return False

        if resp.status_code == 429:
            if attempt == 0:
                time.sleep(5)
                continue
            return False

        if resp.status_code == 400:
            raise ValueError("Pixabay API key is invalid.")

        if resp.status_code != 200:
            return False

        hits = resp.json().get("hits", [])
        if not hits:
            if on_progress:
                on_progress(f'Segment {segment_id} — no Pixabay results for "{keyword}", using black frame')
            return False

        hit = hits[0]
        image_url = hit.get("largeImageURL") or hit.get("webformatURL")
        if not image_url:
            return False

        img_resp = requests.get(image_url, timeout=30, stream=True)
        if img_resp.status_code == 200:
            with open(output_path, "wb") as f:
                for chunk in img_resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            if on_progress:
                on_progress(f'Segment {segment_id} — stock photo downloaded')
            return True

    return False


# ── Public Entry Point ─────────────────────────────────────────────────────────

def fetch_visual(
    segment_id: int,
    keyword: str,
    narration: str,
    visual_type: str,
    pixabay_api_key: str,
    cache_dir: str,
    huggingface_api_key: str = "",
    aspect_ratio: str = "16:9",
    render_id: str = "",
    video_title: str = "",
    visual_style: str = "",
    on_progress=None,
) -> str:
    """
    Fetch or generate a visual for this segment at the correct aspect ratio.
    """
    output_path = os.path.join(cache_dir, f"segment_{segment_id}_visual.jpg")

    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        if on_progress:
            on_progress(f"Segment {segment_id} — visual already cached, skipping")
        return output_path

    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    
    # Get width and height matching selected aspect ratio
    width, height = _get_dimensions(aspect_ratio)
    success = False

    if visual_type == "ai_image":
        import hashlib
        seed_str = f"{render_id}-{segment_id}"
        seed = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16) % 99999 + 1

        prompt = _build_final_prompt(
            keyword=keyword,
            narration=narration,
            video_title=video_title,
            visual_style=visual_style,
            aspect_ratio=aspect_ratio
        )

        if huggingface_api_key:
            if on_progress:
                on_progress(f"Segment {segment_id} — generating AI image via HF FLUX ({aspect_ratio})...")
            success = _fetch_hf_flux_image(
                segment_id=segment_id,
                prompt=prompt,
                width=width,
                height=height,
                hf_token=huggingface_api_key,
                output_path=output_path,
                on_progress=on_progress
            )

        if not success:
            # Fallback to Pollinations.ai (using custom width/height and seed)
            if on_progress:
                on_progress(f"Segment {segment_id} — generating AI image via Pollinations Fallback ({aspect_ratio})...")
            success = _fetch_pollinations_image(
                segment_id=segment_id,
                prompt=prompt,
                width=width,
                height=height,
                output_path=output_path,
                seed=seed,
                on_progress=on_progress
            )

    elif visual_type == "stock_photo":
        success = _fetch_stock_photo(
            segment_id=segment_id,
            keyword=keyword,
            api_key=pixabay_api_key,
            output_path=output_path,
            on_progress=on_progress,
        )

    else:
        if on_progress:
            on_progress(f'Segment {segment_id} — unknown visual_type "{visual_type}", using black frame')

    if not success:
        _create_black_frame(output_path, width, height)

    return output_path
