"""
Voiceover Studio — standalone speech generation for Smart Studio.

Separate from pipeline/voiceover.py, which is bound to the script-to-video
pipeline (segment ids, caching, storyboard timing). This module is for the
Voiceover Studio tab: give it text and an engine, get an audio file back.

Engines:

    supertonic  Supertonic. Offline, 32 languages, weights already cached.
    edge        Edge-TTS. Cloud, free, no key.
    google      Google Cloud TTS. Cloud, premium voices, uses your API key.
    kokoro      Kokoro 82M ONNX. Offline, small and fast.
    piper       Piper. Offline neural voices, ONNX models on disk.
    openvoice   OpenVoice V2. Zero-shot cloning from a 3-10s reference clip.

Engine availability is probed at runtime rather than assumed, so the UI can
show exactly what is usable and why anything is not.
"""

import json
import os

# Set BEFORE any engine is imported. Supertonic and onnxruntime otherwise grab
# every core, which pins this laptop at 100% CPU during synthesis. Two threads
# is plenty for speech and leaves the machine usable.
os.environ.setdefault("SUPERTONIC_INTRA_OP_THREADS", "2")
os.environ.setdefault("SUPERTONIC_INTER_OP_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "2")

import subprocess
import sys
import time
import uuid
import shutil

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OUTPUT_DIR = os.path.join(BASE_DIR, "output", "voiceover")
PROFILE_DIR = os.path.join(BASE_DIR, "config", "voice_profiles")
PROFILE_INDEX = os.path.join(PROFILE_DIR, "profiles.json")
HISTORY_INDEX = os.path.join(OUTPUT_DIR, "history.json")

OPENVOICE_DIR = r"C:\Users\HomePC\Documents\GitHub\OpenVoice"
OPENVOICE_SCRIPT = os.path.join(OPENVOICE_DIR, "clone_voice.py")
OPENVOICE_PYTHON = r"C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe"

PIPER_DIR = r"C:\Users\HomePC\Documents\GitHub\piper-desktop-skill"
PIPER_SCRIPT = os.path.join(PIPER_DIR, "piper_skill.py")

# Kokoro was installed by an Electron app, so the ONNX weights already exist
# on disk. Reuse them rather than downloading a second copy.
# The Electron copies are transformers.js-format files and fail to load in
# onnxruntime with INVALID_PROTOBUF. Only the official kokoro-onnx release
# files work here, so those are tried first.
KOKORO_MODEL_CANDIDATES = [
    os.path.join(BASE_DIR, "config", "kokoro_models", "kokoro-v1.0.onnx"),
    os.path.join(BASE_DIR, "config", "kokoro_models", "kokoro-v1.0.int8.onnx"),
    os.path.join(BASE_DIR, "config", "kokoro", "kokoro-v1.0.onnx"),
]
KOKORO_VOICES_CANDIDATES = [
    os.path.join(BASE_DIR, "config", "kokoro_models", "voices-v1.0.bin"),
    os.path.join(BASE_DIR, "config", "kokoro", "voices-v1.0.bin"),
]

# Offline engines choke on typographic and currency characters that appear all
# over real marketing scripts. Supertonic hard-fails with
# "Found 1 unsupported character(s): ['₦']" rather than skipping them, so
# normalise before synthesis instead of losing the whole clip.
TEXT_REPLACEMENTS = {
    "₦": " naira ", "$": " dollars ", "£": " pounds ", "€": " euros ",
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": " - ", "…": "...", " ": " ",
    "•": ". ", "×": " x ", "→": " to ", "≥": " at least ",
    "&": " and ", "%": " percent ", "°": " degrees ", "™": "", "®": "", "©": "",
}


def normalise_text(text: str, ascii_only: bool = False):
    """Return (clean_text, notes). Spoken-form substitutions first, then an
    optional ASCII fallback for engines that refuse anything else."""
    notes = []
    out = text
    for bad, good in TEXT_REPLACEMENTS.items():
        if bad in out:
            out = out.replace(bad, good)
            notes.append(bad)
    if ascii_only:
        stripped = "".join(c if ord(c) < 128 else " " for c in out)
        if stripped != out:
            notes.append("non-ASCII characters")
            out = stripped
    out = " ".join(out.split())
    return out, notes


SUPERTONIC_VOICES = ["M1", "M2", "M3", "M4", "M5", "F1", "F2", "F3", "F4", "F5"]

MAX_TEXT_CHARS = 20000
HISTORY_LIMIT = 50

# OpenVoice can take minutes on CPU for a long passage.
CLONE_TIMEOUT_SECONDS = 900
PIPER_TIMEOUT_SECONDS = 300
EDGE_TIMEOUT_SECONDS = 180


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

_supertonic_tts = None       # loaded once, on first use, then reused
_supertonic_model = None


def _get_supertonic(model="supertonic-3"):
    """Load the Supertonic model lazily and keep one instance alive.

    Loading is the slow part (several seconds); synthesis afterwards is quick.
    Holding one instance avoids paying that cost per clip without keeping a
    second copy of the weights in RAM."""
    global _supertonic_tts, _supertonic_model
    if _supertonic_tts is not None and _supertonic_model == model:
        return _supertonic_tts
    from supertonic import TTS as SupertonicTTS
    _supertonic_tts = SupertonicTTS(model=model, auto_download=True,
                                    intra_op_num_threads=2, inter_op_num_threads=1)
    _supertonic_model = model
    return _supertonic_tts


def _first_existing(paths):
    for p in paths:
        if p and os.path.isfile(p):
            return p
    return None


def _ensure_dirs():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(PROFILE_DIR, exist_ok=True)


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def _ffmpeg() -> str | None:
    """Smart Studio vendors ffmpeg; fall back to PATH."""
    vendored = os.path.join(BASE_DIR, "vendor", "ffmpeg", "bin", "ffmpeg.exe")
    if os.path.isfile(vendored):
        return vendored
    return shutil.which("ffmpeg")


def _no_window():
    """Keep subprocesses from flashing a console over the pywebview window."""
    if os.name == "nt":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {"startupinfo": si, "creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def _run(cmd, cwd=None, timeout=300):
    """Run a subprocess and return (returncode, stdout, stderr)."""
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        **_no_window(),
    )
    return proc.returncode, (proc.stdout or "").strip(), (proc.stderr or "").strip()


def _new_output_path(ext="wav", label="clip"):
    _ensure_dirs()
    safe = "".join(c for c in (label or "clip") if c.isalnum() or c in "-_")[:40] or "clip"
    name = f"{time.strftime('%Y%m%d-%H%M%S')}_{safe}_{uuid.uuid4().hex[:6]}.{ext}"
    return os.path.join(OUTPUT_DIR, name)


# ---------------------------------------------------------------------------
# engine probing
# ---------------------------------------------------------------------------

def probe_engines() -> dict:
    """
    Report which engines can actually run right now. The UI uses this to
    disable engines rather than letting the user hit a failure mid-generation.
    """
    engines = {}

    # -- Edge-TTS ----------------------------------------------------------
    try:
        import edge_tts  # noqa: F401
        engines["edge"] = {
            "id": "edge",
            "name": "Edge-TTS (high-quality standard voices)",
            "ready": True,
            "offline": False,
            "supports_cloning": False,
            "supports_pitch": True,
        }
    except Exception as e:
        engines["edge"] = {
            "id": "edge", "name": "Edge-TTS", "ready": False, "offline": False,
            "supports_cloning": False, "supports_pitch": True,
            "blocker": f"edge-tts is not importable: {e}",
            "fix": "pip install edge-tts",
        }

    # -- Piper -------------------------------------------------------------
    piper_models = []
    if os.path.isdir(os.path.join(PIPER_DIR, "models")):
        piper_models = [
            os.path.splitext(f)[0]
            for f in os.listdir(os.path.join(PIPER_DIR, "models"))
            if f.endswith(".onnx")
        ]
    piper_binary = shutil.which("piper")
    engines["piper"] = {
        "id": "piper",
        "name": "Piper TTS (fast offline neural voices)",
        "ready": bool(os.path.isfile(PIPER_SCRIPT) and piper_models and piper_binary),
        "offline": True,
        "supports_cloning": False,
        "supports_pitch": False,
        "models": piper_models,
    }
    if not engines["piper"]["ready"]:
        if not os.path.isfile(PIPER_SCRIPT):
            engines["piper"]["blocker"] = f"piper_skill.py not found at {PIPER_SCRIPT}"
        elif not piper_models:
            engines["piper"]["blocker"] = "No .onnx voice models in the Piper models folder."
        else:
            engines["piper"]["blocker"] = "The 'piper' executable is not on PATH."
            engines["piper"]["fix"] = "Install the Piper binary and add it to PATH."

    # -- Supertonic --------------------------------------------------------
    try:
        import supertonic  # noqa: F401
        engines["supertonic"] = {
            "id": "supertonic",
            "name": "Supertonic (offline, 32 languages)",
            "ready": True,
            "offline": True,
            "supports_cloning": False,
            "supports_pitch": False,
            "voices": SUPERTONIC_VOICES,
            "languages": list(getattr(supertonic, "AVAILABLE_LANGUAGES", ["en"])),
        }
    except Exception as e:
        engines["supertonic"] = {
            "id": "supertonic", "name": "Supertonic", "ready": False, "offline": True,
            "supports_cloning": False, "supports_pitch": False,
            "blocker": f"supertonic is not importable: {e}",
            "fix": "pip install supertonic",
        }

    # -- Google Cloud TTS --------------------------------------------------
    engines["google"] = {
        "id": "google",
        "name": "Google Cloud TTS (premium cloud voices)",
        "ready": True,          # key is checked at generation time
        "offline": False,
        "supports_cloning": False,
        "supports_pitch": True,
        "needs_api_key": True,
    }

    # -- Kokoro ------------------------------------------------------------
    kokoro_model = _first_existing(KOKORO_MODEL_CANDIDATES)
    kokoro_voices = _first_existing(KOKORO_VOICES_CANDIDATES)
    try:
        import kokoro_onnx  # noqa: F401
        kokoro_pkg = True
    except Exception:
        kokoro_pkg = False

    engines["kokoro"] = {
        "id": "kokoro",
        "name": "Kokoro 82M (offline, fast)",
        "ready": bool(kokoro_pkg and kokoro_model and kokoro_voices),
        "offline": True,
        "supports_cloning": False,
        "supports_pitch": False,
        "model_path": kokoro_model,
    }
    if not engines["kokoro"]["ready"]:
        missing = []
        if not kokoro_pkg:
            missing.append("the kokoro-onnx Python package")
        if not kokoro_model:
            missing.append("the Kokoro ONNX weights")
        if not kokoro_voices:
            missing.append("the voices-v1.0.bin voice pack")
        engines["kokoro"]["blocker"] = (
            "Kokoro is installed for your Electron app, not for Python. Missing: "
            + ", ".join(missing) + "."
        )
        fix_parts = []
        if not kokoro_pkg:
            fix_parts.append("pip install kokoro-onnx")
        if not kokoro_voices:
            fix_parts.append(
                "download voices-v1.0.bin into config/kokoro/ from "
                "https://github.com/thewh1teagle/kokoro-onnx/releases"
            )
        engines["kokoro"]["fix"] = " && ".join(fix_parts)

    # -- OpenVoice V2 ------------------------------------------------------
    ov = {
        "id": "openvoice",
        "name": "OpenVoice V2 (local instant voice cloning)",
        "ready": False,
        "offline": True,
        "supports_cloning": True,
        "supports_pitch": False,
    }
    if not os.path.isfile(OPENVOICE_SCRIPT):
        ov["blocker"] = f"clone_voice.py not found at {OPENVOICE_SCRIPT}"
    elif not os.path.isfile(OPENVOICE_PYTHON):
        ov["blocker"] = f"Python interpreter not found at {OPENVOICE_PYTHON}"
    else:
        try:
            rc, out, err = _run(
                [OPENVOICE_PYTHON, OPENVOICE_SCRIPT, "--probe"],
                cwd=OPENVOICE_DIR, timeout=120,
            )
            data = json.loads(out.splitlines()[-1]) if out else {}
            ov["ready"] = bool(data.get("ready"))
            ov["languages"] = data.get("languages", [])
            ov["device"] = "cuda" if data.get("cuda") else "cpu"
            if not ov["ready"]:
                ov["blocker"] = data.get("blocker") or "OpenVoice reported it is not ready."
                if not data.get("melo"):
                    ov["fix"] = (
                        f'"{OPENVOICE_PYTHON}" -m pip install '
                        "git+https://github.com/myshell-ai/MeloTTS.git "
                        f'&& "{OPENVOICE_PYTHON}" -m unidic download'
                    )
        except subprocess.TimeoutExpired:
            ov["blocker"] = "OpenVoice probe timed out."
        except Exception as e:
            ov["blocker"] = f"OpenVoice probe failed: {e}"
    engines["openvoice"] = ov

    return engines


# ---------------------------------------------------------------------------
# generation
# ---------------------------------------------------------------------------

def _speed_to_edge_rate(speed: float) -> str:
    pct = int(round((float(speed) - 1.0) * 100))
    return f"{pct:+d}%"


def _pitch_to_edge(pitch_semitones: float) -> str:
    hz = int(round(float(pitch_semitones) * 20))
    return f"{hz:+d}Hz"


def _generate_edge(text, output_path, voice, speed, pitch):
    import asyncio
    import edge_tts

    async def go():
        communicate = edge_tts.Communicate(
            text=text,
            voice=voice or "en-US-AriaNeural",
            rate=_speed_to_edge_rate(speed),
            pitch=_pitch_to_edge(pitch),
        )
        await communicate.save(output_path)

    try:
        asyncio.run(go())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(go())
        finally:
            loop.close()

    if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError("Edge-TTS produced no audio.")
    return {"engine": "edge", "voice": voice}


def _generate_piper(text, output_path, model, speed):
    cmd = [sys.executable, PIPER_SCRIPT, text, "-o", output_path]
    if model:
        cmd += ["-m", model]
    rc, out, err = _run(cmd, cwd=PIPER_DIR, timeout=PIPER_TIMEOUT_SECONDS)
    if rc != 0 or not os.path.isfile(output_path):
        raise RuntimeError(err or out or "Piper produced no audio.")
    return {"engine": "piper", "voice": model}


def _generate_openvoice(text, output_path, reference_audio, language, speed):
    if not reference_audio or not os.path.isfile(reference_audio):
        raise RuntimeError("A reference voice clip is required for OpenVoice cloning.")

    cmd = [
        OPENVOICE_PYTHON, OPENVOICE_SCRIPT,
        "--ref", reference_audio,
        "--text", text,
        "--out", output_path,
        "--language", language or "EN",
        "--speed", str(speed),
    ]
    try:
        rc, out, err = _run(cmd, cwd=OPENVOICE_DIR, timeout=CLONE_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"Cloning timed out after {CLONE_TIMEOUT_SECONDS // 60} minutes. "
            "On CPU, long passages are slow — try a shorter script."
        )

    payload = {}
    if out:
        for line in reversed(out.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    payload = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue

    if not payload.get("ok"):
        raise RuntimeError(payload.get("error") or err or out or "OpenVoice failed with no message.")
    if not os.path.isfile(output_path):
        raise RuntimeError("OpenVoice reported success but wrote no file.")

    return {
        "engine": "openvoice",
        "device": payload.get("device"),
        "language": payload.get("language"),
        "clone_seconds": payload.get("seconds"),
    }


def _generate_supertonic(text, output_path, voice, speed, model="supertonic-3", lang=None):
    text, notes = normalise_text(text, ascii_only=True)
    if not text:
        raise RuntimeError("Nothing speakable left after removing unsupported characters.")
    tts = _get_supertonic(model)
    voice_name = (voice or "M1").upper()
    if voice_name not in SUPERTONIC_VOICES:
        voice_name = "M1"
    style = tts.get_voice_style(voice_name=voice_name)

    # Supertonic uses lowercase two-letter codes ('en'), while OpenVoice uses
    # 'EN' / 'EN-BR'. Normalise, and fall back to the model default rather than
    # erroring out on a code this engine does not know.
    import supertonic as _st
    supported = [c.lower() for c in getattr(_st, "AVAILABLE_LANGUAGES", ["en"])]
    code = (lang or "").split("-")[0].lower() or None
    if code not in supported:
        code = None

    wav = tts.synthesize(text, voice_style=style, speed=float(speed), lang=code)
    if isinstance(wav, tuple):
        wav = wav[0]
    tts.save_audio(wav, output_path)
    if not os.path.isfile(output_path):
        raise RuntimeError("Supertonic produced no audio file.")
    return {"engine": "supertonic", "voice": voice_name, "model": model,
            "text_normalised": notes or None}


def _generate_google(text, output_path, voice, speed, pitch, api_key):
    """Google Cloud Text-to-Speech over the REST API (same key the render
    pipeline already uses). No extra Python package required."""
    import base64
    import requests

    if not api_key:
        raise RuntimeError(
            "Google TTS needs an API key. Add it under Settings — it is the same "
            "key the render pipeline uses for premium voices."
        )

    voice_name = (voice or "en-US-Neural2-F").replace("google:", "")
    parts = voice_name.split("-")
    language_code = "-".join(parts[:2]) if len(parts) >= 2 else "en-US"

    payload = {
        "input": {"text": text},
        "voice": {"languageCode": language_code, "name": voice_name},
        "audioConfig": {
            "audioEncoding": "MP3",
            "speakingRate": max(0.25, min(4.0, float(speed))),
            "pitch": max(-20.0, min(20.0, float(pitch))),
        },
    }
    resp = requests.post(
        f"https://texttospeech.googleapis.com/v1beta1/text:synthesize?key={api_key}",
        json=payload, timeout=120,
    )
    if resp.status_code != 200:
        detail = ""
        try:
            detail = resp.json().get("error", {}).get("message", "")
        except Exception:
            detail = resp.text[:200]
        raise RuntimeError(f"Google TTS refused the request ({resp.status_code}). {detail}")

    audio_b64 = resp.json().get("audioContent")
    if not audio_b64:
        raise RuntimeError("Google TTS returned no audio.")
    with open(output_path, "wb") as f:
        f.write(base64.b64decode(audio_b64))
    return {"engine": "google", "voice": voice_name, "language": language_code}


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


def _generate_kokoro(text, output_path, voice, speed):
    try:
        from kokoro_onnx import Kokoro
    except Exception:
        raise RuntimeError(
            "kokoro-onnx is not installed. The 82M ONNX weights are already on "
            "this machine from your Electron app; only the Python wrapper and the "
            "voice pack are missing."
        )
    model_path = _first_existing(KOKORO_MODEL_CANDIDATES)
    voices_path = _first_existing(KOKORO_VOICES_CANDIDATES)
    if not model_path:
        raise RuntimeError("Kokoro ONNX model not found on disk.")
    if not voices_path:
        raise RuntimeError("Kokoro voices pack (voices-v1.0.bin) not found.")

    text, _ = normalise_text(text)
    import soundfile as sf
    # Same trap as pipeline/voiceover.py: kokoro-onnx makes its own session and
    # ignores the SUPERTONIC_*/OMP thread caps set at the top of this module.
    kokoro = _build_kokoro(Kokoro, model_path, voices_path)
    samples, sample_rate = kokoro.create(text, voice=voice or "af_heart",
                                         speed=float(speed), lang="en-us")
    sf.write(output_path, samples, sample_rate)
    if not os.path.isfile(output_path):
        raise RuntimeError("Kokoro produced no audio file.")
    return {"engine": "kokoro", "voice": voice}


def _to_mp3(wav_path: str) -> str | None:
    ff = _ffmpeg()
    if not ff:
        return None
    mp3_path = os.path.splitext(wav_path)[0] + ".mp3"
    rc, _, err = _run([ff, "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-q:a", "2", mp3_path], timeout=180)
    return mp3_path if rc == 0 and os.path.isfile(mp3_path) else None


def synthesize(
    engine: str,
    text: str,
    voice: str = "",
    reference_audio: str = "",
    language: str = "EN",
    speed: float = 1.0,
    pitch: float = 0.0,
    label: str = "clip",
    also_mp3: bool = True,
    google_api_key: str = "",
) -> dict:
    """
    Generate one audio clip. Returns {ok, path, mp3, meta} or {ok: False, error}.
    """
    _ensure_dirs()

    text = (text or "").strip()
    if not text:
        return {"ok": False, "error": "Enter some text to speak."}
    if len(text) > MAX_TEXT_CHARS:
        return {"ok": False, "error": f"Text is too long ({len(text)} chars). Limit is {MAX_TEXT_CHARS}."}

    try:
        speed = max(0.5, min(2.0, float(speed)))
    except (TypeError, ValueError):
        speed = 1.0
    try:
        pitch = max(-12.0, min(12.0, float(pitch)))
    except (TypeError, ValueError):
        pitch = 0.0

    ext = "mp3" if engine in ("edge", "google") else "wav"
    output_path = _new_output_path(ext=ext, label=label)
    started = time.time()

    try:
        if engine == "edge":
            meta = _generate_edge(text, output_path, voice, speed, pitch)
        elif engine == "supertonic":
            meta = _generate_supertonic(text, output_path, voice, speed, lang=language)
        elif engine == "google":
            meta = _generate_google(text, output_path, voice, speed, pitch, google_api_key)
        elif engine == "kokoro":
            meta = _generate_kokoro(text, output_path, voice, speed)
        elif engine == "piper":
            meta = _generate_piper(text, output_path, voice, speed)
        elif engine == "openvoice":
            meta = _generate_openvoice(text, output_path, reference_audio, language, speed)
        else:
            return {"ok": False, "error": f"Unknown engine '{engine}'."}
    except Exception as e:
        # Leave no half-written file behind.
        if os.path.isfile(output_path):
            try:
                os.remove(output_path)
            except OSError:
                pass
        return {"ok": False, "error": str(e)}

    mp3_path = None
    if also_mp3 and ext == "wav":
        mp3_path = _to_mp3(output_path)

    entry = {
        "id": uuid.uuid4().hex[:12],
        "path": output_path,
        "mp3": mp3_path,
        "engine": engine,
        "label": label,
        "text_preview": text[:120],
        "chars": len(text),
        "speed": speed,
        "pitch": pitch,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed": round(time.time() - started, 2),
        "meta": meta,
    }
    _append_history(entry)

    return {"ok": True, "path": output_path, "mp3": mp3_path, "entry": entry}


# ---------------------------------------------------------------------------
# voice profiles
# ---------------------------------------------------------------------------

def list_profiles() -> list:
    return _read_json(PROFILE_INDEX, [])


def save_profile(name: str, reference_audio: str, language: str = "EN") -> dict:
    """Copy the reference clip into the app so the profile survives the
    original file being moved or deleted."""
    _ensure_dirs()
    name = (name or "").strip()
    if not name:
        return {"ok": False, "error": "Give the voice profile a name."}
    if not reference_audio or not os.path.isfile(reference_audio):
        return {"ok": False, "error": "Reference audio file not found."}

    ext = os.path.splitext(reference_audio)[1].lower() or ".wav"
    if ext not in (".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm"):
        return {"ok": False, "error": f"Unsupported reference audio type '{ext}'."}

    pid = uuid.uuid4().hex[:10]
    stored = os.path.join(PROFILE_DIR, f"{pid}{ext}")
    try:
        shutil.copyfile(reference_audio, stored)
    except Exception as e:
        return {"ok": False, "error": f"Could not store the reference clip: {e}"}

    profiles = list_profiles()
    profiles = [p for p in profiles if p.get("name", "").lower() != name.lower()]
    profiles.append({
        "id": pid,
        "name": name,
        "reference": stored,
        "language": language or "EN",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    _write_json(PROFILE_INDEX, profiles)
    return {"ok": True, "profiles": profiles}


def delete_profile(profile_id: str) -> dict:
    profiles = list_profiles()
    target = next((p for p in profiles if p.get("id") == profile_id), None)
    if not target:
        return {"ok": False, "error": "Profile not found."}
    try:
        if target.get("reference") and os.path.isfile(target["reference"]):
            os.remove(target["reference"])
    except OSError:
        pass
    profiles = [p for p in profiles if p.get("id") != profile_id]
    _write_json(PROFILE_INDEX, profiles)
    return {"ok": True, "profiles": profiles}


# ---------------------------------------------------------------------------
# history
# ---------------------------------------------------------------------------

def _append_history(entry: dict):
    history = _read_json(HISTORY_INDEX, [])
    history.insert(0, entry)
    _write_json(HISTORY_INDEX, history[:HISTORY_LIMIT])


def list_history() -> list:
    history = _read_json(HISTORY_INDEX, [])
    # Drop entries whose audio has since been deleted from disk.
    live = [h for h in history if h.get("path") and os.path.isfile(h["path"])]
    if len(live) != len(history):
        _write_json(HISTORY_INDEX, live)
    return live


def clear_history() -> dict:
    _write_json(HISTORY_INDEX, [])
    return {"ok": True}
