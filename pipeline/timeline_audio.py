"""
pipeline/timeline_audio.py

Build and cache the single concatenated narration audio file for the timeline.
"""

import json
import os
import subprocess

from pipeline.composer import _find_ffmpeg
from pipeline.narration_timing import probe_seconds


def build_timeline_audio(script_data: dict, project_dir: str) -> dict:
    """
    Concatenate every segment's narration into one mp3 for playback.

    Returns {"path": str, "seconds": float, "offsets": {segment_id: float},
             "segments": int, "rebuilt": bool}
    """
    if not project_dir:
        return {
            "ok": False,
            "error": "No project directory specified.",
            "path": "",
            "seconds": 0.0,
            "offsets": {},
            "segments": 0,
            "skipped": 0,
            "rebuilt": False,
            "measured_sum": 0.0,
            "diff_ms": 0.0,
        }

    os.makedirs(project_dir, exist_ok=True)
    output_mp3 = os.path.join(project_dir, "timeline_narration.mp3")
    cache_json = os.path.join(project_dir, "timeline_narration.json")

    segments = (script_data or {}).get("segments") or []
    measured = []
    skipped_count = 0

    for i, seg in enumerate(segments, 1):
        seg_id = seg.get("segment_id", i)
        path = seg.get("narration_audio")
        if path and os.path.isfile(path):
            secs = seg.get("narration_seconds")
            try:
                secs = float(secs)
            except (TypeError, ValueError):
                secs = None
            if secs is None or secs <= 0:
                secs = probe_seconds(path) or 0.0
            
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                mtime = 0.0
            measured.append((seg_id, path, mtime, secs))
        else:
            skipped_count += 1

    if not measured:
        return {
            "ok": False,
            "error": "No measured narration audio files found.",
            "path": "",
            "seconds": 0.0,
            "offsets": {},
            "segments": 0,
            "skipped": len(segments),
            "rebuilt": False,
            "measured_sum": 0.0,
            "diff_ms": 0.0,
        }

    # Fingerprint includes segment IDs, absolute audio paths, and mtimes
    fingerprint = [
        {
            "segment_id": seg_id,
            "path": os.path.abspath(path),
            "mtime": mtime,
            "seconds": secs,
        }
        for seg_id, path, mtime, secs in measured
    ]

    # Check cache
    if os.path.isfile(output_mp3) and os.path.isfile(cache_json):
        try:
            with open(cache_json, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
            if cache_data.get("fingerprint") == fingerprint:
                result = dict(cache_data.get("result", {}))
                result["rebuilt"] = False
                result["path"] = output_mp3
                # Ensure offsets supports both int and str keys for python callers
                if isinstance(result.get("offsets"), dict):
                    norm_offsets = {}
                    for k, v in result["offsets"].items():
                        try:
                            norm_offsets[int(k)] = v
                        except (ValueError, TypeError):
                            pass
                        norm_offsets[str(k)] = v
                    result["offsets"] = norm_offsets
                return result
        except Exception:
            pass

    # Build concatenated track
    offsets = {}
    running_sum = 0.0
    for seg_id, path, mtime, secs in measured:
        offsets[seg_id] = round(running_sum, 3)
        offsets[str(seg_id)] = round(running_sum, 3)
        running_sum += secs
    measured_sum = round(running_sum, 3)

    concat_list_path = os.path.join(project_dir, "timeline_concat_list.txt")
    try:
        with open(concat_list_path, "w", encoding="utf-8") as f:
            for _, path, _, _ in measured:
                escaped = os.path.abspath(path).replace("\\", "/").replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")

        ffmpeg_bin = _find_ffmpeg()
        cmd = [
            ffmpeg_bin, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_list_path,
            "-c", "copy",
            output_mp3
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0 or not os.path.isfile(output_mp3):
            raise RuntimeError(f"FFmpeg concat failed ({proc.returncode}): {proc.stderr or proc.stdout}")

        probed = probe_seconds(output_mp3)
        if probed is None:
            probed = measured_sum
        probed = round(probed, 3)
        diff_ms = round(abs(probed - measured_sum) * 1000, 2)

        # Fallback to libmp3lame re-encode if stream copy drift exceeds 100 ms
        if diff_ms > 100:
            cmd_reencode = [
                ffmpeg_bin, "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_list_path,
                "-c:a", "libmp3lame",
                "-b:a", "192k",
                output_mp3
            ]
            proc2 = subprocess.run(cmd_reencode, capture_output=True, text=True)
            if proc2.returncode == 0 and os.path.isfile(output_mp3):
                probed2 = probe_seconds(output_mp3)
                if probed2 is not None:
                    probed = round(probed2, 3)
                    diff_ms = round(abs(probed - measured_sum) * 1000, 2)
    finally:
        if os.path.isfile(concat_list_path):
            try:
                os.remove(concat_list_path)
            except OSError:
                pass

    # When saving to cache JSON, keep offsets with string keys so json.dump is standard
    json_offsets = {str(seg_id): offsets[seg_id] for seg_id, _, _, _ in measured}
    result_for_cache = {
        "ok": True,
        "path": output_mp3,
        "seconds": probed,
        "measured_sum": measured_sum,
        "diff_ms": diff_ms,
        "offsets": json_offsets,
        "segments": len(measured),
        "skipped": skipped_count,
        "rebuilt": True,
    }

    try:
        with open(cache_json, "w", encoding="utf-8") as f:
            json.dump({"fingerprint": fingerprint, "result": result_for_cache}, f, indent=2)
    except Exception:
        pass

    result = dict(result_for_cache)
    result["offsets"] = offsets
    return result