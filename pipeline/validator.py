"""
Stage 1 — JSON schema validation & loader.
Implements S2V Script Schema v2 specification (SCHEMA.md).
Produces human-readable errors, naming exact paths.
Upconverts v1 scripts in memory without modifying files on disk.
"""

import copy
import json
import os
import re
import sys
from pathlib import Path

# Enums from SCHEMA.md
ALLOWED_ASPECT_RATIOS = {"16:9", "9:16", "1:1", "4:3"}
ALLOWED_CAPTIONS_SOURCES = {"tts_timings", "whisper", "none"}
ALLOWED_SEGMENT_TYPES = {"hook", "body", "conclusion", "transition"}
ALLOWED_TRANSITIONS = {"cut", "fade", "crossfade"}
ALLOWED_TEXT_POSITIONS = {
    "top_left", "top_center", "top_right",
    "bottom_left", "bottom_center", "bottom_right",
    "center"
}
ALLOWED_SHOT_SOURCES = {"library", "generate", "pin"}
ALLOWED_MOTION_KINDS = {"ken_burns", "static", "generative"}
ALLOWED_MOTION_EFFECTS = {"zoom_in", "zoom_out", "pan_left", "pan_right"}
ALLOWED_TREATMENT_FILTERS = {"none", "vignette", "vox_collage", "diptych", "collage", "documentary", "illustration", "silhouette"}
ALLOWED_VISUAL_TYPES = {"stock_photo", "stock_video", "map", "text_card", "ai_image"}


def load_and_upconvert(script_data: dict) -> dict:
    """
    Upconvert v1 scripts to v2 in memory.
    Never modifies files on disk.
    """
    script = copy.deepcopy(script_data)
    if "project" not in script or not isinstance(script["project"], dict):
        return script

    proj = script["project"]

    # Upconvert disable_captions flag
    disable_captions = proj.get("disable_captions", False)
    if "captions" not in proj or not isinstance(proj["captions"], dict):
        proj["captions"] = {"enabled": not disable_captions, "source": "tts_timings"}
    elif disable_captions:
        proj["captions"]["enabled"] = False

    # Apply project defaults
    if "aspect_ratio" not in proj:
        proj["aspect_ratio"] = "16:9"
    if "fps" not in proj:
        proj["fps"] = 30
    if "voice_rate" not in proj:
        proj["voice_rate"] = "+0%"
    if "voice_pitch" not in proj:
        proj["voice_pitch"] = "+0Hz"
    if "background_music" not in proj:
        proj["background_music"] = None
    if "music_volume_db" not in proj:
        proj["music_volume_db"] = -20
    if "character_bible" not in proj:
        proj["character_bible"] = {}
    if "budget" not in proj or not isinstance(proj["budget"], dict):
        proj["budget"] = {"max_generated_clips": 0, "max_spend_usd": 0}

    # Resolution default based on aspect ratio
    if "resolution" not in proj:
        ratio = proj.get("aspect_ratio", "16:9")
        res_map = {"16:9": "1280x720", "9:16": "720x1280", "1:1": "1080x1080", "4:3": "960x720"}
        proj["resolution"] = res_map.get(ratio, "1280x720")

    if "segments" not in script or not isinstance(script["segments"], list):
        return script

    for i, seg in enumerate(script["segments"]):
        if not isinstance(seg, dict):
            continue

        seg_id = seg.get("segment_id", i + 1)

        # Check if segment has v1 format (no 'shots' array) needing upconversion
        is_v1_segment = "shots" not in seg or seg.get("shots") is None

        if is_v1_segment:
            # Construct a single v2 shot from v1 segment fields
            use_base_image = seg.get("use_base_image")
            b_roll = seg.get("b_roll_keyword", "")

            if use_base_image:
                source = "pin"
                pin_path = str(use_base_image)
            else:
                source = "library"
                pin_path = None

            kb = seg.get("ken_burns", "zoom_in")
            if kb in ALLOWED_MOTION_EFFECTS:
                motion = {"kind": "ken_burns", "effect": kb}
            elif kb == "none":
                motion = {"kind": "static"}
            elif isinstance(seg.get("motion"), dict):
                motion = seg["motion"]
            else:
                motion = {"kind": "ken_burns", "effect": "zoom_in"}

            magick_filter = seg.get("magick_filter", "vignette")
            treatment = {
                "filter": magick_filter if magick_filter in ALLOWED_TREATMENT_FILTERS else "vignette",
                "grade": None
            }

            shot_0 = {
                "shot_id": f"{seg_id}a",
                "duration": None,
                "source": source,
                "query": b_roll,
                "pin": pin_path,
                "min_score": 0.26,
                "motion": motion,
                "treatment": treatment
            }

            if "crop" in seg:
                shot_0["crop"] = seg["crop"]
            if "level1_overlay" in seg:
                shot_0["level1_overlay"] = seg["level1_overlay"]

            seg["shots"] = [shot_0]
        else:
            # Ensure v2 shot defaults
            for j, shot in enumerate(seg["shots"]):
                if not isinstance(shot, dict):
                    continue
                if "shot_id" not in shot:
                    shot["shot_id"] = f"{seg_id}{chr(97 + j)}"
                if "duration" not in shot:
                    shot["duration"] = None
                if "source" not in shot:
                    shot["source"] = "library"
                if "min_score" not in shot:
                    shot["min_score"] = 0.26
                if "motion" not in shot or not isinstance(shot["motion"], dict):
                    shot["motion"] = {"kind": "ken_burns", "effect": "zoom_in"}
                if "treatment" not in shot or not isinstance(shot["treatment"], dict):
                    shot["treatment"] = {"filter": "vignette", "grade": None}

    return script


