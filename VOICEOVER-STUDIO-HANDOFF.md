# Smart Studio — Voiceover Studio Handoff

**Last updated:** 25 Aug 2026 · **App:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`

Paste this into a new chat to pick the work up cold.

---

## What Smart Studio is

A **PyWebView desktop app** — Python backend, vanilla JS frontend. No React, no build step.

```
app.py                    class Api  — every method here is callable from JS
                          as window.pywebview.api.<method>()
frontend/index.html       nav rail + <div class="pane" data-pane="X">
frontend/app.js           main UI (76KB) — switchPane() lives here
frontend/voice_studio.js  Voiceover Studio UI (separate module, loaded after app.js)
pipeline/voice_studio.py  Voiceover Studio backend
pipeline/voiceover.py     the OLDER script-to-video narration path — different thing,
                          do not confuse the two
config/settings.json      API keys
output/voiceover/         generated clips + history.json
```

Run it with `run.bat`. The Voiceover Studio is tab **5**.

Python is **not** on PATH under that name — always use the full path:
```
C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe
```

---

## Engine status (all verified by generating real audio)

| Engine | State | Notes |
|---|---|---|
| **Supertonic** | ✅ Working | Offline, 10 voices (M1–M5, F1–F5), 32 languages. ~8s first clip, ~3s after |
| **Edge-TTS** | ✅ Working | Cloud, free, no key. Has Nigerian voices (Ezinne, Abeo) |
| **Google Cloud TTS** | ✅ Working | Cloud, uses the key already in Settings. 14 verified voices |
| **Kokoro** | ✅ Working | Offline, ~11s per clip |
| **Piper** | ⚠️ Not ready | `piper` binary not on PATH. Recommend skipping — Supertonic and Kokoro cover offline better |
| **OpenVoice V2** | ⚠️ Not ready | Needs MeloTTS. See below |

---

## Three bugs fixed on 25 Aug — do not regress these

### 1. Supertonic died on real marketing copy

Supertonic **hard-fails** on characters outside its set rather than skipping them:

```
Found 1 unsupported character(s): ['₦']
```

Every naira sign, smart quote and em dash killed the whole clip. Fixed with `normalise_text()` in `pipeline/voice_studio.py` — spoken-form substitutions (`₦` → " naira ", `&` → " and ", `%` → " percent "), then an ASCII fallback for Supertonic specifically. What got changed is reported back in `entry.meta.text_normalised`.

**Keep the `ascii_only=True` flag on the Supertonic path.** Without it, the engine fails on the exact copy this business writes.

### 2. Kokoro pointed at an unloadable model

There are two Kokoro installs on this machine:

- `%APPDATA%\oro-sas\models\kokoro\...\model_quantized.onnx` — **transformers.js format, fails in onnxruntime with `INVALID_PROTOBUF`.** This belongs to an Electron app; Python cannot use it.
- `config\kokoro_models\kokoro-v1.0.onnx` (310MB) + `voices-v1.0.bin` (28MB) — the official kokoro-onnx release files. **These are the ones that work.**

`KOKORO_MODEL_CANDIDATES` now lists `config\kokoro_models\` first. Do not add the Electron paths back.

### 3. Two Google voices did not exist

`en-NG-Standard-A` and `en-NG-Standard-B` were listed in the UI but return HTTP 400 — **Google has no en-NG voices at all.** The list in `frontend/voice_studio.js` is now 14 voices, every one of which was called against this account key and returned 200. Closest fits to a Nigerian audience are the Indian and Australian Neural2 sets.

**If you add a Google voice, call it first.** Do not add from memory.

---

## OpenVoice V2 — the honest state

`clone_voice.py` at `C:\Users\HomePC\Documents\GitHub\OpenVoice\clone_voice.py` was rewritten. The original extracted a speaker embedding and returned, ignoring `--text`, `--out` and `--speed` — it never produced audio. It now runs the real two-stage pipeline and prints JSON, with a `--probe` mode.

It still cannot run, because **OpenVoice V2 is a tone-colour converter, not a TTS.** Confirmed from the repo's own `docs/USAGE.md` and `demo_part3.ipynb`, both of which import `melo.api`. Something must speak the text before the timbre can be swapped.

```
"C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe" -m pip install git+https://github.com/myshell-ai/MeloTTS.git
"C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe" -m unidic download
```

⚠️ MeloTTS targets Python 3.9 and often fails on 3.12 at `mecab-python3`. It can also disturb the working `torch`. **Do this in a separate venv**, not the main Python.

Check state at any time with:
```
python clone_voice.py --probe
```

---

## GPU — settled, do not revisit

**NVIDIA GeForce MX230, 2GB, driver `26.21.14.4223` (= NVIDIA 442.23, Feb 2020).**

Three independent reasons the GPU is not worth using:

1. That driver caps at CUDA 10.2. Current PyTorch CUDA builds need driver 527+.
2. MX230 is ~256 CUDA cores on a 64-bit bus (~14–16 GB/s). **Slower than this machine's CPU** for models this small.
3. Cost to try: ~2.5GB download, a driver update, larger memory footprint — for a likely slowdown.

Installed torch is `2.5.1+cpu`. **Stay on CPU.**

---

## Performance guardrails (the owner cares about this)

The owner has repeatedly asked that nothing slow the machine down. Currently enforced:

```python
os.environ.setdefault("SUPERTONIC_INTRA_OP_THREADS", "2")
os.environ.setdefault("SUPERTONIC_INTER_OP_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "2")
```

Set **before any engine import** in `pipeline/voice_studio.py`. Without them onnxruntime takes every core and pins the laptop at 100%. Models load lazily; the Supertonic instance is cached module-level so the load cost is paid once per session, not per clip.

**Do not add background workers, watchers or preloading.**

---

## How to test

Never trust the probe alone — generate actual audio:

```bash
cd "C:\Users\HomePC\Documents\GitHub\Smart-Studio"
```

```bash
set PYTHONIOENCODING=utf-8 && "C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe" -c "import sys; sys.path.insert(0,'.'); import app; api=app.Api(); print(api.voice_generate({'engine':'supertonic','text':'Test.','voice':'M1'}))"
```

`PYTHONIOENCODING=utf-8` matters — the Windows console dies on `₦` otherwise, which looks like an engine failure but is not.

Full suite (219 passed, 2 skipped as of 25 Aug):
```bash
"C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe" -m pytest -q
```

---

## Known-open items

1. **Piper** — binary not on PATH. Recommend dropping the engine entirely.
2. **OpenVoice cloning** — blocked on MeloTTS, see above.
3. **Voice profiles / mic recording** — code paths are written and wired but only exercisable once OpenVoice runs, since they exist to feed the cloner.
4. `pipeline/voiceover.py` had Kokoro added to it separately for the video pipeline. That is a **different code path** from `pipeline/voice_studio.py`. Fixing one does not fix the other — check both when touching Kokoro.

---

## Backups on disk

`app.py.pre-voicestudio`, `frontend/index.html.pre-voicestudio`, `frontend/app.js.pre-voicestudio`. Delete once you are confident.
