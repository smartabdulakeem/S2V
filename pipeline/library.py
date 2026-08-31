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

import datetime
import warnings


def get_calibrated_min_score(series_slug: str = None) -> float:
    try:
        cfg = get_calibration_config(series_slug=series_slug)
    except TypeError:
        cfg = get_calibration_config()
    if isinstance(cfg, dict) and cfg.get("min_score") is not None:
        return cfg["min_score"]
    return FALLBACK_MIN_SCORE


def get_calibrated_weak_band(series_slug: str = None) -> float:
    try:
        cfg = get_calibration_config(series_slug=series_slug)
    except TypeError:
        cfg = get_calibration_config()
    if isinstance(cfg, dict) and cfg.get("weak_band") is not None:
        return cfg["weak_band"]
    return FALLBACK_WEAK_BAND


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

    if "medium_block" in pack_data and not isinstance(pack_data["medium_block"], str):
        errors.append("series_pack.medium_block: string required")
    if "palette_block" in pack_data and not isinstance(pack_data["palette_block"], str):
        errors.append("series_pack.palette_block: string required")
    if "era_block" in pack_data and not isinstance(pack_data["era_block"], str):
        errors.append("series_pack.era_block: string required")
    if "brief_subject" in pack_data and pack_data["brief_subject"] is not None and not isinstance(pack_data["brief_subject"], str):
        errors.append("series_pack.brief_subject: string required")
    if "prompt_recipe" in pack_data and pack_data["prompt_recipe"] is not None and not isinstance(pack_data["prompt_recipe"], str):
        errors.append("series_pack.prompt_recipe: string required")

    presets = pack_data.get("style_presets")
    if not isinstance(presets, dict) or not presets:
        errors.append("series_pack.style_presets: expected a non-empty dictionary")
    else:
        from pipeline.composer import SINGLE_IMAGE_TREATMENTS
        for key, entry in presets.items():
            if isinstance(entry, str):
                if not entry.strip():
                    errors.append(f"series_pack.style_presets.{key}: empty prompt string")
                continue
            if not isinstance(entry, dict):
                errors.append(f"series_pack.style_presets.{key}: expected string or object")
                continue
            prompt = entry.get("prompt")
            if not isinstance(prompt, str) or not prompt.strip():
                errors.append(f"series_pack.style_presets.{key}.prompt: required non-empty string")
            label = entry.get("label")
            if label is not None and (not isinstance(label, str) or not label.strip()):
                errors.append(f"series_pack.style_presets.{key}.label: expected non-empty string")
            treatment = entry.get("treatment")
            if treatment is not None and treatment != "none" and treatment not in SINGLE_IMAGE_TREATMENTS:
                errors.append(
                    f"series_pack.style_presets.{key}.treatment: "
                    f"unknown treatment '{treatment}'"
                )

    voice = pack_data.get("voice")
    if not isinstance(voice, dict) or not isinstance(voice.get("id"), str) or not voice.get("id", "").strip():
        errors.append("series_pack.voice.id: required non-empty string missing")

    calib = pack_data.get("calibration")
    if not isinstance(calib, dict):
        errors.append("series_pack.calibration: expected dictionary object")
    else:
        for k in ("real_queries", "fake_queries"):
            v = calib.get(k)
            if not isinstance(v, list) or len(v) < 10:
                errors.append(f"series_pack.calibration.{k}: required list of >= 10 strings")
            else:
                for idx, item in enumerate(v):
                    if not isinstance(item, str) or not item.strip():
                        errors.append(f"series_pack.calibration.{k}[{idx}]: empty string")

    return errors


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


def _apply_series_overrides(data: dict) -> dict:
    """Merge per-niche user overrides from config/series_overrides/<slug>.json if present."""
    if not isinstance(data, dict):
        return data
    slug = data.get("series_slug")
    if not slug:
        return data
    override_dir = os.path.join(ROOT, "config", "series_overrides")
    override_path = os.path.join(override_dir, f"{slug}.json")
    if os.path.exists(override_path):
        try:
            with open(override_path, "r", encoding="utf-8") as of:
                overrides = json.load(of)
            if isinstance(overrides, dict):
                data = dict(data)
                data.update(overrides)
                if "style_presets" in overrides:
                    data["style_presets_is_override"] = True
        except Exception:
            pass
    return data