def resolve_shot_durations(shots: list[dict], total_segment_duration: float) -> list[float]:
    """
    Given a list of shots and the segment's narration duration, compute each shot's resolved_duration.
    1. Sum explicit duration values.
    2. Split the remainder evenly across shots with duration: null.
    3. If explicit durations exceed the audio, scale them all down proportionally and warn.
    4. A segment whose shots are all explicit and all short leaves a gap — the last shot stretches to cover it.
    """
    if not shots:
        return []

    explicit_shots = [s for s in shots if s.get("duration") is not None]
    null_shots = [s for s in shots if s.get("duration") is None]

    explicit_sum = sum(float(s["duration"]) for s in explicit_shots)
    resolved = [0.0] * len(shots)

    if null_shots:
        remainder = total_segment_duration - explicit_sum
        if remainder > 0:
            each_null = remainder / len(null_shots)
            for i, s in enumerate(shots):
                if s.get("duration") is None:
                    resolved[i] = round(each_null, 3)
                else:
                    resolved[i] = float(s["duration"])
        else:
            scale = total_segment_duration / explicit_sum if explicit_sum > 0 else 1.0
            for i, s in enumerate(shots):
                if s.get("duration") is None:
                    resolved[i] = 0.0
                else:
                    resolved[i] = round(float(s["duration"]) * scale, 3)
    else:
        if explicit_sum > total_segment_duration:
            scale = total_segment_duration / explicit_sum
            for i, s in enumerate(shots):
                resolved[i] = round(float(s["duration"]) * scale, 3)
        elif explicit_sum < total_segment_duration:
            for i, s in enumerate(shots):
                resolved[i] = float(s["duration"])
            gap = total_segment_duration - explicit_sum
            resolved[-1] = round(resolved[-1] + gap, 3)
        else:
            for i, s in enumerate(shots):
                resolved[i] = float(s["duration"])

    return resolved


