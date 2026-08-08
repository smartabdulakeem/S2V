#!/usr/bin/env python3
"""
tools/promote_sounds.py

Review gate between sound fetcher inbox and sound library.

    python tools/promote_sounds.py --sheets     # build contact sheet MP3s + TXT manifests to listen & review
    python tools/promote_sounds.py              # move survivors into library/sounds/
    python tools/promote_sounds.py --stats      # show inbox vs library counts

How it works:
  1. The fetcher writes new sound files into library/sounds/_inbox/
  2. Run --sheets. It builds concatenated contact sheets in library/sounds/_sheets/, 10 clips each,
     with 0.5s silence gaps, plus a matching .txt index for each sheet.
  3. Listen to contact sheets. For any bad clip, note its filename from the .txt list and delete it
     from library/sounds/_inbox/
  4. Run this script with no arguments. Whatever is still in _inbox moves into library/sounds/
     and manifest.jsonl paths are updated to match.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import imageio_ffmpeg

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOUNDS = os.path.join(ROOT, "library", "sounds")
INBOX = os.path.join(SOUNDS, "_inbox")
SHEETS = os.path.join(SOUNDS, "_sheets")
MANIFEST = os.path.join(SOUNDS, "manifest.jsonl")

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
EXT = (".mp3", ".wav", ".ogg", ".flac")


def inbox_files():
    if not os.path.isdir(INBOX):
        return []
    return sorted(f for f in os.listdir(INBOX) if f.lower().endswith(EXT))


def build_sheets(chunk_size=10):
    files = inbox_files()
    if not files:
        print("Inbox is empty — nothing to review")
        return

    if os.path.isdir(SHEETS):
        shutil.rmtree(SHEETS, ignore_errors=True)
    os.makedirs(SHEETS, exist_ok=True)

    # Read manifest metadata for rich TXT output
    manifest_map = {}
    if os.path.exists(MANIFEST):
        with open(MANIFEST, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                    fname = os.path.basename(r.get("path", ""))
                    manifest_map[fname] = r
                except Exception:
                    pass

    made = 0
    for start in range(0, len(files), chunk_size):
        chunk = files[start:start + chunk_size]
        made += 1
        out_mp3 = os.path.join(SHEETS, f"contact_{made:03d}.mp3")
        out_txt = os.path.join(SHEETS, f"contact_{made:03d}.txt")

        # Create concat list for ffmpeg with 0.5s silence in between
        # Generate 0.5s silence file if needed
        silence_file = os.path.join(SHEETS, "_silence_05s.mp3")
        if not os.path.exists(silence_file):
            cmd_silence = [
                FFMPEG_EXE, "-y", "-hide_banner", "-f", "lavfi",
                "-i", "anullsrc=r=44100:cl=stereo", "-t", "0.5",
                "-b:a", "192k", silence_file
            ]
            subprocess.run(cmd_silence, capture_output=True)

        concat_list_path = os.path.join(SHEETS, f"_concat_{made:03d}.txt")
        lines = []
        txt_lines = [f"=== Contact Sheet #{made:03d} ({len(chunk)} sounds) ===\n"]

        for idx, fn in enumerate(chunk, 1):
            file_path = os.path.join(INBOX, fn).replace("\\", "/")
            lines.append(f"file '{file_path}'")
            if os.path.exists(silence_file):
                lines.append(f"file '{silence_file.replace('\\', '/')}'")

            info = manifest_map.get(fn, {})
            cat = info.get("category", "unknown")
            dur = info.get("duration", 0)
            q = info.get("query", "unknown")
            lic = info.get("licence_type", "unknown")
            txt_lines.append(f"  [{idx:02d}] {fn} | {cat:<8} | {dur:4.1f}s | {lic:<5} | query: '{q}'")

        with open(concat_list_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        with open(out_txt, "w", encoding="utf-8") as f:
            f.write("\n".join(txt_lines) + "\n")

        # Concatenate using ffmpeg
        cmd_concat = [
            FFMPEG_EXE, "-y", "-hide_banner", "-f", "concat", "-safe", "0",
            "-i", concat_list_path, "-c", "copy", out_mp3
        ]
        res = subprocess.run(cmd_concat, capture_output=True)

        if res.returncode != 0 or not os.path.exists(out_mp3):
            # Fallback re-encode if copy failed
            cmd_concat_reencode = [
                FFMPEG_EXE, "-y", "-hide_banner", "-f", "concat", "-safe", "0",
                "-i", concat_list_path, "-b:a", "192k", out_mp3
            ]
            subprocess.run(cmd_concat_reencode, capture_output=True)

        if os.path.exists(concat_list_path):
            os.remove(concat_list_path)

    silence_file = os.path.join(SHEETS, "_silence_05s.mp3")
    if os.path.exists(silence_file):
        os.remove(silence_file)

    print(f"{len(files)} sound files -> {made} contact sheet MP3s in library/sounds/_sheets/")
    print("\nListen to the contact sheets. To reject a bad sound, delete its file from library/sounds/_inbox/")
    print("Then promote the survivors by running:")
    print("   python tools/promote_sounds.py")


def promote():
    files = inbox_files()
    if not files:
        print("Inbox is empty — nothing to promote")
        return

    os.makedirs(SOUNDS, exist_ok=True)
    moved = collided = 0
    for fn in files:
        src, dst = os.path.join(INBOX, fn), os.path.join(SOUNDS, fn)
        if os.path.exists(dst):
            os.remove(src)
            collided += 1
        else:
            shutil.move(src, dst)
            moved += 1

    # Rewrite manifest paths that point at _inbox
    rewritten = dropped = 0
    if os.path.exists(MANIFEST):
        keep = []
        for line in open(MANIFEST, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            p = r.get("path", "")
            if "_inbox" in p:
                newp = p.replace("library/sounds/_inbox", "library/sounds")
                if os.path.exists(os.path.join(ROOT, newp)):
                    r["path"] = newp
                    rewritten += 1
                else:
                    dropped += 1  # file was deleted by reviewer
                    continue
            keep.append(r)
        with open(MANIFEST, "w", encoding="utf-8") as f:
            for r in keep:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    if os.path.isdir(SHEETS):
        shutil.rmtree(SHEETS, ignore_errors=True)

    print(f"Promoted   : {moved} sounds")
    if collided:
        print(f"Duplicates : {collided} (identical content hash already in library)")
    print(f"Manifest   : {rewritten} paths updated, {dropped} rejected records removed")
    print(f"Library    : {len([f for f in os.listdir(SOUNDS) if f.endswith(EXT)])} sounds total")


def stats():
    files = inbox_files()
    n_lib = len([f for f in os.listdir(SOUNDS) if f.endswith(EXT)]) if os.path.isdir(SOUNDS) else 0
    print(f"Inbox   : {len(files)} awaiting review")
    print(f"Library : {n_lib} approved")
    if files:
        print("\nNext:  python tools/promote_sounds.py --sheets")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Review gate for sound library.")
    ap.add_argument("--sheets", action="store_true", help="build contact sheet MP3s for review")
    ap.add_argument("--stats", action="store_true", help="show counts and exit")
    a = ap.parse_args()
    if a.stats:
        stats()
    elif a.sheets:
        build_sheets()
    else:
        promote()
