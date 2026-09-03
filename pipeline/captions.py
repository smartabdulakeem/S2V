"""Stage 3 — Caption generation using Google TTS timepoints or OpenAI Whisper."""

import os
import re
import subprocess
import threading
from pathlib import Path

_WHISPER_MODELS = {}
_WHISPER_LOCK = threading.Lock()
_WHISPER_LOAD_COUNT = 0

# A Whisper model holds mutable decode state, so two threads calling transcribe()
# on the same instance corrupt each other — the failure surfaces as a different
# torch error each run ("cannot reshape tensor of 0 elements", a bare module repr).
# Phase 4 made the model a singleton to stop 52 reloads per render; this serialises
# its use. Transcription is already multi-threaded inside torch, so little is lost.
_TRANSCRIBE_LOCK = threading.Lock()


def _ensure_ffmpeg_on_path():
    """Ensure vendor/ffmpeg directory is in os.environ['PATH'] for whisper subprocess calls."""
    try:
        from pipeline.ffmpeg_locate import find_ffmpeg
        ffmpeg_bin = find_ffmpeg()
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
    max_words_per_line: int = 7,
    audio_path: str = None,
    audio_duration: float = None,
) -> str:
    """
    Generate an SRT caption file directly from TTS timepoint marks.
    Intermediate caption lines end at the next mark. The final caption line's
    end time matches the exact audio duration probed via ffprobe.
    """
    if not timepoints or not words:
        return ""

    if audio_duration is None and audio_path and os.path.exists(audio_path):
        try:
            from pipeline.ffmpeg_locate import find_ffprobe
            ffprobe = find_ffprobe()
            cmd = [ffprobe, "-i", audio_path, "-show_entries", "format=duration", "-v", "quiet", "-of", "csv=p=0"]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                audio_duration = float(res.stdout.strip())
        except Exception:
            pass

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
        elif audio_duration:
            t_next = audio_duration
        else:
            t_next = t_start + 1.5

        if len(curr_words) >= max_words_per_line or w_text.endswith((".", "?", "!", ";", ":")):
            lines.append((curr_start, t_next, " ".join(curr_words)))
            curr_words = []
            curr_start = None

    if curr_words and curr_start is not None:
        last_end = audio_duration if audio_duration else curr_start + 1.5
        lines.append((curr_start, last_end, " ".join(curr_words)))

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
    narration: str = "",
    on_progress=None,
) -> str:
    """
    Transcribe audio with OpenAI Whisper and write an SRT file.
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

    if on_progress:
        on_progress(f"Segment {segment_id} — transcribing audio (Whisper {model_name})")
    model = _get_whisper_model(model_name, on_progress)
    with _TRANSCRIBE_LOCK:
        result = model.transcribe(audio_path, word_timestamps=False)
    segments = result.get("segments", [])

    if not segments:
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,000 --> 00:00:05,000\n \n\n")
        return srt_path

    texts = _redistribute_narration(narration, segments)

    with open(srt_path, "w", encoding="utf-8") as f:
        for i, (seg, text) in enumerate(zip(segments, texts), 1):
            start = _seconds_to_srt_time(seg["start"])
            end = _seconds_to_srt_time(seg["end"])
            f.write(f"{i}\n{start} --> {end}\n{text.strip()}\n\n")

    return srt_path


def _redistribute_narration(narration: str, segments: list) -> list:
    """
    Whisper gives good timings and unreliable words. We already know the exact words,
    so keep its timings and lay the real narration over them, split in proportion to
    how many words it heard in each segment.

    Without this, synthesised speech comes back mis-transcribed and proper nouns are
    the first casualty — "the Caliph Al-Mansur founded" was captioned as "the Kayla
    Falmon surfounded". Names are exactly what a history channel cannot get wrong.

    Falls back to Whisper's own text when no narration is supplied.
    """
    heard = [str(s.get("text", "")).strip() for s in segments]
    if not narration or not narration.strip():
        return heard

    # SSML tags are spoken as nothing — strip them before counting words.
    clean = re.sub(r"<[^>]+>", " ", narration)
    true_words = clean.split()
    if not true_words:
        return heard

    heard_counts = [max(1, len(t.split())) for t in heard]
    total_heard = sum(heard_counts)

    out, cursor = [], 0
    for idx, count in enumerate(heard_counts):
        if idx == len(heard_counts) - 1:
            take = len(true_words) - cursor           # last segment absorbs the remainder
        else:
            take = round(len(true_words) * count / total_heard)
            take = max(1, min(take, len(true_words) - cursor - (len(heard_counts) - idx - 1)))
        out.append(" ".join(true_words[cursor:cursor + take]))
        cursor += take

    return out


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
