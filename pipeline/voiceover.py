"""
Stage 2 — Voiceover generation.

Engine routing (based on voice ID prefix):
  "edge:<Name>"    → edge-tts — free, 400+ voices, reliable (default fallback)
  "hf:suno/bark"   → Suno Bark on Hugging Face Serverless
  "hf:coqui/XTTS"  → Coqui XTTS-v2 on Hugging Face Serverless
  "local:piper"    → local offline Piper TTS using lessac-medium model
"""

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
import urllib.error
from pathlib import Path

# ── FFmpeg Finder ─────────────────────────────────────────────────────────────

def _find_ffmpeg() -> str:
    env_path = os.environ.get("IMAGEIO_FFMPEG_EXE", "")
    if env_path and os.path.exists(env_path):
        return env_path
    
    # Check default vendor path
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    vendor_ffmpeg = os.path.join(base_dir, "vendor", "ffmpeg", "bin", "ffmpeg.exe")
    if os.path.exists(vendor_ffmpeg):
        return vendor_ffmpeg

    found = shutil.which("ffmpeg")
    if found:
        return found
    raise RuntimeError("FFmpeg not found. Please run setup.bat first.")


def _transcode_to_mp3(input_bytes: bytes, output_path: str):
    """Write bytes to a temp file and transcode to MP3 using FFmpeg."""
    ffmpeg = _find_ffmpeg()
    with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as tmp:
        tmp_path = tmp.name
        tmp.write(input_bytes)

    try:
        cmd = [
            ffmpeg, "-y",
            "-i", tmp_path,
            "-codec:a", "libmp3lame",
            "-q:a", "2",
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg transcoding failed: {result.stderr}")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

# ── Local Piper TTS ───────────────────────────────────────────────────────────

def _generate_with_local_piper(narration: str, output_path: str, on_progress=None, segment_id: int = 0):
    """Generate audio offline using local Piper executable and model."""
    piper_exe = r"C:\Users\HomePC\Downloads\piper_extracted\piper\piper.exe"
    model_path = r"C:\Users\HomePC\Documents\GitHub\piper-desktop-skill\models\en_US-lessac-medium.onnx"

    if not os.path.exists(piper_exe):
        raise FileNotFoundError(f"Local Piper executable not found at: {piper_exe}")
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Local Piper model ONNX file not found at: {model_path}")

    if on_progress:
        on_progress(f"Segment {segment_id} — Generating offline voiceover via local Piper (lessac-medium)")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        temp_wav = tmp.name

    try:
        cmd = [
            piper_exe,
            "--model", model_path,
            "--output_file", temp_wav
        ]
        
        # Run Piper process and pipe narration to stdin
        result = subprocess.run(
            cmd,
            input=narration.encode("utf-8"),
            capture_output=True,
            check=False
        )
        
        if result.returncode != 0:
            err_details = result.stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"Piper execution failed: {err_details}")

        if not os.path.exists(temp_wav) or os.path.getsize(temp_wav) < 1000:
            raise RuntimeError("Piper generated an empty or invalid WAV file.")

        # Transcode WAV to MP3
        with open(temp_wav, "rb") as f:
            wav_bytes = f.read()
        _transcode_to_mp3(wav_bytes, output_path)

    finally:
        try:
            os.unlink(temp_wav)
        except OSError:
            pass

# ── Hugging Face TTS API ──────────────────────────────────────────────────────

def _generate_with_hf(
    narration: str,
    model_id: str,
    hf_token: str,
    output_path: str,
    on_progress=None,
    segment_id: int = 0
):
    """
    Generate voiceover using Hugging Face serverless inference.
    Automatically retries on rate limits (429) or model loading (503).
    """
    if not hf_token:
        raise ValueError("Hugging Face API Token is required for premium cloud voices.")

    url = f"https://router.huggingface.co/hf-inference/models/{model_id}"
    headers = {
        "Authorization": f"Bearer {hf_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "inputs": narration,
        "options": {"wait_for_model": True}
    }
    body = json.dumps(payload).encode("utf-8")

    max_attempts = 4
    last_error = None

    for attempt in range(max_attempts):
        try:
            req = urllib.request.Request(
                url, data=body, headers=headers, method="POST"
            )
            with urllib.request.urlopen(req, timeout=90) as resp:
                content_type = resp.headers.get("Content-Type", "")
                data = resp.read()

                if "application/json" in content_type:
                    try:
                        err_json = json.loads(data.decode("utf-8"))
                        if "error" in err_json:
                            raise RuntimeError(err_json["error"])
                    except json.JSONDecodeError:
                        pass

                if len(data) < 100:
                    try:
                        txt = data.decode("utf-8")
                        raise RuntimeError(f"Unexpected response text: {txt}")
                    except UnicodeDecodeError:
                        pass

                _transcode_to_mp3(data, output_path)
                return

        except urllib.error.HTTPError as e:
            try:
                err_text = e.read().decode("utf-8")
                err_json = json.loads(err_text)
                last_error = err_json.get("error", err_text)
            except Exception:
                last_error = str(e)
            
            if e.code in (503, 504, 429) and attempt < max_attempts - 1:
                wait = 5 * (attempt + 1)
                if on_progress:
                    on_progress(
                        f"Segment {segment_id} — Hugging Face API temporary error {e.code} ({last_error}). "
                        f"Retrying in {wait}s..."
                    )
                time.sleep(wait)
                continue
            raise urllib.error.HTTPError(e.url, e.code, f"HF API Error: {last_error}", e.headers, None)
        except Exception as e:
            last_error = str(e)
            if attempt < max_attempts - 1:
                wait = 5 * (attempt + 1)
                if on_progress:
                    on_progress(f"Segment {segment_id} — Connection error ({e}). Retrying in {wait}s...")
                time.sleep(wait)
                continue
            raise RuntimeError(f"Hugging Face TTS call failed: {last_error}")

    raise RuntimeError(f"Hugging Face TTS API failed after {max_attempts} attempts: {last_error}")

