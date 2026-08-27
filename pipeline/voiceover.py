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
import re
import base64
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request

from pipeline.net import install as _install_net_shim

# Google's hosts fail a dual-stack lookup on machines with a broken IPv6 path, which
# kills every TTS request before it is sent. Retry IPv4 when that happens.
_install_net_shim()
import urllib.error
from pathlib import Path

# OPTIMIZATION: Limit ONNX Runtime CPU threads to prevent active RAM and CPU overhead
os.environ["SUPERTONIC_INTRA_OP_THREADS"] = "2"
os.environ["SUPERTONIC_INTER_OP_THREADS"] = "1"

# OPTIMIZATION: Monkey patch ONNX Runtime SessionOptions to disable memory arena
try:
    import onnxruntime as ort
    original_init = ort.SessionOptions.__init__
    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.enable_cpu_mem_arena = False
    ort.SessionOptions.__init__ = patched_init
except Exception:
    pass

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


def _transcode_to_mp3(input_bytes: bytes, output_path: str, is_raw_pcm: bool = False, sample_rate: int = 24000):
    """Write bytes to a temp file and transcode to MP3 using FFmpeg."""
    ffmpeg = _find_ffmpeg()
    with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as tmp:
        tmp_path = tmp.name
        tmp.write(input_bytes)

    try:
        if is_raw_pcm:
            # Raw PCM data requires explicit format, sample rate and channel count inputs for FFmpeg to decode correctly
            cmd = [
                ffmpeg, "-y",
                "-f", "s16le",
                "-ar", str(sample_rate),
                "-ac", "1",
                "-i", tmp_path,
                "-codec:a", "libmp3lame",
                "-q:a", "2",
                output_path
            ]
        else:
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

#: Broadcast mastering chain for local TTS.
#
# Offline engines output a raw, unmastered signal: even, quiet, and centred, with
# no presence lift and no dynamics. That is what "flat" means here — it is not the
# model's expressiveness, it is the absence of the processing every broadcast
# voice gets. Costs nothing and needs no download.
#
#   highpass   drop rumble below the voice
#   equalizer  cut boxiness at 300Hz, lift presence at 3.2kHz, add air at 9kHz
#   compand    gentle compression so quiet syllables come forward
#   loudnorm   EBU R128 to a consistent broadcast level
MASTERING_CHAIN = (
    "highpass=f=85,"
    "equalizer=f=300:t=q:w=1.2:g=-2,"
    "equalizer=f=3200:t=q:w=1.4:g=3.5,"
    "equalizer=f=9000:t=q:w=1.0:g=2,"
    "compand=attacks=0.02:decays=0.25:points=-60/-60|-32/-20|-18/-12|-6/-7|0/-6:soft-knee=4:gain=2,"
    "loudnorm=I=-16:TP=-1.5:LRA=11"
)


