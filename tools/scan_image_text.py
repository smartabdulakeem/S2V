"""
tools/scan_image_text.py

Scans every image in library/images/ for burned-in text artifacts using RapidOCR (CPU).
Caches results in library/text_scan.jsonl keyed by SHA-256 content hash (resumable).
Generates library/text_scan_report.html contact sheet.
Optional --quarantine flag moves "burned" bucket images to library/_quarantine/.
"""

import os
import sys
import re
import json
import time
import shutil
import argparse
import hashlib
from pathlib import Path
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

LIBRARY_DIR = os.path.join(ROOT_DIR, "library")
IMAGES_DIR = os.path.join(LIBRARY_DIR, "images")
QUARANTINE_DIR = os.path.join(LIBRARY_DIR, "_quarantine")
MANIFEST_PATH = os.path.join(LIBRARY_DIR, "manifest.jsonl")
CACHE_FILE = os.path.join(LIBRARY_DIR, "text_scan.jsonl")
REPORT_HTML = os.path.join(LIBRARY_DIR, "text_scan_report.html")
SAMPLES_DIR = os.path.join(ROOT_DIR, "samples")


def hash_file(filepath: str) -> str:
    """Compute SHA-256 hash of file content."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def calculate_polygon_area(pts: list) -> float:
    """Calculate area of a 4-point polygon using the Shoelace formula."""
    if not pts or len(pts) < 3:
        return 0.0
    n = len(pts)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += pts[i][0] * pts[j][1]
        area -= pts[j][0] * pts[i][1]
    return abs(area) / 2.0


def load_known_script_texts() -> set:
    """
    Loads project titles, narration strings, and b-roll queries from manifest
    and sample scripts into a set of normalized target words/phrases.
    """
    known_strings = set()

    # Load manifest
    if os.path.exists(MANIFEST_PATH):
        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        for key in ["title", "narration", "b_roll_keyword", "query", "project_title"]:
                            val = entry.get(key)
                            if val and isinstance(val, str):
                                known_strings.add(val.strip().lower())
                    except Exception:
                        pass
        except Exception:
            pass

    # Load samples
    if os.path.exists(SAMPLES_DIR):
        for s_file in Path(SAMPLES_DIR).glob("*.json"):
            try:
                with open(s_file, "r", encoding="utf-8") as f:
                    s_data = json.load(f)
                    proj = s_data.get("project", {})
                    if proj.get("title"):
                        known_strings.add(proj["title"].strip().lower())
                    for seg in s_data.get("segments", []):
                        if seg.get("narration"):
                            known_strings.add(seg["narration"].strip().lower())
                        for shot in seg.get("shots", []):
                            if shot.get("query"):
                                known_strings.add(shot["query"].strip().lower())
            except Exception:
                pass

    # Add known leftover phrases confirmed in library
    known_strings.update([
        "american civil war intro sample",
        "fort sumter",
        "civil war",
        "abraham lincoln",
        "fiogght",
        "ofbrother",
        "apollo 11",
        "saturn v",
        "the rise of baghdad"
    ])

    return known_strings


def load_manifest_paths() -> set:
    """Returns normalized relative paths present in manifest.jsonl."""
    paths = set()
    if os.path.exists(MANIFEST_PATH):
        try:
            with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        p = entry.get("path") or entry.get("file_path")
                        if p:
                            norm_p = p.replace("\\", "/")
                            paths.add(norm_p)
                    except Exception:
                        pass
        except Exception:
            pass
    return paths


def classify_detections(detections: list, total_area_pct: float, text_concat: str, known_texts: set) -> tuple[str, bool, str]:
    """
    Classifies detection results into ('clean', 'review', 'burned').
    Returns (bucket, matches_known_text, reason).
    """
    if not detections:
        return "clean", False, "No text detected"

    text_lower = text_concat.lower()

    # Check for direct script/title text match
    matched_phrase = None
    for known in known_texts:
        if len(known) >= 4 and known in text_lower:
            matched_phrase = known
            break
        # Also check individual long words from title/narration
        words = [w for w in re.split(r'\W+', known) if len(w) >= 5]
        for w in words:
            if len(w) >= 6 and w in text_lower:
                matched_phrase = f"word '{w}'"
                break

    if matched_phrase:
        return "burned", True, f"Matches script/manifest text ({matched_phrase})"

    # High confidence detections count
    high_conf_detections = [d for d in detections if d["confidence"] >= 0.75]
    long_strings = [d for d in detections if len(d["text"]) >= 14 and d["confidence"] >= 0.70]

    # Threshold rules for burned vs review
    if total_area_pct >= 1.2 and len(high_conf_detections) >= 1:
        return "burned", False, f"Large text block (covered area {total_area_pct:.2f}% >= 1.2%)"

    if len(long_strings) >= 1:
        return "burned", False, f"Long text block detected ('{long_strings[0]['text'][:20]}...')"

    if len(high_conf_detections) >= 3:
        return "burned", False, f"Multiple text blocks detected ({len(high_conf_detections)} lines)"

    # Small or low-confidence text -> review bucket
    return "review", False, f"Low-confidence or small text (area {total_area_pct:.2f}%, {len(detections)} lines)"


def load_cache() -> dict:
    """Loads existing text_scan.jsonl cache into a dict mapping sha256 -> record."""
    cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                        if "sha256" in record:
                            cache[record["sha256"]] = record
                    except Exception:
                        pass
        except Exception:
            pass
    return cache


def save_cache_record(record: dict):
    """Appends a single scan record to text_scan.jsonl."""
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def generate_html_report(scan_results: list):
    """
    Generates a dark-themed HTML contact sheet report grouped by bucket (burned -> review -> clean).
    """
    burned_list = [r for r in scan_results if r["bucket"] == "burned"]
    review_list = [r for r in scan_results if r["bucket"] == "review"]
    clean_list = [r for r in scan_results if r["bucket"] == "clean"]

    # Sort burned and review worst-first (by area pct and detection count)
    burned_list.sort(key=lambda x: (x.get("matches_script_text", False), x.get("total_covered_area_pct", 0.0), len(x.get("detections", []))), reverse=True)
    review_list.sort(key=lambda x: (x.get("total_covered_area_pct", 0.0), len(x.get("detections", []))), reverse=True)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Smart Studio — Image Text Scan Report</title>
<style>
  :root {{
    --bg: #0f172a;
    --card-bg: #1e293b;
    --border: #334155;
    --text: #f8fafc;
    --text-muted: #94a3b8;
    --burned: #ef4444;
    --review: #f59e0b;
    --clean: #10b981;
  }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background-color: var(--bg);
    color: var(--text);
    margin: 0;
    padding: 24px;
  }}
  h1 {{
    margin-top: 0;
    font-size: 24px;
  }}
  .stats-bar {{
    display: flex;
    gap: 16px;
    margin-bottom: 24px;
  }}
  .stat-card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px 24px;
    min-width: 140px;
  }}
  .stat-val {{
    font-size: 28px;
    font-weight: bold;
  }}
  .stat-val.burned {{ color: var(--burned); }}
  .stat-val.review {{ color: var(--review); }}
  .stat-val.clean {{ color: var(--clean); }}
  .stat-lbl {{
    font-size: 13px;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }}

  section {{
    margin-bottom: 40px;
  }}
  h2 {{
    font-size: 18px;
    border-bottom: 1px solid var(--border);
    padding-bottom: 8px;
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 8px;
  }}

  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 16px;
  }}
  .card {{
    background: var(--card-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }}
  .card-img {{
    width: 100%;
    height: 190px;
    object-fit: cover;
    background: #000;
  }}
  .card-body {{
    padding: 12px 16px;
    font-size: 13px;
    flex-grow: 1;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }}
  .card-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .badge {{
    font-size: 11px;
    font-weight: bold;
    padding: 2px 8px;
    border-radius: 12px;
    text-transform: uppercase;
  }}
  .badge.burned {{ background: rgba(239, 68, 68, 0.2); color: var(--burned); border: 1px solid var(--burned); }}
  .badge.review {{ background: rgba(245, 158, 11, 0.2); color: var(--review); border: 1px solid var(--review); }}
  .badge.clean {{ background: rgba(16, 185, 129, 0.2); color: var(--clean); border: 1px solid var(--clean); }}

  .path {{
    font-family: monospace;
    font-size: 12px;
    color: var(--text-muted);
    word-break: break-all;
  }}
  .detections-table {{
    width: 100%;
    border-collapse: collapse;
    margin-top: 4px;
    font-size: 12px;
  }}
  .detections-table th, .detections-table td {{
    text-align: left;
    padding: 4px 6px;
    border-bottom: 1px solid var(--border);
  }}
  .detections-table th {{
    color: var(--text-muted);
  }}
  .detected-text {{
    color: #f1f5f9;
    font-weight: 500;
  }}
  .reason {{
    font-size: 12px;
    color: #cbd5e1;
    font-style: italic;
  }}
</style>
</head>
<body>
  <h1>Smart Studio — Image Text Scan Report</h1>

  <div class="stats-bar">
    <div class="stat-card">
      <div class="stat-val">{len(scan_results)}</div>
      <div class="stat-lbl">Total Scanned</div>
    </div>
    <div class="stat-card">
      <div class="stat-val burned">{len(burned_list)}</div>
      <div class="stat-lbl">Burned Text</div>
    </div>
    <div class="stat-card">
      <div class="stat-val review">{len(review_list)}</div>
      <div class="stat-lbl">Review Needed</div>
    </div>
    <div class="stat-card">
      <div class="stat-val clean">{len(clean_list)}</div>
      <div class="stat-lbl">Clean</div>
    </div>
  </div>
"""

    def render_card_grid(records: list):
        if not records:
            return "<p style='color: var(--text-muted);'>No images in this category.</p>"
        cards_html = []
        for r in records:
            rel_path = r["path"].replace("\\", "/")
            fname = os.path.basename(rel_path)
            bucket = r["bucket"]
            manifest_tag = "<span style='color:#38bdf8;'>[in manifest]</span>" if r.get("in_manifest") else ""
            reason = r.get("reason", "")
            cov_pct = r.get("total_covered_area_pct", 0.0)

            det_rows = ""
            for d in r.get("detections", []):
                txt = d["text"]
                conf = d["confidence"]
                area = d.get("area_pct", 0.0)
                det_rows += f"<tr><td class='detected-text'>{txt}</td><td>{conf:.2f}</td><td>{area:.2f}%</td></tr>"

            det_table = f"""
            <table class='detections-table'>
              <thead><tr><th>Text Detected</th><th>Conf</th><th>Area</th></tr></thead>
              <tbody>{det_rows}</tbody>
            </table>
            """ if r.get("detections") else "<div style='color: var(--text-muted); font-size:12px;'>No text detected</div>"

            card = f"""
            <div class="card">
              <img class="card-img" src="images/{fname}" alt="{fname}" loading="lazy" />
              <div class="card-body">
                <div class="card-header">
                  <span class="badge {bucket}">{bucket}</span>
                  {manifest_tag}
                </div>
                <div class="path">{fname} ({cov_pct:.2f}% text area)</div>
                <div class="reason">{reason}</div>
                {det_table}
              </div>
            </div>
            """
            cards_html.append(card)
        return f'<div class="grid">{"".join(cards_html)}</div>'

    html_content += f"""
  <section>
    <h2 style="color: var(--burned);">🔥 Burned Text ({len(burned_list)})</h2>
    {render_card_grid(burned_list)}
  </section>

  <section>
    <h2 style="color: var(--review);">⚠️ Review Needed ({len(review_list)})</h2>
    {render_card_grid(review_list)}
  </section>

  <section>
    <h2 style="color: var(--clean);">✅ Clean Images ({len(clean_list)})</h2>
    <p style="color: var(--text-muted);">{len(clean_list)} clean images verified without text artifacts.</p>
  </section>
</body>
</html>
"""

    with open(REPORT_HTML, "w", encoding="utf-8") as f:
        f.write(html_content)


