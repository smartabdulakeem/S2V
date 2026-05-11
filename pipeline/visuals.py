"""Stage 4 — Visual sourcing.

Routing logic:
  - visual_type == "ai_image"   → Pollinations.ai (free, no API key, Flux model, 1920x1080)
  - visual_type == "stock_photo" → Pixabay API (requires API key)
  - anything else                → black frame fallback
"""

import os
import time
import urllib.request
import urllib.parse
from pathlib import Path

PIXABAY_SEARCH_URL = "https://pixabay.com/api/"
POLLINATIONS_URL   = "https://image.pollinations.ai/prompt/{prompt}?width=1920&height=1080&nologo=true&seed={seed}"
FALLBACK_SIZE      = (1920, 1080)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _create_black_frame(output_path: str):
    from PIL import Image
    img = Image.new("RGB", FALLBACK_SIZE, color=(0, 0, 0))
    img.save(output_path, "JPEG", quality=95)


def _build_ai_prompt(keyword: str, narration: str) -> str:
    """
    Build a rich Pollinations prompt from the segment keyword + first sentence of narration.
    Adds cinematic style keywords for consistently good documentary-style imagery.
    """
    # Take up to first 120 chars of narration for context
    context = narration.strip()
    if len(context) > 120:
        # Cut at last space before 120 chars
        context = context[:120].rsplit(" ", 1)[0]

    prompt = (
        f"{keyword}, {context}, "
        "cinematic documentary photography, dramatic natural lighting, "
        "highly detailed, sharp focus, 16:9 aspect ratio, photorealistic"
    )
    return prompt


# ── AI image (Pollinations.ai) ─────────────────────────────────────────────────

def _fetch_ai_image(
    segment_id: int,
    keyword: str,
    narration: str,
    output_path: str,
    on_progress=None,
) -> bool:
    """
    Generate an AI image via Pollinations.ai.
    Returns True on success, False on failure (caller should fall back to black frame).
    """
    prompt = _build_ai_prompt(keyword, narration)
    encoded_prompt = urllib.parse.quote(prompt)
    url = POLLINATIONS_URL.format(prompt=encoded_prompt, seed=segment_id * 42)

    if on_progress:
        on_progress(f'Segment {segment_id} — generating AI image for "{keyword}"')

    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "S2V/1.0"},
            )
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = resp.read()

            if len(data) < 1024:
                # Suspiciously small — probably an error page
                if on_progress:
                    on_progress(f"Segment {segment_id} — AI image response too small, retrying…")
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
                    on_progress(f"Segment {segment_id} — AI image attempt {attempt+1} failed ({e}), retrying…")
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
    """
    Download a stock photo from Pixabay.
    Returns True on success, False on failure.
    """
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
        except requests.exceptions.ConnectionError:
            if on_progress:
                on_progress(f"Segment {segment_id} — network error fetching visual, using black frame")
            return False
        except requests.exceptions.Timeout:
            if on_progress:
                on_progress(f"Segment {segment_id} — Pixabay request timed out, using black frame")
            return False

        if resp.status_code == 429:
            if attempt == 0:
                if on_progress:
                    on_progress(f"Segment {segment_id} — Pixabay rate limit hit, waiting 5 seconds…")
                time.sleep(5)
                continue
            else:
                if on_progress:
                    on_progress(f"Segment {segment_id} — Pixabay rate limit persists, using black frame")
                return False

        if resp.status_code == 400:
            raise ValueError(
                "Pixabay API key is invalid. Please check your key in the Settings panel."
            )

        if resp.status_code != 200:
            if on_progress:
                on_progress(f"Segment {segment_id} — Pixabay returned status {resp.status_code}, using black frame")
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
                on_progress(f'Segment {segment_id} — stock photo downloaded for "{keyword}"')
            return True
        else:
            return False

    return False


# ── Public entry point ─────────────────────────────────────────────────────────

def fetch_visual(
    segment_id: int,
    keyword: str,
    narration: str,
    visual_type: str,
    api_key: str,
    cache_dir: str,
    on_progress=None,
) -> str:
    """
    Fetch or generate a visual for the segment.

    visual_type:
      "ai_image"    → Pollinations.ai (free, no key needed)
      "stock_photo" → Pixabay (requires api_key)
      other         → black frame

    Returns path to the saved JPG.
    Skips if already cached.
    """
    output_path = os.path.join(cache_dir, f"segment_{segment_id}_visual.jpg")

    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        if on_progress:
            on_progress(f"Segment {segment_id} — visual already cached, skipping")
        return output_path

    Path(cache_dir).mkdir(parents=True, exist_ok=True)

    success = False

    if visual_type == "ai_image":
        success = _fetch_ai_image(
            segment_id=segment_id,
            keyword=keyword,
            narration=narration,
            output_path=output_path,
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
