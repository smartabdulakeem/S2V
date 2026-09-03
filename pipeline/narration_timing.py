"""
pipeline/narration_timing.py

How long each line of narration actually takes to say.

Planning guessed from a word count. That average is fine across a film and
wrong on every individual line, and picture boundaries placed on a guess drift
from the audio the viewer hears. The narration is generated anyway, so the
real number is one ffprobe away.
"""

import os
import subprocess
import sys

from pipeline.text_parser import WORDS_PER_SECOND
from pipeline.voiceover import generate_voiceover


def estimated_seconds(narration: str) -> float:
    """The word-count stand-in, used until the audio exists."""
    words = len((narration or "").split())
    return round(words / WORDS_PER_SECOND, 3) if words else 0.0


def segment_seconds(script_data: dict) -> list:
    """
    Seconds per segment, in script order.

    Measured where a timing pass has run, estimated everywhere else, so a
    half-finished pass degrades to the old behaviour rather than to zeros.
    """
    out = []
    for seg in (script_data.get("segments") or []):
        measured = seg.get("narration_seconds")
        try:
            measured = float(measured)
        except (TypeError, ValueError):
            measured = None
        if measured and measured > 0:
            out.append(measured)
        else:
            out.append(estimated_seconds(seg.get("narration") or ""))
    return out


def probe_seconds(path: str):
    """Length of an audio file in seconds, or None if it cannot be read."""
    if not path or not os.path.exists(path):
        return None
    try:
        from pipeline.ffmpeg_locate import find_ffprobe
        cmd = [find_ffprobe(), "-i", path, "-show_entries", "format=duration",
               "-v", "quiet", "-of", "csv=p=0"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        value = float(res.stdout.strip())
        return value if value > 0 else None
    except Exception:
        return None


def measure_narration(script_data: dict, cache_dir: str, google_api_key: str = "",
                      on_progress=None) -> dict:
    """
    Render each segment's narration and record how long it really takes.

    Returns {"measured": int, "failed": int, "seconds": float}.

    A segment that cannot be rendered or probed is left without
    `narration_seconds` rather than being written as zero: `segment_seconds`
    falls back to the word estimate for it, and a zero would collapse the
    boundary maths around that line.
    """
    project = script_data.get("project") or {}
    voice = project.get("voice") or ""
    segments = script_data.get("segments") or []

    measured = failed = 0
    total = 0.0

    for i, seg in enumerate(segments, 1):
        narration = (seg.get("narration") or "").strip()
        if not narration:
            seg["narration_seconds"] = 0.0
            continue

        seg_id = seg.get("segment_id", i)
        if on_progress:
            on_progress(f"Timing segment {i} of {len(segments)}")

        try:
            path = generate_voiceover(
                segment_id=seg_id,
                narration=narration,
                voice=voice,
                voice_rate=project.get("voice_rate", "+0%"),
                voice_pitch=project.get("voice_pitch", "+0Hz"),
                cache_dir=cache_dir,
                google_api_key=google_api_key,
                voice_steering=seg.get("voice_steering", "") or "",
                narrative_tone=project.get("narrative_tone", "") or "",
            )
        except Exception as err:
            sys.stderr.write(f"[narration_timing] segment {seg_id}: {err}\n")
            failed += 1
            continue

        # Kept whether or not the probe succeeds: WolfCut export needs the path
        # and the duration separately, and a readable file with an unreadable
        # duration is still a clip it can lay on the narration track.
        seg["narration_audio"] = path

        seconds = probe_seconds(path)
        if seconds is None:
            failed += 1
            continue

        seg["narration_seconds"] = round(seconds, 3)
        total += seconds
        measured += 1

    return {"measured": measured, "failed": failed, "seconds": round(total, 3)}


def timing_maps(script_data: dict) -> tuple:
    """
    `(audio_paths_map, durations_map)` keyed by segment_id.

    Exactly the two arguments `write_wolfcut_project` takes. It measures
    nothing itself, so these maps are the only thing standing between a script
    and a WolfCut timeline — and building them here means that timeline no
    longer requires a rendered video.
    """
    audio_paths, durations = {}, {}
    seconds = segment_seconds(script_data)
    for i, seg in enumerate(script_data.get("segments") or []):
        seg_id = seg.get("segment_id", i + 1)
        durations[seg_id] = seconds[i] if i < len(seconds) else 0.0
        path = seg.get("narration_audio")
        if path:
            audio_paths[seg_id] = path
    return audio_paths, durations