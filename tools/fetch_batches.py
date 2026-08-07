#!/usr/bin/env python3
"""
tools/fetch_batches.py

Download image batches by id. No JSON, no copy-paste.

    python tools/fetch_batches.py A1 A2 B1      # specific batches
    python tools/fetch_batches.py --theme I     # every batch in one theme
    python tools/fetch_batches.py --tier q      # every human-subject batch (Imagen)
    python tools/fetch_batches.py --all         # the whole taxonomy
    python tools/fetch_batches.py --list        # show batch ids and exit

Human-subject batches route to Google Imagen 4.0 when a key is present in
config/settings.json; everything else uses free Pollinations. Any Imagen failure
falls back to Pollinations automatically.

Built for long unattended runs: paced requests, automatic backoff on rate limits,
never crashes on a single bad item, and fully resumable — re-running skips whatever
already landed.
"""

import argparse
import base64
import hashlib
import json
import os
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from taxonomy import build_batches, batch_map  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES = os.path.join(ROOT, "library", "images")
INBOX  = os.path.join(ROOT, "library", "_inbox")
MANIFEST = os.path.join(ROOT, "library", "manifest.jsonl")
SETTINGS = os.path.join(ROOT, "config", "settings.json")

IMAGEN_URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
              "imagen-4.0-generate-001:predict?key={key}")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

lock = threading.Lock()
stop = threading.Event()
stats = {"saved": 0, "skipped": 0, "failed": 0, "rejected": 0, "imagen": 0, "pollinations": 0, "throttled": 0}
throttle = {"delay": 1.0, "min": 0.4, "max": 45.0, "ok": 0}
T0 = time.time()
DEST = IMAGES


def on_rate_limit():
    with lock:
        throttle["delay"] = min(throttle["max"], max(2.0, throttle["delay"] * 2))
        throttle["ok"] = 0
        stats["throttled"] += 1
        print(f"   rate limited - easing to {throttle['delay']:.1f}s between requests", flush=True)


def on_success():
    with lock:
        throttle["ok"] += 1
        if throttle["ok"] >= 10 and throttle["delay"] > throttle["min"]:
            throttle["delay"] = max(throttle["min"], throttle["delay"] * 0.75)
            throttle["ok"] = 0


def pace():
    with lock:
        d = throttle["delay"]
    time.sleep(d + random.uniform(0, 0.4))


def google_key():
    try:
        with open(SETTINGS, "r", encoding="utf-8") as f:
            return json.load(f).get("google_api_key", "").strip()
    except Exception:
        return ""


def fetch_imagen(prompt, key, retries=2):
    payload = {"instances": [{"prompt": prompt}],
               "parameters": {"sampleCount": 1, "aspectRatio": "16:9",
                              "outputMimeType": "image/jpeg"}}
    for attempt in range(retries + 1):
        if stop.is_set():
            return None
        try:
            pace()
            r = requests.post(IMAGEN_URL.format(key=key), json=payload,
                              headers={"Content-Type": "application/json"}, timeout=90)
            if r.status_code == 200:
                preds = r.json().get("predictions") or []
                if preds and preds[0].get("bytesBase64Encoded"):
                    on_success()
                    return base64.b64decode(preds[0]["bytesBase64Encoded"])
            elif r.status_code in (429, 503):
                on_rate_limit()
            elif r.status_code in (400, 403):
                return None
        except Exception:
            pass
        if attempt < retries:
            time.sleep(2 ** (attempt + 1))
    return None


def fetch_pollinations(url, retries=3):
    for attempt in range(retries + 1):
        if stop.is_set():
            return None
        try:
            pace()
            r = requests.get(url, headers=UA, timeout=120)
            if r.status_code == 200 and len(r.content) >= 2048:
                on_success()
                return r.content
            if r.status_code in (429, 503):
                on_rate_limit()
        except Exception:
            pass
        if attempt < retries:
            time.sleep(2 ** (attempt + 1))
    return None


def image_is_bad(data):
    """
    Reject failed renders before they enter the library.

    The 2 KB size check is not enough — six greyscale-banding images from the first run
    passed it. Catches: unreadable files, wrong aspect, near-flat frames, and the
    desaturated horizontal-banding pattern a failed diffusion pass produces.
    Returns a reason string, or None if the image is fine.
    """
    try:
        from io import BytesIO
        import numpy as np
        from PIL import Image
        im = Image.open(BytesIO(data))
        im.verify()
        im = Image.open(BytesIO(data)).convert("RGB")
    except Exception as e:
        return f"unreadable ({type(e).__name__})"

    w, h = im.size
    if w < 512 or h < 288:
        return f"too small ({w}x{h})"
    if not (1.2 < w / h < 2.4):
        return f"wrong aspect ({w}x{h})"

    import numpy as np
    a = np.asarray(im.resize((128, 72))).astype(np.float32)
    if a.std() < 12:
        return "near-flat frame"
    sat = (a.max(axis=2) - a.min(axis=2)).mean()
    band = a.mean(axis=(1, 2)).std()
    if sat < 8 and band > 28:
        return "greyscale banding (failed render)"
    return None


