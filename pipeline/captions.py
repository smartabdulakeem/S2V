"""Stage 3 — Caption generation using OpenAI Whisper (local, offline, free)."""

import os
import re
from pathlib import Path


def _seconds_to_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def generate_captions(
    segment_id: int,
    audio_path: str,
    cache_dir: str,
    model_name: str = "base",
    on_progress=None,
) -> str:
    """
    Transcribe audio with Whisper and write an SRT file.
    Returns path to the SRT file.
    Skips if already cached.
    """
    srt_path = os.path.join(cache_dir, f"segment_{segment_id}_captions.srt")

    if os.path.exists(srt_path) and os.path.getsize(srt_path) > 0:
        if on_progress:
            on_progress(f"Segment {segment_id} — captions already cached, skipping")
        return srt_path

    if on_progress:
        on_progress(f"Segment {segment_id} — transcribing audio (Whisper {model_name})")

    Path(cache_dir).mkdir(parents=True, exist_ok=True)

    import whisper

    try:
        model = whisper.load_model(model_name)
    except (RuntimeError, MemoryError):
        if on_progress:
            on_progress(f"Segment {segment_id} — not enough memory for '{model_name}' model, falling back to 'tiny'")
        model = whisper.load_model("tiny")

    result = model.transcribe(audio_path, word_timestamps=False)

    segments = result.get("segments", [])
    if not segments:
        # Whisper returned nothing — write a single caption covering the full narration
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,000 --> 00:00:05,000\n \n\n")
        return srt_path

    with open(srt_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, 1):
            start = _seconds_to_srt_time(seg["start"])
            end = _seconds_to_srt_time(seg["end"])
            text = seg["text"].strip()
            f.write(f"{i}\n{start} --> {end}\n{text}\n\n")

    return srt_path


def parse_srt(srt_path: str) -> list[tuple[float, float, str]]:
    """
    Parse an SRT file into a list of (start_sec, end_sec, text) tuples.
    Used by composer.py to overlay captions on video frames.
    """
    entries = []
    if not os.path.exists(srt_path):
        return entries

    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()

    # SRT block pattern: index, timestamps, text
    pattern = re.compile(
        r"\d+\n"
        r"(\d{2}:\d{2}:\d{2},\d{3})\s-->\s(\d{2}:\d{2}:\d{2},\d{3})\n"
        r"([\s\S]*?)(?=\n\n|\Z)",
        re.MULTILINE
    )

    for match in pattern.finditer(content):
        start_str, end_str, text = match.groups()
        entries.append((_srt_time_to_seconds(start_str), _srt_time_to_seconds(end_str), text.strip()))

    return entries


def _srt_time_to_seconds(time_str: str) -> float:
    h, m, rest = time_str.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000
