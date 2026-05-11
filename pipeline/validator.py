"""Stage 1 — JSON schema validation. Produces human-readable errors, no stack traces."""

import json
import sys
from pathlib import Path

ALLOWED_KEN_BURNS = {"zoom_in", "zoom_out", "pan_left", "pan_right", "none"}
ALLOWED_TRANSITIONS = {"fade", "cut", "crossfade"}
ALLOWED_VISUAL_TYPES = {"stock_photo", "stock_video", "map", "text_card", "ai_image"}
ALLOWED_OVERLAY_POSITIONS = {
    "top_left", "top_center", "top_right",
    "bottom_left", "bottom_center", "bottom_right",
    "center"
}
ALLOWED_SEGMENT_TYPES = {"hook", "body", "transition", "conclusion"}


def _err(field: str, message: str) -> str:
    return f'  • Field "{field}": {message}'


def validate(script: dict) -> list[str]:
    """Return a list of error strings. Empty list means valid."""
    errors = []

    # ── project block ──────────────────────────────────────────────────────────
    if "project" not in script:
        errors.append('  • Missing required top-level key "project"')
        return errors

    proj = script["project"]
    required_project_fields = ["title", "output_filename", "voice", "voice_rate", "voice_pitch"]
    for field in required_project_fields:
        if field not in proj:
            errors.append(_err(f"project.{field}", "required field is missing"))

    if "output_filename" in proj:
        if not isinstance(proj["output_filename"], str) or not proj["output_filename"].endswith(".mp4"):
            errors.append(_err("project.output_filename", 'must be a string ending with ".mp4"'))

    if "background_music" in proj and proj["background_music"] is not None:
        bm = proj["background_music"]
        if not isinstance(bm, str):
            errors.append(_err("project.background_music", "must be a file path string or null"))
        elif not Path(bm).exists():
            errors.append(_err("project.background_music", f'file not found: "{bm}"'))

    if "music_volume_db" in proj and not isinstance(proj.get("music_volume_db"), (int, float)):
        errors.append(_err("project.music_volume_db", "must be a number (e.g. -20)"))

    # ── segments array ─────────────────────────────────────────────────────────
    if "segments" not in script:
        errors.append('  • Missing required top-level key "segments"')
        return errors

    segs = script["segments"]
    if not isinstance(segs, list) or len(segs) == 0:
        errors.append('  • "segments" must be a non-empty array')
        return errors

    seen_ids = []
    for i, seg in enumerate(segs):
        prefix = f"segments[{i}]"

        seg_id = seg.get("segment_id")
        if not isinstance(seg_id, int):
            errors.append(_err(f"{prefix}.segment_id", "must be an integer"))
        else:
            if seg_id in seen_ids:
                errors.append(_err(f"{prefix}.segment_id", f"duplicate id {seg_id}"))
            seen_ids.append(seg_id)

        if "type" in seg and seg["type"] not in ALLOWED_SEGMENT_TYPES:
            errors.append(_err(f"{prefix}.type",
                               f'"{seg["type"]}" is not valid. Use: {sorted(ALLOWED_SEGMENT_TYPES)}'))

        narration = seg.get("narration")
        if not isinstance(narration, str) or not narration.strip():
            errors.append(_err(f"{prefix}.narration", "must be a non-empty string"))

        b_roll = seg.get("b_roll_keyword")
        if not isinstance(b_roll, str) or not b_roll.strip():
            errors.append(_err(f"{prefix}.b_roll_keyword", "must be a non-empty string"))

        visual_type = seg.get("visual_type")
        if visual_type not in ALLOWED_VISUAL_TYPES:
            errors.append(_err(f"{prefix}.visual_type",
                               f'"{visual_type}" is not valid. Use: {sorted(ALLOWED_VISUAL_TYPES)}'))

        ken_burns = seg.get("ken_burns")
        if ken_burns not in ALLOWED_KEN_BURNS:
            errors.append(_err(f"{prefix}.ken_burns",
                               f'"{ken_burns}" is not valid. Use: {sorted(ALLOWED_KEN_BURNS)}'))

        transition_in = seg.get("transition_in")
        if transition_in not in ALLOWED_TRANSITIONS:
            errors.append(_err(f"{prefix}.transition_in",
                               f'"{transition_in}" is not valid. Use: {sorted(ALLOWED_TRANSITIONS)}'))

        transition_out = seg.get("transition_out")
        if transition_out not in ALLOWED_TRANSITIONS:
            errors.append(_err(f"{prefix}.transition_out",
                               f'"{transition_out}" is not valid. Use: {sorted(ALLOWED_TRANSITIONS)}'))

        overlay = seg.get("text_overlay")
        if overlay is not None:
            if not isinstance(overlay, dict):
                errors.append(_err(f"{prefix}.text_overlay", "must be an object or null"))
            else:
                if not isinstance(overlay.get("text"), str) or not overlay["text"].strip():
                    errors.append(_err(f"{prefix}.text_overlay.text", "must be a non-empty string"))
                if overlay.get("position") not in ALLOWED_OVERLAY_POSITIONS:
                    errors.append(_err(f"{prefix}.text_overlay.position",
                                       f'"{overlay.get("position")}" is not valid. Use: {sorted(ALLOWED_OVERLAY_POSITIONS)}'))
                if not isinstance(overlay.get("duration_seconds"), (int, float)):
                    errors.append(_err(f"{prefix}.text_overlay.duration_seconds", "must be a number"))

    # ── sequential IDs check ───────────────────────────────────────────────────
    if seen_ids and sorted(seen_ids) != list(range(1, len(seen_ids) + 1)):
        errors.append(
            f'  • segment_ids must be sequential starting at 1. Found: {sorted(seen_ids)}'
        )

    return errors


def validate_file(json_path: str) -> tuple[dict | None, list[str]]:
    """Load and validate a JSON file. Returns (script_dict, errors)."""
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            script = json.load(f)
    except FileNotFoundError:
        return None, [f'  • File not found: "{json_path}"']
    except json.JSONDecodeError as e:
        return None, [f'  • Invalid JSON syntax: {e}']

    errors = validate(script)
    return (script if not errors else None), errors


# Alias so app.py can import either name
validate_script = validate


def estimate_duration(script: dict) -> float:
    """Rough estimate: 15 characters per second of narration."""
    total_chars = sum(len(s.get("narration", "")) for s in script.get("segments", []))
    return round(total_chars / 15, 1)


if __name__ == "__main__":
    # Fix Windows console to print UTF-8 emoji correctly
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
            print(e)
        sys.exit(1)
    else:
        est = estimate_duration(script)
        print(f"\n✅ Validation passed — {len(script['segments'])} segments, ~{est}s estimated")
        sys.exit(0)