def get_series_override(series_slug: str) -> dict:
    """Return user overrides for a niche from config/series_overrides/<slug>.json."""
    if not series_slug:
        return {}
    slug = series_slug.strip().lower().replace("-", "_")
    override_path = os.path.join(ROOT, "config", "series_overrides", f"{slug}.json")
    if os.path.exists(override_path):
        try:
            with open(override_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def save_series_override(series_slug: str, overrides: dict) -> dict:
    """
    Save per-niche overrides to config/series_overrides/<slug>.json.
    Only keys that differ from the base pack in config/series/<slug>.json are saved.
    Never writes to config/series/*.json.
    """
    if not series_slug:
        return {"success": False, "error": "series_slug required"}
    slug = series_slug.strip().lower().replace("-", "_")
    base_path = os.path.join(SERIES_CONFIG_DIR, f"{slug}.json")
    override_dir = os.path.join(ROOT, "config", "series_overrides")
    os.makedirs(override_dir, exist_ok=True)
    override_path = os.path.join(override_dir, f"{slug}.json")

    allowed_keys = (
        "display_name", "medium_block", "palette_block", "era_block",
        "negative_block", "style_block", "brief_subject", "prompt_recipe",
        "world_anchor", "style_presets"
    )

    if os.path.exists(base_path):
        base_data = {}
        try:
            with open(base_path, "r", encoding="utf-8") as f:
                base_data = json.load(f)
        except Exception:
            pass

        # Keep only modified keys
        to_save = {}
        for k in allowed_keys:
            if k in overrides:
                val = overrides[k]
                if k == "style_presets":
                    if isinstance(val, dict):
                        to_save[k] = val
                elif val is not None and str(val).strip() != str(base_data.get(k, "")).strip():
                    to_save[k] = val

        if not to_save:
            # No differences, delete override file if exists
            if os.path.exists(override_path):
                try:
                    os.remove(override_path)
                except Exception:
                    pass
            return {"success": True, "overrides": {}, "is_overridden": False, "is_user_created": False}

        try:
            with open(override_path, "w", encoding="utf-8") as f:
                json.dump(to_save, f, indent=2, ensure_ascii=False)
            return {"success": True, "overrides": to_save, "is_overridden": True, "is_user_created": False}
        except Exception as e:
            return {"success": False, "error": str(e)}
    else:
        # User-created niche: full pack saved in override_path
        user_pack = {}
        if os.path.exists(override_path):
            try:
                with open(override_path, "r", encoding="utf-8") as f:
                    user_pack = json.load(f)
            except Exception:
                user_pack = {}
        if not user_pack:
            default_path = os.path.join(SERIES_CONFIG_DIR, "default.json")
            if os.path.exists(default_path):
                try:
                    with open(default_path, "r", encoding="utf-8") as f:
                        user_pack = json.load(f)
                except Exception:
                    user_pack = {}

        user_pack["series_slug"] = slug
        for k in allowed_keys:
            if k in overrides and overrides[k] is not None:
                user_pack[k] = overrides[k]

        try:
            with open(override_path, "w", encoding="utf-8") as f:
                json.dump(user_pack, f, indent=2, ensure_ascii=False)
            return {"success": True, "overrides": user_pack, "is_overridden": True, "is_user_created": True}
        except Exception as e:
            return {"success": False, "error": str(e)}


def reset_series_override(series_slug: str) -> dict:
    """Reset a niche to default by deleting its override file."""
    if not series_slug:
        return {"success": False, "error": "series_slug required"}
    slug = series_slug.strip().lower().replace("-", "_")
    override_path = os.path.join(ROOT, "config", "series_overrides", f"{slug}.json")
    if os.path.exists(override_path):
        try:
            os.remove(override_path)
        except Exception as e:
            return {"success": False, "error": str(e)}
    return {"success": True, "is_overridden": False}


def create_user_niche(series_slug: str, display_name: str, base_slug: str = "default") -> dict:
    """Create a new user-defined niche seeded from default.json into config/series_overrides/."""
    if not series_slug or not series_slug.strip():
        return {"success": False, "error": "series_slug is required"}
    slug = re.sub(r"[^\w\-]", "_", series_slug.strip().lower()).strip("_")
    if not slug:
        return {"success": False, "error": "Invalid series_slug"}

    # Check collision with shipped packs
    base_shipped = os.path.join(SERIES_CONFIG_DIR, f"{slug}.json")
    if os.path.exists(base_shipped):
        return {"success": False, "error": f"Niche '{slug}' already exists as a shipped pack"}

    override_dir = os.path.join(ROOT, "config", "series_overrides")
    os.makedirs(override_dir, exist_ok=True)
    override_path = os.path.join(override_dir, f"{slug}.json")
    if os.path.exists(override_path):
        return {"success": False, "error": f"Niche '{slug}' already exists"}

    base_template_path = os.path.join(SERIES_CONFIG_DIR, f"{base_slug}.json")
    if not os.path.exists(base_template_path):
        base_template_path = os.path.join(SERIES_CONFIG_DIR, "default.json")

    template_data = {}
    if os.path.exists(base_template_path):
        try:
            with open(base_template_path, "r", encoding="utf-8") as f:
                template_data = json.load(f)
        except Exception:
            template_data = {}

    template_data["series_slug"] = slug
    template_data["display_name"] = display_name.strip() if (display_name and display_name.strip()) else slug.replace("_", " ").title()
    template_data["prompt_recipe"] = ""
    template_data["style_presets"] = style_presets_for(template_data)

    try:
        with open(override_path, "w", encoding="utf-8") as f:
            json.dump(template_data, f, indent=2, ensure_ascii=False)
        return {"success": True, "series_slug": slug, "display_name": template_data["display_name"]}
    except Exception as e:
        return {"success": False, "error": str(e)}


def delete_user_niche(series_slug: str) -> dict:
    """Delete a user-created niche from config/series_overrides/."""
    if not series_slug:
        return {"success": False, "error": "series_slug is required"}
    slug = series_slug.strip().lower().replace("-", "_")
    base_path = os.path.join(SERIES_CONFIG_DIR, f"{slug}.json")
    if os.path.exists(base_path):
        return {"success": False, "error": "Shipped niches cannot be deleted, only reset to default."}

    override_path = os.path.join(ROOT, "config", "series_overrides", f"{slug}.json")
    if os.path.exists(override_path):
        try:
            os.remove(override_path)
            return {"success": True, "series_slug": slug}
        except Exception as e:
            return {"success": False, "error": str(e)}
    return {"success": False, "error": f"Niche '{slug}' not found."}


def get_series_config(series_slug: str = None, project_title: str = None) -> dict:
    """
    Resolves per-series prompt configuration and pack defaults strictly from series_slug.
    Validates loaded pack using validate_series_pack() and merges overrides if present.
    """
    # The same list the validator checks against, so a pack cannot be loadable
    # here and unknown there.
    from pipeline.validator import known_series_slugs
    available_packs = {slug: os.path.basename(path)
                       for slug, path in known_series_slugs().items()}
    override_dir = os.path.join(ROOT, "config", "series_overrides")

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
                return _apply_series_overrides(data)
            except Exception as e:
                if isinstance(e, ValueError):
                    raise e
                raise ValueError(f"Failed to read series pack '{slug_clean}.json': {e}")

        # Check user-created niche in series_overrides
        user_override_path = os.path.join(override_dir, f"{slug_clean}.json")
        if os.path.exists(user_override_path):
            try:
                with open(user_override_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                errors = validate_series_pack(data)
                if errors:
                    raise ValueError(f"Invalid user series pack '{slug_clean}.json': {'; '.join(errors)}")
                if "style_presets" in data:
                    data["style_presets_is_override"] = True
                return data
            except Exception as e:
                if isinstance(e, ValueError):
                    raise e
                raise ValueError(f"Failed to read user series pack '{slug_clean}.json': {e}")

        sorted_packs = sorted(list(available_packs.keys()))
        raise ValueError(
            f"Unknown series_slug '{series_slug}'. Available series packs: {', '.join(sorted_packs)}"
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
            return _apply_series_overrides(data)
        except Exception:
            pass

    return _apply_series_overrides({
        "series_slug": "default",
        "display_name": "General Documentary",
        "voice": {"id": "en-US-GuyNeural", "steering": "", "tone": ""},
        "grade": "none",
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
    })


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


#: Indexes for folders outside the library live here, one file per folder.
FOLDER_INDEX_DIR = os.path.join(ROOT, "cache", "folder_index")


def _folder_index_path(folder_abs: str) -> str:
    import hashlib
    key = os.path.abspath(folder_abs).lower().encode("utf-8")
    return os.path.join(FOLDER_INDEX_DIR, hashlib.sha1(key).hexdigest()[:12] + ".npz")


def folder_image_files(folder_abs: str) -> list:
    """Images directly inside a working folder, sorted."""
    if not folder_abs or not os.path.isdir(folder_abs):
        return []
    exts = (".jpg", ".jpeg", ".png", ".webp")
    return sorted(
        os.path.join(folder_abs, n) for n in os.listdir(folder_abs)
        if n.lower().endswith(exts)
    )


def index_folder(folder_abs: str, on_progress=None):
    """
    Index any folder on this machine so a project can work from it directly.

    A working folder is a handful of pictures chosen for one video, kept wherever
    the user keeps them — a desktop folder, a Drive folder. Paths are stored
    absolute, because this folder is not inside the library and may never be.
    Embeddings are reused exactly as the main index does, so re-running after
    adding one picture costs one picture.

    Returns (image_count, elapsed_seconds).
    """
    t0 = time.time()
    images = folder_image_files(folder_abs)
    index_path = _folder_index_path(folder_abs)
    os.makedirs(FOLDER_INDEX_DIR, exist_ok=True)

    if not images:
        np.savez(index_path, embeddings=np.empty((0, 512), dtype=np.float32),
                 paths=np.array([], dtype=str))
        return 0, time.time() - t0

    existing, index_mtime = {}, 0.0
    if os.path.exists(index_path):
        index_mtime = os.path.getmtime(index_path)
        try:
            data = np.load(index_path)
            emb = data.get("embeddings") if "embeddings" in data else data.get("emb")
            old = [str(p).replace("\\", "/") for p in data["paths"]]
            if emb is not None and len(old) == len(emb):
                existing = {p: emb[i] for i, p in enumerate(old)}
        except Exception:
            existing = {}

    keys = [to_portable_path(p) for p in images]
    to_embed = [
        (i, p) for i, (p, key) in enumerate(zip(images, keys))
        if key not in existing or os.path.getmtime(p) > index_mtime
    ]
    if on_progress:
        on_progress(f"Indexing {len(to_embed)} of {len(images)} image(s) in this folder")

    dim = len(next(iter(existing.values()))) if existing else 512
    out = np.zeros((len(images), dim), dtype=np.float32)
    for i, key in enumerate(keys):
        if key in existing:
            out[i] = existing[key]

    if to_embed:
        import torch
        model, preprocess, _ = _load_clip()
        for start in range(0, len(to_embed), 64):
            batch = to_embed[start:start + 64]
            tensors = []
            for _, p in batch:
                try:
                    tensors.append(preprocess(Image.open(p).convert("RGB")))
                except Exception:
                    tensors.append(preprocess(Image.new("RGB", (224, 224), (0, 0, 0))))
            with torch.no_grad():
                feats = model.encode_image(torch.tensor(np.stack(tensors)))
                feats /= feats.norm(dim=-1, keepdim=True)
                feats = feats.cpu().numpy().astype(np.float32)
            for (idx, _), vec in zip(batch, feats):
                out[idx] = vec

    np.savez(index_path, embeddings=out, paths=np.array(keys))
    return len(images), time.time() - t0


def load_folder_index(folder_abs: str):
    """(embeddings, absolute paths) for a working folder, indexing it if needed."""
    index_path = _folder_index_path(folder_abs)
    images = folder_image_files(folder_abs)
    stale = not os.path.exists(index_path)
    if not stale:
        try:
            data = np.load(index_path)
            stale = len(data["paths"]) != len(images) or any(
                os.path.getmtime(p) > os.path.getmtime(index_path) for p in images
            )
        except Exception:
            stale = True
    if stale:
        index_folder(folder_abs)
    data = np.load(_folder_index_path(folder_abs))
    emb = data.get("embeddings") if "embeddings" in data else data.get("emb")
    return emb, [str(p).replace("\\", "/") for p in data["paths"]]


def _setting(name: str, default=None):
    """Read one value from config/settings.json, falling back to a default."""
    try:
        with open(os.path.join(ROOT, "config", "settings.json"), "r", encoding="utf-8") as f:
            return json.load(f).get(name, default)
    except Exception:
        return default


def get_image_files():
    """
    Every indexable image, including subfolders.

    Subfolders are how a project keeps its own small set of images: pointing a
    video at library/images/motivation means retrieval only ever sees those,
    which is far faster to curate than steering a search across 1,200 pictures.
    Folders beginning with "_" are workspaces (_inbox, _retired) and stay out.
    """
    if not os.path.exists(IMAGES_DIR):
        return []
    exts = (".jpg", ".jpeg", ".png", ".webp")
    files = []
    for root, dirs, names in os.walk(IMAGES_DIR):
        dirs[:] = [d for d in dirs if not d.startswith("_")]
        files.extend(
            os.path.join(root, n) for n in names if n.lower().endswith(exts)
        )
    return sorted(files)


def list_image_folders() -> list:
    """Subfolders of library/images that hold images, with their counts."""
    folders = []
    if not os.path.exists(IMAGES_DIR):
        return folders
    exts = (".jpg", ".jpeg", ".png", ".webp")
    for entry in sorted(os.listdir(IMAGES_DIR)):
        full = os.path.join(IMAGES_DIR, entry)
        if not os.path.isdir(full) or entry.startswith("_"):
            continue
        count = sum(
            1 for root, dirs, names in os.walk(full)
            for n in names if n.lower().endswith(exts)
        )
        if count:
            folders.append({"name": entry, "count": count})
    return folders


def to_portable_path(path: str) -> str:
    """
    Store a path relative to the project when it lives inside it.

    A working folder is often a folder of the project itself, and a script that
    names its images absolutely stops being portable and trips the validator's
    "stay inside the project" rule. Only genuinely external folders — a desktop
    folder, a Drive folder — keep an absolute path.
    """
    if not path:
        return ""
    absolute = os.path.abspath(str(path))
    try:
        rel = os.path.relpath(absolute, ROOT)
    except ValueError:          # different drive on Windows
        return absolute.replace("\\", "/")
    if not rel.startswith(".."):
        return rel.replace("\\", "/")
    return absolute.replace("\\", "/")


def _path_in_scope(path: str, folder: str) -> bool:
    """
    Is this image part of the source the project is currently drawing on?

    With no folder set, the whole library counts. With a working folder, only
    images inside it do — anything else is left over from a previous choice and
    must be re-planned rather than silently kept.
    """
    if not folder:
        return True
    if not path:
        return False
    # Compare as absolute paths, because a stored path may be project-relative
    # while the folder is given absolutely, or the other way round.
    resolved = os.path.abspath(path if os.path.isabs(path) else os.path.join(ROOT, path))
    base = os.path.abspath(folder if os.path.isabs(str(folder))
                           else os.path.join(IMAGES_DIR, str(folder)))
    return (resolved.replace("\\", "/").lower()
            .startswith(base.replace("\\", "/").lower().rstrip("/") + "/"))


def clear_out_of_scope_choices(script_data: dict, folder: str) -> dict:
    """
    Drop image choices that no longer belong to the chosen source.

    Choosing a working folder means "use these pictures". Any pin or remembered
    match pointing outside it is left over from a previous decision, and keeping
    it makes the new folder look like it did nothing. Reported rather than done
    quietly, because some of those pins were deliberate.

    Returns {"pins": n, "resolved": n}.
    """
    cleared = {"pins": 0, "resolved": 0}
    for seg in (script_data or {}).get("segments", []):
        for shot in seg.get("shots") or []:
            pin = shot.get("pin")
            if pin and not _path_in_scope(pin, folder):
                shot.pop("pin", None)
                shot["source"] = "library"
                cleared["pins"] += 1
            resolved = shot.get("resolved")
            if resolved and not _path_in_scope(resolved, folder):
                shot.pop("resolved", None)
                shot.pop("resolved_score", None)
                cleared["resolved"] += 1
    return cleared


def _folder_prefix(folder: str) -> str:
    """Repo-relative path prefix for a project folder, or '' for the whole library."""
    folder = (folder or "").strip().strip("/\\")
    if not folder:
        return ""
    return f"{os.path.relpath(IMAGES_DIR, ROOT)}/{folder}/".replace("\\", "/")


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


def _load_existing_embeddings() -> dict:
    """Embeddings already computed, keyed by repo-relative path."""
    if not os.path.exists(INDEX_PATH):
        return {}
    try:
        data = np.load(INDEX_PATH)
        emb = data.get("embeddings") if "embeddings" in data else data.get("emb")
        paths = [str(p).replace("\\", "/") for p in data["paths"]]
        if emb is None or len(paths) != len(emb):
            return {}
        return {p: emb[i] for i, p in enumerate(paths)}
    except Exception:
        return {}


def reindex(force=False, on_progress=None):
    """
    Bring the CLIP index up to date, embedding only what actually changed.

    This used to re-embed the entire library on any change — adding one image
    meant 182 seconds of CLIP over 1,176 files, and the storyboard blocked on it
    with nothing on screen but a spinner. Growing a library one image at a time
    was the intended workflow and the most expensive thing you could do.

    An image is re-embedded when it is new, or when its file is newer than the
    index. Everything else keeps the vector it already had.

    Returns (image_count, elapsed_seconds).
    """
    images = get_image_files()
    if not force and is_index_current():
        data = np.load(INDEX_PATH)
        paths = data["paths"]
        return len(paths), 0.0

    t0 = time.time()
    if not images:
        np.savez(INDEX_PATH, embeddings=np.empty((0, 512), dtype=np.float32), paths=np.array([], dtype=str))
        return 0, time.time() - t0

    index_mtime = os.path.getmtime(INDEX_PATH) if os.path.exists(INDEX_PATH) else 0.0
    existing = {} if force else _load_existing_embeddings()

    rel_paths = [os.path.relpath(p, ROOT).replace("\\", "/") for p in images]
    to_embed = [
        (i, p) for i, (p, rel) in enumerate(zip(images, rel_paths))
        if rel not in existing or os.path.getmtime(p) > index_mtime
    ]

    if on_progress:
        on_progress(f"Indexing {len(to_embed)} new or changed image(s); "
                    f"reusing {len(images) - len(to_embed)}")

    dim = len(next(iter(existing.values()))) if existing else 512
    embeddings_np = np.zeros((len(images), dim), dtype=np.float32)
    for i, rel in enumerate(rel_paths):
        if rel in existing:
            embeddings_np[i] = existing[rel]

    if to_embed:
        import torch
        model, preprocess, _ = _load_clip()
        batch_size = 64
        for start in range(0, len(to_embed), batch_size):
            batch = to_embed[start:start + batch_size]
            tensors = []
            for _, p in batch:
                try:
                    tensors.append(preprocess(Image.open(p).convert("RGB")))
                except Exception:
                    tensors.append(preprocess(Image.new("RGB", (224, 224), (0, 0, 0))))
            with torch.no_grad():
                features = model.encode_image(torch.tensor(np.stack(tensors)))
                features /= features.norm(dim=-1, keepdim=True)
                features = features.cpu().numpy().astype(np.float32)
            for (idx, _), vec in zip(batch, features):
                embeddings_np[idx] = vec
            if on_progress:
                on_progress(f"Indexed {min(start + batch_size, len(to_embed))}/{len(to_embed)}")

    # Description vectors are stored with the index so retrieval never has to
    # embed them at query time.
    desc_emb = build_description_embeddings(rel_paths, on_progress)

    np.savez(INDEX_PATH, embeddings=embeddings_np, paths=np.array(rel_paths),
             desc_embeddings=desc_emb)
    _DESC_INDEX["paths"] = None
    _DESC_INDEX["embeddings"] = None
    return len(images), time.time() - t0


def load_index():
    if not is_index_current():
        reindex()
    data = np.load(INDEX_PATH)
    embeddings = data.get("embeddings") if "embeddings" in data else data.get("emb")
    paths = [p.replace("\\", "/") for p in data["paths"]]
    return embeddings, paths


#: Encoded queries, kept for the life of the process.
_QUERY_CACHE = {}
_QUERY_CACHE_LIMIT = 4000


def encode_text_query(query: str):
    """
    Embed a piece of text, remembering the result.

    Planning a board encodes each shot's query at least twice — once to score the
    pictures and once to score their descriptions — and every re-plan encodes the
    same queries again. At ~70ms each on this CPU that was most of the wait.
    """
    key = query or ""
    cached = _QUERY_CACHE.get(key)
    if cached is not None:
        return cached

    import torch
    model, _, tokenizer = _load_clip()
    text_tokens = tokenizer([key])
    with torch.no_grad():
        text_features = model.encode_text(text_tokens)
        text_features /= text_features.norm(dim=-1, keepdim=True)
    vec = text_features.cpu().numpy()[0]

    if len(_QUERY_CACHE) >= _QUERY_CACHE_LIMIT:
        _QUERY_CACHE.clear()
    _QUERY_CACHE[key] = vec
    return vec


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


#: A description has to be close to a paraphrase of the shot query before it can
#: rescue an image, because CLIP text-to-text similarity has a high floor: any two
#: short English phrases score 0.6-0.75 whatever they say. Measured on this
#: library of 1,178 images:
#:
#:   threshold  "Prophet Abu Bakr"  "quantum computing data centre"  "sushi kitchen"
#:   0.62             311 images            315 images                  273 images
#:   0.85               (top 0.954)           (top 0.797)                 (top 0.726)
#:
#: At 0.62 a third of the library "matched" topics it has nothing to do with. Only
#: a near-paraphrase carries real information, so the bar sits above every score
#: an unrelated query could reach.
DESCRIPTION_MIN_SCORE = 0.85

_DESC_CACHE = {}
#: Description vectors for the currently loaded index, keyed by its path list.
_DESC_INDEX = {"paths": None, "embeddings": None}


def describe_image(rel_path: str, manifest_prompts: dict = None) -> str:
    """
    The words that belong to an image: its recorded prompt, else its filename.

    Images generated from a composed prompt are named after that prompt by most
    tools ("Madinah_outside_borders_7th_century_20260811.jpeg"), which is a real
    description sitting unused. Retrieval compared the shot query only against the
    picture, so an image made *for* a shot could still be ranked 833rd for it.
    """
    if manifest_prompts:
        prompt = manifest_prompts.get(rel_path.replace("\\", "/"))
        if prompt and prompt.strip():
            return " ".join(prompt.split())[:300]

    stem = os.path.splitext(os.path.basename(rel_path))[0]
    stem = re.sub(r"\(\d+\)$", "", stem).strip()
    stem = re.sub(r"[_\-]?\d{8,}.*$", "", stem)        # trailing timestamps
    stem = re.sub(r"[_\-]+", " ", stem).strip()
    # A bare content hash carries no meaning; better to admit that than invent one.
    if not stem or re.fullmatch(r"[0-9a-f]{6,}", stem.replace(" ", "")):
        return ""
    return stem


def load_manifest_prompts() -> dict:
    """Recorded prompt per image path, from the library manifest."""
    prompts = {}
    if not os.path.exists(MANIFEST_PATH):
        return prompts
    try:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                path = (rec.get("path") or "").replace("\\", "/")
                prompt = rec.get("prompt") or rec.get("query") or ""
                if path and prompt:
                    prompts[path] = prompt
    except Exception:
        pass
    return prompts


def build_description_embeddings(paths: list, on_progress=None) -> np.ndarray:
    """Embed each image's description once, aligned with `paths`."""
    manifest_prompts = load_manifest_prompts()
    dim = 512
    out = np.zeros((len(paths), dim), dtype=np.float32)
    cache = {}
    total = 0
    for i, path in enumerate(paths):
        desc = describe_image(path, manifest_prompts)
        if not desc:
            continue
        vec = cache.get(desc)
        if vec is None:
            vec = encode_text_query(desc)
            cache[desc] = vec
            total += 1
        out[i] = vec
    if on_progress and total:
        on_progress(f"Embedded {total} image description(s)")
    return out


def description_scores(query: str, paths: list) -> np.ndarray:
    """
    Similarity between the shot query and each image's own description.

    These vectors live in the index, computed once when an image is indexed.
    Computing them on demand meant 73 seconds of CLIP the first time a board was
    planned, and it made every Replace click pay for a full re-plan — the single
    biggest reason the app felt slow in manual use.
    """
    cached = _DESC_INDEX.get("paths")
    if cached is not None and cached == list(paths):
        desc_emb = _DESC_INDEX["embeddings"]
    else:
        desc_emb = _load_description_embeddings(paths)
        _DESC_INDEX["paths"] = list(paths)
        _DESC_INDEX["embeddings"] = desc_emb

    if desc_emb is None or len(desc_emb) != len(paths):
        return np.zeros(len(paths), dtype=np.float32)
    return np.dot(desc_emb, encode_text_query(query)).astype(np.float32)


def _load_description_embeddings(paths: list):
    """Description vectors from the index, or built now if the index predates them."""
    try:
        data = np.load(INDEX_PATH)
        if "desc_embeddings" in data:
            stored = data["desc_embeddings"]
            if len(stored) == len(paths):
                return stored
    except Exception:
        pass
    return build_description_embeddings(paths)


#: Openers the prompt composer adds. They describe framing, not subject, and every
#: prompt starts with one — so they must not be treated as the prompt's identity.
_PROMPT_OPENERS = (
    "wide establishing shot of", "low angle shot of", "overhead shot of",
    "close detail of", "over-the-shoulder view of", "wide shot of",
    "establishing shot of", "silhouette against", "close up of", "shot of",
)

_PROMPT_STOPWORDS = {
    "the", "a", "an", "of", "and", "in", "on", "at", "to", "for", "with", "his",
    "her", "their", "its", "was", "were", "is", "are", "that", "this", "from",
}


def prompt_head(prompt: str, words: int = 6) -> list:
    """
    The first few meaningful words of a prompt — what a filename keeps.

    Image tools name their output after the opening of the prompt, usually three
    to five words. Those words are the strongest link between a picture and the
    shot it was made for, and they are exact: no model, no threshold.
    """
    if not prompt:
        return []
    text = " ".join(str(prompt).split())
    lowered = text.lower()
    for opener in _PROMPT_OPENERS:
        if lowered.startswith(opener):
            text = text[len(opener):]
            break
    # The subject ends at the first comma; everything after is scene and style.
    subject = text.split(",")[0]
    tokens = [t for t in re.findall(r"[a-z0-9']+", subject.lower())
              if t not in _PROMPT_STOPWORDS and len(t) > 1]
    return tokens[:words]


def filename_subject_words(filename: str) -> list:
    """
    The subject words left in a filename after the number and framing opener.

    Often there are none. Tools truncate to roughly twenty characters and every
    prompt starts with a framing phrase, so "12_wide_establishing_sh" carries no
    subject at all — that was 19 of 47 files in a real folder. Returning an empty
    list is the honest answer, and the caller must not treat it as a mismatch.
    """
    stem = os.path.splitext(os.path.basename(str(filename)))[0]
    stem = re.sub(r"^\d{1,4}[ _\-.]+", "", stem)
    lowered = re.sub(r"[_\-]+", " ", stem).strip().lower()
    for opener in _PROMPT_OPENERS:
        for cut in range(len(opener), 3, -1):
            if lowered.startswith(opener[:cut]):
                lowered = lowered[cut:]
                break
        else:
            continue
        break
    words = [w for w in re.findall(r"[a-z0-9']+", lowered)
             if w not in _PROMPT_STOPWORDS and len(w) > 2]
    return words


def _words_agree(name_words, prompt_words) -> bool:
    """
    Whether a filename's surviving words back up a prompt.

    Exact equality is the wrong test, because the truncation that makes this
    check necessary is the same truncation that breaks it: a tool cutting the
    name at twenty characters turns "illustration" into "illustrati", which
    matches no prompt word at all. Every image in a real sheet folder was
    rejected on that alone.

    So a filename word counts when it is the start of a prompt word, or the
    prompt word is the start of it. Four characters minimum - shorter stems
    agree by accident.
    """
    for nw in name_words:
        for pw in prompt_words:
            if nw == pw:
                return True
            shorter, longer = (nw, pw) if len(nw) <= len(pw) else (pw, nw)
            if len(shorter) >= 4 and longer.startswith(shorter):
                return True
    return False


def match_shots_by_number(paths: list, shot_count: int, shot_prompts: dict = None) -> dict:
    """
    Images named 1_, 2_, 3_… belong to shots 1, 2, 3.

    Generating one image per prompt produces a numbered set, and that number is
    the user saying exactly which shot the picture is for. Nothing inferred from
    pixels or filenames can beat it.

    It also rescues the case name matching cannot touch at all: image tools
    truncate filenames to about twenty characters, so a prompt beginning "wide
    establishing shot of…" becomes "12_wide_establishing_sh" — nineteen of
    forty-seven files in a real folder carried no subject words whatsoever.

    Deliberately cautious, because a stray digit must not hijack a library:
      - the number must be followed by a separator, so 2ab05c49.jpg is not "2"
      - it must fall within the number of shots
      - most of the folder has to be numbered, or this is coincidence

    Returns {shot_index: path}, zero-based.
    """
    if not paths or shot_count <= 0:
        return {}

    numbered = {}
    for path in paths:
        name = os.path.basename(str(path))
        # Either a bare number ("12_…") or one carrying a project tag
        # ("thebat12_…"), which is what Copy all prompts now produces.
        m = re.match(r"^[a-z]{0,8}(\d{1,4})[ _\-.]", name, re.IGNORECASE)
        if not m:
            continue
        n = int(m.group(1))
        if 1 <= n <= shot_count and n not in numbered:
            numbered[n] = str(path).replace("\\", "/")

    if len(numbered) < max(3, int(0.5 * len(paths))):
        return {}

    out = {}
    for n, path in numbered.items():
        idx = n - 1

        # Cross-check the number against the words, when the filename kept any.
        # Numbers repeat across videos — every set starts at 1 — so once images
        # from several scripts share a folder the number alone can pair a shot
        # with a picture from a different film. Words settle it. When the
        # filename was truncated past its subject there is nothing to check
        # against, and the number is the only evidence there is.
        words = filename_subject_words(path)
        if words and shot_prompts and idx in shot_prompts:
            prompt_words = set(prompt_head(shot_prompts[idx], words=10))
            if prompt_words and not _words_agree(words, prompt_words):
                continue

        out[idx] = path
    return out


def parse_external_prompts(pasted_text: str) -> list:
    """
    Split pasted text on blank lines.
    Recipe (§31-33) emits each prompt as its own block without numbering or labels.
    """
    if not pasted_text or not str(pasted_text).strip():
        return []
    blocks = re.split(r"\n\s*\n", str(pasted_text).strip())
    return [b.strip() for b in blocks if b.strip()]


def picture_owning_shots(script_data: dict) -> list:
    """
    Every shot that owns a distinct picture, in film order, as (segment, shot).

    The single list that pasted prompts, numbered folder images and
    `image_prompts.txt` all count from. When the image budget is reduced,
    `plan_image_budget` merges segments into runs and marks the shots that do
    not get their own picture with `share_with`. Counting every shot instead
    bound prompt 1..12 to the first twelve *shots* — of which ten were sharing —
    so ten real pictures received no prompt and ten prompts were discarded in
    silence. Slot *n* means the *n*th picture the film actually makes, nothing
    else, and every caller has to agree on that or the mismatch simply moves.
    """
    owning = []
    for seg in (script_data.get("segments") or []):
        for shot in (seg.get("shots") or []):
            if not shot.get("share_with"):
                owning.append((seg, shot))
    return owning


def match_folder_images_by_slot(image_paths: list, slot_count: int) -> tuple:
    """
    Match images from a working folder directly to 1-based shot slots (1..slot_count).
    - An image whose filename starts with a number (e.g. 3_whatever.jpg, 3-whatever.jpg, 3.jpg)
      belongs to slot 3 (0-based index 2).
    - If NO images have leading numbers: fall back to sorted filename order.
    - Never falls back to similarity scoring.
    Returns (dict {slot_index: image_path}, is_fallback_to_sorted).
    """
    if not image_paths or slot_count <= 0:
        return {}, False

    clean_paths = sorted([str(p).replace("\\", "/") for p in image_paths])

    # First pass: try leading number matching
    numbered = {}
    for p in clean_paths:
        name = os.path.basename(p)
        # Match leading number: e.g. "3_...", "3-...", "3....", "3.jpg", "03_..."
        # Or optional project tag prefix e.g. "proj3_..."
        m = re.match(r"^(?:[a-zA-Z]{0,10})?(\d+)[_\-\. ]", name)
        if not m:
            m = re.match(r"^(?:[a-zA-Z]{0,10})?(\d+)\.[a-zA-Z0-9]+$", name)
        if m:
            num = int(m.group(1))
            if 1 <= num <= slot_count:
                idx = num - 1
                if idx not in numbered:
                    numbered[idx] = p

    if numbered:
        return numbered, False

    # Fallback: sorted filename order
    sorted_matched = {}
    for idx, p in enumerate(clean_paths):
        if idx < slot_count:
            sorted_matched[idx] = p
    return sorted_matched, True


def apply_external_prompts(script_data: dict, pasted_text: str, folder: str = None) -> dict:
    """
    Bind pasted external prompts to storyboard shots in order, match images from folder by number,
    and return mapping table and status summary.
    """
    prompts = parse_external_prompts(pasted_text)
    if not prompts:
        return {"success": False, "error": "No prompts found in pasted text."}

    # Only shots that own a picture. A shot marked `share_with` is drawn from
    # another shot's image and can never carry a prompt of its own.
    owning = picture_owning_shots(script_data)
    picture_shots = [shot for _, shot in owning]

    total_shots = sum(len(seg.get("shots") or []) for seg in (script_data.get("segments") or []))
    if not picture_shots:
        return {"success": False, "error": "No shots found in storyboard."}

    total_prompts = len(prompts)
    total_pictures = len(picture_shots)
    count_to_bind = min(total_prompts, total_pictures)

    # Assign prompts to the shots that actually make a picture
    for i in range(count_to_bind):
        picture_shots[i]["prompt_override"] = prompts[i]
        picture_shots[i]["prompt"] = prompts[i]

    # Image matching if folder is provided or set on project
    target_folder = folder or ((script_data.get("project") or {}).get("image_folder"))
    matched_images = {}
    fallback_used = False
    if target_folder and os.path.isdir(target_folder):
        img_files = folder_image_files(target_folder)
        matched_images, fallback_used = match_folder_images_by_slot(img_files, count_to_bind)
        for idx, img_path in matched_images.items():
            picture_shots[idx]["pin"] = img_path
            picture_shots[idx]["resolved"] = img_path
            picture_shots[idx]["resolved_score"] = 1.0
            picture_shots[idx]["source"] = "library"

    # Build mapping table
    mapping_table = []
    missing_slots = []
    matched_count = 0

    for i in range(count_to_bind):
        p_text = prompts[i]
        p_preview = p_text[:60] + ("…" if len(p_text) > 60 else "")
        img_path = matched_images.get(i)
        img_name = os.path.basename(img_path) if img_path else "—"
        status = "matched" if img_path else "missing"
        if img_path:
            matched_count += 1
        else:
            missing_slots.append(i + 1)

        mapping_table.append({
            "slot": i + 1,
            "prompt_preview": p_preview,
            "prompt_full": p_text,
            "image_found": img_name,
            "image_path": img_path,
            "status": status,
        })

    # Summary line
    if missing_slots:
        if len(missing_slots) == 1:
            missing_str = f"slot {missing_slots[0]} missing."
        else:
            missing_str = f"slots {', '.join(str(s) for s in missing_slots)} missing."
    else:
        missing_str = "all images matched."

    # Both counts, always, before anything else. A mismatch between what the
    # film needs and what was pasted is the failure this whole route is prone
    # to, and it used to happen without a word on screen.
    def _plural(n, word):
        return f"{n} {word}{'' if n == 1 else 's'}"

    counts_msg = (f"This film needs {_plural(total_pictures, 'picture')} "
                  f"across {_plural(total_shots, 'shot')}. "
                  f"You pasted {_plural(total_prompts, 'prompt')}.")

    unprompted = total_pictures - count_to_bind
    unused = total_prompts - count_to_bind
    if unprompted:
        counts_msg += (f" {_plural(unprompted, 'picture')} will fall back to "
                       f"library search.")
    elif unused:
        counts_msg += (f" {_plural(unused, 'prompt')} more than this film has "
                       f"pictures — the extra was ignored.")

    summary_msg = (f"{counts_msg} "
                   f"{_plural(matched_count, 'image')} matched, {missing_str}")
    if fallback_used and matched_count > 0:
        summary_msg += " (Images had no leading numbers; matched by sorted filename order)."

    return {
        "success": True,
        "script_data": script_data,
        "mapping_table": mapping_table,
        "summary": summary_msg,
        "counts": counts_msg,
        "prompts_count": count_to_bind,
        "pasted_count": total_prompts,
        "total_pictures": total_pictures,
        "total_shots": total_shots,
        "unprompted_pictures": unprompted,
        "unused_prompts": unused,
        "matched_count": matched_count,
        "missing_slots": missing_slots,
        "fallback_to_sorted": fallback_used,
    }


def prompt_name_match(prompt: str, image_path: str, min_words: int = 3) -> int:
    """
    How many of a prompt's opening words appear in an image's filename.

    Returns 0 unless at least `min_words` line up, so a single common word never
    counts as a match. This is checked before any visual scoring: when the user
    generated a picture from this exact prompt, the filename says so outright and
    guessing from pixels can only do worse.
    """
    head = prompt_head(prompt)
    if len(head) < min_words:
        return 0
    desc = describe_image(image_path)
    if not desc:
        return 0
    # The filename keeps the framing opener the prompt head drops, and tools
    # truncate names to ~20 characters, so strip it from both sides or a file
    # called "12_wide_establishing_sh" can never line up with any prompt.
    lowered = re.sub(r"^\d{1,4}[ _\-.]+", "", desc.lower())
    for opener in _PROMPT_OPENERS:
        if lowered.startswith(opener[:len(lowered)]) or lowered.startswith(opener):
            lowered = lowered[len(opener):]
            break
    have = set(re.findall(r"[a-z0-9']+", lowered))
    hits = sum(1 for t in head if t in have)
    return hits if hits >= min_words else 0


def match_shots_by_prompt_name(shot_prompts: dict, paths: list,
                               excluded: set = None) -> dict:
    """
    Pair shots with images their filenames name, before any visual matching.

    {shot_index: prompt} in, {shot_index: path} out. Each image is claimed once,
    strongest match first, so two shots with similar prompts cannot both take the
    same picture.
    """
    if not shot_prompts or not paths:
        return {}
    taken = {p.replace("\\", "/") for p in (excluded or set())}

    candidates = []
    for idx, prompt in shot_prompts.items():
        for path in paths:
            norm = path.replace("\\", "/")
            if norm in taken:
                continue
            hits = prompt_name_match(prompt, norm)
            if hits:
                candidates.append((hits, idx, norm))

    candidates.sort(key=lambda c: -c[0])
    assigned, used = {}, set()
    for hits, idx, norm in candidates:
        if idx in assigned or norm in used:
            continue
        assigned[idx] = norm
        used.add(norm)
    return assigned


def score_matrix(queries: list, paths: list, embeddings, floor: float,
                 use_descriptions: bool = True):
    """
    Every shot scored against every image: rows are queries, columns are images.

    This is the same eligibility score `search` computes, produced for the whole
    board at once so the assignment can be solved globally instead of shot by
    shot.
    """
    if not queries or len(paths) == 0:
        return np.zeros((len(queries), len(paths)), dtype=np.float32)

    q_emb = np.stack([encode_text_query(q) for q in queries]).astype(np.float32)
    scores = np.dot(q_emb, embeddings.T).astype(np.float32)

    if use_descriptions:
        desc_emb = _load_description_embeddings(paths)
        if desc_emb is not None and len(desc_emb) == len(paths):
            desc = np.dot(q_emb, np.asarray(desc_emb, dtype=np.float32).T)
            lifted = floor + (desc - DESCRIPTION_MIN_SCORE) * 0.05
            scores = np.where(desc >= DESCRIPTION_MIN_SCORE,
                              np.maximum(scores, lifted), scores)
    return scores


def optimal_assignment(queries: list, paths: list, embeddings, floor: float,
                       excluded: set = None, allow_reuse: bool = False,
                       use_descriptions: bool = True) -> dict:
    """
    Choose the best image for every shot at once, rather than one at a time.

    Greedy assignment settles each shot before it has looked at the next, so an
    early shot takes an image a later shot needed and the loss cascades. With two
    shots and two images that is the difference between a total of 0.40 and 0.57;
    across ninety-five shots it is most of why a folder of images generated one
    per shot came back badly paired.

    Returns {shot_index: (path, score)}. Shots with nothing left are absent —
    with fewer images than shots and no reuse, some shots must go unfilled.
    """
    if not queries or len(paths) == 0:
        return {}

    scores = score_matrix(queries, paths, embeddings, floor, use_descriptions)

    # Rejections and images already claimed are simply unavailable.
    rejected = get_rejected_pairs()
    norm_paths = [p.replace("\\", "/") for p in paths]
    taken = {p.replace("\\", "/") for p in (excluded or set())}
    blocked = np.zeros_like(scores, dtype=bool)
    for j, path in enumerate(norm_paths):
        if path in taken:
            blocked[:, j] = True
    for i, q in enumerate(queries):
        ql = (q or "").strip().lower()
        if not rejected:
            break
        for j, path in enumerate(norm_paths):
            if (ql, path) in rejected:
                blocked[i, j] = True

    usable = np.where(blocked, -np.inf, scores)

    if allow_reuse:
        # Repeats are permitted, so there is nothing to trade off — each shot
        # simply takes its own best.
        out = {}
        for i in range(len(queries)):
            j = int(np.argmax(usable[i]))
            if np.isfinite(usable[i, j]):
                out[i] = (norm_paths[j], float(scores[i, j]))
        return out

    try:
        from scipy.optimize import linear_sum_assignment
    except Exception:
        # Without scipy the greedy path still works; it is just worse.
        return {}

    # linear_sum_assignment minimises, and cannot see -inf.
    cost = np.where(np.isfinite(usable), -usable, 1e6).astype(np.float64)
    rows, cols = linear_sum_assignment(cost)

    out = {}
    for i, j in zip(rows, cols):
        if np.isfinite(usable[i, j]):
            out[int(i)] = (norm_paths[int(j)], float(scores[int(i), int(j)]))
    return out


def resolve_library_path(rel_path: str) -> str:
    """
    Turn a stored library-relative path ("library/images/x.jpg") into an absolute
    path, or return None if it does not exist. Pins are stored relative so a
    project stays portable; every consumer must resolve through here.
    """
    if not rel_path or not isinstance(rel_path, str):
        return None
    cleaned = rel_path.strip().replace("\\", "/")
    if not cleaned:
        return None
    candidate = cleaned if os.path.isabs(cleaned) else os.path.join(ROOT, cleaned)
    return candidate if os.path.exists(candidate) else None


# ── 3. Diversity Search ────────────────────────────────────────────────────────

#: How much an already-used image is penalised when reuse is allowed. Large
#: enough that a fresh image always wins when one exists, finite so that a folder
#: holding a single picture can still fill an entire film.
REUSE_PENALTY = 0.5


def search(query: str, k: int = 5, exclude: set = None, min_score: float = None,
           use_descriptions: bool = True, folder: str = None, allow_reuse: bool = False):
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

    # A working folder anywhere on this machine gets its own small index; a plain
    # name still means a subfolder of the library.
    external = bool(folder) and os.path.isabs(str(folder)) and os.path.isdir(str(folder))
    if external:
        embeddings, paths = load_folder_index(str(folder))
    else:
        embeddings, paths = load_index()
    if len(paths) == 0:
        return []

    q_emb = encode_text_query(query)
    raw_scores = np.dot(embeddings, q_emb)

    # An image made for this very shot can still lose on picture similarity alone:
    # measured here, images generated from a shot's own composed prompt ranked
    # between 43rd and 833rd for that shot. Their descriptions matched it at
    # 0.72-0.80. When the description is a strong match, lift the image to the
    # floor so it is findable — the picture score still decides the ordering.
    desc_scores = description_scores(query, [p.replace("\\", "/") for p in paths]) \
        if use_descriptions else np.zeros(len(paths), dtype=np.float32)

    render_usage_counts = get_render_usage_counts()
    rejected_pairs = get_rejected_pairs()
    query_lower = query.strip().lower()
    prefix = "" if external else _folder_prefix(folder)

    floor = min_score if min_score is not None else get_calibrated_min_score()

    adjusted_results = []
    for idx, (path, raw_score) in enumerate(zip(paths, raw_scores)):
        norm_path = path.replace("\\", "/")

        # Only this project's folder, when one is chosen.
        if prefix and not norm_path.startswith(prefix):
            continue

        # Rejection memory: never return a rejected pairing
        if (query_lower, norm_path) in rejected_pairs:
            continue

        # Diversity. Excluding used images outright is right for a full library
        # and wrong for a thin one — and impossible for a project that means to
        # carry one picture through a whole film, which is normal for a
        # motivational piece. With reuse allowed it becomes a heavy penalty
        # instead: a fresh image still always wins, but a repeat beats a gap.
        already_used = norm_path in clean_exclude
        if already_used and not allow_reuse:
            continue

        # Two scores, deliberately. `eligible` answers "is this a good enough
        # match?" and is what the caller sees; `rank` answers "which of these
        # should I hand back first?" and carries the penalties. Subtracting the
        # reuse penalty from the reported score pushed a repeat under the match
        # floor, so a one-image project produced nothing but gaps.
        eligible_score = float(raw_score)

        desc_score = float(desc_scores[idx])
        if desc_score >= DESCRIPTION_MIN_SCORE:
            # A near-paraphrase description lifts the image to the floor, so a
            # picture made for this shot is findable by it.
            eligible_score = max(eligible_score,
                                 floor + (desc_score - DESCRIPTION_MIN_SCORE) * 0.05)

        rank_score = eligible_score
        if already_used:
            rank_score -= REUSE_PENALTY
        rank_score -= RENDER_USAGE_PENALTY * render_usage_counts.get(norm_path, 0)

        adjusted_results.append((norm_path, rank_score, eligible_score))

    # Best candidate first, penalties included.
    adjusted_results.sort(key=lambda x: x[1], reverse=True)

    # Report the eligibility score: whether this is a good match does not depend
    # on how many other shots already took it.
    return [(norm_path, eligible) for norm_path, _rank, eligible in adjusted_results[:k]]


# ── 4. Prompt Composition for Gaps ─────────────────────────────────────────────

def scene_from_narration(narration: str, max_words: int = 34) -> str:
    """
    A short visual description of what this shot is about, taken from its own
    narration.

    The prompt's subject used to be the shot query alone — three words of keyword
    salad like "Usama Madinah Cancel" — so an image generated from it had almost
    no relationship to the scene being narrated. The narration is the only place
    the actual content lives.

    Quoted speech, episode furniture and calls to action are removed: they are
    things people say, not things a picture can show.
    """
    if not narration:
        return ""
    text = re.sub(r'<[^>]+>', ' ', narration)
    text = re.sub(r'[“”"‘’]', ' ', text)
    # Drop the presenter's own asides, which describe the video and not the scene.
    text = re.sub(
        r'\b(hit subscribe|subscribe|if you are new here|last time|next episode|'
        r'we are walking through|this history is only getting bigger)[^.]*\.',
        ' ', text, flags=re.IGNORECASE)
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
    if not sentences:
        return ""

    words = []
    for sentence in sentences:
        words.extend(sentence.split())
        if len(words) >= max_words:
            break
    scene = " ".join(words[:max_words]).strip(" ,;:.")
    return re.sub(r'\s+', ' ', scene)


#: Generators weight early tokens heavily; an unbounded brief would out-argue
#: the shot's own subject.
BRIEF_MAX_WORDS = 30

#: How each treatment names the kind of picture the film is made of.
#: How every prompt in one film opens.
#:
#: These name the *kind of picture*, never a physical object. "Illustration
#: plate from a documentary on early Islamic history" came back as a decorative
#: plate with that sentence lettered underneath it, and "Plate 40:" printed
#: across the frame. A generator draws the nouns it is given: ask for a plate,
#: a still, a study or a panel and it renders the artefact and captions it.
#: "of" rather than "from" matters for the same reason - "from" implies the
#: picture was cut out of some larger printed thing.
#: Retired: the brief no longer opens by naming a medium. Kept only as a note
#: for scripts/author_brief_subjects.py, which still refers to it.
_RETIRED_BRIEF_OPENERS = {
    "documentary": "A documentary photograph of",
    "illustration": "An illustrated scene of",
    "silhouette": "A silhouetted scene of",
    "vox_collage": "Collaged imagery of",
    "vignette": "A cinematic scene of",
}

#: A capitalised name, allowing hyphenated forms (Jean-Baptiste) and the Arabic
#: nasab, where the particle and the name are separated by a space ("Khalid ibn
#: al-Walid"). The previous pattern required them contiguous, so it split that
#: name into "Khalid" and "Walid" - one man read as two characters.
#: The particles had to be separated. Written as one alternation with `\s*`
#: after it, "de" matched the opening of the next ordinary word: "Allah decided
#: to create Adam" was read as a character called "Allah decided", and that
#: phrase went into every image prompt in the film. A standing particle now has
#: to be a whole word followed by a space; only the prefixing ones attach.
_NAME_RE = re.compile(
    r"\b[A-Z][a-z]{2,}(?:-[A-Z][a-z]+)*"
    r"(?:"
    r"\s+(?:ibn|bin|bint|de|van|von)\s+(?:al-|el-)?[A-Z]?[a-z][a-zA-Z-]*"
    r"|\s+(?:al-|el-)[A-Z]?[a-z][a-zA-Z-]*"
    r"|\s+[A-Z][a-z]+(?:-[A-Z][a-z]+)*"
    r")*"
)

#: Words that start a sentence and are capitalised for that reason alone.
_BRIEF_STOPWORDS = {
    # Only words of three or more letters can match, so single letters and
    # two-letter words are deliberately absent - they could never match anyway.
    "The", "And", "But", "For", "Nor", "Yet", "This", "That", "These", "Those",
    "There", "Then", "Than", "They", "Their", "Them", "She", "His", "Her",
    "Hers", "Its", "You", "Your", "Our", "Ours", "Who", "Whom", "Whose",
    "When", "Where", "What", "Why", "How", "Which", "While", "With", "Within",
    "Without", "After", "Before", "During", "Under", "Over", "Above", "Below",
    "Between", "Because", "Since", "Until", "Unless", "Although", "Though",
    "Once", "Now", "Soon", "Later", "Never", "Always", "Often", "Sometimes",
    "Suddenly", "Finally", "Meanwhile", "Instead", "However", "Therefore",
    "Every", "Each", "Both", "Many", "Most", "Some", "Such", "One", "Two",
    "Three", "Four", "Five", "Not", "Only", "Even", "Still", "Just", "Here",
    "From", "Into", "Onto", "Upon", "About", "Against", "Among", "Through",
    "Toward", "Towards", "Behind", "Beyond", "Across", "Along", "Around",
    "Bring", "Come", "Take", "Give", "Look", "See", "Say", "Said", "Let",
    # Openers that begin a clause and so get capitalised. "According to the
    # reports" put a character called "According" into the brief the moment a
    # real name was excluded and a slot opened up.
    "According", "Consider", "Imagine", "Picture", "Remember", "Notice",
    "Perhaps", "Maybe", "Indeed", "Rather", "Nothing", "Nobody", "Something",
    "Someone", "Everything", "Everyone", "Another", "Others", "Whether",
    "Before", "Yes", "Well", "First", "Second", "Third", "Last", "Next",
    "Today", "Tomorrow", "Yesterday", "Long", "Far", "More", "Less", "Much",
}


def never_depict_names(series_cfg: dict) -> set:
    """
    Lowercased names the niche says no picture may show.

    Declared in the niche file as `never_depict`, so it travels with the niche
    and needs no screen of its own. It reaches both places a name can turn into
    a picture: the brief that names recurring figures, and the instruction the
    description model is given.
    """
    raw = (series_cfg or {}).get("never_depict") or []
    if isinstance(raw, str):
        raw = [raw]
    return {str(n).strip().lower() for n in raw if str(n).strip()}


def draft_project_brief(title: str, series_cfg: dict, script_text: str,
                        treatment: str = None) -> str:
    """
    The opening block shared by every prompt in one script.

    The title is never emitted: it is metadata, not a picture. What carries
    across shots is the subject and the figures who recur often enough to need
    to look the same in every frame.

    The brief no longer opens by naming a medium. It used to — "A documentary
    photograph of ..." — chosen from the treatment, drafted once and then never
    revisited. The picked visual type states the medium already, so when the two
    agreed the prompt said it twice, and when they disagreed the prompt asked
    for both at once. A project set to Paper Collage carried "A documentary
    photograph of real people and places" alongside "Cut-paper collage on
    textured board" in all 55 of its prompts. `treatment` is accepted and
    ignored, so existing callers keep working.
    """

    # world_anchor is not a place in most packs - it carries medium language
    # too ("Matthew Brady tintype archival photograph"), which fights the picked
    # visual type. brief_subject names the subject and nothing else.
    # A pack that predates brief_subject still has to contribute its setting,
    # because the setting slot now stays quiet whenever a brief is present.
    # Falling back to world_anchor keeps custom packs working; it is only the
    # authored packs that get medium-free wording.
    subject = ((series_cfg or {}).get("brief_subject")
               or (series_cfg or {}).get("world_anchor")
               or "")
    parts = [subject] if subject.strip() else []

    # Count by first name, keep the fullest form. A script that says "Khalid ibn
    # al-Walid" once and "Khalid" thereafter is describing one man twice, not two
    # men once each - counting the exact strings separately left both below the
    # threshold and dropped the protagonist from the brief.
    # Figures the niche says are never drawn. A name can recur all through a
    # script and still be one no picture may show — a film about Adam and Iblis
    # says "Allah" constantly, and "consistent depiction of Allah" in every
    # prompt is not what the niche wants drawn. The niche decides, because it
    # is a matter for the subject, not for the app.
    never = never_depict_names(series_cfg)

    counts = {}
    fullest = {}
    for m in _NAME_RE.finditer(script_text or ""):
        name = m.group(0).strip()
        head = name.split()[0]
        if head in _BRIEF_STOPWORDS or head.lower() in never:
            continue
        counts[head] = counts.get(head, 0) + 1
        if len(name) > len(fullest.get(head, "")):
            fullest[head] = name

    # A name is a word that is never an ordinary word. "According", "Different",
    # "Suddenly" are capitalised because they open a clause, and they also turn
    # up in lower case elsewhere in the same script; "Adam" and "Iblis" never
    # do. Listing the openers one at a time did not hold — excluding one name
    # freed a slot and the next opener took it — so the test is structural.
    def _is_a_name(head: str) -> bool:
        # Case-sensitive: does this word ever appear in lower case here? A name
        # never does. Counting occurrences instead was wrong, because a name
        # following a capitalised opener is swallowed into it - "Before Adam"
        # is one match headed "Before" - which deflated the name's own count.
        return not re.search(rf"\b{re.escape(head.lower())}\b", script_text or "")

    recurring = [fullest[h] for h in
                 sorted([h for h, c in counts.items() if c >= 2 and _is_a_name(h)],
                        key=lambda h: (-counts[h], h))[:3]]
    if recurring:
        parts.append("consistent depiction of " + ", ".join(recurring))

    return cap_project_brief(", ".join(parts))


def cap_project_brief(brief: str) -> str:
    """
    Trim a brief to BRIEF_MAX_WORDS without leaving a dangling clause.

    Applied to hand-edited briefs too, not only drafted ones: generators weight
    early tokens heavily, so an unbounded opening would out-argue the shot's own
    subject in every prompt of the film.
    """
    brief = (brief or "").strip()
    words = brief.split()
    if len(words) > BRIEF_MAX_WORDS:
        cut = " ".join(words[:BRIEF_MAX_WORDS])
        if "," in cut:
            cut = cut[:cut.rindex(",")]
        brief = cut
    return brief.rstrip(" ,")


def ensure_project_brief(project_info: dict, script_text: str = "") -> str:
    """
    The project's brief: the recurring figures, drafted fresh every time.

    It used to be drafted once and never overwritten, to protect a hand-edited
    brief across re-plans. There is no longer a box to hand-edit it in — the
    niche recipe carries the look now — and freezing it was doing harm: a brief
    drafted before the visual type was picked went on claiming the wrong medium
    for the life of the project, and no amount of changing the visual type
    could dislodge it. Redrawing it costs nothing and cannot go stale.
    """

    slug = (project_info or {}).get("series_slug")
    cfg = {}
    if slug:
        try:
            cfg = get_series_config(series_slug=slug)
        except Exception:
            cfg = {}

    visual_type = (project_info or {}).get("visual_type") or ""
    preset = resolve_style_preset(cfg, visual_type)
    treatment = preset.get("treatment") if preset else None
    if not treatment and visual_type:
        from pipeline.composer import SINGLE_IMAGE_TREATMENTS
        if visual_type in SINGLE_IMAGE_TREATMENTS:
            treatment = visual_type

    return draft_project_brief(
        (project_info or {}).get("title", ""), cfg, script_text, treatment
    )


#: Looks that suit any niche. A true-crime film and a wildlife film can both
#: want photoreal or cartoon; only the niche-specific entries in each pack need
#: to differ. A pack may override any of these by using the same key.
UNIVERSAL_STYLE_PRESETS = {
    "photoreal": {
        "prompt": "Photorealistic image, natural light, true-to-life colour and "
                  "texture, sharp focus, no stylisation.",
        "treatment": "documentary",
    },
    "cinematic": {
        "prompt": "Cinematic film still, anamorphic framing, shallow depth of "
                  "field, graded colour, subtle halation.",
        "treatment": "none",
    },
    "black_and_white": {
        "prompt": "Black and white photograph, deep blacks, controlled "
                  "highlights, visible silver grain.",
        "treatment": "documentary",
    },
    "stylised_illustration": {
        "prompt": "Stylised illustration, confident inked line, limited palette, "
                  "flat colour fields.",
        "treatment": "illustration",
    },
    "cartoon": {
        "prompt": "Clean cartoon illustration, bold outlines, flat cel shading, "
                  "simplified expressive shapes.",
        "treatment": "illustration",
    },
    "three_d_render": {
        "prompt": "3D render, soft global illumination, physically based "
                  "materials, shallow depth of field.",
        "treatment": "none",
    },
}


def style_presets_for(series_cfg: dict) -> dict:
    """
    Every visual type this niche offers: its own first, then the universal ones.

    When the pack comes from an override, its style_presets list is authoritative and no merge occurs.
    A pack wins any key collision, so a niche can give "cartoon" its own wording
    without losing the rest of the shared set.
    """
    presets = (series_cfg or {}).get("style_presets") or {}
    if (series_cfg or {}).get("style_presets_is_override"):
        return dict(presets)
    merged = {}
    for key, entry in presets.items():
        merged[key] = entry
    for key, entry in UNIVERSAL_STYLE_PRESETS.items():
        merged.setdefault(key, entry)
    return merged


def resolve_style_preset(series_cfg: dict, visual_type: str) -> dict | None:
    """
    The picked visual type, as {"prompt": str, "treatment": str | None}.

    A pack entry is either prose on its own or an object that also names the
    post-processing treatment it maps to, because a preset called
    "evidence_photo" cannot have its treatment inferred from its key.
    Returns None when nothing usable is defined, and callers fall back to
    style_block.
    """
    if not visual_type:
        return None
    entry = style_presets_for(series_cfg).get(visual_type)
    if isinstance(entry, str) and entry.strip():
        return {"prompt": entry.strip(), "treatment": None}
    if isinstance(entry, dict):
        prompt = entry.get("prompt")
        if isinstance(prompt, str) and prompt.strip():
            return {"prompt": prompt.strip(), "treatment": entry.get("treatment")}
    return None


_PACK_ANCHORS_CACHE = None


def _pack_world_anchors() -> set:
    """Every series pack's world_anchor, lowercased, for recognising a stale copy."""
    global _PACK_ANCHORS_CACHE
    if _PACK_ANCHORS_CACHE is None:
        found = set()
        try:
            for name in os.listdir(SERIES_CONFIG_DIR):
                if not name.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(SERIES_CONFIG_DIR, name), "r", encoding="utf-8") as f:
                        anchor = (json.load(f).get("world_anchor") or "").strip().lower()
                except Exception:
                    continue
                if anchor:
                    found.add(anchor)
        except Exception:
            pass
        _PACK_ANCHORS_CACHE = found
    return _PACK_ANCHORS_CACHE


def project_world_anchor(project_info: dict) -> str:
    """
    The project's own world anchor, or None to let the current pack speak.

    The pack's anchor used to be copied into the project when the script was
    first parsed, and compose_gap_prompt always honours an explicit anchor over
    the pack's own. So whichever niche a script was first planned under followed
    it for the rest of its life: a wildlife film built from an Islamic-history
    draft still demanded seventh century Arabia in every prompt, and the era was
    stated twice over because the brief said it too.

    An anchor matching a pack verbatim is that stale copy, not the user's words,
    so it defers to the pack. Anything else is a deliberate override and stands.

    visual_style is never an anchor. It holds the label of the picked visual
    type ("Stylised Illustration"), and reading it here put the name of a style
    into the setting slot.
    """
    raw = ((project_info or {}).get("world_anchor") or "").strip()
    if not raw or raw.lower() in _pack_world_anchors():
        return None
    return raw


def compose_gap_prompt(
    shot_query: str,
    world_anchor: str = None,
    character_bible: dict = None,
    script_context: str = "",
    series_slug: str = None,
    project_title: str = None,
    include_negative: bool = None,
    visual_type: str = None,
    project_brief: str = None,
    visual_description: str = None,
    shot_position: int = None,
    apply_era: bool = True,
) -> str:
    """
    A ready-to-use image prompt for one shot, built from named slots.

    Slots, in order: subject (leads), framing, project brief, motion, ground,
    atmosphere, setting, light, character bible, medium & palette, era (last,
    omittable), negative prompt. A slot that matches nothing is omitted rather
    than emitting filler.
    """
    from pipeline.prompt_slots import (
        match_slot, PROMPT_FRAMING, PROMPT_MOTION, PROMPT_GROUND,
        PROMPT_ATMOSPHERE, PROMPT_LIGHT, default_framing_for,
    )

    series_cfg = get_series_config(series_slug=series_slug, project_title=project_title)
    blob = f"{shot_query or ''} {script_context or ''}"

    preset = resolve_style_preset(series_cfg, visual_type)
    if not preset:
        # Pack default: if visual_type is empty, resolve to the first entry in style_presets_for
        all_presets = style_presets_for(series_cfg)
        if all_presets:
            first_key = next(iter(all_presets))
            preset = resolve_style_preset(series_cfg, first_key)

    if preset:
        medium = preset["prompt"]
    else:
        med = (series_cfg.get("medium_block") or "").strip()
        pal = (series_cfg.get("palette_block") or "").strip()
        if med or pal:
            medium = ", ".join(p for p in (med, pal) if p)
        else:
            medium = (series_cfg.get("style_block") or "").strip()

    era = (series_cfg.get("era_block") or "").strip() if apply_era else ""

    parts = []

    # Subject slot: use visual_description when present and non-empty, otherwise shot_query
    subject_text = (visual_description or "").strip() if (visual_description and visual_description.strip()) else (shot_query or "").strip()

    # The subject leads.
    parts.append(subject_text)

    # Only supply framing the subject does not already state.
    if match_slot(PROMPT_FRAMING, subject_text) is None:
        parts.append(default_framing_for(shot_position))

    if project_brief:
        parts.append(project_brief.rstrip(" ,."))

    for table in (PROMPT_MOTION, PROMPT_GROUND, PROMPT_ATMOSPHERE):
        phrase = match_slot(table, blob)
        if phrase:
            parts.append(phrase)

    # Setting slot / world anchor.
    explicit = (world_anchor or "").strip()
    if explicit and " " not in explicit and "_" in explicit:
        explicit = ""
    already_said = f"{medium} {era} {project_brief or ''}".lower()
    if explicit:
        if explicit.lower() not in already_said:
            parts.append(explicit)
    elif not project_brief and apply_era and not era:
        anchor = series_cfg.get("world_anchor") or ""
        if anchor and anchor.lower() not in already_said:
            parts.append(anchor)

    light = match_slot(PROMPT_LIGHT, blob)
    if light:
        parts.append(light)

    if character_bible:
        for char_name, char_desc in character_bible.items():
            pattern = r'\b' + re.escape(char_name) + r'\b'
            if re.search(pattern, shot_query or "", re.IGNORECASE) or \
               (script_context and re.search(pattern, script_context, re.IGNORECASE)):
                parts.append(f"featuring: {char_desc}")

    if medium:
        parts.append(medium.rstrip(" ."))

    if era and not project_brief:
        current_lower = ", ".join(p for p in parts if p).lower()
        if era.lower() not in current_lower:
            parts.append(era.rstrip(" ."))

    if include_negative is None:
        include_negative = bool(_setting("include_negative_prompt", False))
    if include_negative:
        negative_block = series_cfg.get("negative_block")
        if negative_block:
            parts.append(f"Negative prompt: {negative_block}")

    return ", ".join(p for p in parts if p).rstrip(" ,") + "."


# ── 5. Coverage & Plan Shots ───────────────────────────────────────────────────

def plan_shots(script_data: dict, min_score: float = None, weak_band: float = None):
    """
    Analyzes all shots in a script against the library index.
    Ensures diversity (NO image used twice in a single script).
    Reports 3 states per shot: matched, weak, gap.
    Keeps GAPS and WEAK lists separated so counters and lists match strictly.
    """
    project_info = script_data.get("project", {})
    title = project_info.get("title", "Untitled Project")
    series_slug = project_info.get("series_slug")

    if min_score is None:
        min_score = get_calibrated_min_score(series_slug=series_slug)
    if weak_band is None:
        weak_band = get_calibrated_weak_band(series_slug=series_slug)

    world_anchor = project_world_anchor(project_info)
    visual_type = project_info.get("visual_type") or ""
    project_brief = ensure_project_brief(
        project_info,
        " ".join(seg.get("narration", "") for seg in script_data.get("segments", [])),
    )
    project_info["project_brief"] = project_brief
    apply_era = project_info.get("apply_era", True)
    character_bible = project_info.get("character_bible") or {}

    # A project can restrict itself to one folder of images. Curating twenty
    # pictures you chose beats steering a search across twelve hundred.
    folder = project_info.get("image_folder") or ""

    # Repeating an image is normal for some work — a motivational piece may run
    # one picture for fifteen minutes while the motion and the cuts carry it.
    allow_reuse = project_info.get("allow_image_reuse")
    if allow_reuse is None:
        allow_reuse = _setting("allow_image_reuse", True)

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
                # A shot's own slice of the narration when it has one, so each
                # shot in a segment gets a prompt describing its own moment.
                "narration": shot.get("scene") or narration,
                # The board lets the user choose an image. That choice is a pin, and a
                # re-plan must honour it instead of asking CLIP again.
                "pin": (shot.get("pin") or "").strip() if isinstance(shot.get("pin"), str) else None,
                # What this shot settled on last time it was planned. Retrieval is
                # greedy and forbids reuse, so without this every re-plan reshuffled
                # the whole board: choosing an image for one shot freed its old one
                # and cascaded through all the others. The board needs a memory.
                "resolved": (shot.get("resolved") or "").strip() if isinstance(shot.get("resolved"), str) else None,
                "resolved_score": shot.get("resolved_score"),
                # The prompt this shot advertised. Kept on the shot so that an
                # image generated from it hours later is still recognised: the
                # board shows a prompt, the user goes away and makes the picture,
                # and Refresh has to know what it was waiting for.
                "prompt": shot.get("prompt") or "",
                "prompt_override": (shot.get("prompt_override") or "").strip() if isinstance(shot.get("prompt_override"), str) else None,
                "share_with": shot.get("share_with"),
                "run_index": shot.get("run_index"),
                "run_position": shot.get("run_position"),
                "visual_description": shot.get("visual_description"),
                "_shot": shot,
            })

    if _setting("ai_shot_descriptions", False):
        try:
            from pipeline.shot_description import describe_shots
            google_key = _setting("google_api_key", "")
            series_cfg = get_series_config(series_slug=series_slug, project_title=title)
            shots_for_desc = []
            for s in all_shots:
                scene_text = s.get("narration") or (s.get("_shot") and s["_shot"].get("scene")) or ""
                shots_for_desc.append({
                    "shot_id": s["shot_id"],
                    "scene": scene_text,
                    "visual_description": s.get("visual_description") or (s.get("_shot") and s["_shot"].get("visual_description")),
                })
            # The whole narration, in order, so a shot can be placed in its film
            # before it is described. A lone clause is not enough to illustrate.
            script_context = [
                (seg.get("narration") or "").strip()
                for seg in (script_data.get("segments") or [])
            ]
            descriptions = describe_shots(shots_for_desc, series_cfg=series_cfg,
                                          script_context=script_context)
            for s in all_shots:
                if s["shot_id"] in descriptions:
                    s["visual_description"] = descriptions[s["shot_id"]]
                    if s.get("_shot") is not None:
                        s["_shot"]["visual_description"] = descriptions[s["shot_id"]]
        except Exception as e:
            sys.stderr.write(f"[plan_shots] AI shot description failed: {e}\n")

    script_used_images = set()

    matched_count = 0
    weak_count = 0
    gap_count = 0
    pinned_count = 0

    shot_reports = []
    resolved_by_id = {}
    query_to_segments = {}

    # Reserve pinned and previously-resolved images before anything searches, so a
    # later shot cannot be handed an image another shot has already claimed.
    for s in all_shots:
        s["pin_resolved"] = resolve_library_path(s["pin"]) if s["pin"] else None
        if s["pin_resolved"]:
            script_used_images.add(s["pin"].replace("\\", "/"))

    # Work out the numbered pairing first. A folder of images named 1_, 2_, 3_ is
    # the user stating which picture goes where, and that has to outrank the
    # board's own memory of an earlier plan — otherwise a shot that already holds
    # a library image never looks at the numbered file at all.
    numbered_matches = {}
    if folder and _setting("match_by_prompt_name", True):
        try:
            _external = os.path.isabs(str(folder)) and os.path.isdir(str(folder))
            _, _num_paths = (load_folder_index(str(folder)) if _external else load_index())
            numbered_matches = match_shots_by_number(
                [p.replace("\\", "/") for p in _num_paths
                 if _path_in_scope(p.replace("\\", "/"), "" if _external else folder)],
                len(all_shots),
                shot_prompts={i: s["prompt"] for i, s in enumerate(all_shots) if s["prompt"]},
            )
        except Exception:
            numbered_matches = {}

    for idx_s, s in enumerate(all_shots):
        s["keep_resolved"] = None
        if s["pin_resolved"] or not s["resolved"] or idx_s in numbered_matches:
            continue
        candidate = s["resolved"].replace("\\", "/")
        # Only keep it if it still exists, nobody else has claimed it, and it
        # comes from the image source this project is now using. Without the last
        # check, choosing a working folder changed nothing: every shot already
        # remembered a library image and never consulted the folder at all.
        if (candidate not in script_used_images
                and resolve_library_path(candidate)
                and _path_in_scope(candidate, folder)):
            s["keep_resolved"] = candidate
            script_used_images.add(candidate)

    # Solve the whole board at once for the shots still needing an image. Doing
    # this shot by shot lets an early shot take an image a later one needed, and
    # the loss cascades — which is exactly what happens to a folder of images
    # generated one per shot.
    open_shots = [i for i, s in enumerate(all_shots)
                  if not s["pin_resolved"] and not s["keep_resolved"] and not s.get("share_with")]

    # An image named after a shot's own prompt belongs to that shot. This is
    # exact — the filename literally repeats the prompt's opening words — so it
    # is settled before any pixel is scored. It is also what makes generating
    # images later work: the prompt is remembered on the shot, so an image made
    # hours after the board was planned is still claimed by the right shot.
    name_matched = {}

    # The numbered pairing, worked out before the board's memory was consulted.
    for i, path in numbered_matches.items():
        if not all_shots[i]["pin_resolved"] and path not in script_used_images:
            name_matched[i] = path
            script_used_images.add(path)

    still_open = [i for i in open_shots if i not in name_matched]
    if still_open and _setting("match_by_prompt_name", True):
        try:
            external = bool(folder) and os.path.isabs(str(folder)) and os.path.isdir(str(folder))
            _, name_paths = (load_folder_index(str(folder)) if external else load_index())
            in_scope_paths = [
                p.replace("\\", "/") for p in name_paths
                if _path_in_scope(p.replace("\\", "/"), "" if external else folder)
            ]
            by_name = match_shots_by_prompt_name(
                {i: all_shots[i]["prompt"] for i in still_open if all_shots[i]["prompt"]},
                in_scope_paths,
                excluded=script_used_images,
            )
            for i, path in by_name.items():
                name_matched[i] = path
                script_used_images.add(path)
        except Exception:
            pass

    open_shots = [i for i in open_shots if i not in name_matched]
    assignment = {}
    if open_shots and _setting("optimal_assignment", True):
        try:
            external = bool(folder) and os.path.isabs(str(folder)) and os.path.isdir(str(folder))
            emb_all, paths_all = (load_folder_index(str(folder)) if external else load_index())
            in_scope = [
                (j, p.replace("\\", "/")) for j, p in enumerate(paths_all)
                if _path_in_scope(p.replace("\\", "/"), "" if external else folder)
            ]
            if in_scope:
                cols = [j for j, _ in in_scope]
                solved = optimal_assignment(
                    queries=[all_shots[i]["query"] for i in open_shots],
                    paths=[p for _, p in in_scope],
                    embeddings=np.asarray(emb_all)[cols],
                    floor=min_score,
                    excluded=script_used_images,
                    allow_reuse=allow_reuse,
                )
                for row, (path, score) in solved.items():
                    assignment[open_shots[row]] = (path, score)
        except Exception:
            assignment = {}   # greedy still works; never lose the board over this

    for idx, s in enumerate(all_shots):
        q = s["query"]
        target_min = s["min_score"]
        target_weak = target_min - weak_band

        if q not in query_to_segments:
            query_to_segments[q] = []
        query_to_segments[q].append(s["segment_id"])

        pin_missing = bool(s["pin"]) and not s["pin_resolved"]

        # When a shot shares an image with an earlier shot in a run, copy the
        # resolution directly without running its own library search.
        # A pin outranks sharing. The run assigns one image to a stretch of
        # segments, but a pin is the user pointing at a picture and saying "this
        # one, here" - it survives a re-plan at any image count. Without this
        # guard the branch below runs first and its `continue` skips the pin
        # branch entirely, silently discarding the choice.
        if s.get("share_with") and not s["pin_resolved"]:
            ref_id = s["share_with"]
            ref_rep = resolved_by_id.get(ref_id)
            if ref_rep and ref_rep.get("best_path"):
                best_path = ref_rep["best_path"]
                best_score = ref_rep["best_score"]
                state = ref_rep["state"]
                alts = ref_rep.get("alternatives") or []

                if state in ("matched", "pinned"):
                    matched_count += 1
                elif state == "weak":
                    weak_count += 1
                else:
                    gap_count += 1

                override_prompt = (s.get("prompt_override") or (s.get("_shot") and s["_shot"].get("prompt_override")) or "").strip()
                if override_prompt:
                    composed = override_prompt
                else:
                    composed = compose_gap_prompt(
                        shot_query=q,
                        world_anchor=world_anchor,
                        character_bible=character_bible,
                        script_context=s["narration"],
                        series_slug=series_slug,
                        project_title=title,
                        visual_type=visual_type,
                        project_brief=project_brief,
                        visual_description=s.get("visual_description"),
                        shot_position=idx,
                        apply_era=apply_era,
                    )
                if s.get("_shot") is not None:
                    if override_prompt:
                        s["_shot"]["prompt"] = override_prompt
                        s["_shot"]["prompt_override"] = override_prompt
                    elif not s["_shot"].get("prompt"):
                        s["_shot"]["prompt"] = composed
                    s["_shot"]["resolved"] = best_path
                    s["_shot"]["resolved_score"] = best_score
                    if "source" in ref_rep:
                        s["_shot"]["source"] = ref_rep["source"]

                rep = {
                    "segment_id": s["segment_id"],
                    "shot_id": s["shot_id"],
                    "query": q,
                    "state": state,
                    "best_score": best_score,
                    "best_path": best_path,
                    "alternatives": alts,
                    "pin_missing": False,
                    "composed_prompt": composed,
                    "prompt_override": override_prompt if override_prompt else None,
                    "share_with": ref_id,
                    "source": ref_rep.get("source", "library"),
                }
                shot_reports.append(rep)
                resolved_by_id[s["shot_id"]] = rep
                continue

        if s["pin_resolved"]:
            # The user chose this image. Offer alternatives so Replace still has
            # something to show, but the choice itself is not up for re-litigation.
            alt_results = search(q, k=5, exclude=script_used_images, min_score=0.0,
                                 folder=folder, allow_reuse=allow_reuse)
            override_prompt = (s.get("prompt_override") or (s.get("_shot") and s["_shot"].get("prompt_override")) or "").strip()
            if override_prompt:
                composed = override_prompt
            else:
                composed = compose_gap_prompt(
                    shot_query=q,
                    world_anchor=world_anchor,
                    character_bible=character_bible,
                    script_context=s["narration"],
                    series_slug=series_slug,
                    project_title=title,
                    visual_type=visual_type,
                    project_brief=project_brief,
                    visual_description=s.get("visual_description"),
                    shot_position=idx,
                    apply_era=apply_era,
                )
            rep = {
                "segment_id": s["segment_id"],
                "shot_id": s["shot_id"],
                "query": q,
                "state": "pinned",
                "best_score": 1.0,
                "best_path": s["pin"].replace("\\", "/"),
                "alternatives": alt_results[:4],
                "pin_missing": False,
                "composed_prompt": composed,
                "prompt_override": override_prompt if override_prompt else None,
                "source": s["_shot"].get("source", "library") if s.get("_shot") else "library",
            }
            if s.get("_shot") is not None:
                if override_prompt:
                    s["_shot"]["prompt"] = override_prompt
                    s["_shot"]["prompt_override"] = override_prompt
                elif not s["_shot"].get("prompt"):
                    s["_shot"]["prompt"] = composed
                s["_shot"]["resolved"] = rep["best_path"]
                s["_shot"]["resolved_score"] = 1.0
            shot_reports.append(rep)
            resolved_by_id[s["shot_id"]] = rep
            pinned_count += 1
            continue

        if s["keep_resolved"]:
            # This shot already had an image and nothing has taken it away. Keep it,
            # so choosing an image for one shot cannot disturb any other.
            kept_score = s["resolved_score"] if isinstance(s["resolved_score"], (int, float)) else target_min
            state = "matched" if kept_score >= target_min else "weak"
            alt_results = search(q, k=5, exclude=script_used_images, min_score=0.0,
                                 folder=folder, allow_reuse=allow_reuse)
            if state == "matched":
                matched_count += 1
            else:
                weak_count += 1
            override_prompt = (s.get("prompt_override") or (s.get("_shot") and s["_shot"].get("prompt_override")) or "").strip()
            if override_prompt:
                composed = override_prompt
            else:
                composed = compose_gap_prompt(
                    shot_query=q,
                    world_anchor=world_anchor,
                    character_bible=character_bible,
                    script_context=s["narration"],
                    series_slug=series_slug,
                    project_title=title,
                    visual_type=visual_type,
                    project_brief=project_brief,
                    visual_description=s.get("visual_description"),
                    shot_position=idx,
                    apply_era=apply_era,
                )
            rep = {
                "segment_id": s["segment_id"],
                "shot_id": s["shot_id"],
                "query": q,
                "state": state,
                "best_score": kept_score,
                "best_path": s["keep_resolved"],
                "alternatives": alt_results[:4],
                "pin_missing": pin_missing,
                "composed_prompt": composed,
                "prompt_override": override_prompt if override_prompt else None,
                "source": s["_shot"].get("source", "library") if s.get("_shot") else "library",
            }
            if s.get("_shot") is not None:
                if override_prompt:
                    s["_shot"]["prompt"] = override_prompt
                    s["_shot"]["prompt_override"] = override_prompt
                elif not s["_shot"].get("prompt"):
                    s["_shot"]["prompt"] = composed
                s["_shot"]["resolved"] = rep["best_path"]
                s["_shot"]["resolved_score"] = kept_score
            shot_reports.append(rep)
            resolved_by_id[s["shot_id"]] = rep
            continue

        results = search(q, k=5, exclude=script_used_images, min_score=target_min,
                         folder=folder, allow_reuse=allow_reuse)

        # An image whose filename repeats this shot's prompt wins outright.
        named = name_matched.get(idx)
        if named:
            results = [(named, max(target_min, 1.0))] + [r for r in results if r[0] != named]

        # Prefer the globally-solved choice; `results` still supplies the
        # alternatives shown under the card.
        chosen = assignment.get(idx)
        if chosen and chosen[0] not in script_used_images:
            results = [chosen] + [r for r in results if r[0] != chosen[0]]

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

        override_prompt = (s.get("prompt_override") or (s.get("_shot") and s["_shot"].get("prompt_override")) or "").strip()
        if override_prompt:
            composed = override_prompt
        else:
            composed = compose_gap_prompt(
                shot_query=q,
                world_anchor=world_anchor,
                character_bible=character_bible,
                script_context=s["narration"],
                series_slug=series_slug,
                project_title=title,
                visual_type=visual_type,
                project_brief=project_brief,
                visual_description=s.get("visual_description"),
                shot_position=idx,
                apply_era=apply_era,
            )

        # Remember the prompt on the shot itself. The board shows it, the user
        # goes away and generates the picture, and when they come back Refresh
        # has to still know what this shot asked for — that memory has to
        # outlive the session, so it lives in the script, not in a variable.
        if s.get("_shot") is not None:
            if override_prompt:
                s["_shot"]["prompt"] = override_prompt
                s["_shot"]["prompt_override"] = override_prompt
            elif not s["_shot"].get("prompt"):
                s["_shot"]["prompt"] = composed
            if best_path:
                s["_shot"]["resolved"] = best_path
                s["_shot"]["resolved_score"] = best_score

        rep = {
            "segment_id": s["segment_id"],
            "shot_id": s["shot_id"],
            "query": q,
            "state": state,
            "best_score": best_score,
            "best_path": best_path,
            "alternatives": results[1:] if len(results) > 1 else [],
            "pin_missing": pin_missing,
            "composed_prompt": composed,
            "prompt_override": override_prompt if override_prompt else None,
            "source": s["_shot"].get("source", "library") if s.get("_shot") else "library",
        }
        shot_reports.append(rep)
        resolved_by_id[s["shot_id"]] = rep

    # Alternatives are computed while the board is planned, so a shot could be
    # offered an image that a *later* shot then claims as its own best match.
    # Choosing that alternative handed the image over and silently broke the other
    # shot — fix one, break another, which is exactly what it felt like. Only offer
    # images nothing else is currently using.
    assigned = {r["best_path"] for r in shot_reports if r.get("best_path")}
    for r in shot_reports:
        kept = []
        for alt in r.get("alternatives") or []:
            alt_path = alt[0] if isinstance(alt, (list, tuple)) else alt
            if alt_path not in assigned:
                kept.append(alt)
        r["alternatives"] = kept

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
        "pinned": pinned_count,
        "shot_reports": shot_reports,
        # The board needs this back: plan_shots writes the drafted brief onto a
        # bridge-deserialised copy of project_info, so mutating it there never
        # reaches the UI.
        "project_brief": project_brief,
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

