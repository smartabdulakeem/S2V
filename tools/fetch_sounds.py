#!/usr/bin/env python3
"""
tools/fetch_sounds.py

Download sound batches by category or batch ID from Freesound.org.

    python tools/fetch_sounds.py BED1 BED2          # specific batches
    python tools/fetch_sounds.py --category beds    # every batch in 'beds'
    python tools/fetch_sounds.py --all              # the whole sound taxonomy
    python tools/fetch_sounds.py --list             # show batch IDs and exit

Built for long unattended runs: paced requests, automatic backoff on rate limits,
never crashes on a single bad item, audio quality gate (peak > -45dB, duration bounds,
silence check), -16 LUFS loudness normalization, and fully resumable.
"""

import argparse
import hashlib
import json
import os
import random
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests
import imageio_ffmpeg

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sound_taxonomy import build_sound_batches, sound_batch_map, CATEGORIES  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOUNDS_DIR = os.path.join(ROOT, "library", "sounds")
INBOX_DIR = os.path.join(SOUNDS_DIR, "_inbox")
MANIFEST_PATH = os.path.join(SOUNDS_DIR, "manifest.jsonl")
SETTINGS_PATH = os.path.join(ROOT, "config", "settings.json")

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
UA = {"User-Agent": "S2V-AudioFetcher/1.0 (Mozilla/5.0 Windows NT 10.0; Win64; x64)"}

lock = threading.Lock()
stop = threading.Event()
stats = {
    "saved": 0, "skipped": 0, "failed": 0, "rejected": 0,
    "cc0": 0, "cc_by": 0, "throttled": 0,
    "rejections": {}  # reason -> count
}
throttle = {"delay": 1.0, "min": 0.4, "max": 30.0, "ok": 0}
T0 = time.time()
DEST_DIR = INBOX_DIR


def get_freesound_token():
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            token = json.load(f).get("freesound_token", "").strip()
            if token:
                return token
    except Exception:
        pass
    return os.environ.get("FREESOUND_TOKEN", "").strip()


def on_rate_limit():
    with lock:
        throttle["delay"] = min(throttle["max"], max(2.0, throttle["delay"] * 2))
        throttle["ok"] = 0
        stats["throttled"] += 1
        print(f"   rate limited / slow connection - easing delay to {throttle['delay']:.1f}s", flush=True)


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


def analyze_and_normalize_audio(raw_bytes, min_dur, max_dur, target_lufs=-16):
    """
    Quality gate & normalization:
    1. Save raw preview bytes to temporary file
    2. Run ffmpeg volumedetect to get duration & peak volume
    3. Validate duration is within [min_dur, max_dur]
    4. Validate peak volume > -45.0 dB (not silent/dead)
    5. Run ffmpeg loudnorm filter to normalize to target_lufs (-16 LUFS)
    6. Return (normalized_bytes, duration, peak_db, reject_reason)
    """
    import tempfile
    tmp_dir = tempfile.gettempdir()
    tmp_in = os.path.join(tmp_dir, f"s2v_tmp_{threading.get_ident()}_{random.randint(1000, 9999)}.mp3")
    tmp_out = tmp_in.replace(".mp3", "_norm.mp3")

    try:
        with open(tmp_in, "wb") as f:
            f.write(raw_bytes)

        # Run ffmpeg volumedetect
        cmd_vol = [
            FFMPEG_EXE, "-hide_banner", "-i", tmp_in,
            "-af", "volumedetect", "-f", "null", "-"
        ]
        res = subprocess.run(cmd_vol, capture_output=True, text=True, timeout=30)
        stderr = res.stderr

        duration = 0.0
        peak_db = -99.0

        for line in stderr.splitlines():
            if "Duration:" in line:
                try:
                    parts = line.split("Duration:")[1].split(",")[0].strip().split(":")
                    if len(parts) == 3:
                        duration = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                except Exception:
                    pass
            elif "max_volume:" in line:
                try:
                    val = line.split("max_volume:")[1].replace("dB", "").strip()
                    peak_db = float(val)
                except Exception:
                    pass

        if duration <= 0.05:
            return None, 0, 0, "unreadable or 0s duration"

        if duration < min_dur or duration > max_dur:
            return None, duration, peak_db, f"duration {duration:.1f}s out of range [{min_dur}-{max_dur}s]"

        if peak_db < -45.0:
            return None, duration, peak_db, f"near silent (peak {peak_db:.1f} dB < -45 dB)"

        # Normalize to -16 LUFS using loudnorm
        cmd_norm = [
            FFMPEG_EXE, "-y", "-hide_banner", "-i", tmp_in,
            "-af", f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11",
            "-b:a", "192k", tmp_out
        ]
        res_norm = subprocess.run(cmd_norm, capture_output=True, text=True, timeout=60)

        if res_norm.returncode != 0 or not os.path.exists(tmp_out):
            return None, duration, peak_db, "ffmpeg loudnorm failed"

        with open(tmp_out, "rb") as f:
            norm_bytes = f.read()

        if len(norm_bytes) < 1024:
            return None, duration, peak_db, "normalized output file too small"

        return norm_bytes, duration, peak_db, None

    except Exception as e:
        return None, 0, 0, f"processing error ({type(e).__name__})"
    finally:
        for f in [tmp_in, tmp_out]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass


