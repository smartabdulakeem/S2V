#!/usr/bin/env python3
"""
tools/fetch_selection.py

Download every prompt you ticked in library/image-studio.html.

Workflow:
  1. Tick prompts in the studio page
  2. Click "Export ticked", copy the JSON
  3. Save it as library/selection.json
  4. python tools/fetch_selection.py

Downloads into library/images/ with content-hash filenames, skips anything already
present, appends to library/manifest.jsonl. Safe to re-run — nothing is duplicated.
"""

import argparse
import hashlib
import json
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import base64

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES = os.path.join(ROOT, "library", "images")
MANIFEST = os.path.join(ROOT, "library", "manifest.jsonl")
SELECTION = os.path.join(ROOT, "library", "selection.json")
SETTINGS = os.path.join(ROOT, "config", "settings.json")

IMAGEN_URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
              "imagen-4.0-generate-001:predict?key={key}")

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

lock = threading.Lock()
stats = {"saved": 0, "skipped": 0, "failed": 0, "imagen": 0, "pollinations": 0, "throttled": 0}
stop = threading.Event()
T0 = time.time()

# Adaptive throttle. Built for long unattended runs: every 429 widens the gap between
# requests, every clean run of successes narrows it again. Slow but it keeps going.
throttle = {"delay": 1.0, "min": 0.4, "max": 45.0, "ok_streak": 0}


def on_rate_limit():
    with lock:
        throttle["delay"] = min(throttle["max"], max(2.0, throttle["delay"] * 2))
        throttle["ok_streak"] = 0
        stats["throttled"] += 1
        print(f"  rate limited — backing off to {throttle['delay']:.1f}s between requests",
              flush=True)


def on_success():
    with lock:
        throttle["ok_streak"] += 1
        if throttle["ok_streak"] >= 10 and throttle["delay"] > throttle["min"]:
            throttle["delay"] = max(throttle["min"], throttle["delay"] * 0.75)
            throttle["ok_streak"] = 0


def pace():
    with lock:
        d = throttle["delay"]
    time.sleep(d + random.uniform(0, 0.4))


def google_key():
    """Read the Google API key from config/settings.json, if present."""
    try:
        with open(SETTINGS, "r", encoding="utf-8") as f:
            return json.load(f).get("google_api_key", "").strip()
    except Exception:
        return ""


def fetch_imagen(prompt, key, retries=2, timeout=90):
    """Generate via Imagen 4.0 — markedly better than FLUX on faces and hands."""
    payload = {
        "instances": [{"prompt": prompt}],
        "parameters": {"sampleCount": 1, "aspectRatio": "16:9", "outputMimeType": "image/jpeg"},
    }
    for attempt in range(retries + 1):
        if stop.is_set():
            return None
        try:
            pace()
            r = requests.post(IMAGEN_URL.format(key=key), json=payload,
                              headers={"Content-Type": "application/json"}, timeout=timeout)
            if r.status_code == 200:
                preds = r.json().get("predictions") or []
                if preds and preds[0].get("bytesBase64Encoded"):
                    on_success()
                    return base64.b64decode(preds[0]["bytesBase64Encoded"])
            elif r.status_code in (429, 503):
                on_rate_limit()
            elif r.status_code in (400, 403):
                return None          # bad key or blocked prompt — do not retry
        except Exception:
            pass
        if attempt < retries:
            time.sleep(2 ** (attempt + 1))
    return None