def validate(script_data: dict) -> list[str]:
    """
    Return a list of human-readable error strings. Empty list means valid.
    Names exact paths for all validation errors.
    """
    errors = []
    if not isinstance(script_data, dict):
        return ["script: root of JSON script must be an object/dict"]

    if "project" not in script_data or not isinstance(script_data["project"], dict):
        return ['project: required top-level object "project" is missing']

    # Upconvert in memory for validation check
    script = load_and_upconvert(script_data)
    proj = script["project"]

    # ── project block ──────────────────────────────────────────────────────────
    if "title" not in proj or not isinstance(proj["title"], str) or not proj["title"].strip():
        errors.append("project.title: required non-empty string is missing")

    if "output_filename" not in proj or not isinstance(proj["output_filename"], str) or not proj["output_filename"].strip():
        errors.append("project.output_filename: required string is missing")
    elif not proj["output_filename"].endswith(".mp4"):
        errors.append('project.output_filename: must end with ".mp4"')

    if "voice" not in proj or not isinstance(proj["voice"], str) or not proj["voice"].strip():
        errors.append("project.voice: required string is missing")

    if "aspect_ratio" in proj and proj["aspect_ratio"] not in ALLOWED_ASPECT_RATIOS:
        errors.append(f'project.aspect_ratio: "{proj["aspect_ratio"]}" is not valid.\n  Expected one of: {", ".join(sorted(ALLOWED_ASPECT_RATIOS))}.')

    if "fps" in proj and (not isinstance(proj["fps"], int) or proj["fps"] <= 0):
        errors.append("project.fps: must be an integer > 0")

    if "captions" in proj and isinstance(proj["captions"], dict):
        cap = proj["captions"]
        if "enabled" in cap and not isinstance(cap["enabled"], bool):
            errors.append("project.captions.enabled: must be a boolean")
        if "source" in cap and cap["source"] not in ALLOWED_CAPTIONS_SOURCES:
            errors.append(f'project.captions.source: "{cap["source"]}" is not valid.\n  Expected one of: {", ".join(sorted(ALLOWED_CAPTIONS_SOURCES))}.')

    if "background_music" in proj and proj["background_music"] is not None:
        bm = proj["background_music"]
        if not isinstance(bm, str):
            errors.append("project.background_music: must be a file path string or null")
        elif not Path(bm).exists():
            errors.append(f'project.background_music: file not found: "{bm}"')

    if "music_volume_db" in proj and not isinstance(proj["music_volume_db"], (int, float)):
        errors.append("project.music_volume_db: must be a number")

    if "character_bible" in proj and not isinstance(proj["character_bible"], dict):
        errors.append("project.character_bible: must be an object mapping names to descriptions")

    if "series_slug" in proj and proj["series_slug"] is not None:
        slug_val = proj["series_slug"]
        if not isinstance(slug_val, str):
            errors.append("project.series_slug: must be a string")
        elif slug_val.strip():
            slug_clean = slug_val.strip().lower().replace("-", "_")
            series_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "series")
            slug_file = os.path.join(series_dir, f"{slug_clean}.json")
            if not os.path.exists(slug_file):
                available = []
                if os.path.exists(series_dir):
                    available = sorted([p.stem for p in Path(series_dir).glob("*.json")])
                errors.append(f'project.series_slug: "{slug_val}" is not a known series pack. Available packs: {", ".join(available)}.')

    max_clips = 0
    max_spend = 0.0
    if "budget" in proj and isinstance(proj["budget"], dict):
        b = proj["budget"]
        max_clips = b.get("max_generated_clips", 0)
        max_spend = b.get("max_spend_usd", 0.0)
        if not isinstance(max_clips, int) or max_clips < 0:
            errors.append("project.budget.max_generated_clips: must be an integer >= 0")
        if not isinstance(max_spend, (int, float)) or max_spend < 0:
            errors.append("project.budget.max_spend_usd: must be a number >= 0")

    # ── segments array ─────────────────────────────────────────────────────────
    if "segments" not in script or not isinstance(script["segments"], list):
        return ['segments: required top-level array "segments" is missing']

    segs = script["segments"]
    if len(segs) == 0:
        errors.append("segments: array must contain at least 1 segment")
        return errors

    seen_segment_ids = set()
    for i, seg in enumerate(segs):
        prefix = f"segments[{i}]"
        if not isinstance(seg, dict):
            errors.append(f"{prefix}: segment must be an object")
            continue

        # Rule 1: segment_id unique and >= 1
        seg_id = seg.get("segment_id")
        if not isinstance(seg_id, int):
            errors.append(f"{prefix}.segment_id: must be an integer >= 1")
        elif seg_id < 1:
            errors.append(f"{prefix}.segment_id: must be >= 1 (got {seg_id})")
        elif seg_id in seen_segment_ids:
            errors.append(f"{prefix}.segment_id: duplicate id {seg_id}")
        else:
            seen_segment_ids.add(seg_id)

        if "type" in seg and seg["type"] not in ALLOWED_SEGMENT_TYPES:
            errors.append(f'{prefix}.type: "{seg["type"]}" is not valid.\n  Expected one of: {", ".join(sorted(ALLOWED_SEGMENT_TYPES))}.')

        narration = seg.get("narration")
        if not isinstance(narration, str) or not narration.strip():
            errors.append(f"{prefix}.narration: must be a non-empty string")

        if "transition_in" in seg and seg["transition_in"] not in ALLOWED_TRANSITIONS:
            errors.append(f'{prefix}.transition_in: "{seg["transition_in"]}" is not valid.\n  Expected one of: {", ".join(sorted(ALLOWED_TRANSITIONS))}.')
        if "transition_out" in seg and seg["transition_out"] not in ALLOWED_TRANSITIONS:
            errors.append(f'{prefix}.transition_out: "{seg["transition_out"]}" is not valid.\n  Expected one of: {", ".join(sorted(ALLOWED_TRANSITIONS))}.')

        if "text_overlay" in seg and seg["text_overlay"] is not None:
            ov = seg["text_overlay"]
            if not isinstance(ov, dict):
                errors.append(f"{prefix}.text_overlay: must be an object or null")
            else:
                if not isinstance(ov.get("text"), str) or not ov["text"].strip():
                    errors.append(f"{prefix}.text_overlay.text: must be a non-empty string")
                if "position" in ov and ov["position"] not in ALLOWED_TEXT_POSITIONS:
                    errors.append(f'{prefix}.text_overlay.position: "{ov["position"]}" is not valid.\n  Expected one of: {", ".join(sorted(ALLOWED_TEXT_POSITIONS))}.')
                if "start" in ov and not isinstance(ov["start"], (int, float)):
                    errors.append(f"{prefix}.text_overlay.start: must be a number")
                if "duration_seconds" in ov and not isinstance(ov["duration_seconds"], (int, float)):
                    errors.append(f"{prefix}.text_overlay.duration_seconds: must be a number")

        if "sfx" in seg and seg["sfx"] is not None:
            if not isinstance(seg["sfx"], list):
                errors.append(f"{prefix}.sfx: must be an array")
            else:
                for k, sfx_item in enumerate(seg["sfx"]):
                    if not isinstance(sfx_item, dict):
                        errors.append(f"{prefix}.sfx[{k}]: must be an object")
                    else:
                        if "name" not in sfx_item or not isinstance(sfx_item["name"], str):
                            errors.append(f"{prefix}.sfx[{k}].name: must be a string")
                        if "offset_ms" in sfx_item and not isinstance(sfx_item["offset_ms"], (int, float)):
                            errors.append(f"{prefix}.sfx[{k}].offset_ms: must be a number")
                        if "gain_db" in sfx_item and not isinstance(sfx_item["gain_db"], (int, float)):
                            errors.append(f"{prefix}.sfx[{k}].gain_db: must be a number")

        if "magick_filter" in seg and seg["magick_filter"] not in ALLOWED_TREATMENT_FILTERS:
            errors.append(f'{prefix}.magick_filter: "{seg["magick_filter"]}" is not valid.\n  Expected one of: {", ".join(sorted(ALLOWED_TREATMENT_FILTERS))}.')

        # Rule 2: every segment has >= 1 shot; shot_id unique within segment
        shots = seg.get("shots")
        if not isinstance(shots, list) or len(shots) == 0:
            errors.append(f"{prefix}: segment must contain at least 1 shot in shots array")
            continue

        seen_shot_ids = set()
        for j, shot in enumerate(shots):
            shot_prefix = f"{prefix}.shots[{j}]"
            if not isinstance(shot, dict):
                errors.append(f"{shot_prefix}: shot must be an object")
                continue

            shot_id = shot.get("shot_id")
            if shot_id:
                if shot_id in seen_shot_ids:
                    errors.append(f"{shot_prefix}.shot_id: duplicate shot_id '{shot_id}' in segment")
                seen_shot_ids.add(shot_id)

            # Rule 5: explicit duration > 0
            dur = shot.get("duration")
            if dur is not None:
                if not isinstance(dur, (int, float)) or dur <= 0:
                    errors.append(f"{shot_prefix}.duration: explicit duration must be > 0 (got {dur})")

            source = shot.get("source", "library")
            if source not in ALLOWED_SHOT_SOURCES:
                errors.append(f'{shot_prefix}.source: "{source}" is not valid.\n  Expected one of: {", ".join(sorted(ALLOWED_SHOT_SOURCES))}.')

            # Rule 3: source: pin requires pin, file must exist
            if source == "pin":
                pin_val = shot.get("pin")
                if not pin_val or not isinstance(pin_val, str) or not pin_val.strip():
                    errors.append(f'{shot_prefix}: source is "pin" but no pin path was given.')
                else:
                    # Rule 8: pin paths must stay inside the project — no absolute paths, no ..
                    clean_pin = pin_val.replace("\\", "/")
                    if os.path.isabs(pin_val) or clean_pin.startswith("/") or re.search(r'^[a-zA-Z]:', clean_pin):
                        errors.append(f'{shot_prefix}.pin: path must stay inside the project (absolute path "{pin_val}" is not allowed).')
                    elif ".." in Path(pin_val).parts or ".." in clean_pin.split("/"):
                        errors.append(f'{shot_prefix}.pin: path must stay inside the project (path traversal ".." in "{pin_val}" is not allowed).')

            # Rule 4: source: library or generate requires a non-empty query
            if source in ("library", "generate"):
                query_val = shot.get("query")
                if not isinstance(query_val, str) or not query_val.strip():
                    errors.append(f'{shot_prefix}.query: source is "{source}" but no non-empty query was given.')

            # Motion validation
            motion = shot.get("motion")
            if not isinstance(motion, dict):
                errors.append(f"{shot_prefix}.motion: must be an object")
            else:
                m_kind = motion.get("kind", "ken_burns")
                if m_kind not in ALLOWED_MOTION_KINDS:
                    errors.append(f'{shot_prefix}.motion.kind: "{m_kind}" is not valid.\n  Expected one of: {", ".join(sorted(ALLOWED_MOTION_KINDS))}.')

                elif m_kind == "ken_burns":
                    m_effect = motion.get("effect", "zoom_in")
                    if m_effect not in ALLOWED_MOTION_EFFECTS:
                        errors.append(f'{shot_prefix}.motion.effect: "{m_effect}" is not valid.\n  Expected one of: {", ".join(sorted(ALLOWED_MOTION_EFFECTS))}.')

                elif m_kind == "generative":
                    # Rule 6: motion.seconds between 1 and 10
                    m_sec = motion.get("seconds", 5)
                    if not isinstance(m_sec, (int, float)) or m_sec < 1 or m_sec > 10:
                        errors.append(f"{shot_prefix}.motion.seconds: must be between 1 and 10 (got {m_sec})")

                    # Rule 7: generative motion requires budget > 0
                    if max_clips <= 0 and max_spend <= 0:
                        errors.append(f"project.budget.max_spend_usd is 0 but {shot_prefix} requests generative motion.\n  Raise the budget or change motion.kind.")

            # Treatment validation
            treatment = shot.get("treatment")
            if treatment is not None and isinstance(treatment, dict):
                t_filter = treatment.get("filter")
                if t_filter and t_filter not in ALLOWED_TREATMENT_FILTERS:
                    errors.append(f'{shot_prefix}.treatment.filter: "{t_filter}" is not valid.\n  Expected one of: {", ".join(sorted(ALLOWED_TREATMENT_FILTERS))}.')

    return errors