def load_seen():
    seen_ids = set()
    if not os.path.exists(MANIFEST_PATH):
        return seen_ids
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                if r.get("seed_or_id"):
                    seen_ids.add(int(r["seed_or_id"]))
            except Exception:
                continue
    return seen_ids


def search_freesound(token, query, fallbacks, dur_filter):
    """Search Freesound. Try primary query, fallback to secondary queries if count < 5."""
    queries_to_try = [query] + fallbacks
    for q in queries_to_try:
        if stop.is_set():
            return [], q
        params = {
            "query": q,
            "filter": f'duration:{dur_filter} license:("Creative Commons 0" OR "Attribution")',
            "fields": "id,name,username,license,previews,duration,url",
            "token": token,
            "page_size": 25,
        }
        try:
            pace()
            r = requests.get("https://freesound.org/apiv2/search/text/", params=params, headers=UA, timeout=20)
            if r.status_code == 200:
                data = r.json()
                results = data.get("results", [])
                if len(results) >= 3 or q == queries_to_try[-1]:
                    on_success()
                    return results, q
            elif r.status_code in (429, 503):
                on_rate_limit()
        except Exception:
            pass
    return [], query


def process_query_job(job, token, seen_ids, total_jobs):
    if stop.is_set():
        return

    q = job["query"]
    fallbacks = job["fallbacks"]
    cat = job["category"]
    bid = job["batch_id"]
    min_dur = job["min_dur"]
    max_dur = job["max_dur"]
    dur_filter = job["dur_filter"]

    results, working_query = search_freesound(token, q, fallbacks, dur_filter)

    if not results:
        with lock:
            stats["failed"] += 1
            print(f"   FAILED query '{q}' (no results returned)", flush=True)
        return

    # Sort results to prefer CC0 over CC-BY
    def license_priority(item):
        lic = item.get("license", "").lower()
        if "zero" in lic or "publicdomain" in lic:
            return 0
        return 1

    results.sort(key=license_priority)

    # Try up to top 3 items per query to land at least 1 valid file
    landed_for_query = 0
    for item in results[:4]:
        if stop.is_set() or landed_for_query >= 2:
            break

        sound_id = item["id"]
        with lock:
            if sound_id in seen_ids:
                stats["skipped"] += 1
                continue
            seen_ids.add(sound_id)

        preview_url = item.get("previews", {}).get("preview-hq-mp3")
        if not preview_url:
            continue

        # Fetch preview MP3
        raw_bytes = None
        for attempt in range(2):
            if stop.is_set():
                break
            try:
                pace()
                r = requests.get(preview_url, headers=UA, timeout=30, stream=True)
                if r.status_code == 200:
                    raw_bytes = r.content
                    on_success()
                    break
                elif r.status_code in (429, 503):
                    on_rate_limit()
            except Exception:
                pass
            time.sleep(1.0)

        if not raw_bytes or len(raw_bytes) < 1024:
            with lock:
                stats["failed"] += 1
            continue

        # Audio quality gate & LUFS normalization
        norm_bytes, dur, peak, reject_reason = analyze_and_normalize_audio(
            raw_bytes, min_dur, max_dur, target_lufs=-16
        )

        if reject_reason:
            with lock:
                seen_ids.discard(sound_id)
                stats["rejected"] += 1
                stats["rejections"][reject_reason] = stats["rejections"].get(reject_reason, 0) + 1
                print(f"   REJECT {reject_reason}: sound {sound_id} '{item['name'][:40]}'", flush=True)
            continue

        # Parse license type & attribution string
        lic_url = item.get("license", "")
        is_cc0 = "zero" in lic_url.lower() or "publicdomain" in lic_url.lower()
        lic_type = "CC0" if is_cc0 else "CC-BY"
        username = item.get("username", "unknown")
        sound_name = item.get("name", f"sound_{sound_id}")
        attribution = f"{username} - '{sound_name}' ({lic_url})"

        # Content hash filename
        fname = hashlib.sha1(norm_bytes).hexdigest()[:12] + ".mp3"
        fpath = os.path.join(DEST_DIR, fname)
        canonical_path = os.path.join(SOUNDS_DIR, fname)

        with lock:
            if os.path.exists(fpath) or os.path.exists(canonical_path):
                stats["skipped"] += 1
            else:
                with open(fpath, "wb") as f:
                    f.write(norm_bytes)
                stats["saved"] += 1

                if is_cc0:
                    stats["cc0"] += 1
                else:
                    stats["cc_by"] += 1

                # Record in manifest
                rel_path = os.path.relpath(fpath, ROOT).replace("\\", "/")
                with open(MANIFEST_PATH, "a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "path": rel_path,
                        "query": working_query,
                        "category": cat,
                        "batch": bid,
                        "source": "freesound",
                        "licence": lic_url,
                        "licence_type": lic_type,
                        "attribution": attribution,
                        "duration": round(dur, 2),
                        "peak_db": round(peak, 1),
                        "seed_or_id": sound_id,
                        "bytes": len(norm_bytes),
                        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    }, ensure_ascii=False) + "\n")

                landed_for_query += 1
                print(f"   SAVED [{lic_type}] {dur:4.1f}s | {working_query:<16} | "
                      f"sound {sound_id}: '{sound_name[:45]}'", flush=True)