def scan_images(force_rescan: bool = False) -> tuple[list, float]:
    """
    Scans every image in library/images/ using RapidOCR.
    Resumes from text_scan.jsonl cache unless force_rescan is True.
    """
    if not os.path.exists(IMAGES_DIR):
        print(f"Error: Images directory '{IMAGES_DIR}' does not exist.")
        return [], 0.0

    image_paths = sorted(list(Path(IMAGES_DIR).glob("*.jpg")) + list(Path(IMAGES_DIR).glob("*.png")))
    total_images = len(image_paths)

    if total_images == 0:
        print("No images found to scan.")
        return [], 0.0

    print(f"Loaded {total_images} images from {IMAGES_DIR}")

    cache = {} if force_rescan else load_cache()
    known_texts = load_known_script_texts()
    manifest_paths = load_manifest_paths()

    ocr_engine = RapidOCR()
    scan_results = []

    start_time = time.time()
    scanned_count = 0
    cached_count = 0

    for idx, img_p in enumerate(image_paths, 1):
        abs_p = str(img_p)
        rel_p = f"library/images/{img_p.name}".replace("\\", "/")
        in_manifest = rel_p in manifest_paths or img_p.name in manifest_paths

        file_hash = hash_file(abs_p)

        if not force_rescan and file_hash in cache:
            rec = cache[file_hash]
            rec["path"] = rel_p
            rec["in_manifest"] = in_manifest
            scan_results.append(rec)
            cached_count += 1
        else:
            # Perform OCR on image
            try:
                img = Image.open(abs_p)
                w, h = img.size
                img_area = float(w * h)
            except Exception:
                img_area = 1280.0 * 720.0

            try:
                result, _ = ocr_engine(abs_p)
            except Exception as e:
                result = None

            detections = []
            total_box_area = 0.0
            text_chunks = []

            if result:
                for item in result:
                    # item format: [pts, text, conf]
                    pts, txt, conf = item[0], item[1], float(item[2])
                    text_chunks.append(txt)
                    box_area = calculate_polygon_area(pts)
                    total_box_area += box_area
                    area_pct = (box_area / img_area) * 100.0 if img_area > 0 else 0.0
                    detections.append({
                        "text": txt,
                        "confidence": round(conf, 4),
                        "bbox": pts,
                        "area_pct": round(area_pct, 4)
                    })

            total_covered_area_pct = round((total_box_area / img_area) * 100.0, 4) if img_area > 0 else 0.0
            concat_text = " ".join(text_chunks)

            bucket, matches_known, reason = classify_detections(detections, total_covered_area_pct, concat_text, known_texts)

            rec = {
                "sha256": file_hash,
                "path": rel_p,
                "has_text": len(detections) > 0,
                "detections": detections,
                "total_covered_area_pct": total_covered_area_pct,
                "in_manifest": in_manifest,
                "matches_script_text": matches_known,
                "bucket": bucket,
                "reason": reason
            }

            save_cache_record(rec)
            cache[file_hash] = rec
            scan_results.append(rec)
            scanned_count += 1

        if idx % 50 == 0 or idx == total_images:
            elapsed = time.time() - start_time
            avg_per_img = elapsed / max(scanned_count, 1)
            remaining_ocr = total_images - idx
            eta_sec = remaining_ocr * avg_per_img
            print(f"Progress: {idx}/{total_images} images processed ({cached_count} cached, {scanned_count} scanned) — Elapsed: {elapsed:.1f}s — ETA: {eta_sec:.1f}s")

    total_elapsed = time.time() - start_time
    generate_html_report(scan_results)

    return scan_results, total_elapsed