# ── Microsoft Edge TTS ────────────────────────────────────────────────────────

async def _edge_tts_async(text: str, voice: str, rate: str, pitch: str, output_path: str):
    import edge_tts
    if voice.startswith("edge:"):
        voice = voice.split(":", 1)[1]
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    await communicate.save(output_path)


def _generate_with_edge_tts(narration: str, voice: str, voice_rate: str, voice_pitch: str, output_path: str):
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
    huggingface_api_key: str = "",
    on_progress=None,
) -> str:
    """
    Generate MP3 voiceover. Returns path to the MP3 file.
    Skips if already cached (resume support).

    Voice ID formats:
      "edge:en-US-GuyNeural"  edge-tts (free)
      "hf:suno/bark"          Suno Bark (Hugging Face)
      "hf:coqui/XTTS-v2"      Coqui XTTS-v2 (Hugging Face)
      "local:piper"           local Piper offline (Free)
    """
    output_path = os.path.join(cache_dir, f"segment_{segment_id}_audio.mp3")

    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        if on_progress:
            on_progress(f"Segment {segment_id} — voiceover already cached, skipping")
        return output_path

    Path(cache_dir).mkdir(parents=True, exist_ok=True)

    voice_lower = voice.lower()
    
    # Determine routing
    is_hf = voice_lower.startswith("hf:") or "bark" in voice_lower or "xtts" in voice_lower
    is_piper = voice_lower.startswith("local:piper") or voice_lower.startswith("piper:")

    if is_piper:
        # Run local offline Piper
        _generate_with_local_piper(
            narration=narration,
            output_path=output_path,
            on_progress=on_progress,
            segment_id=segment_id
        )

    elif is_hf:
        # Determine Hugging Face model repository path
        model_id = voice
        if voice_lower == "hf:suno/bark" or voice_lower == "suno/bark":
            model_id = "suno/bark"
        elif voice_lower == "hf:suno/bark-small" or voice_lower == "suno/bark-small":
            model_id = "suno/bark-small"
        elif voice_lower == "hf:coqui/xtts-v2" or voice_lower == "coqui/xtts-v2" or "xtts-v2" in voice_lower:
            model_id = "coqui/XTTS-v2"
        elif model_id.startswith("hf:"):
            model_id = model_id.split(":", 1)[1]

        if on_progress:
            on_progress(f"Segment {segment_id} — Generating cloud voiceover (HF: {model_id})")

        _generate_with_hf(
            narration=narration,
            model_id=model_id,
            hf_token=huggingface_api_key,
            output_path=output_path,
            on_progress=on_progress,
            segment_id=segment_id
        )

    else:
        # Fallback to Microsoft Edge neural voices
        clean_voice = voice
        if voice.startswith("edge:"):
            clean_voice = voice.split(":", 1)[1]
        elif voice.startswith("gemini:"):
            clean_voice = "en-US-GuyNeural"
            if on_progress:
                on_progress(f"Segment {segment_id} — legacy Gemini voice found. Routing to edge:en-US-GuyNeural")

        if on_progress:
            on_progress(f"Segment {segment_id} — Generating Edge Neural voiceover ({clean_voice})")
            
        _generate_with_edge_tts(narration, clean_voice, voice_rate, voice_pitch, output_path)

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError(
            f"Segment {segment_id}: voiceover file was not created. "
            "Check network connection or API status and try again."
        )

    return output_path


def get_audio_duration(mp3_path: str) -> float:
    from moviepy.editor import AudioFileClip
    with AudioFileClip(mp3_path) as clip:
        return clip.duration
