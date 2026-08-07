#!/usr/bin/env python3
"""
tools/build_library.py

Standalone image generator for Islamic-history documentary series (7th-9th century Arabia, Levant, Mesopotamia).
Uses Pollinations AI (Flux model) to generate images into library/images/ and track them in library/manifest.jsonl.
"""

import argparse
import hashlib
import json
import os
import random
import sys
import time
import urllib.parse
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import requests

SUBJECTS = [
    "desert caravan", "oasis", "mosque exterior", "mosque interior",
    "city walls", "marketplace", "open-air council", "horse cavalry", "camel riders",
    "open manuscript", "scribe writing", "oil lamp", "dates and bread", "water well",
    "battle plain aftermath", "war banners", "robed elder", "young warrior",
    "crowd listening", "lone rider on ridge", "palm grove", "stone courtyard",
    "tent encampment", "mountain pass"
]

SETTINGS = [
    "open desert", "walled city", "palm oasis", "rocky highland", "riverbank"
]

LIGHTS = [
    "dawn", "harsh noon", "golden hour", "dusk", "night by firelight"
]

SHOTS = [
    "wide establishing", "medium", "close detail"
]

SEEDS = [42, 101, 202, 303]

# Subjects that are interiors or object-scale: an outdoor SETTING is meaningless
# for these ("oil lamp, open desert"), so they use a single neutral setting.
# Without this ~40% of the cross-product is incoherent and wastes generations.
SETTING_AGNOSTIC = {
    "mosque interior", "open manuscript", "scribe writing",
    "oil lamp", "dates and bread",
}

STYLE_SUFFIX = (
    "cinematic documentary photography, dramatic natural lighting, "
    "historical realism, highly detailed, sharp focus, no text, no watermark, no modern objects"
)


def fetch_image_with_retry(prompt, seed, max_retries=3):
    encoded_prompt = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1280&height=720&nologo=true&seed={seed}&model=flux"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    for attempt in range(max_retries + 1):
        try:
            # Jitter so 4 workers don't burst the free endpoint in lockstep.
            time.sleep(random.uniform(0.3, 1.2))
            resp = requests.get(url, headers=headers, timeout=60)
            if resp.status_code == 200:
                data = resp.content
                if len(data) >= 2048:
                    return data
        except Exception:
            pass

        if attempt < max_retries:
            sleep_time = 2 ** (attempt + 1)  # Exponential backoff: 2s, 4s, 8s
            time.sleep(sleep_time)

    return None


def main():
    parser = argparse.ArgumentParser(description="Build Islamic history image library via Pollinations AI.")
    parser.add_argument("--workers", type=int, default=4, help="Number of concurrent workers (default: 4)")
    parser.add_argument("--target", type=int, default=1200, help="Target total images in manifest (default: 1200)")
    args = parser.parse_args()

    images_dir = os.path.join("library", "images")
    os.makedirs(images_dir, exist_ok=True)

    manifest_path = os.path.join("library", "manifest.jsonl")
    seen_manifest = set()
    existing_count = 0

    if os.path.exists(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    p = record.get("prompt")
                    s = record.get("seed")
                    if p and s is not None:
                        seen_manifest.add((p, int(s)))
                    existing_count += 1
                except json.JSONDecodeError:
                    pass

    print(f"[INIT] Loaded {existing_count} existing entries from {manifest_path}", flush=True)

    if args.target > 0 and existing_count >= args.target:
        print(f"[INFO] Manifest already has {existing_count} images (target: {args.target}). Exiting.", flush=True)
        return

    # Generate cross-product taxonomy tasks
    tasks = []
    for subject in SUBJECTS:
        settings = [""] if subject in SETTING_AGNOSTIC else SETTINGS
        for setting in settings:
            for light in LIGHTS:
                for shot in SHOTS:
                    where = f", {setting}" if setting else ""
                    prompt = f"{shot} shot of {subject}{where}, {light}, {STYLE_SUFFIX}"
                    for seed in SEEDS:
                        if (prompt, seed) not in seen_manifest:
                            tasks.append({
                                "prompt": prompt,
                                "subject": subject,
                                "setting": setting,
                                "light": light,
                                "shot": shot,
                                "seed": seed
                            })

    # CRITICAL: tasks are built subject-outermost. Without shuffling, stopping at
    # --target only ever reaches the first few subjects (1200/300 = 4 of 24).
    # Shuffling makes any truncation an even sample across the whole taxonomy.
    random.seed(1337)
    random.shuffle(tasks)

    print(f"[QUEUE] {len(tasks)} tasks queued (shuffled across "
          f"{len(SUBJECTS)} subjects).", flush=True)

    file_lock = threading.Lock()
    total_manifest_count = existing_count
    newly_saved = 0
    error_count = 0
    stop_event = threading.Event()

    def worker(task):
        nonlocal total_manifest_count, newly_saved, error_count

        if stop_event.is_set():
            return None

        prompt = task["prompt"]
        seed = task["seed"]

        image_bytes = fetch_image_with_retry(prompt, seed, max_retries=3)

        with file_lock:
            if stop_event.is_set() or (prompt, seed) in seen_manifest:
                return None

            if image_bytes is None:
                error_count += 1
                return None

            seen_manifest.add((prompt, seed))

            sha1_hash = hashlib.sha1(image_bytes).hexdigest()[:12]
            filename = f"{sha1_hash}.jpg"
            rel_path = os.path.join("library", "images", filename).replace("\\", "/")
            full_path = os.path.join(images_dir, filename)

            if not os.path.exists(full_path):
                with open(full_path, "wb") as f_img:
                    f_img.write(image_bytes)

            created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            record = {
                "path": rel_path,
                "prompt": prompt,
                "subject": task["subject"],
                "setting": task["setting"],
                "light": task["light"],
                "shot": task["shot"],
                "seed": seed,
                "bytes": len(image_bytes),
                "created_at": created_at
            }

            with open(manifest_path, "a", encoding="utf-8") as f_man:
                f_man.write(json.dumps(record, ensure_ascii=False) + "\n")

            newly_saved += 1
            total_manifest_count += 1

            if newly_saved % 25 == 0:
                print(f"[PROGRESS] {total_manifest_count} images in library (+{newly_saved} saved this run, {error_count} errors)", flush=True)

            if args.target > 0 and total_manifest_count >= args.target:
                stop_event.set()

            return rel_path

    start_time = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(worker, t) for t in tasks]
        for future in as_completed(futures):
            if stop_event.is_set():
                break

    elapsed = time.time() - start_time
    print(f"[COMPLETE] Finished run in {elapsed:.1f}s. Total manifest count: {total_manifest_count} (+{newly_saved} new images, {error_count} errors).", flush=True)


if __name__ == "__main__":
    main()