def quarantine_burned_images(scan_results: list):
    """
    Moves all images in the 'burned' bucket to library/_quarantine/,
    updates manifest.jsonl paths, and calls reindex().
    """
    os.makedirs(QUARANTINE_DIR, exist_ok=True)
    burned_records = [r for r in scan_results if r["bucket"] == "burned"]

    if not burned_records:
        print("No burned images found to quarantine.")
        return

    print(f"\nMoving {len(burned_records)} burned images to {QUARANTINE_DIR}...")
    moved_count = 0
    quarantined_paths_map = {}

    for r in burned_records:
        rel_p = r["path"].replace("\\", "/")
        fname = os.path.basename(rel_p)
        src_p = os.path.join(IMAGES_DIR, fname)
        dst_p = os.path.join(QUARANTINE_DIR, fname)

        if os.path.exists(src_p):
            shutil.move(src_p, dst_p)
            new_rel_p = f"library/_quarantine/{fname}"
            quarantined_paths_map[rel_p] = new_rel_p
            quarantined_paths_map[fname] = new_rel_p
            moved_count += 1

    print(f"Successfully quarantined {moved_count} burned files.")

    # Update manifest.jsonl if present
    if os.path.exists(MANIFEST_PATH) and quarantined_paths_map:
        new_lines = []
        updated_manifest_entries = 0
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    p = (entry.get("path") or entry.get("file_path") or "").replace("\\", "/")
                    fname = os.path.basename(p)
                    if p in quarantined_paths_map or fname in quarantined_paths_map:
                        entry["path"] = quarantined_paths_map.get(p) or quarantined_paths_map.get(fname)
                        updated_manifest_entries += 1
                    new_lines.append(json.dumps(entry, ensure_ascii=False))
                except Exception:
                    new_lines.append(line.strip())

        with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
            for nl in new_lines:
                f.write(nl + "\n")
        print(f"Updated {updated_manifest_entries} paths in {MANIFEST_PATH}")

    # Reindex library
    from pipeline.library import reindex
    print("Reindexing library after quarantine...")
    cnt, elapsed = reindex(force=True)
    print(f"Reindexed {cnt} active images in {elapsed:.2f}s.")


