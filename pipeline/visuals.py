"""Stage 4 — Visual sourcing.

Routing logic:
  - visual_type == "ai_image"    → Pollinations.ai (free, Flux model, 1920x1080)
                                   Prompt is written by Gemini if a Google API key
                                   is available, otherwise falls back to a basic
                                   keyword + narration prompt.
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
POLLINATIONS_URL   = "https://image.pollinations.ai/prompt/{prompt}?width=1920&height=1080&nologo=true&seed={seed}&model=flux"
GEMINI_URL         = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={key}"
FALLBACK_SIZE      = (1920, 1080)


# ── Black frame fallback ───────────────────────────────────────────────────────

def _create_black_frame(output_path: str):
    from PIL import Image
    img = Image.new("RGB", FALLBACK_SIZE, color=(0, 0, 0))
    img.save(output_path, "JPEG", quality=95)


# ── Prompt building ────────────────────────────────────────────────────────────

def _basic_prompt(keyword: str, narration: str, video_title: str, visual_style: str) -> str:
    """Fallback prompt when Gemini is unavailable."""
    context = narration.strip()
    if len(context) > 150:
        context = context[:150].rsplit(" ", 1)[0]

    style = visual_style.strip() if visual_style.strip() else (
        "cinematic documentary photography, dramatic natural lighting, "
        "highly detailed, sharp focus, photorealistic"
    )

    parts = []
    if video_title:
        parts.append(video_title)
    parts.append(keyword)
    parts.append(context)
    parts.append(style)
    parts.append("16:9 widescreen")
    return ", ".join(parts)


def _gemini_prompt(
    narration: str,
    keyword: str,
    video_title: str,
    visual_style: str,
    google_api_key: str,
) -> str:
    """
    Ask Gemini to write a detailed, scene-specific image generation prompt.
    Returns the prompt string, or raises an exception if the call fails.
    """
    style_instruction = (
        visual_style.strip()
        if visual_style.strip()
        else "cinematic documentary, photorealistic, dramatic lighting, high detail"
    )

    request_text = (
        f"You write image generation prompts for the Flux AI image model.\n\n"
        f"Video title: {video_title}\n"
        f"Visual style for the whole video: {style_instruction}\n"
        f"Scene narration: {narration}\n\n"
        f"Write a detailed 40–60 word image generation prompt for this specific scene. "
        f"Include: the exact visual moment, historical setting and era, specific location, "
        f"lighting, mood, and the visual style above. "
        f"Return ONLY the image prompt — no explanation, no quotes, no extra text."
    )

    url = GEMINI_URL.format(key=google_api_key)
    body = json.dumps({
        "contents": [{"parts": [{"text": request_text}]}],
        "generationConfig": {"maxOutputTokens": 200, "temperature": 0.7},
    }).encode("utf-8")

    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read())
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def build_image_prompt(
    narration: str,
    keyword: str,
    video_title: str,
    visual_style: str,
    google_api_key: str,
    on_progress=None,
    segment_id: int = 0,
) -> str:
    """
    Build the best possible image prompt for this segment.
    Uses Gemini if a Google API key is available, otherwise falls back to
    the basic keyword + narration approach.
    """
    if google_api_key:
        try:
            prompt = _gemini_prompt(narration, keyword, video_title, visual_style, google_api_key)
            if on_progress:
                on_progress(f"Segment {segment_id} — Gemini wrote image prompt")
            return prompt
        except Exception as e:
            if on_progress:
                on_progress(f"Segment {segment_id} — Gemini unavailable ({e}), using basic prompt")

    return _basic_prompt(keyword, narration, video_title, visual_style)


# ── AI image (Pollinations.ai) ─────────────────────────────────────────────────

def _fetch_ai_image(
    segment_id: int,
    prompt: str,
    output_path: str,
    seed: int = 0,
    on_progress=None,
) -> bool:
    """
    Generate an AI image via Pollinations.ai using the given prompt.
    Returns True on success, False on failure.
    """
    encoded = urllib.parse.quote(prompt)
    url = POLLINATIONS_URL.format(prompt=encoded, seed=seed)

    if on_progress:
        on_progress(f"Segment {segment_id} — generating AI image…")

    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "S2V/1.0"})
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = resp.read()

            if len(data) < 1024:
                if on_progress:
                    on_progress(f"Segment {segment_id} — image response too small, retrying…")
                time.sleep(3)
                continue

            with open(output_path, "wb") as f:
                f.write(data)

            if on_progress:
                on_progress(f"Segment {segment_id} — AI image ready ({len(data)//1024} KB)")
            return True

        except Exception as e:
            if attempt < 2:
                if on_progress:
                    on_progress(f"Segment {segment_id} — attempt {attempt+1} failed ({e}), retrying…")
                time.sleep(4)
            else:
                if on_progress:
                    on_progress(f"Segment {segment_id} — AI image failed after 3 attempts, using black frame")
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


# ── Public entry point ─────────────────────────────────────────────────────────

def fetch_visual(
    segment_id: int,
    keyword: str,
    narration: str,
    visual_type: str,
    api_key: str,
    cache_dir: str,
    render_id: str = "",
    video_title: str = "",
    visual_style: str = "",
    google_api_key: str = "",
    on_progress=None,
) -> str:
    """
    Fetch or generate a visual for this segment.

    For ai_image:
      - Gemini writes a rich, scene-specific prompt (if google_api_key is set)
      - Pollinations.ai generates the image at 1920x1080
      - Each render session uses a unique seed → different images every run

    Returns path to the saved JPG.
    Skips generation if already cached (within the same render session).
    """
    output_path = os.path.join(cache_dir, f"segment_{segment_id}_visual.jpg")

    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        if on_progress:
            on_progress(f"Segment {segment_id} — visual already cached, skipping")
        return output_path

    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    success = False

    if visual_type == "ai_image":
        import hashlib
        seed_str = f"{render_id}-{segment_id}"
        seed = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16) % 99999 + 1

        prompt = build_image_prompt(
            narration=narration,
            keyword=keyword,
            video_title=video_title,
            visual_style=visual_style,
            google_api_key=google_api_key,
            on_progress=on_progress,
            segment_id=segment_id,
        )

        success = _fetch_ai_image(
            segment_id=segment_id,
            prompt=prompt,
            output_path=output_path,
            seed=seed,
            on_progress=on_progress,
        )

    elif visual_type == "stock_photo":
        success = _fetch_stock_photo(
            segment_id=segment_id,
            keyword=keyword,
            api_key=api_key,
            output_path=output_path,
            on_progress=on_progress,
        )

    else:
        if on_progress:
            on_progress(f'Segment {segment_id} — unknown visual_type "{visual_type}", using black frame')

    if not success:
        _create_black_frame(output_path)

    return output_path