def main():
    ap = argparse.ArgumentParser(description="Fetch sound batches from Freesound.org.")
    ap.add_argument("batches", nargs="*", help="batch IDs, e.g. BED1 BED2 SHOT1 STING1")
    ap.add_argument("--all", action="store_true", help="every batch in the sound taxonomy")
    ap.add_argument("--category", choices=["beds", "oneshots", "stingers"], help="category name")
    ap.add_argument("--list", action="store_true", help="list batch IDs and exit")
    ap.add_argument("--workers", type=int, default=2, help="number of parallel workers")
    ap.add_argument("--delay", type=float, default=1.0, help="request pacing delay")
    ap.add_argument("--limit", type=int, help="max queries to process")
    ap.add_argument("--direct", action="store_true",
                    help="write straight to library/sounds instead of _inbox")
    args = ap.parse_args()

    all_batches = build_sound_batches()

    if args.list:
        print(f"Sound Taxonomy ({len(all_batches)} batches):\n")
        for b in all_batches:
            print(f"  {b['id']:<6} {b['category']:<10} {len(b['prompts']):>2} queries  {b['theme']}")
        return

    token = get_freesound_token()
    if not token:
        print("ERROR: freesound_token not found in config/settings.json or environment!")
        sys.exit(1)

    chosen = []
    if args.all:
        chosen = all_batches
    elif args.category:
        chosen = [b for b in all_batches if b["category"] == args.category]
    elif args.batches:
        bm = sound_batch_map()
        for bid in args.batches:
            b = bm.get(bid.upper())
            if b:
                chosen.append(b)
            else:
                print(f"Unknown batch ID: {bid}  (run --list to see available batches)")
                sys.exit(1)
    else:
        ap.print_help()
        print("\nNothing selected. Try:  python tools/fetch_sounds.py BED1")
        sys.exit(1)

    global DEST_DIR
    DEST_DIR = SOUNDS_DIR if args.direct else INBOX_DIR
    os.makedirs(SOUNDS_DIR, exist_ok=True)
    os.makedirs(DEST_DIR, exist_ok=True)

    seen_ids = load_seen()
    throttle["delay"] = max(throttle["min"], args.delay)

    jobs = []
    for b in chosen:
        for p in b["prompts"]:
            jobs.append({
                "batch_id": b["id"],
                "category": b["category"],
                "query": p["query"],
                "fallbacks": p["fallbacks"],
                "min_dur": p["min_dur"],
                "max_dur": p["max_dur"],
                "dur_filter": p["dur_filter"],
            })

    if args.limit:
        jobs = jobs[:args.limit]

    print(f"batches   : {len(chosen)} ({', '.join(b['id'] for b in chosen)})")
    print(f"queries   : {len(jobs)}")
    print(f"manifest  : {len(seen_ids)} sound IDs already recorded - skipped")
    print(f"destination: {os.path.relpath(DEST_DIR, ROOT)}")
    print(f"pacing    : {args.workers} workers, {throttle['delay']:.1f}s delay, auto-backoff")
    print("Safe to leave running. Ctrl+C stops cleanly; re-run resumes.\n", flush=True)

    global T0
    T0 = time.time()

    try:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            list(ex.map(lambda j: process_query_job(j, token, seen_ids, len(jobs)), jobs))
    except KeyboardInterrupt:
        stop.set()
        print("\nInterrupted — finishing in-flight sound downloads ...")

    elapsed = (time.time() - T0) / 60
    print(f"\nDone in {elapsed:.1f} min — saved {stats['saved']}, skipped {stats['skipped']}, "
          f"failed {stats['failed']}, rejected {stats['rejected']}")
    print(f"Licence split : CC0 = {stats['cc0']}, CC-BY = {stats['cc_by']}")
    if stats["rejections"]:
        print("Rejections breakdown:")
        for reason, cnt in stats["rejections"].items():
            print(f"   {reason}: {cnt}")
    print(f"Destination folder contains {len(os.listdir(DEST_DIR))} files")


if __name__ == "__main__":
    main()