def validate_file(json_path: str) -> tuple[dict | None, list[str]]:
    """Load and validate a JSON file. Returns (upconverted_script, errors)."""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            script_data = json.load(f)
    except FileNotFoundError:
        return None, [f'file not found: "{json_path}"']
    except json.JSONDecodeError as e:
        return None, [f'invalid JSON syntax: {e}']

    errors = validate(script_data)
    upconverted = load_and_upconvert(script_data) if not errors else None
    return upconverted, errors


# Aliases
validate_script = validate


def estimate_duration(script: dict) -> float:
    """Rough estimate: 15 characters per second of narration."""
    total_chars = sum(len(s.get("narration", "")) for s in script.get("segments", []))
    return round(total_chars / 15, 1)


if __name__ == "__main__":
    import io
    try:
        if sys.stdout and sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

    if len(sys.argv) < 2:
        print("Usage: python validator.py <script.json>")
        sys.exit(1)

    path = sys.argv[1]
    script, errors = validate_file(path)
    if errors:
        print(f"\n❌ Validation failed for: {path}\n")
        for e in errors:
            print(f"  • {e}")
        sys.exit(1)
    else:
        est = estimate_duration(script)
        print(f"\n✅ Validation passed — {len(script['segments'])} segments, ~{est}s estimated")
        sys.exit(0)