def main():
    parser = argparse.ArgumentParser(description="Smart Studio — Image Text Scan & Quarantine Tool")
    parser.add_argument("--quarantine", action="store_true", help="Move burned images to library/_quarantine/, update manifest, and reindex.")
    parser.add_argument("--force-rescan", action="store_true", help="Bypass scan cache and re-OCR all images.")
    args = parser.parse_args()

    results, total_elapsed = scan_images(force_rescan=args.force_rescan)

    clean_count = sum(1 for r in results if r["bucket"] == "clean")
    review_count = sum(1 for r in results if r["bucket"] == "review")
    burned_count = sum(1 for r in results if r["bucket"] == "burned")

    print("\n==================================================")
    print("      SMART STUDIO — IMAGE TEXT SCAN REPORT      ")
    print("==================================================")
    print(f"TOTAL IMAGES SCANNED : {len(results)}")
    print(f"CLEAN BUCKET        : {clean_count}")
    print(f"REVIEW BUCKET       : {review_count}")
    print(f"BURNED BUCKET       : {burned_count}")
    print(f"SCAN RUNTIME        : {total_elapsed:.2f}s")
    print(f"HTML REPORT         : {REPORT_HTML}")
    print("==================================================\n")

    # Print 10 worst offenders in burned bucket
    burned_sorted = sorted([r for r in results if r["bucket"] == "burned"],
                           key=lambda x: (x.get("matches_script_text", False), x.get("total_covered_area_pct", 0.0), len(x.get("detections", []))),
                           reverse=True)

    print("--- TOP 10 WORST OFFENDERS (BURNED BUCKET) ---")
    for idx, r in enumerate(burned_sorted[:10], 1):
        fname = os.path.basename(r["path"])
        det_texts = [f"'{d['text']}'" for d in r.get("detections", [])[:5]]
        text_str = ", ".join(det_texts) if det_texts else "None"
        cov_pct = r.get("total_covered_area_pct", 0.0)
        line = f"{idx:2d}. {fname:<25} (Area: {cov_pct:5.2f}%) -> Detected: {text_str}"
        try:
            print(line)
        except UnicodeEncodeError:
            print(line.encode("ascii", errors="backslashreplace").decode("ascii"))

    if args.quarantine:
        quarantine_burned_images(results)


if __name__ == "__main__":
    main()
