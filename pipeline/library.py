"""
pipeline/library.py

CLIP retrieval, diversity search, rejection memory, gap detection, and prompt composition.
"""

import os
import sys
import json
import time
import argparse
import re
import numpy as np
from pathlib import Path
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIBRARY_DIR = os.path.join(ROOT, "library")
IMAGES_DIR = os.path.join(LIBRARY_DIR, "images")
INDEX_PATH = os.path.join(LIBRARY_DIR, "index.npz")
REJECTIONS_PATH = os.path.join(LIBRARY_DIR, "rejections.jsonl")
MANIFEST_PATH = os.path.join(LIBRARY_DIR, "manifest.jsonl")
CONFIG_PATH = os.path.join(ROOT, "config", "library_config.json")
SERIES_CONFIG_DIR = os.path.join(ROOT, "config", "series")
RENDER_USAGE_PATH = os.path.join(LIBRARY_DIR, "render_usage.json")
WAR_IMAGE_PROMPTS_PATH = os.path.join(LIBRARY_DIR, "WAR_IMAGE_PROMPTS.md")

_MODEL = None
_PREPROCESS = None
_TOKENIZER = None

FALLBACK_MIN_SCORE = 0.2796
FALLBACK_WEAK_BAND = 0.0045
RENDER_USAGE_PENALTY = 0.0008

import warnings


def get_calibration_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                return {
                    "min_score": float(cfg.get("min_score", FALLBACK_MIN_SCORE)),
                    "weak_band": float(cfg.get("weak_band", FALLBACK_WEAK_BAND))
                }
        except Exception:
            pass
    return {"min_score": FALLBACK_MIN_SCORE, "weak_band": FALLBACK_WEAK_BAND}


def get_calibrated_min_score() -> float:
    return get_calibration_config()["min_score"]


def get_calibrated_weak_band() -> float:
    return get_calibration_config()["weak_band"]


def save_calibration_config(min_score: float, weak_band: float):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    cfg["min_score"] = round(float(min_score), 4)
    cfg["weak_band"] = round(float(weak_band), 4)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def validate_series_pack(pack_data: dict) -> list[str]:
    """
    Validates a series pack dictionary according to SCHEMA.md v2 rules.
    Returns a list of path-naming error strings.
    """
    errors = []
    if not isinstance(pack_data, dict):
        return ["series_pack: expected dictionary object"]

    if not isinstance(pack_data.get("series_slug"), str) or not pack_data.get("series_slug", "").strip():
        errors.append("series_pack.series_slug: required non-empty string missing")

    if not isinstance(pack_data.get("display_name"), str) or not pack_data.get("display_name", "").strip():
        errors.append("series_pack.display_name: required non-empty string missing")

    if not isinstance(pack_data.get("world_anchor"), str):
        errors.append("series_pack.world_anchor: string required")

    if not isinstance(pack_data.get("style_block"), str):
        errors.append("series_pack.style_block: string required")

    if not isinstance(pack_data.get("negative_block"), str):
        errors.append("series_pack.negative_block: string required")

    voice = pack_data.get("voice")
    if not isinstance(voice, dict) or not isinstance(voice.get("id"), str) or not voice.get("id", "").strip():
        errors.append("series_pack.voice.id: required non-empty string missing")

    calib = pack_data.get("calibration")
    if not isinstance(calib, dict):
        errors.append("series_pack.calibration: expected dictionary object")
    else:
        real_q = calib.get("real_queries")
        if not isinstance(real_q, list) or len(real_q) < 10:
            errors.append("series_pack.calibration.real_queries: expected array of at least 10 query strings")
        fake_q = calib.get("fake_queries")
        if not isinstance(fake_q, list) or len(fake_q) < 10:
            errors.append("series_pack.calibration.fake_queries: expected array of at least 10 query strings")

    return errors