def master_audio(input_path: str, output_path: str = None, chain: str = None) -> str:
    """
    Apply the mastering chain to a narration file, in place by default.

    Returns the path written. On any failure the original file is left untouched
    and its path returned — a render must never be lost to a cosmetic filter.
    """
    target = output_path or input_path
    ffmpeg = _find_ffmpeg()
    tmp_out = target + ".mastered.mp3"
    cmd = [
        ffmpeg, "-y", "-i", input_path,
        "-af", chain or MASTERING_CHAIN,
        "-codec:a", "libmp3lame", "-q:a", "2",
        tmp_out,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and os.path.exists(tmp_out) and os.path.getsize(tmp_out) > 1000:
            os.replace(tmp_out, target)
            return target
    except Exception:
        pass
    finally:
        if os.path.exists(tmp_out):
            try:
                os.remove(tmp_out)
            except OSError:
                pass
    return input_path


def _sanitize_text(text: str) -> str:
    if not text:
        return ""
    # Map common non-ASCII punctuation and unsupported ASCII symbols to standard alternatives
    replacements = {
        '“': '"', '”': '"',
        '‘': "'", '’': "'",
        '—': '-', '–': '-',
        '…': '...',
        '•': ' ', '·': ' ',
        '➔': ' ', '→': ' ',
        '✔': ' ', '★': ' ',
        '[': '(', ']': ')',
        '{': '(', '}': ')',
        '`': "'",
        '_': ' ',
        '\\': ' ',
        '|': ' ',
        '@': ' at ',
        '#': ' ',
    }
    for orig, rep in replacements.items():
        text = text.replace(orig, rep)
    
    # Keep only standard printable ASCII (excluding unsupported ones), Arabic characters, and space
    # (This strips all emojis, complex unicode icons, and unsupported symbols)
    unsupported_ascii = {'#', '@', '[', '\\', ']', '_', '`', '|'}
    cleaned = []
    for char in text:
        o = ord(char)
        # ASCII printable (32-126) excluding unsupported, or Arabic Unicode block (0x0600-0x06FF)
        if ((32 <= o <= 126) and char not in unsupported_ascii) or (0x0600 <= o <= 0x06FF):
            cleaned.append(char)
        elif char in '\n\r\t':
            cleaned.append(' ')
        else:
            # Replace unsupported character/emoji with space to avoid merging adjacent words
            cleaned.append(' ')
            
    import re
    return re.sub(r' +', ' ', ''.join(cleaned)).strip()

# ── Local Supertonic TTS ──────────────────────────────────────────────────────
import threading
import gc

_tts_instance = None
_tts_lock = threading.Lock()
_tts_last_active_time = time.time()
_tts_monitor_started = False

def _monitor_tts_inactivity():
    global _tts_instance, _tts_last_active_time
    while True:
        time.sleep(30)
        with _tts_lock:
            if _tts_instance is not None:
                idle_duration = time.time() - _tts_last_active_time
                if idle_duration > 300:  # 5 minutes of inactivity
                    print(f"S2V: TTS engine idle for {int(idle_duration)}s. Unloading model weights to free RAM.")
                    _tts_instance = None
                    gc.collect()

def _generate_with_local_supertonic(
    narration: str,
    voice: str,
    voice_rate: str,
    output_path: str,
    on_progress=None,
    segment_id: int = 0,
    narrative_tone: str = ""
):
    """Generate audio offline using local Supertonic synthesis."""
    global _tts_instance, _tts_last_active_time, _tts_monitor_started
    
    # Sanitize narration to prevent tokenizer index errors with emojis/symbols
    narration = _sanitize_text(narration)
    if not narration:
        if on_progress:
            on_progress(f"Segment {segment_id} — Narration is empty after sanitization")
        # Generate a tiny bit of silence so the segment is not empty
        _transcode_to_mp3(b"\x00" * 3200, output_path, is_raw_pcm=True)
        return
    
    with _tts_lock:
        _tts_last_active_time = time.time()
        
        # Start inactivity monitor thread if not already running
        if not _tts_monitor_started:
            threading.Thread(target=_monitor_tts_inactivity, daemon=True).start()
            _tts_monitor_started = True
            
        if _tts_instance is None:
            from supertonic import TTS
            print("S2V: Loading Multilingual (English/Arabic) TTS model weights...")
            _tts_instance = TTS()  # Defaults to supertonic-3 (multilingual)
        tts_instance = _tts_instance

    if on_progress:
        on_progress(f"Segment {segment_id} — Generating offline voiceover via Supertonic")

    # 1. Map voice name to style. Default to "M1"
    voice_name = "M1"
    voice_lower = voice.lower()
    for v_style in ["m1", "m2", "m3", "m4", "m5", "f1", "f2", "f3", "f4", "f5"]:
        if v_style in voice_lower:
            voice_name = v_style.upper()
            break

    style = tts_instance.get_voice_style(voice_name=voice_name)

    # 2. Speed and pause length come from the tone, with the user's own rate
    #    folded in on top. Supertonic chunks the text itself and takes the gap
    #    between chunks as a parameter, so a motivational read genuinely holds
    #    between lines rather than just running slower.
    from pipeline.delivery import delivery_for, apply_rate
    profile = delivery_for(narrative_tone)
    speed = apply_rate(profile["speed"], voice_rate)
    silence_duration = float(profile["silence"])

    # 3. Detect / extract language code
    lang = None
    parts = voice_lower.split("-")
    if len(parts) >= 3:
        potential_lang = parts[-1]
        if potential_lang in ["en", "ko", "ja", "ar", "bg", "cs", "da", "de", "el", "es", "et", "fi", "fr", "hi", "hr", "hu", "id", "it", "lt", "lv", "nl", "pl", "pt", "ro", "ru", "sk", "sl", "sv", "tr", "uk", "vi"]:
            lang = potential_lang

    if not lang:
        # Detect if narration is primarily Arabic (over 10% characters)
        arabic_chars = len(re.findall(r'[\u0600-\u06FF]', narration))
        if arabic_chars > len(narration) * 0.1:
            lang = "ar"
        else:
            lang = "en"

    # Check for speaker switching tags in the narration
    has_speaker_switch = bool(re.search(r'\[(?:M|F)[1-5]\]', narration))

    if has_speaker_switch:
        if on_progress:
            on_progress(f"Segment {segment_id} — Processing conversational speaker switches")
        
        # Split text by speaker tags
        text_parts = re.split(r'(\[(?:M|F)[1-5]\])', narration)
        
        active_voice_name = voice_name
        active_style = style
        
        temp_wav_files = []
        
        try:
            part_idx = 0
            for part in text_parts:
                part = part.strip()
                if not part:
                    continue
                
                # Check if this part is a speaker tag
                tag_match = re.match(r'^\[((?:M|F)[1-5])\]$', part, re.IGNORECASE)
                if tag_match:
                    active_voice_name = tag_match.group(1).upper()
                    active_style = tts_instance.get_voice_style(voice_name=active_voice_name)
                    continue
                
                # This part is narration text. Clean other emotional tags inside it.
                part_clean = part
                part_clean = re.sub(r'\[(?:sigh|pause|gasp)\]', '... ', part_clean)
                part_clean = re.sub(r'\[(?:laughter|laugh)\]', ', ', part_clean)
                part_clean = re.sub(r'\[[^\]]+\]', '', part_clean)
                part_clean = re.sub(r'\s+', ' ', part_clean)
                part_clean = re.sub(r'\.{4,}', '...', part_clean)
                part_clean = part_clean.strip()
                
                if not part_clean:
                    continue
                
                # Synthesize part
                part_wav, _ = tts_instance.synthesize(
                    text=part_clean,
                    voice_style=active_style,
                    speed=speed,
                    silence_duration=silence_duration,
                    lang=lang
                )
                
                temp_part_wav = os.path.join(tempfile.gettempdir(), f"s2v_seg_{segment_id}_part_{part_idx}.wav")
                tts_instance.save_audio(part_wav, temp_part_wav)
                temp_wav_files.append(temp_part_wav)
                part_idx += 1
                
            if not temp_wav_files:
                raise RuntimeError("No audio parts were generated for speaker-switching narration.")
                
            # Concatenate all parts using FFmpeg concat demuxer
            ffmpeg = _find_ffmpeg()
            
            # Write list file
            list_path = os.path.join(tempfile.gettempdir(), f"s2v_seg_{segment_id}_list.txt")
            with open(list_path, "w", encoding="utf-8") as lf:
                for tf in temp_wav_files:
                    safe_tf = tf.replace("\\", "/")
                    lf.write(f"file '{safe_tf}'\n")
                    
            final_wav = os.path.join(tempfile.gettempdir(), f"s2v_seg_{segment_id}_final.wav")
            
            cmd = [
                ffmpeg, "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", list_path,
                "-c", "copy",
                final_wav
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            # Clean list file
            try:
                os.unlink(list_path)
            except OSError:
                pass
                
            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg audio parts concat failed: {result.stderr}")
                
            # Transcode final WAV to output MP3
            with open(final_wav, "rb") as f:
                wav_bytes = f.read()
            _transcode_to_mp3(wav_bytes, output_path)
            
            # Clean final wav
            try:
                os.unlink(final_wav)
            except OSError:
                pass
                
        finally:
            # Clean up all part files
            for tf in temp_wav_files:
                try:
                    if os.path.exists(tf):
                        os.unlink(tf)
                except OSError:
                    pass
    else:
        # Standard single speaker narration
        clean_text = narration
        clean_text = re.sub(r'\[(?:sigh|pause|gasp)\]', '... ', clean_text)
        clean_text = re.sub(r'\[(?:laughter|laugh)\]', ', ', clean_text)
        clean_text = re.sub(r'\[[^\]]+\]', '', clean_text)
        clean_text = re.sub(r'\s+', ' ', clean_text)
        clean_text = re.sub(r'\.{4,}', '...', clean_text)
        clean_text = clean_text.strip()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            temp_wav = tmp.name

        try:
            wav, _ = tts_instance.synthesize(
                text=clean_text,
                voice_style=style,
                speed=speed,
                silence_duration=silence_duration,
                lang=lang
            )
            tts_instance.save_audio(wav, temp_wav)

            if not os.path.exists(temp_wav) or os.path.getsize(temp_wav) < 1000:
                raise RuntimeError("Supertonic generated an empty or invalid WAV file.")

            with open(temp_wav, "rb") as f:
                wav_bytes = f.read()
            _transcode_to_mp3(wav_bytes, output_path)

        finally:
            try:
                os.unlink(temp_wav)
            except OSError:
                pass

# ── Kokoro Offline TTS ────────────────────────────────────────────────────────

_kokoro_instance = None
_kokoro_lock = threading.Lock()

def _get_kokoro_instance():
    global _kokoro_instance
    with _kokoro_lock:
        if _kokoro_instance is None:
            from kokoro_onnx import Kokoro
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            
            candidates = [
                (
                    os.path.join(base_dir, "config", "kokoro_models", "kokoro-v1.0.onnx"),
                    os.path.join(base_dir, "config", "kokoro_models", "voices-v1.0.bin")
                ),
                (
                    os.path.join(base_dir, "config", "kokoro", "kokoro-v1.0.onnx"),
                    os.path.join(base_dir, "config", "kokoro", "voices-v1.0.bin")
                ),
            ]
            
            model_path, voices_path = None, None
            for mp, vp in candidates:
                if os.path.exists(mp) and os.path.exists(vp):
                    model_path, voices_path = mp, vp
                    break
                    
            if not model_path:
                model_path, voices_path = candidates[0]
                
            # kokoro-onnx builds its own InferenceSession with NO SessionOptions,
            # so the SessionOptions monkeypatch above never fires for it and the
            # SUPERTONIC_* env vars do not apply either. Left alone it takes every
            # core. Hand it a session we configured instead.
            _kokoro_instance = _build_kokoro(Kokoro, model_path, voices_path)
        return _kokoro_instance


def _build_kokoro(Kokoro, model_path, voices_path):
    """Kokoro on a thread-capped CPU session, so synthesis cannot peg the machine."""
    try:
        import onnxruntime as ort
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = int(os.environ.get("KOKORO_INTRA_OP_THREADS", "2"))
        opts.inter_op_num_threads = int(os.environ.get("KOKORO_INTER_OP_THREADS", "1"))
        opts.enable_cpu_mem_arena = False
        session = ort.InferenceSession(
            model_path, sess_options=opts, providers=["CPUExecutionProvider"]
        )
        return Kokoro.from_session(session, voices_path)
    except (AttributeError, ImportError):
        # Older kokoro-onnx has no from_session; uncapped is better than broken.
        return Kokoro(model_path, voices_path)


def _generate_with_local_kokoro(
    narration: str,
    voice: str,
    voice_rate: str,
    output_path: str,
    on_progress=None,
    segment_id: int = 0,
    narrative_tone: str = ""
):
    """Generate audio offline using local Kokoro-ONNX synthesis."""
    import soundfile as sf
    narration = _sanitize_text(narration)
    if not narration:
        if on_progress:
            on_progress(f"Segment {segment_id} — Narration is empty after sanitization")
        _transcode_to_mp3(b"\x00" * 3200, output_path, is_raw_pcm=True)
        return

    # Extract voice name (e.g. "local:kokoro-af_heart" -> "af_heart")
    voice_name = "af_heart"
    v_clean = voice.lower()
    if "kokoro-" in v_clean:
        voice_name = v_clean.split("kokoro-", 1)[1].strip()
    elif ":" in v_clean:
        voice_name = v_clean.split(":", 1)[1].strip()

    # Speed and pauses come from the tone. Unlike Supertonic, kokoro-onnx has
    # no silence parameter, so the narration is spoken a block at a time and
    # the gaps are stitched in as real samples.
    from pipeline.delivery import delivery_for, apply_rate, split_blocks, join_with_silence
    profile = delivery_for(narrative_tone)
    speed = apply_rate(profile["speed"], voice_rate)

    if on_progress:
        on_progress(f"Segment {segment_id} — Generating offline voiceover via Kokoro ({voice_name})")

    kokoro = _get_kokoro_instance()
    
    # Map language
    lang = "en-us"
    if voice_name.startswith("b"):
        lang = "en-gb"
    elif voice_name.startswith("j"):
        lang = "ja"
    elif voice_name.startswith("z"):
        lang = "zh"
    elif voice_name.startswith("e"):
        lang = "es"
    elif voice_name.startswith("f"):
        lang = "fr"
    elif voice_name.startswith("h"):
        lang = "hi"
    elif voice_name.startswith("i"):
        lang = "it"
    elif voice_name.startswith("p"):
        lang = "pt-br"

    blocks = split_blocks(narration)
    if len(blocks) <= 1:
        samples, sr = kokoro.create(narration, voice=voice_name, speed=speed, lang=lang)
    else:
        pieces = []
        sr = None
        for chunk, gap in blocks:
            chunk_samples, chunk_sr = kokoro.create(
                chunk, voice=voice_name, speed=speed, lang=lang)
            sr = sr or chunk_sr
            pieces.append((chunk_samples, gap))
        samples = join_with_silence(pieces, sr, profile)
        if samples is None:
            raise RuntimeError("Kokoro produced no audio for any block.")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        temp_wav = tmp.name

    try:
        sf.write(temp_wav, samples, sr)
        if not os.path.exists(temp_wav) or os.path.getsize(temp_wav) < 1000:
            raise RuntimeError("Kokoro generated an empty or invalid WAV file.")
            
        with open(temp_wav, "rb") as f:
            wav_bytes = f.read()
        _transcode_to_mp3(wav_bytes, output_path)
    finally:
        try:
            os.unlink(temp_wav)
        except OSError:
            pass


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

# ── Public API ────────────────────────────────────────────────────────────────



TIMEPOINT_CAPABLE_VOICE_TYPES = ("neural2", "wavenet", "standard", "news", "polyglot")

def is_timepoint_capable_voice(voice_name: str) -> bool:
    """Return True if Google TTS voice supports SSML mark timepoints (Neural2/Wavenet/Standard)."""
    v_lower = voice_name.lower()
    return any(v_type in v_lower for v_type in TIMEPOINT_CAPABLE_VOICE_TYPES) and not ("studio" in v_lower or "journey" in v_lower)


def _generate_with_google_tts(
    narration: str,
    voice: str,
    voice_rate: str,
    voice_pitch: str,
    google_api_key: str,
    output_path: str,
    on_progress=None,
    segment_id: int = 0,
    cache_dir: str = "",
):
    """Generate audio using Google Cloud Text-to-Speech REST API and extract SSML word timepoints for captions."""
    if not google_api_key:
        raise ValueError("Google API key is required for Google Premium Voices.")

    url = f"https://texttospeech.googleapis.com/v1beta1/text:synthesize?key={google_api_key}"

    # Parse voice name and language code
    voice_name = voice
    if voice.startswith("google:"):
        voice_name = voice.split(":", 1)[1]

    parts = voice_name.split("-")
    language_code = "en-US"
    if len(parts) >= 2:
        language_code = f"{parts[0]}-{parts[1]}"

    # Parse speaking rate
    speaking_rate = 1.0
    if voice_rate:
        voice_rate = voice_rate.strip()
        if voice_rate.endswith("%"):
            try:
                val = float(voice_rate[:-1])
                speaking_rate = round(1.0 + (val / 100.0), 2)
                speaking_rate = max(0.25, min(4.0, speaking_rate))
            except ValueError:
                pass

    # Parse pitch config (convert pitch to semitones)
    pitch_semitones = 0.0
    if voice_pitch:
        voice_pitch = voice_pitch.strip()
        m = re.match(r"^([+-]?\d+)", voice_pitch)
        if m:
            try:
                pitch_semitones = float(m.group(1))
                pitch_semitones = max(-20.0, min(20.0, pitch_semitones))
            except ValueError:
                pass

    clean_text = re.sub(r'<[^>]+>', '', narration).strip()
    words = clean_text.split()

    headers = {
        "Content-Type": "application/json"
    }

    # Check if voice supports SSML mark timepoints
    supports_timepoints = is_timepoint_capable_voice(voice_name)
    if not supports_timepoints:
        if on_progress:
            on_progress(f"Segment {segment_id} — Google voice '{voice_name}' does not support SSML mark timepoints. Synthesizing plain audio; captions will fall back to Whisper.")

        payload_fallback = {
            "input": {"text": clean_text},
            "voice": {"languageCode": language_code, "name": voice_name},
            "audioConfig": {
                "audioEncoding": "MP3",
                "speakingRate": speaking_rate,
                "pitch": pitch_semitones,
            },
        }
        body_fb = json.dumps(payload_fallback).encode("utf-8")
        req_fb = urllib.request.Request(url, data=body_fb, headers=headers, method="POST")
        with urllib.request.urlopen(req_fb, timeout=60) as resp_fb:
            response_data_fb = json.loads(resp_fb.read().decode("utf-8"))
        audio_bytes = base64.b64decode(response_data_fb["audioContent"])
        with open(output_path, "wb") as f:
            f.write(audio_bytes)
        return

    # Voice supports SSML mark timepoints — build SSML payload
    if not narration.strip().startswith("<speak>"):
        ssml_parts = ["<speak>"]
        for idx, w in enumerate(words):
            w_xml = w.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")
            ssml_parts.append(f'<mark name="w{idx}"/>{w_xml}')
        ssml_parts.append("</speak>")
        ssml_narration = " ".join(ssml_parts)
    else:
        ssml_narration = narration

    payload = {
        "input": {
            "ssml": ssml_narration
        },
        "voice": {
            "languageCode": language_code,
            "name": voice_name
        },
        "audioConfig": {
            "audioEncoding": "MP3",
            "speakingRate": speaking_rate,
            "pitch": pitch_semitones
        },
        "enableTimePointing": ["SSML_MARK"]
    }
    body = json.dumps(payload).encode("utf-8")

    headers = {
        "Content-Type": "application/json"
    }

    for attempt in range(3):
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=60) as resp:
                response_data = json.loads(resp.read().decode("utf-8"))

            if "audioContent" not in response_data:
                raise RuntimeError(f"Google TTS API response missing 'audioContent': {response_data}")

            audio_bytes = base64.b64decode(response_data["audioContent"])
            with open(output_path, "wb") as f:
                f.write(audio_bytes)

            timepoints = response_data.get("timepoints", [])
            if timepoints and cache_dir:
                from pipeline.captions import create_srt_from_tts_timings
                srt_path = os.path.join(cache_dir, f"segment_{segment_id}_captions.srt")
                create_srt_from_tts_timings(words, timepoints, srt_path, audio_path=output_path)
                if on_progress:
                    on_progress(f"Segment {segment_id} — Captions generated directly from Google TTS timepoints")
            return
        except urllib.error.HTTPError as e:
            if e.code == 400:
                # Voice does not support SSML mark timepoints (e.g. Studio/Journey voices) — fallback to plain text synthesis
                payload_fallback = {
                    "input": {"text": clean_text},
                    "voice": {"languageCode": language_code, "name": voice_name},
                    "audioConfig": {
                        "audioEncoding": "MP3",
                        "speakingRate": speaking_rate,
                        "pitch": pitch_semitones,
                    },
                }
                body_fb = json.dumps(payload_fallback).encode("utf-8")
                try:
                    req_fb = urllib.request.Request(url, data=body_fb, headers=headers, method="POST")
                    with urllib.request.urlopen(req_fb, timeout=60) as resp_fb:
                        response_data_fb = json.loads(resp_fb.read().decode("utf-8"))
                    audio_bytes = base64.b64decode(response_data_fb["audioContent"])
                    with open(output_path, "wb") as f:
                        f.write(audio_bytes)
                    return
                except Exception as fb_err:
                    raise RuntimeError(f"Google TTS fallback failed: {fb_err}")
            if attempt < 2:
                time.sleep(2)
            else:
                raise RuntimeError(f"Google TTS failed after 3 attempts: {e}")
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
            else:
                raise RuntimeError(f"Google TTS failed after 3 attempts: {e}")


def _generate_with_gemini_tts(
    narration: str,
    voice: str,
    google_api_key: str,
    output_path: str,
    voice_steering: str = "",
    on_progress=None,
    segment_id: int = 0
):
    """Generate audio using Google Gemini 3.1 Flash TTS Preview API."""
    if not google_api_key:
        raise ValueError("Google API key is required for Gemini TTS voices.")

    # Determine voice name
    voice_name = "Puck" # Default
    if voice.startswith("google:gemini-3.1-flash-tts-preview:"):
        voice_name = voice.split(":", 2)[2]
    elif voice.startswith("google:"):
        potential_name = voice.split(":", 1)[1]
        # If it's not the model name, use it
        if potential_name != "gemini-3.1-flash-tts-preview":
            voice_name = potential_name
    else:
        try:
            from app import _load_settings
            settings = _load_settings()
            voice_name = settings.get("tts_voice_name", "Puck")
        except Exception:
            pass

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-tts-preview:generateContent?key={google_api_key}"

    # Formulate steering input
    text_content = narration
    if voice_steering:
        # Prepend steering tag to text
        text_content = f"{voice_steering}\n{narration}"

    payload = {
        "contents": [{
            "parts": [{"text": text_content}]
        }],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": voice_name
                    }
                }
            }
        }
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    for attempt in range(3):
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=90) as resp:
                response_data = json.loads(resp.read().decode("utf-8"))
            
            candidates = response_data.get("candidates", [])
            if not candidates:
                raise RuntimeError(f"No candidates returned: {response_data}")
            
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                raise RuntimeError(f"No parts returned: {response_data}")
            
            inline_data = parts[0].get("inlineData", {})
            if not inline_data:
                raise RuntimeError(f"No inline audio data returned: {response_data}")
            
            b64_data = inline_data.get("data", "")
            if not b64_data:
                raise RuntimeError("Base64 audio data is empty.")
            
            mime_type = inline_data.get("mimeType", "audio/pcm")
            audio_bytes = base64.b64decode(b64_data)
            
            is_raw_pcm = "audio/pcm" in mime_type or "audio/l16" in mime_type
            sample_rate = 24000
            rate_match = re.search(r"rate=(\d+)", mime_type)
            if rate_match:
                sample_rate = int(rate_match.group(1))
                
            _transcode_to_mp3(audio_bytes, output_path, is_raw_pcm=is_raw_pcm, sample_rate=sample_rate)
            return
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
            else:
                raise RuntimeError(f"Gemini 3.1 Flash TTS failed after 3 attempts: {e}")


