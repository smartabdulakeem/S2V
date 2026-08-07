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
WAR_IMAGE_PROMPTS_PATH = os.path.join(LIBRARY_DIR, "WAR_IMAGE_PROMPTS.md")

_MODEL = None
_PREPROCESS = None
_TOKENIZER = None

STYLE_BLOCK = (
    "Shot on 35mm film, cinematic documentary photography, natural directional light, "
    "shallow depth of field, muted earth palette of ochre sand, dust grey and deep indigo shadow, "
    "fine film grain, historically accurate 7th century Arabian Peninsula, early Islamic era."
)

NEGATIVE_BLOCK = (
    "No modern objects, no firearms, no curved scimitars, no Ottoman or Persian costume, "
    "no plate armour, no European castles, no text, no watermark, no signature, no logo, "
    "no lens flare, no plastic-looking skin."
)

DEFAULT_WORLD_ANCHOR = "7th century Arabian Peninsula, early Islamic era"

# ── 1. CLIP Model Singleton & Reindex ──────────────────────────────────────────

def _load_clip():
    global _MODEL, _PREPROCESS, _TOKENIZER
    if _MODEL is None:
        import open_clip
        model, _, preprocess = open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai", device="cpu")
        tokenizer = open_clip.get_tokenizer("ViT-B-32")
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


# ── 2. Manifest Usage & Rejection Memory ──────────────────────────────────────

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
    if (query_clean, path_clean) in existing:
        return

    record = {"query": query_clean, "image_path": path_clean, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")}
    os.makedirs(os.path.dirname(REJECTIONS_PATH), exist_ok=True)
    with open(REJECTIONS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── 3. Diversity Search ────────────────────────────────────────────────────────

def search(query: str, k: int = 5, exclude: set = None, min_score: float = 0.26):
    """
    Returns [(path, score)] ranked by score after applying penalties:
      - 1.0 score penalty for image in exclude set (already used in render)
      - 1.0 score penalty for (query, image) in rejections memory
      - 0.03 * lifetime_usage_count penalty from manifest
    """
    if exclude is None:
        exclude = set()

    clean_exclude = {p.replace("\\", "/") for p in exclude}
    embeddings, paths = load_index()
    if len(paths) == 0:
        return []

    q_emb = encode_text_query(query)
    raw_scores = np.dot(embeddings, q_emb)

    manifest_counts = get_manifest_usage_counts()
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

        # Lifetime manifest usage penalty
        lifetime_use = manifest_counts.get(norm_path, 0)
        penalized_score -= (0.03 * lifetime_use)

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
    script_context: str = ""
) -> str:
    """
    Composes a ready-to-use prompt for a library gap:
      shot query + world_anchor + character_bible entries matching + style block + negative block + framing bias
    """
    parts = []

    # Framing bias toward wide/silhouette/detail rather than mid-distance faces
    framing_bias = ""
    query_lower = shot_query.lower()
    if not any(f in query_lower for f in ["wide", "silhouette", "detail", "close", "aerial", "extreme wide"]):
        if any(term in query_lower for term in ["man", "woman", "soldier", "rider", "warrior", "leader", "elder", "people", "crowd", "figure"]):
            framing_bias = "wide establishing shot of "

    parts.append(f"{framing_bias}{shot_query}")

    anchor = world_anchor or DEFAULT_WORLD_ANCHOR
    parts.append(anchor)

    # Character bible matching
    if character_bible:
        for char_name, char_desc in character_bible.items():
            pattern = r'\b' + re.escape(char_name) + r'\b'
            if re.search(pattern, shot_query, re.IGNORECASE) or (script_context and re.search(pattern, script_context, re.IGNORECASE)):
                parts.append(f"featuring: {char_desc}")

    parts.append(STYLE_BLOCK)
    parts.append(f"Negative prompt: {NEGATIVE_BLOCK}")

    return ", ".join(parts)


# ── 5. Coverage & Plan Shots ───────────────────────────────────────────────────

def plan_shots(script_data: dict, min_score: float = 0.26):
    """
    Analyzes all shots in a script against the library index.
    Ensures diversity (NO image used twice in a single script).
    Reports 3 states per shot: matched, weak, gap.
    Ranks gaps by reuse value across the script.
    """
    project_info = script_data.get("project", {})
    title = project_info.get("title", "Untitled Project")
    world_anchor = project_info.get("world_anchor") or project_info.get("visual_style") or DEFAULT_WORLD_ANCHOR
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
                "min_score": shot.get("min_score", min_score),
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
            elif target_min - 0.05 <= best_score < target_min:
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
            script_context=s["narration"]
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

    # Find and rank gaps by reuse value
    gaps_ranked = []
    seen_gap_queries = set()
    for s_rep in shot_reports:
        if s_rep["state"] == "gap":
            q = s_rep["query"]
            if q not in seen_gap_queries:
                seen_gap_queries.add(q)
                related_segs = sorted(list(set(query_to_segments[q])))
                gaps_ranked.append({
                    "query": q,
                    "first_segment_id": s_rep["segment_id"],
                    "first_shot_id": s_rep["shot_id"],
                    "best_score": s_rep["best_score"],
                    "reuse_count": len(related_segs),
                    "related_segments": related_segs,
                    "composed_prompt": s_rep["composed_prompt"]
                })

    gaps_ranked.sort(key=lambda x: (x["reuse_count"], x["best_score"]), reverse=True)

    return {
        "title": title,
        "total_shots": len(all_shots),
        "matched": matched_count,
        "weak": weak_count,
        "gaps": gap_count,
        "shot_reports": shot_reports,
        "ranked_gaps": gaps_ranked,
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

    if report["ranked_gaps"]:
        for i, gap in enumerate(report["ranked_gaps"], 1):
            others = [str(sid) for sid in gap["related_segments"] if sid != gap["first_segment_id"]]
            also_str = f"   also needed by {', '.join(others)}" if others else ""
            print(f"GAP {i}  segment {gap['first_segment_id']} shot {gap['first_shot_id']}   best {gap['best_score']:.2f}{also_str}")
            print(f"  → {gap['composed_prompt']}\n")
    else:
        print("No gaps detected — full library coverage achieved!\n")


# ── 6. CLI Entry Point ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "reindex":
        count, elapsed = reindex(force=True)
        print(f"Reindexed {count} images in {elapsed:.2f}s -> {INDEX_PATH}")
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
        print("  python -m pipeline.library search \"<query>\" [k]")
        print("  python -m pipeline.library coverage <script.json>")