def save_calibration_config(min_score: float, weak_band: float):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    cfg["min_score"] = round(float(min_score), 4)
    cfg["weak_band"] = round(float(weak_band), 4)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def get_calibration_config(series_slug: str = None) -> dict:
    """
    Returns per-pack calibration configuration.
    If a pack has no calibration data or under 200 matching indexed images,
    reports 'not calibrated — generation-first' status.
    """
    embeddings, paths = load_index()
    n_images = len(paths)

    pack = get_series_config(series_slug=series_slug)
    calib = pack.get("calibration", {})
    min_score = calib.get("min_score")
    weak_band = calib.get("weak_band")

    if min_score is None or n_images < 200:
        return {
            "min_score": None,
            "weak_band": None,
            "status": "not calibrated — generation-first"
        }

    return {
        "min_score": min_score,
        "weak_band": weak_band,
        "status": "calibrated"
    }


def get_series_config(series_slug: str = None, project_title: str = None) -> dict:
    """
    Resolves per-series prompt configuration and pack defaults strictly from series_slug.
    Validates loaded pack using validate_series_pack().
    """
    available_packs = {}
    if os.path.exists(SERIES_CONFIG_DIR):
        for p in Path(SERIES_CONFIG_DIR).glob("*.json"):
            available_packs[p.stem] = p.name

    if series_slug:
        slug_clean = series_slug.strip().lower().replace("-", "_")
        slug_path = os.path.join(SERIES_CONFIG_DIR, f"{slug_clean}.json")
        if os.path.exists(slug_path):
            try:
                with open(slug_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                errors = validate_series_pack(data)
                if errors:
                    raise ValueError(f"Invalid series pack '{slug_clean}.json': {'; '.join(errors)}")
                return data
            except Exception as e:
                if isinstance(e, ValueError):
                    raise e
                raise ValueError(f"Failed to read series pack '{slug_clean}.json': {e}")
        
        sorted_packs = sorted(list(available_packs.keys()))
        raise ValueError(
            f"Unknown series_slug '{series_slug}'. Available series packs in config/series/: {', '.join(sorted_packs)}"
        )

    # Missing series_slug -> emit warning naming project title and fall back to default
    title_str = project_title or "Untitled Project"
    warning_msg = f"Project '{title_str}' has no 'series_slug' specified; falling back to 'default' series pack."
    warnings.warn(warning_msg, UserWarning)
    sys.stderr.write(f"WARNING: {warning_msg}\n")

    default_path = os.path.join(SERIES_CONFIG_DIR, "default.json")
    if os.path.exists(default_path):
        try:
            with open(default_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except Exception:
            pass

    return {
        "series_slug": "default",
        "display_name": "General Documentary",
        "voice": {"id": "en-US-GuyNeural", "steering": "", "tone": ""},
        "grade": "vignette",
        "caption_style": "bottom_center",
        "shot_rhythm_seconds": 4.0,
        "world_anchor": "",
        "style_block": "Shot on 35mm film, cinematic documentary photography, natural directional light, shallow depth of field, muted color palette, fine film grain.",
        "negative_block": "No text, no watermark, no signature, no logo, no lens flare, no plastic-looking skin, no blur, no distortion.",
        "calibration": {
            "min_score": None,
            "weak_band": None,
            "real_queries": [],
            "fake_queries": []
        }
    }


# ── 1. CLIP Model Singleton & Reindex ──────────────────────────────────────────

def _load_clip():
    global _MODEL, _PREPROCESS, _TOKENIZER
    if _MODEL is None:
        import open_clip
        model, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32-quickgelu", pretrained="openai", device="cpu")
        tokenizer = open_clip.get_tokenizer("ViT-B-32-quickgelu")
        model.eval()
        _MODEL = model
        _PREPROCESS = preprocess
        _TOKENIZER = tokenizer
    return _MODEL, _PREPROCESS, _TOKENIZER


def get_image_files():
    if not os.path.exists(IMAGES_DIR):
        return []
    exts = (".jpg", ".jpeg", ".png", ".webp")
    files = [os.path.join(IMAGES_DIR, f) for f in os.listdir(IMAGES_DIR) if f.lower().endswith(exts)]
    return sorted(files)


def is_index_current():
    if not os.path.exists(INDEX_PATH):
        return False
    index_mtime = os.path.getmtime(INDEX_PATH)
    images = get_image_files()
    if not images:
        return True
    
    # Check if image count matches or if any image is newer than index
    try:
        data = np.load(INDEX_PATH)
        paths = data["paths"]
        if len(paths) != len(images):
            return False
    except Exception:
        return False

    for img_path in images:
        if os.path.getmtime(img_path) > index_mtime:
            return False
    return True


def reindex(force=False):
    images = get_image_files()
    if not force and is_index_current():
        data = np.load(INDEX_PATH)
        emb = data.get("embeddings") if "embeddings" in data else data.get("emb")
        paths = data["paths"]
        return len(paths), 0.0

    t0 = time.time()
    if not images:
        # Save empty index
        np.savez(INDEX_PATH, embeddings=np.empty((0, 512), dtype=np.float32), paths=np.array([], dtype=str))
        return 0, time.time() - t0

    import torch
    model, preprocess, _ = _load_clip()

    batch_size = 64
    all_embeddings = []
    
    for i in range(0, len(images), batch_size):
        batch_paths = images[i:i + batch_size]
        batch_tensors = []
        for p in batch_paths:
            try:
                img = Image.open(p).convert("RGB")
                batch_tensors.append(preprocess(img))
            except Exception as e:
                # Fallback black image if corrupt
                batch_tensors.append(preprocess(Image.new("RGB", (224, 224), (0, 0, 0))))

        tensor_stack = torch.tensor(np.stack(batch_tensors))
        with torch.no_grad():
            features = model.encode_image(tensor_stack)
            features /= features.norm(dim=-1, keepdim=True)
            all_embeddings.append(features.cpu().numpy())

    embeddings_np = np.vstack(all_embeddings).astype(np.float32)
    # Store relative normalized forward slash paths for portability and exact matching
    rel_paths = np.array([os.path.relpath(p, ROOT).replace("\\", "/") for p in images])

    np.savez(INDEX_PATH, embeddings=embeddings_np, paths=rel_paths)
    elapsed = time.time() - t0
    return len(images), elapsed


def load_index():
    if not is_index_current():
        reindex()
    data = np.load(INDEX_PATH)
    embeddings = data.get("embeddings") if "embeddings" in data else data.get("emb")
    paths = [p.replace("\\", "/") for p in data["paths"]]
    return embeddings, paths


def encode_text_query(query: str):
    import torch
    model, _, tokenizer = _load_clip()
    text_tokens = tokenizer([query])
    with torch.no_grad():
        text_features = model.encode_text(text_tokens)
        text_features /= text_features.norm(dim=-1, keepdim=True)
    return text_features.cpu().numpy()[0]


# ── 2. Render Usage Counter & Rejection Memory ─────────────────────────────

def get_render_usage_counts() -> dict:
    """Returns per-image render usage counts from render_usage.json."""
    if not os.path.exists(RENDER_USAGE_PATH):
        return {}
    try:
        with open(RENDER_USAGE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def record_render_usage(image_path: str):
    """Increments render usage count for image_path when it is used in a completed render."""
    norm_path = image_path.strip().replace("\\", "/")
    counts = get_render_usage_counts()
    counts[norm_path] = counts.get(norm_path, 0) + 1
    os.makedirs(os.path.dirname(RENDER_USAGE_PATH), exist_ok=True)
    with open(RENDER_USAGE_PATH, "w", encoding="utf-8") as f:
        json.dump(counts, f, indent=2)


def get_manifest_usage_counts():
    counts = {}
    if not os.path.exists(MANIFEST_PATH):
        return counts
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                p = r.get("path", "").replace("\\", "/")
                if p:
                    counts[p] = counts.get(p, 0) + 1
            except Exception:
                pass
    return counts


def get_rejected_pairs():
    rejected = set()
    if not os.path.exists(REJECTIONS_PATH):
        return rejected
    with open(REJECTIONS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                q = r.get("query", "").strip().lower()
                p = r.get("image_path", "").strip().replace("\\", "/")
                if q and p:
                    rejected.add((q, p))
            except Exception:
                pass
    return rejected


def record_rejection(query: str, image_path: str):
    query_clean = query.strip().lower()
    path_clean = image_path.strip().replace("\\", "/")
    
    existing = get_rejected_pairs()
    record = {"query": query_clean, "image_path": path_clean, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")}
    os.makedirs(os.path.dirname(REJECTIONS_PATH), exist_ok=True)
    with open(REJECTIONS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── 3. Diversity Search ────────────────────────────────────────────────────────

def search(query: str, k: int = 5, exclude: set = None, min_score: float = None):
    """
    Returns [(path, score)] ranked by score after applying penalties:
      - 1.0 score penalty for image in exclude set (already used in render)
      - 1.0 score penalty for (query, image) in rejections memory
      - RENDER_USAGE_PENALTY (0.0008) * render_usage_count penalty
    """
    if min_score is None:
        min_score = get_calibrated_min_score()

    if exclude is None:
        exclude = set()

    clean_exclude = {p.replace("\\", "/") for p in exclude}
    embeddings, paths = load_index()
    if len(paths) == 0:
        return []

    q_emb = encode_text_query(query)
    raw_scores = np.dot(embeddings, q_emb)

    render_usage_counts = get_render_usage_counts()
    rejected_pairs = get_rejected_pairs()
    query_lower = query.strip().lower()

    adjusted_results = []
    for idx, (path, raw_score) in enumerate(zip(paths, raw_scores)):
        norm_path = path.replace("\\", "/")

        # Rejection memory: never return a rejected pairing
        if (query_lower, norm_path) in rejected_pairs:
            continue

        # Diversity: never return an image used in the current render
        if norm_path in clean_exclude:
            continue

        penalized_score = float(raw_score)

        # Real render usage penalty (small relative to weak_band=0.0045)
        uses = render_usage_counts.get(norm_path, 0)
        penalized_score -= (RENDER_USAGE_PENALTY * uses)

        adjusted_results.append((norm_path, penalized_score, float(raw_score)))

    # Sort descending by penalized score
    adjusted_results.sort(key=lambda x: x[1], reverse=True)

    # Filter/return top k
    top_k = []
    for norm_path, pen_score, r_score in adjusted_results[:k]:
        top_k.append((norm_path, pen_score))
    return top_k


# ── 4. Prompt Composition for Gaps ─────────────────────────────────────────────

def compose_gap_prompt(
    shot_query: str,
    world_anchor: str = None,
    character_bible: dict = None,
    script_context: str = "",
    series_slug: str = None,
    project_title: str = None
) -> str:
    """
    Composes a ready-to-use prompt for a library gap using per-series prompt configuration.
    Never includes project_title or raw narration text directly in the prompt.
    Script context (narration) is ONLY used for character-bible matching.
    """
    series_cfg = get_series_config(series_slug=series_slug, project_title=project_title)
    parts = []

    # Framing bias toward wide/silhouette/detail rather than mid-distance faces
    framing_bias = ""
    query_lower = shot_query.lower()
    if not any(f in query_lower for f in ["wide", "silhouette", "detail", "close", "aerial", "extreme wide"]):
        if any(term in query_lower for term in ["man", "woman", "soldier", "rider", "warrior", "leader", "elder", "people", "crowd", "figure"]):
            framing_bias = "wide establishing shot of "

    parts.append(f"{framing_bias}{shot_query}")

    anchor = world_anchor or series_cfg.get("world_anchor")
    if anchor:
        parts.append(anchor)

    # Character bible matching using script_context / shot_query
    if character_bible:
        for char_name, char_desc in character_bible.items():
            pattern = r'\b' + re.escape(char_name) + r'\b'
            if re.search(pattern, shot_query, re.IGNORECASE) or (script_context and re.search(pattern, script_context, re.IGNORECASE)):
                parts.append(f"featuring: {char_desc}")

    style_block = series_cfg.get("style_block")
    negative_block = series_cfg.get("negative_block")

    if style_block:
        parts.append(style_block)
    if negative_block:
        parts.append(f"Negative prompt: {negative_block}")

    return ", ".join(parts)


# ── 5. Coverage & Plan Shots ───────────────────────────────────────────────────

def plan_shots(script_data: dict, min_score: float = None, weak_band: float = None):
    """
    Analyzes all shots in a script against the library index.
    Ensures diversity (NO image used twice in a single script).
    Reports 3 states per shot: matched, weak, gap.
    Keeps GAPS and WEAK lists separated so counters and lists match strictly.
    """
    if min_score is None:
        min_score = get_calibrated_min_score()
    if weak_band is None:
        weak_band = get_calibrated_weak_band()

    project_info = script_data.get("project", {})
    title = project_info.get("title", "Untitled Project")
    series_slug = project_info.get("series_slug")
    world_anchor = project_info.get("world_anchor") or project_info.get("visual_style")
    character_bible = project_info.get("character_bible") or {}

    segments = script_data.get("segments", [])
    
    # Extract all shots
    all_shots = []
    for seg in segments:
        seg_id = seg.get("segment_id", 1)
        narration = seg.get("narration", "")

        shots = seg.get("shots")
        if not shots:
            keyword = seg.get("b_roll_keyword") or seg.get("query") or f"segment {seg_id} visual"
            shots = [{
                "shot_id": f"{seg_id}a",
                "query": keyword
            }]
        
        for shot in shots:
            all_shots.append({
                "segment_id": seg_id,
                "shot_id": shot.get("shot_id", f"{seg_id}a"),
                "query": shot.get("query") or seg.get("b_roll_keyword") or "visual landscape",
                "min_score": shot.get("min_score") or min_score,
                "narration": narration
            })

    script_used_images = set()

    matched_count = 0
    weak_count = 0
    gap_count = 0

    shot_reports = []
    query_to_segments = {}

    for s in all_shots:
        q = s["query"]
        target_min = s["min_score"]
        target_weak = target_min - weak_band
        
        if q not in query_to_segments:
            query_to_segments[q] = []
        query_to_segments[q].append(s["segment_id"])

        results = search(q, k=5, exclude=script_used_images, min_score=target_min)

        if not results:
            state = "gap"
            best_path, best_score = None, 0.0
        else:
            best_path, best_score = results[0]
            if best_score >= target_min:
                state = "matched"
                script_used_images.add(best_path)
            elif target_weak <= best_score < target_min:
                state = "weak"
                script_used_images.add(best_path)
            else:
                state = "gap"

        if state == "matched":
            matched_count += 1
        elif state == "weak":
            weak_count += 1
        else:
            gap_count += 1

        composed = compose_gap_prompt(
            shot_query=q,
            world_anchor=world_anchor,
            character_bible=character_bible,
            script_context=s["narration"],
            series_slug=series_slug,
            project_title=title
        )

        shot_reports.append({
            "segment_id": s["segment_id"],
            "shot_id": s["shot_id"],
            "query": q,
            "state": state,
            "best_score": best_score,
            "best_path": best_path,
            "alternatives": results[1:] if len(results) > 1 else [],
            "composed_prompt": composed
        })

    # Rank WEAK matches
    ranked_weak = []
    seen_weak_queries = set()
    for s_rep in shot_reports:
        if s_rep["state"] == "weak":
            q = s_rep["query"]
            if q not in seen_weak_queries:
                seen_weak_queries.add(q)
                ranked_weak.append({
                    "query": q,
                    "first_segment_id": s_rep["segment_id"],
                    "first_shot_id": s_rep["shot_id"],
                    "state": "weak",
                    "best_score": s_rep["best_score"],
                    "best_path": s_rep["best_path"],
                    "alternatives": s_rep["alternatives"]
                })

    # Rank GAPS strictly (state == 'gap' only!)
    ranked_gaps = []
    seen_gap_queries = set()
    for s_rep in shot_reports:
        if s_rep["state"] == "gap":
            q = s_rep["query"]
            if q not in seen_gap_queries:
                seen_gap_queries.add(q)
                related_segs = sorted(list(set(query_to_segments[q])))
                ranked_gaps.append({
                    "query": q,
                    "first_segment_id": s_rep["segment_id"],
                    "first_shot_id": s_rep["shot_id"],
                    "state": "gap",
                    "best_score": s_rep["best_score"],
                    "reuse_count": len(related_segs),
                    "related_segments": related_segs,
                    "composed_prompt": s_rep["composed_prompt"]
                })

    ranked_gaps.sort(key=lambda x: (x["reuse_count"], x["best_score"]), reverse=True)

    return {
        "title": title,
        "total_shots": len(all_shots),
        "matched": matched_count,
        "weak": weak_count,
        "gaps": gap_count,
        "shot_reports": shot_reports,
        "ranked_weak": ranked_weak,
        "ranked_gaps": ranked_gaps,
        "used_images": list(script_used_images)
    }


def print_coverage_report(script_path: str):
    if not os.path.exists(script_path):
        print(f"Error: Script file not found at '{script_path}'")
        return

    with open(script_path, "r", encoding="utf-8") as f:
        script_data = json.load(f)

    report = plan_shots(script_data)

    print(f"\n{report['title']}   ·  {report['total_shots']} shots")
    print(f"COVERED  {report['matched']}   WEAK  {report['weak']}   GAPS  {report['gaps']}\n")

    if report["ranked_weak"]:
        print(f"--- WEAK MATCHES ({len(report['ranked_weak'])}) ---")
        for i, w in enumerate(report["ranked_weak"], 1):
            alt_str = ""
            if w.get("alternatives"):
                alt_path, alt_score = w["alternatives"][0]
                alt_str = f"   (alt: {alt_path} {alt_score:.4f})"
            print(f"WEAK {i}  segment {w['first_segment_id']} shot {w['first_shot_id']}   best {w['best_score']:.4f} ({w['best_path']}){alt_str}")
        print()

    if report["ranked_gaps"]:
        print(f"--- GAPS TO FILL ({len(report['ranked_gaps'])}) ---")
        for i, gap in enumerate(report["ranked_gaps"], 1):
            others = [str(sid) for sid in gap["related_segments"] if sid != gap["first_segment_id"]]
            also_str = f"   also needed by {', '.join(others)}" if others else ""
            print(f"GAP {i}  segment {gap['first_segment_id']} shot {gap['first_shot_id']}   best {gap['best_score']:.4f}{also_str}")
            print(f"  -> {gap['composed_prompt']}\n")

    if not report["ranked_weak"] and not report["ranked_gaps"]:
        print("No gaps detected — full library coverage achieved!\n")


# ── 6. Calibration Command ─────────────────────────────────────────────────────

def calibrate(series_slug: str = "islamic_history"):
    """
    Runs per-pack real queries and fake queries against the real index.
    Prints both distributions, recommends min_score and weak_band.
    Saves min_score, weak_band, and calibrated_at back into the series pack JSON file.
    """
    pack = get_series_config(series_slug=series_slug)
    calib = pack.get("calibration", {})
    real_queries = calib.get("real_queries", [])
    fake_queries = calib.get("fake_queries", [])

    if not real_queries or not fake_queries:
        print(f"Error: Series pack '{series_slug}' does not contain valid real_queries/fake_queries in calibration block.")
        return 0.0, 0.0

    embeddings, paths = load_index()
    if len(paths) == 0:
        print("Error: Library index is empty. Please run reindex first.")
        return 0.0, 0.0

    real_scores = []
    print(f"\n--- Real Queries (Known Good for '{series_slug}') ---")
    for q in real_queries:
        q_emb = encode_text_query(q)
        scores = np.dot(embeddings, q_emb)
        best = float(np.max(scores))
        real_scores.append(best)
        print(f"  {best:.4f}  {q}")

    fake_scores = []
    print(f"\n--- Fake Queries (Known Impossible for '{series_slug}') ---")
    for q in fake_queries:
        q_emb = encode_text_query(q)
        scores = np.dot(embeddings, q_emb)
        best = float(np.max(scores))
        fake_scores.append(best)
        print(f"  {best:.4f}  {q}")

    real_min, real_max = min(real_scores), max(real_scores)
    real_mean, real_med = float(np.mean(real_scores)), float(np.median(real_scores))

    fake_min, fake_max = min(fake_scores), max(fake_scores)
    fake_mean, fake_med = float(np.mean(fake_scores)), float(np.median(fake_scores))

    print(f"\n=== DISTRIBUTION SUMMARY ('{series_slug}') ===")
    print(f"REAL QUERIES : min={real_min:.4f}, max={real_max:.4f}, mean={real_mean:.4f}, median={real_med:.4f}")
    print(f"FAKE QUERIES : min={fake_min:.4f}, max={fake_max:.4f}, mean={fake_mean:.4f}, median={fake_med:.4f}")

    if real_min > fake_max:
        gap_low = fake_max
        gap_high = real_min
        rec_min_score = (gap_low + gap_high) / 2.0
        rec_weak_band = round(gap_high - rec_min_score, 4)
        print(f"\nCLEAN GAP DETECTED: [{gap_low:.4f}, {gap_high:.4f}]")
        print(f"RECOMMENDED MIN_SCORE: {rec_min_score:.4f}, WEAK_BAND: {rec_weak_band:.4f}")
    else:
        rec_min_score = fake_max + 0.015
        rec_weak_band = 0.0050
        print(f"\nOVERLAP WARNING: Highest fake ({fake_max:.4f}) >= lowest real ({real_min:.4f}).")
        print(f"RECOMMENDED MIN_SCORE: {rec_min_score:.4f}, WEAK_BAND: {rec_weak_band:.4f}")

    # Write calibration parameters back to the series pack file directly
    pack_path = os.path.join(SERIES_CONFIG_DIR, f"{series_slug}.json")
    if os.path.exists(pack_path):
        with open(pack_path, "r", encoding="utf-8") as f:
            pack_data = json.load(f)
        if "calibration" not in pack_data or not isinstance(pack_data["calibration"], dict):
            pack_data["calibration"] = {}
        pack_data["calibration"]["min_score"] = round(float(rec_min_score), 4)
        pack_data["calibration"]["weak_band"] = round(float(rec_weak_band), 4)
        pack_data["calibration"]["calibrated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with open(pack_path, "w", encoding="utf-8") as f:
            json.dump(pack_data, f, indent=2)
        print(f"Saved min_score={rec_min_score:.4f}, weak_band={rec_weak_band:.4f} directly into {pack_path}\n")

    return round(float(rec_min_score), 4), round(float(rec_weak_band), 4)


# ── 7. CLI Entry Point ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "reindex":
        count, elapsed = reindex(force=True)
        print(f"Reindexed {count} images in {elapsed:.2f}s -> {INDEX_PATH}")
    elif len(sys.argv) > 1 and sys.argv[1] == "calibrate":
        target_slug = sys.argv[2] if len(sys.argv) > 2 else "islamic_history"
        calibrate(series_slug=target_slug)
    elif len(sys.argv) > 1 and sys.argv[1] == "search":
        if len(sys.argv) < 3:
            print("Usage: python -m pipeline.library search \"<query>\" [k]")
            sys.exit(1)
        query = sys.argv[2]
        k = int(sys.argv[3]) if len(sys.argv) > 3 else 5
        results = search(query, k=k)
        print(f"\nSearch results for '{query}':")
        for p, score in results:
            print(f"  {score:.4f}  {p}")
    elif len(sys.argv) > 1 and sys.argv[1] == "coverage":
        if len(sys.argv) < 3:
            print("Usage: python -m pipeline.library coverage <script_path>")
            sys.exit(1)
        script_path = sys.argv[2]
        print_coverage_report(script_path)
    else:
        print("Usage:")
        print("  python -m pipeline.library reindex")
        print("  python -m pipeline.library calibrate [series_slug]")
        print("  python -m pipeline.library search \"<query>\" [k]")
        print("  python -m pipeline.library coverage <script.json>")

