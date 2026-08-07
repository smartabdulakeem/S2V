"""Stage 3 — Caption generation using Google TTS timepoints, faster-whisper, or OpenAI Whisper."""

import os
import re
import threading
from pathlib import Path

_WHISPER_MODELS = {}
_FASTER_WHISPER_MODELS = {}
_WHISPER_LOCK = threading.Lock()
_WHISPER_LOAD_COUNT = 0


def _ensure_ffmpeg_on_path():
    """Ensure vendor/ffmpeg directory is in os.environ['PATH'] for whisper subprocess calls."""
    try:
        from pipeline.composer import _find_ffmpeg
        ffmpeg_bin = _find_ffmpeg()
        ffmpeg_dir = os.path.dirname(ffmpeg_bin)
        if ffmpeg_dir and ffmpeg_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
    except Exception:
        pass


def _seconds_to_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _srt_time_to_seconds(time_str: str) -> float:
    h, m, rest = time_str.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def get_whisper_load_count() -> int:
    """Return the total number of times a Whisper model was loaded from disk in this process."""
    global _WHISPER_LOAD_COUNT
    with _WHISPER_LOCK:
        return _WHISPER_LOAD_COUNT


def _get_whisper_model(model_name: str = "base", on_progress=None):
    """
    Get or lazily load a Whisper model singleton (thread-safe).
    Ensures model loads at most once per process across concurrent threads.
    """
    global _WHISPER_MODELS, _WHISPER_LOAD_COUNT
    with _WHISPER_LOCK:
        if model_name in _WHISPER_MODELS:
            return _WHISPER_MODELS[model_name]

        import whisper
        if on_progress:
            on_progress(f"Loading Whisper model '{model_name}' (singleton load #{_WHISPER_LOAD_COUNT + 1})")

        try:
            model = whisper.load_model(model_name)
        except (RuntimeError, MemoryError):
            if on_progress:
                on_progress(f"Not enough memory for '{model_name}' model, falling back to 'tiny'")
            model_name = "tiny"
            if model_name in _WHISPER_MODELS:
                return _WHISPER_MODELS[model_name]
            model = whisper.load_model("tiny")

        _WHISPER_MODELS[model_name] = model
        _WHISPER_LOAD_COUNT += 1
        return model


def create_srt_from_tts_timings(
    words: list[str],
    timepoints: list[dict],
    srt_path: str,
    max_words_per_line: int = 7
) -> str:
    """
    Generate an SRT caption file directly from TTS timepoint marks.
    Requires ZERO Whisper calls!
    """
    if not timepoints or not words:
        return ""

    word_times = []
    for tp in timepoints:
        mark = tp.get("markName") or tp.get("mark_name") or ""
        time_sec = tp.get("timeSeconds") if tp.get("timeSeconds") is not None else tp.get("time_seconds")
        if mark.startswith("w") and time_sec is not None:
            try:
                idx = int(mark[1:])
                word_times.append((idx, float(time_sec)))
            except ValueError:
                pass

    if not word_times:
        return ""

    word_times.sort(key=lambda x: x[0])

    lines = []
    curr_words = []
    curr_start = None

    for i in range(len(word_times)):
        idx, t_start = word_times[i]
        if idx >= len(words):
            continue
        w_text = words[idx]

        if curr_start is None:
            curr_start = t_start

        curr_words.append(w_text)

        if i + 1 < len(word_times):
            t_next = word_times[i + 1][1]
        else:
            t_next = t_start + 0.6

        if len(curr_words) >= max_words_per_line or w_text.endswith((".", "?", "!", ";", ":")):
            lines.append((curr_start, t_next, " ".join(curr_words)))
            curr_words = []
            curr_start = None

    if curr_words and curr_start is not None:
        lines.append((curr_start, curr_start + 0.6, " ".join(curr_words)))

    Path(os.path.dirname(srt_path)).mkdir(parents=True, exist_ok=True)
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, (st, et, text) in enumerate(lines, 1):
            f.write(f"{i}\n{_seconds_to_srt_time(st)} --> {_seconds_to_srt_time(et)}\n{text}\n\n")

    return srt_path


def generate_captions(
    segment_id: int,
    audio_path: str,
    cache_dir: str,
    model_name: str = "base",
    on_progress=None,
) -> str:
    """
    Transcribe audio with faster-whisper or Whisper and write an SRT file.
    Returns path to the SRT file.
    Skips if already cached (e.g., generated directly from Google TTS timepoints).
    """
    srt_path = os.path.join(cache_dir, f"segment_{segment_id}_captions.srt")

    if os.path.exists(srt_path) and os.path.getsize(srt_path) > 0:
        if on_progress:
            on_progress(f"Segment {segment_id} — captions already cached/generated from TTS timings, skipping Whisper")
        return srt_path

    Path(cache_dir).mkdir(parents=True, exist_ok=True)
    _ensure_ffmpeg_on_path()

    # Prefer faster-whisper (CTranslate2) if available
    try:
        from faster_whisper import WhisperModel
        if on_progress:
            on_progress(f"Segment {segment_id} — transcribing audio (faster-whisper {model_name})")
        global _FASTER_WHISPER_MODELS, _WHISPER_LOAD_COUNT
        with _WHISPER_LOCK:
            if model_name not in _FASTER_WHISPER_MODELS:
                _FASTER_WHISPER_MODELS[model_name] = WhisperModel(model_name, device="cpu", compute_type="int8")
                _WHISPER_LOAD_COUNT += 1
            fw_model = _FASTER_WHISPER_MODELS[model_name]

        segments_iter, _ = fw_model.transcribe(audio_path, word_timestamps=False)
        segments = [{"start": seg.start, "end": seg.end, "text": seg.text} for seg in segments_iter]
    except Exception:
        # Fall back to standard OpenAI Whisper
        if on_progress:
            on_progress(f"Segment {segment_id} — transcribing audio (Whisper {model_name})")
        model = _get_whisper_model(model_name, on_progress)
        result = model.transcribe(audio_path, word_timestamps=False)
        segments = result.get("segments", [])

    if not segments:
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