def check_watermark(im):
    """
    Check if bottom-left or bottom-right corner strip has high edge density
    compared to its own local background band immediately above it (>4.8x)
    and contains text-like high-contrast transitions.
    """
    from PIL import ImageFilter
    import numpy as np
    w, h = im.size
    edges = im.convert("L").filter(ImageFilter.FIND_EDGES)
    edges_np = np.asarray(edges, dtype=np.float32)

    y1, y2 = int(h * 0.90), int(h * 0.98)
    ref_y1, ref_y2 = int(h * 0.78), int(h * 0.88)

    for x1, x2 in [(int(w * 0.02), int(w * 0.20)), (int(w * 0.80), int(w * 0.98))]:
        corner = edges_np[y1:y2, x1:x2]
        ref = edges_np[ref_y1:ref_y2, x1:x2]

        c_mean = corner.mean()
        r_mean = max(ref.mean(), 1.0)

        if c_mean > 4.8 * r_mean:
            binary = (corner > 60).astype(np.uint8)
            diffs = np.abs(np.diff(binary, axis=1))
            transitions = diffs.sum()
            if transitions > 380:
                return True
    return False


def load_seen():
    seen = set()
    if not os.path.exists(MANIFEST):
        return seen
    with open(MANIFEST, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                if r.get("prompt") and r.get("seed") is not None:
                    seen.add((r["prompt"], int(r["seed"])))
            except Exception:
                continue
    return seen


def work(job, seen, gkey, total):
    try:
        _work(job, seen, gkey, total)
    except Exception as e:
        with lock:
            stats["failed"] += 1
            print(f"   ERROR  {type(e).__name__}: {e}", flush=True)


def _work(job, seen, gkey, total):
    if stop.is_set():
        return
    p, bid, tier = job["p"], job["bid"], job["tier"]
    ident = (p["prompt"], p["seed"])

    with lock:
        if ident in seen:
            stats["skipped"] += 1
            return
        seen.add(ident)

    data, source = None, "pollinations"
    if tier == "q" and gkey:
        data = fetch_imagen(p["prompt"], gkey)
        if data is not None:
            source = "imagen"
    if data is None:
        data = fetch_pollinations(p["url"])

    if data is None:
        with lock:
            stats["failed"] += 1
            print(f"   FAILED {p['text'][:66]}", flush=True)
        return

    bad = image_is_bad(data)
    if bad:
        # Do not record it — leaving it out of the manifest means a re-run retries it.
        with lock:
            seen.discard(ident)
            stats["rejected"] += 1
            print(f"   REJECT {bad}: {p['text'][:52]}", flush=True)
        return

    fname = hashlib.sha1(data).hexdigest()[:12] + ".jpg"
    fpath = os.path.join(DEST, fname)
    already = os.path.join(IMAGES, fname)

    with lock:
        stats[source] += 1
        if os.path.exists(fpath) or os.path.exists(already):
            stats["skipped"] += 1
        else:
            with open(fpath, "wb") as f:
                f.write(data)
            stats["saved"] += 1

        with open(MANIFEST, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "path": os.path.relpath(fpath, ROOT).replace("\\", "/"), "prompt": p["prompt"],
                "batch": bid, "tier": tier, "source": source,
                "subject": p["subject"], "shot": p["shot"], "light": p["light"],
                "seed": p["seed"], "bytes": len(data),
                "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }, ensure_ascii=False) + "\n")

        n = stats["saved"] + stats["skipped"] + stats["failed"]
        if n % 10 == 0 or n == total:
            el = time.time() - T0
            eta = (total - n) / (n / el) if n and el else 0
            print(f"   [{n}/{total}] saved {stats['saved']} skipped {stats['skipped']} "
                  f"failed {stats['failed']} | {throttle['delay']:.1f}s pace | "
                  f"eta {eta/60:.0f} min", flush=True)


def main():
    ap = argparse.ArgumentParser(description="Fetch image batches by id.")
    ap.add_argument("batches", nargs="*", help="batch ids, e.g. A1 A2 B1")
    ap.add_argument("--all", action="store_true", help="every batch in the taxonomy")
    ap.add_argument("--theme", help="every batch in one theme code, e.g. I")
    ap.add_argument("--tier", choices=["q", "b"], help="q = human subjects, b = bulk")
    ap.add_argument("--list", action="store_true", help="list batch ids and exit")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--limit", type=int, help="stop after N prompts — handy for a test run")
    ap.add_argument("--direct", action="store_true",
                    help="write straight to library/images instead of the review inbox")
    ap.add_argument("--no-imagen", action="store_true", help="force free Pollinations only")
    args = ap.parse_args()

    all_batches = build_batches()

    if args.list:
        all_jobs = [{"p": p, "bid": b["id"], "tier": p.get("tier", b["tier"])} for b in all_batches for p in b["prompts"]]
        total_prompts = len(all_jobs)
        total_q = sum(1 for j in all_jobs if j["tier"] == "q")
        total_b = total_prompts - total_q
        print(f"{len(all_batches)} batches, {total_prompts} prompts ({total_q} quality/Imagen, {total_b} bulk/Pollinations)\n")
        cur = None
        for b in all_batches:
            if b["code"] != cur:
                cur = b["code"]
                print(f"\n{b['theme']}  [{'IMAGEN' if b['tier']=='q' else 'bulk'}]")
            b_q = sum(1 for p in b["prompts"] if p.get("tier", b["tier"]) == "q")
            print(f"   {b['id']:<5} {len(b['prompts'])} prompts ({b_q} quality)")
        return

    chosen = []
    if args.all:
        chosen = all_batches
    elif args.theme:
        chosen = [b for b in all_batches if b["code"].upper() == args.theme.upper()]
    elif args.tier:
        chosen = [b for b in all_batches if any(p.get("tier", b["tier"]) == args.tier for p in b["prompts"])]
    elif args.batches:
        bm = batch_map()
        for bid in args.batches:
            b = bm.get(bid.upper())
            if b:
                chosen.append(b)
            else:
                print(f"unknown batch id: {bid}   (run --list to see them all)")
                sys.exit(1)
    else:
        ap.print_help()
        print("\nNothing selected. Try:  python tools/fetch_batches.py --list")
        sys.exit(1)

    throttle["delay"] = max(throttle["min"], args.delay)
    global DEST
    DEST = IMAGES if args.direct else INBOX
    os.makedirs(IMAGES, exist_ok=True)
    os.makedirs(DEST, exist_ok=True)
    seen = load_seen()
    gkey = "" if args.no_imagen else google_key()

    jobs = [{"p": p, "bid": b["id"], "tier": p.get("tier", b["tier"])} for b in chosen for p in b["prompts"]]
    if args.limit:
        jobs = jobs[:args.limit]
    nq = sum(1 for j in jobs if j["tier"] == "q")

    print(f"batches   : {len(chosen)}  ({', '.join(b['id'] for b in chosen[:12])}"
          f"{' ...' if len(chosen) > 12 else ''})")
    print(f"prompts   : {len(jobs)}  ({nq} human-subject, {len(jobs)-nq} bulk)")
    print(f"manifest  : {len(seen)} already recorded - those are skipped")
    print(f"images    : {len(os.listdir(IMAGES))} on disk")
    if nq:
        print(f"quality   : {'Imagen 4.0' if gkey else 'no Google key, falling back to Pollinations'}")
    print(f"dest      : {os.path.relpath(DEST, ROOT)}"
          + ("" if args.direct else "   (review, then: python tools/promote_inbox.py)"))
    print(f"pacing    : {args.workers} workers, {throttle['delay']:.1f}s apart, auto-backoff")
    print("Safe to leave running. Ctrl+C stops cleanly; re-run resumes.\n", flush=True)

    global T0
    T0 = time.time()
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            list(ex.map(lambda j: work(j, seen, gkey, len(jobs)), jobs))
    except KeyboardInterrupt:
        stop.set()
        print("\ninterrupted - finishing in-flight requests ...")

    print(f"\ndone in {(time.time()-T0)/60:.1f} min - saved {stats['saved']}, "
          f"skipped {stats['skipped']}, failed {stats['failed']}, rejected {stats['rejected']}")
    print(f"sources: imagen {stats['imagen']}, pollinations {stats['pollinations']}"
          + (f", rate-limited {stats['throttled']}x" if stats["throttled"] else ""))
    print(f"library/images now holds {len(os.listdir(IMAGES))} files")
    if stats["failed"]:
        print("Re-run the same command to retry failures - everything else is skipped.")


if __name__ == "__main__":
    main()
