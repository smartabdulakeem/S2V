#!/usr/bin/env python3
"""
tools/promote_inbox.py

Review gate between download and library.

    python tools/promote_inbox.py --sheets     # build contact sheets to review
    python tools/promote_inbox.py              # move survivors into the library
    python tools/promote_inbox.py --stats      # what is waiting

How it works:
  1. The fetcher writes new images into library/_inbox/
  2. Run --sheets. It builds numbered contact sheets in library/_sheets/, 24 images each,
     with the filename printed under every tile.
  3. Open the sheets. For anything bad, delete that file from library/_inbox/ — Windows
     Explorer in Large Icons view works fine for this too.
  4. Run this script with no arguments. Whatever is still in _inbox moves into
     library/images/ and the manifest paths are rewritten to match.

Deleting from _inbox is the rejection. Nothing else to click.
"""

import argparse
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INBOX = os.path.join(ROOT, "library", "_inbox")
IMAGES = os.path.join(ROOT, "library", "images")
SHEETS = os.path.join(ROOT, "library", "_sheets")
MANIFEST = os.path.join(ROOT, "library", "manifest.jsonl")

EXT = (".jpg", ".jpeg", ".png", ".webp")


def inbox_files():
    if not os.path.isdir(INBOX):
        return []
    return sorted(f for f in os.listdir(INBOX) if f.lower().endswith(EXT))


def build_sheets(cols=6, rows=4, tile=(320, 180)):
    from PIL import Image, ImageDraw

    files = inbox_files()
    if not files:
        print("inbox is empty — nothing to review")
        return

    if os.path.isdir(SHEETS):
        shutil.rmtree(SHEETS)
    os.makedirs(SHEETS, exist_ok=True)

    tw, th = tile
    label = 16
    per = cols * rows
    made = 0

    for start in range(0, len(files), per):
        chunk = files[start:start + per]
        used_rows = -(-len(chunk) // cols)          # only as tall as the tiles need
        used_cols = min(cols, len(chunk))
        sheet = Image.new("RGB", (used_cols * tw, used_rows * (th + label)), (16, 18, 22))
        draw = ImageDraw.Draw(sheet)
        for i, fn in enumerate(chunk):
            x, y = (i % cols) * tw, (i // cols) * (th + label)
            try:
                im = Image.open(os.path.join(INBOX, fn)).convert("RGB").resize((tw, th))
                sheet.paste(im, (x, y))
            except Exception:
                draw.rectangle([x, y, x + tw, y + th], fill=(60, 20, 20))
            draw.text((x + 4, y + th + 3), fn, fill=(150, 160, 170))
        made += 1
        out = os.path.join(SHEETS, f"sheet_{made:03d}.jpg")
        sheet.save(out, "JPEG", quality=88)

    print(f"{len(files)} images -> {made} contact sheets in library/_sheets/")
    print("\nReview them, delete any bad file from library/_inbox/, then run:")
    print("   python tools/promote_inbox.py")


def promote():
    files = inbox_files()
    if not files:
        print("inbox is empty — nothing to promote")
        return

    os.makedirs(IMAGES, exist_ok=True)
    moved = collided = 0
    for fn in files:
        src, dst = os.path.join(INBOX, fn), os.path.join(IMAGES, fn)
        if os.path.exists(dst):
            os.remove(src)          # same content hash, already in the library
            collided += 1
        else:
            shutil.move(src, dst)
            moved += 1

    # rewrite manifest paths that still point at the inbox
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
                newp = p.replace("library/_inbox", "library/images")
                if os.path.exists(os.path.join(ROOT, newp)):
                    r["path"] = newp
                    rewritten += 1
                else:
                    dropped += 1       # the operator deleted it — drop the record too
                    continue
            keep.append(r)
        with open(MANIFEST, "w", encoding="utf-8") as f:
            for r in keep:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    if os.path.isdir(SHEETS):
        shutil.rmtree(SHEETS, ignore_errors=True)

    print(f"promoted   : {moved}")
    if collided:
        print(f"duplicates : {collided} (identical bytes already in the library)")
    print(f"manifest   : {rewritten} paths updated, {dropped} rejected records removed")
    print(f"library    : {len(os.listdir(IMAGES))} images total")
    print("\nReindex CLIP when you are done adding:")
    print("   python -m pipeline.library reindex")


def stats():
    files = inbox_files()
    n_lib = len(os.listdir(IMAGES)) if os.path.isdir(IMAGES) else 0
    print(f"inbox   : {len(files)} awaiting review")
    print(f"library : {n_lib} approved")
    if files:
        print("\nNext:  python tools/promote_inbox.py --sheets")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Review gate between download and library.")
    ap.add_argument("--sheets", action="store_true", help="build contact sheets for review")
    ap.add_argument("--stats", action="store_true", help="show counts and exit")
    a = ap.parse_args()
    if a.stats:
        stats()
    elif a.sheets:
        build_sheets()
    else:
        promote()