def load_manifest_keys():
    """(prompt, seed) pairs already recorded, so we never re-fetch."""
    keys = set()
    if not os.path.exists(MANIFEST):
        return keys
    with open(MANIFEST, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                if r.get("prompt") is not None and r.get("seed") is not None:
                    keys.add((r["prompt"], int(r["seed"])))
            except (json.JSONDecodeError, ValueError, TypeError):
                continue
    return keys


def fetch(url, retries=3, timeout=120):
    for attempt in range(retries + 1):
        if stop.is_set():
            return None
        try:
            pace()
            resp = requests.get(url, headers=UA, timeout=timeout)
            if resp.status_code == 200 and len(resp.content) >= 2048:
                on_success()
                return resp.content
            if resp.status_code in (429, 503):
                on_rate_limit()
        except Exception:
            pass
        if attempt < retries:
            time.sleep(2 ** (attempt + 1))
    return None


def worker(item, seen, gkey, total):
    """Never raises. A single bad item must not end an overnight run."""
    try:
        _worker(item, seen, gkey, total)
    except Exception as e:
        with lock:
            stats["failed"] += 1
            print(f"  ERROR   {type(e).__name__}: {e}", flush=True)


def _worker(item, seen, gkey, total):
    if stop.is_set():
        return
    prompt, seed = item["prompt"], int(item["seed"])

    with lock:
        if (prompt, seed) in seen:
            stats["skipped"] += 1
            return
        seen.add((prompt, seed))

    # Human-subject batches go to Imagen when a key is available; everything else,
    # and any Imagen failure, falls back to free Pollinations.
    data, source = None, "pollinations"
    if item.get("tier") == "q" and gkey:
        data = fetch_imagen(prompt, gkey)
        if data is not None:
            source = "imagen"
    if data is None:
        data = fetch(item["url"])

    if data is None:
        with lock:
            stats["failed"] += 1
            print(f"  FAILED  {item.get('subject', prompt)[:70]}", flush=True)
        return

    with lock:
        stats[source] += 1

    digest = hashlib.sha1(data).hexdigest()[:12]
    fname = f"{digest}.jpg"
    fpath = os.path.join(IMAGES, fname)

    with lock:
        if os.path.exists(fpath):
            stats["skipped"] += 1        # identical bytes already on disk
        else:
            with open(fpath, "wb") as f:
                f.write(data)
            stats["saved"] += 1

        record = {
            "path": f"library/images/{fname}",
            "prompt": prompt,
            "batch": item.get("batch"),
            "subject": item.get("subject"),
            "tier": item.get("tier", "b"),
            "source": source,
            "seed": seed,
            "bytes": len(data),
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        with open(MANIFEST, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        n = stats["saved"] + stats["skipped"] + stats["failed"]
        if n % 10 == 0 or n == total:
            el = time.time() - T0
            rate = n / el if el else 0
            eta = (total - n) / rate if rate else 0
            print(f"  [{n}/{total}]  saved {stats['saved']}  skipped {stats['skipped']}  "
                  f"failed {stats['failed']}  |  {throttle['delay']:.1f}s pace  |  "
                  f"eta {eta/60:.0f} min", flush=True)


def main():
    ap = argparse.ArgumentParser(description="Fetch ticked prompts from the Image Studio.")
    ap.add_argument("--selection", default=SELECTION, help="path to selection.json")
    ap.add_argument("--workers", type=int, default=2,
                    help="concurrent requests (default 2 — slow and steady beats rate-limited)")
    ap.add_argument("--delay", type=float, default=1.0,
                    help="starting seconds between requests; widens automatically on 429")
    ap.add_argument("--no-imagen", action="store_true",
                    help="force everything through free Pollinations, ignore the Google key")
    args = ap.parse_args()
    throttle["delay"] = max(throttle["min"], args.delay)

    if not os.path.exists(args.selection):
        print(f"No selection file at {args.selection}\n\n"
              f"Open library/image-studio.html, tick the prompts you want, click\n"
              f'"Export ticked", copy the JSON and save it to that path.')
        sys.exit(1)

    with open(args.selection, "r", encoding="utf-8") as f:
        items = json.load(f)

    if not isinstance(items, list) or not items:
        print("selection.json is empty or not a list.")
        sys.exit(1)

    os.makedirs(IMAGES, exist_ok=True)
    seen = load_manifest_keys()
    gkey = "" if args.no_imagen else google_key()
    nq = sum(1 for i in items if i.get("tier") == "q")

    print(f"selection : {len(items)} prompts  ({nq} human-subject, {len(items)-nq} bulk)")
    print(f"manifest  : {len(seen)} already recorded")
    print(f"images    : {len(os.listdir(IMAGES))} currently on disk")
    if nq and gkey:
        print(f"quality   : {nq} prompts route to Imagen 4.0")
    elif nq:
        print(f"quality   : no Google key found — all {nq} fall back to Pollinations")
    print(f"pacing    : {args.workers} workers, {throttle['delay']:.1f}s apart, "
          f"auto-backoff on rate limits")
    print("Safe to leave running. Ctrl+C stops cleanly; re-run resumes where it left off.\n",
          flush=True)

    global T0
    T0 = time.time()
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            list(ex.map(lambda it: worker(it, seen, gkey, len(items)), items))
    except KeyboardInterrupt:
        stop.set()
        print("\ninterrupted — finishing in-flight requests ...")

    el = time.time() - T0
    print(f"\ndone in {el/60:.1f} min — saved {stats['saved']}, skipped {stats['skipped']}, "
          f"failed {stats['failed']}")
    print(f"sources: imagen {stats['imagen']}, pollinations {stats['pollinations']}"
          + (f", rate-limited {stats['throttled']}x" if stats["throttled"] else ""))
    print(f"library/images now holds {len(os.listdir(IMAGES))} files")
    if stats["failed"]:
        print("Re-run to retry the failures — completed items are skipped automatically.")


if __name__ == "__main__":
    main()
