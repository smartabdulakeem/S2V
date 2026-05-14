"""
Stage 2 — Voiceover generation.

Routing:
  voice starts with "gemini:"  → Gemini 2.5 Flash TTS (natural, human-sounding)
  anything else                → edge-tts (free, 400+ voices, no API key needed)

Gemini voices (use "gemini:<VoiceName>" as the voice ID):
  Charon      — informative, authoritative  (best for documentary)
  Sadaltager  — knowledgeable, measured     (great for history)
  Rasalgethi  — informative, clear
  Orus        — firm, confident
  Algieba     — smooth, professional
  Sulafat     — warm, engaging
  Aoede       — breezy, clear  (female)
  Kore        — firm, clear    (female)
"""

import asyncio
import base64
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
import wave
from pathlib import Path

GEMINI_TTS_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash-preview-tts:generateContent?key={key}"
)


# ── Gemini TTS ────────────────────────────────────────────────────────────────

def _find_ffmpeg() -> str:
    """Find the FFmpeg executable — vendor folder first, then system PATH."""
    # Set by app.py at startup
    env_path = os.environ.get("IMAGEIO_FFMPEG_EXE", "")
    if env_path and os.path.exists(env_path):
        return env_path

    found = shutil.which("ffmpeg")
    if found:
        return found

    raise RuntimeError(
        "FFmpeg not found. Please run setup.bat first to install it."
    )


def _pcm_to_mp3(pcm_bytes: bytes, sample_rate: int, output_path: str):
    """Convert raw PCM (16-bit mono) to MP3 using FFmpeg."""
    ffmpeg = _find_ffmpeg()

    # Write PCM to a temp WAV file (more reliable than piping on Windows)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = tmp.name

    try:
        with wave.open(wav_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)       # 16-bit = 2 bytes per sample
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)

        subprocess.run(
            [
                ffmpeg, "-y",
                "-i", wav_path,
                "-codec:a", "libmp3lame",
                "-q:a", "2",         # VBR quality ~190 kbps
                output_path,
            ],
            check=True,
            capture_output=True,
        )
    finally:
        try:
            os.unlink(wav_path)
        except OSError:
            pass


def _generate_with_gemini(
    narration: str,
    voice_name: str,
    google_api_key: str,
    output_path: str,
):
    """
    Generate voiceover using Gemini 2.5 Flash TTS.
    Saves result as MP3 at output_path.
    """
    url = GEMINI_TTS_URL.format(key=google_api_key)

    body = json.dumps({
        "contents": [{"parts": [{"text": narration}]}],
        "generationConfig": {
            "response_modalities": ["AUDIO"],
            "speech_config": {
                "voice_config": {
                    "prebuilt_voice_config": {
                        "voice_name": voice_name,
                    }
                }
            },
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read())

    # Extract audio from response
    parts = data["candidates"][0]["content"]["parts"]
    audio_part = next(p for p in parts if "inlineData" in p)
    mime_type  = audio_part["inlineData"]["mimeType"]   # e.g. "audio/pcm;rate=24000"
    pcm_b64    = audio_part["inlineData"]["data"]

    # Parse sample rate from MIME type
    sample_rate = 24000
    if "rate=" in mime_type:
        try:
            sample_rate = int(mime_type.split("rate=")[1].split(";")[0])
        except (ValueError, IndexError):
            pass

    pcm_bytes = base64.b64decode(pcm_b64)
    _pcm_to_mp3(pcm_bytes, sample_rate, output_path)


# ── edge-tts ──────────────────────────────────────────────────────────────────

async def _edge_tts_async(
    text: str, voice: str, rate: str, pitch: str, output_path: str
):
    import edge_tts
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    await communicate.save(output_path)


def _generate_with_edge_tts(
    narration: str,
    voice: str,
    voice_rate: str,
    voice_pitch: str,
    output_path: str,
):
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
    Generate MP3 voiceover for a segment. Returns path to the MP3 file.
    Skips generation if file already exists (resume support).

    voice:
      "gemini:Charon"      → Gemini TTS, voice name Charon
      "en-US-GuyNeural"    → edge-tts (Microsoft neural voice)
    """
    output_path = os.path.join(cache_dir, f"segment_{segment_id}_audio.mp3")

    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        if on_progress:
            on_progress(f"Segment {segment_id} — voiceover already cached, skipping")
        return output_path

    Path(cache_dir).mkdir(parents=True, exist_ok=True)

    use_gemini = voice.startswith("gemini:") and google_api_key

    if on_progress:
        engine = "Gemini TTS" if use_gemini else "edge-tts"
        on_progress(f"Segment {segment_id} — generating voiceover ({engine}: {voice})")

    if use_gemini:
        voice_name = voice.split(":", 1)[1]
        try:
            _generate_with_gemini(narration, voice_name, google_api_key, output_path)
        except Exception as e:
            if on_progress:
                on_progress(
                    f"Segment {segment_id} — Gemini TTS failed ({e}), "
                    f"falling back to edge-tts"
                )
            # Fall back to a reliable edge-tts voice
            _generate_with_edge_tts(
                narration, "en-US-GuyNeural", voice_rate, voice_pitch, output_path
            )
    else:
        _generate_with_edge_tts(narration, voice, voice_rate, voice_pitch, output_path)

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError(
            f"Segment {segment_id}: voiceover file was not created. "
            "Check your internet connection and try again."
        )

    return output_path


def get_audio_duration(mp3_path: str) -> float:
    """Return duration in seconds using moviepy."""
    from moviepy.editor import AudioFileClip
    with AudioFileClip(mp3_path) as clip:
        return clip.duration