def generate_voiceover(
    segment_id: int,
    narration: str,
    voice: str,
    voice_rate: str,
    voice_pitch: str,
    cache_dir: str,
    google_api_key: str = "",
    on_progress=None,
    voice_steering: str = "",
    narrative_tone: str = ""
) -> str:
    """
    Generate MP3 voiceover. Returns path to the MP3 file.
    Skips if already cached (resume support).

    Voice ID formats:
      "edge:<voice_name>"    edge-tts (free)
      "google:<voice_name>"  Google Cloud Text-to-Speech (requires Google API Key)
      "hf:<model_id>"        Hugging Face cloud model (requires HF API Key)
      "local:piper"          local Piper offline
    """
    output_path = os.path.join(cache_dir, f"segment_{segment_id}_audio.mp3")

    # The tone changes how the words are read, so cached audio from a different
    # tone is the wrong audio. The filename is left alone - app.py and the
    # caption tests both look for segment_N_audio.mp3 - and the tone is
    # recorded beside it instead.
    from pipeline.delivery import resolve_tone
    tone_key = resolve_tone(narrative_tone)
    tone_marker = output_path + ".tone"

    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        cached_tone = ""
        try:
            with open(tone_marker, "r", encoding="utf-8") as tf:
                cached_tone = tf.read().strip()
        except OSError:
            pass
        if cached_tone == tone_key:
            if on_progress:
                on_progress(f"Segment {segment_id} — voiceover already cached, skipping")
            return output_path
        if on_progress:
            on_progress(f"Segment {segment_id} — tone changed, re-recording")
        try:
            os.unlink(output_path)
        except OSError:
            pass

    Path(cache_dir).mkdir(parents=True, exist_ok=True)

    voice_lower = voice.lower()
    is_gemini_tts = "gemini-3.1-flash-tts" in voice_lower
    is_google = voice_lower.startswith("google:")
    is_google_tts = is_google and not is_gemini_tts
    is_supertonic = (
        voice_lower.startswith("local:supertonic")
        or voice_lower.startswith("supertonic:")
        or voice_lower.startswith("local:piper")
        or voice_lower.startswith("piper:")
    )

    tts_text = narration
    if is_gemini_tts or not is_google:
        # Strip any SSML tags so non-SSML engines do not read them aloud
        tts_text = re.sub(r'<[^>]+>', '', narration)

    if is_supertonic:
        # Run local offline Supertonic
        _generate_with_local_supertonic(
            narration=tts_text,
            voice=voice,
            voice_rate=voice_rate,
            output_path=output_path,
            on_progress=on_progress,
            segment_id=segment_id,
            narrative_tone=narrative_tone
        )

    elif is_gemini_tts:
        # Run Gemini 3.1 Flash TTS Preview
        if on_progress:
            on_progress(f"Segment {segment_id} — Generating Gemini 3.1 Flash TTS voiceover")
        _generate_with_gemini_tts(
            narration=tts_text,
            voice=voice,
            google_api_key=google_api_key,
            output_path=output_path,
            voice_steering=voice_steering,
            on_progress=on_progress,
            segment_id=segment_id
        )

    elif is_google_tts:
        # Run Google Premium Cloud TTS
        if on_progress:
            on_progress(f"Segment {segment_id} — Generating Google Premium voiceover ({voice})")
        _generate_with_google_tts(
            narration=tts_text,
            voice=voice,
            voice_rate=voice_rate,
            voice_pitch=voice_pitch,
            google_api_key=google_api_key,
            output_path=output_path,
            on_progress=on_progress,
            segment_id=segment_id,
            cache_dir=cache_dir
        )

    elif voice_lower.startswith("local:kokoro") or voice_lower.startswith("kokoro:"):
        _generate_with_local_kokoro(
            narration=tts_text,
            voice=voice,
            voice_rate=voice_rate,
            output_path=output_path,
            on_progress=on_progress,
            segment_id=segment_id,
            narrative_tone=narrative_tone
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
            
        _generate_with_edge_tts(tts_text, clean_voice, voice_rate, voice_pitch, output_path)

    try:
        with open(tone_marker, "w", encoding="utf-8") as tf:
            tf.write(tone_key)
    except OSError:
        pass

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError(
            f"Segment {segment_id}: voiceover file was not created. "
            "Check network connection or API status and try again."
        )

    if _mastering_enabled():
        if on_progress:
            on_progress(f"Segment {segment_id} — mastering narration audio")
        master_audio(output_path)

    return output_path


def _mastering_enabled() -> bool:
    """config/settings.json → master_narration_audio (default on)."""
    try:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(base, "config", "settings.json"), "r", encoding="utf-8") as f:
            return bool(json.load(f).get("master_narration_audio", True))
    except Exception:
        return True


def get_audio_duration(mp3_path: str) -> float:
    from moviepy.editor import AudioFileClip
    with AudioFileClip(mp3_path) as clip:
        return clip.duration

def stitch_master_audio(segment_audio_paths: list[str], output_path: str):
    ffmpeg = _find_ffmpeg()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        list_file = f.name
        for path in segment_audio_paths:
            safe_path = path.replace("\\", "/")
            f.write(f"file '{safe_path}'\n")
    try:
        cmd = [
            ffmpeg, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_file,
            "-c", "copy",
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg master audio concat failed: {result.stderr}")
    finally:
        if os.path.exists(list_file):
            os.remove(list_file)
    return output_path
