"""
Stage 2 — Voiceover generation.

Engine routing (based on voice ID prefix):
  "gemini:<Name>"   → Gemini 2.5 Flash TTS — natural, human-sounding
  "piper:<Name>"    → Piper TTS — offline, free, no internet needed
  anything else     → edge-tts — free, 400+ voices, reliable fallback

Gemini voices:
  gemini:Charon       informative, authoritative  ← best for documentary
  gemini:Sadaltager   knowledgeable, measured
  gemini:Rasalgethi   informative, clear
  gemini:Orus         firm, confident
  gemini:Algieba      smooth, professional
  gemini:Sulafat      warm (female)
  gemini:Aoede        clear (female)
  gemini:Kore         firm (female)

Piper voices (must be downloaded via setup.bat first):
  piper:en_US-ryan-high    US male, high quality
  piper:en_GB-alan-medium  British male
"""

import asyncio
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

GEMINI_TTS_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash-preview-tts:generateContent?key={key}"
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_base_dir() -> str:
    """Return the S2V root directory — works in both dev and PyInstaller builds."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    # voiceover.py lives in pipeline/, so go up one level
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _find_ffmpeg() -> str:
    env_path = os.environ.get("IMAGEIO_FFMPEG_EXE", "")
    if env_path and os.path.exists(env_path):
        return env_path
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise RuntimeError("FFmpeg not found. Please run setup.bat first.")


def _pcm_to_mp3(pcm_bytes: bytes, sample_rate: int, output_path: str):
    """Convert raw 16-bit mono PCM to MP3 via FFmpeg."""
    ffmpeg = _find_ffmpeg()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = tmp.name
    try:
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)
        subprocess.run(
            [ffmpeg, "-y", "-i", wav_path,
             "-codec:a", "libmp3lame", "-q:a", "2", output_path],
            check=True, capture_output=True,
        )
    finally:
        try:
            os.unlink(wav_path)
        except OSError:
            pass


def _wav_to_mp3(wav_path: str, output_path: str):
    """Convert WAV to MP3 via FFmpeg."""
    ffmpeg = _find_ffmpeg()
    subprocess.run(
        [ffmpeg, "-y", "-i", wav_path,
         "-codec:a", "libmp3lame", "-q:a", "2", output_path],
        check=True, capture_output=True,
    )


# ── Gemini TTS ────────────────────────────────────────────────────────────────

def _generate_with_gemini(
    narration: str,
    voice_name: str,
    google_api_key: str,
    output_path: str,
    on_progress=None,
    segment_id: int = 0,
):
    """
    Generate voiceover using Gemini 2.5 Flash TTS.
    Automatically retries on rate-limit (429) with exponential backoff.
    """
    url = GEMINI_TTS_URL.format(key=google_api_key)
    body = json.dumps({
        "contents": [{"parts": [{"text": narration}]}],
        "generationConfig": {
            "response_modalities": ["AUDIO"],
            "speech_config": {
                "voice_config": {
                    "prebuilt_voice_config": {"voice_name": voice_name}
                }
            },
        },
    }).encode("utf-8")

    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            req = urllib.request.Request(
                url, data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
            break  # success — exit retry loop

        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_attempts - 1:
                # Rate limit — wait with exponential backoff: 5s, 10s, 20s, 40s
                wait = 5 * (2 ** attempt)
                if on_progress:
                    on_progress(
                        f"Segment {segment_id} — Gemini rate limit hit, "
                        f"waiting {wait}s before retry…"
                    )
                time.sleep(wait)
                continue
            raise  # non-429 error or exhausted retries

    # Parse response
    parts     = data["candidates"][0]["content"]["parts"]
    audio_part = next(p for p in parts if "inlineData" in p)
    mime_type  = audio_part["inlineData"]["mimeType"]
    pcm_b64    = audio_part["inlineData"]["data"]

    sample_rate = 24000
    if "rate=" in mime_type:
        try:
            sample_rate = int(mime_type.split("rate=")[1].split(";")[0])
        except (ValueError, IndexError):
            pass

    _pcm_to_mp3(base64.b64decode(pcm_b64), sample_rate, output_path)


# ── Piper TTS (offline) ────────────────────────────────────────────────────────

def _find_piper_exe() -> str | None:
    """Return path to piper.exe, or None if not installed."""
    base = _get_base_dir()
    candidate = os.path.join(base, "vendor", "piper", "piper.exe")
    if os.path.exists(candidate):
        return candidate
    return shutil.which("piper")


def _find_piper_voice(voice_name: str) -> str | None:
    """Return path to the .onnx model for a Piper voice, or None if not found."""
    base = _get_base_dir()
    voices_dir = os.path.join(base, "vendor", "piper", "voices")
    model_path = os.path.join(voices_dir, f"{voice_name}.onnx")
    return model_path if os.path.exists(model_path) else None


def _generate_with_piper(
    narration: str,
    voice_name: str,
    output_path: str,
    on_progress=None,
    segment_id: int = 0,
):
    """
    Generate voiceover using Piper TTS (offline, no internet needed).
    Requires: vendor/piper/piper.exe + vendor/piper/voices/<voice>.onnx
    Run setup.bat to download these automatically.
    """
    piper_exe = _find_piper_exe()
    if not piper_exe:
        raise RuntimeError(
            "Piper TTS not found. Run setup.bat to download it, "
            "or choose a different voice."
        )

    voice_model = _find_piper_voice(voice_name)
    if not voice_model:
        raise RuntimeError(
            f"Piper voice '{voice_name}' not found. "
            f"Run setup.bat to download voices, "
            f"or check vendor/piper/voices/ for available models."
        )

    if on_progress:
        on_progress(f"Segment {segment_id} — Piper TTS generating offline…")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = tmp.name

    try:
        subprocess.run(
            [piper_exe,
             "--model", voice_model,
             "--output_file", wav_path],
            input=narration.encode("utf-8"),
            check=True,
            capture_output=True,
        )
        _wav_to_mp3(wav_path, output_path)
    finally:
        try:
            os.unlink(wav_path)
        except OSError:
            pass


# ── edge-tts ──────────────────────────────────────────────────────────────────

async def _edge_tts_async(text, voice, rate, pitch, output_path):
    import edge_tts
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    await communicate.save(output_path)


def _generate_with_edge_tts(narration, voice, voice_rate, voice_pitch, output_path):
    try:
        asyncio.run(_edge_tts_async(narration, voice, voice_rate, voice_pitch, output_path))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                _edge_tts_async(narration, voice, voice_rate, voice_pitch, output_path)
            )
        finally:
            loop.close()


# ── Public API ────────────────────────────────────────────────────────────────

def generate_voiceover(
    segment_id: int,
    narration: str,
    voice: str,
    voice_rate: str,
    voice_pitch: str,
    cache_dir: str,
    google_api_key: str = "",
    on_progress=None,
) -> str:
    """
    Generate MP3 voiceover. Returns path to the MP3 file.
    Skips if already cached (resume support).

    Voice ID formats:
      "gemini:Charon"       Gemini TTS (requires google_api_key)
      "piper:en_US-ryan-high"  Piper offline TTS
      "en-US-GuyNeural"     edge-tts (default fallback)
    """
    output_path = os.path.join(cache_dir, f"segment_{segment_id}_audio.mp3")

    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        if on_progress:
            on_progress(f"Segment {segment_id} — voiceover already cached, skipping")
        return output_path

    Path(cache_dir).mkdir(parents=True, exist_ok=True)

    # ── Route to the right engine ──────────────────────────────────────────────
    if voice.startswith("gemini:") and google_api_key:
        voice_name = voice.split(":", 1)[1]
        if on_progress:
            on_progress(f"Segment {segment_id} — Gemini TTS ({voice_name})")
        try:
            _generate_with_gemini(
                narration, voice_name, google_api_key, output_path,
                on_progress=on_progress, segment_id=segment_id,
            )
        except Exception as e:
            if on_progress:
                on_progress(
                    f"Segment {segment_id} — Gemini TTS failed ({e}), "
                    f"falling back to edge-tts"
                )
            _generate_with_edge_tts(
                narration, "en-US-GuyNeural", voice_rate, voice_pitch, output_path
            )

    elif voice.startswith("piper:"):
        voice_name = voice.split(":", 1)[1]
        if on_progress:
            on_progress(f"Segment {segment_id} — Piper TTS offline ({voice_name})")
        try:
            _generate_with_piper(
                narration, voice_name, output_path,
                on_progress=on_progress, segment_id=segment_id,
            )
        except Exception as e:
            if on_progress:
                on_progress(
                    f"Segment {segment_id} — Piper failed ({e}), "
                    f"falling back to edge-tts"
                )
            _generate_with_edge_tts(
                narration, "en-US-GuyNeural", voice_rate, voice_pitch, output_path
            )

    else:
        if on_progress:
            on_progress(f"Segment {segment_id} — edge-tts ({voice})")
        _generate_with_edge_tts(narration, voice, voice_rate, voice_pitch, output_path)

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError(
            f"Segment {segment_id}: voiceover file was not created. "
            "Check your internet connection and try again."
        )

    return output_path


def get_audio_duration(mp3_path: str) -> float:
    from moviepy.editor import AudioFileClip
    with AudioFileClip(mp3_path) as clip:
        return clip.duration
