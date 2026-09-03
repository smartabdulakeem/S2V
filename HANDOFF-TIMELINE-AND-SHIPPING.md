# Handoff — Smart Studio, 3 Sep 2026

Paste this whole file into a new chat to pick the work up cold. It is the only thing the owner
pastes. It supersedes `HANDOFF-PICTURE-BOUNDARIES.md` for everything after 2 Sep.

## Which document goes where

| Document | Who reads it |
|---|---|
| **This file** | **The new chat.** The owner pastes it in. |
| `PLAN-REVISION-FRONTEND-FIRST.md` | **Read second.** The slice plan, A-F, and why the old plan's ordering was wrong. |
| `STRATEGIC-WORKBENCH-AND-PLAN-REVISION.md` | The owner's 3-stage blueprint, written with Antigravity. |
| `ACCEPTANCE-FINDINGS.md` | Why 15 pictures beat 60, and why Task 13's metric was broken. |
| `docs/superpowers/plans/2026-09-01-model-chosen-picture-boundaries.md` | 80 KB, from disk. **Never ask the owner to paste it.** Its engine work stands; its ordering and scope decisions are superseded. |

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget` — **153 commits ahead, nothing pushed. Do not push.**
**Python:** `C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe` (not on PATH).
Prefix anything printing prompt text with `PYTHONIOENCODING=utf-8`.
**Suite: 708 passed, 1 xfailed, 0 failures. ~11 minutes.**

**Gemini works** on `gemini-2.5-flash` and is the only live LLM key. Provider chain is
anthropic → openai → gemini → deepseek; the first two are cleared, DeepSeek is never reached.

## How the work runs

The owner is **not a programmer**. He tests through the front end and cannot review code.

1. Claude writes a brief as `ANTIGRAVITY-<TOPIC>.md` in the repo root.
2. The owner hands the whole file to Antigravity, which writes code and **stops**.
3. The owner says "Antigravity is done".
4. Claude reviews the working tree, fixes what is wrong, runs the suite, and **commits**.

Never run two Antigravity tasks at once — on 30 Aug two agents edited one file inside ninety
seconds and nobody could say what it contained. That is why `ANTIGRAVITY-RULES.md` exists.

---

## What happened on 2-3 Sep

Five commits. Every claim below was measured, not assumed.

### `752dd81` — Slice A: the dead controls go

All 106 buttons were inventoried and the owner approved each row. `index.html` went **92 → 78**.

Twelve of the fourteen removals had **never done anything**: five whole Settings sections —
Defaults, Spending, Performance, Pronunciation dictionary, Language packs — with hardcoded values
and zero code behind them. The Spending panel reported "$3.12 this month" from a literal in the
HTML.

`Render video` moved off the Storyboard to the Timeline. **`Open in Timeline` was built** — stage
2 → 3 had no door at all. The rail now reads Script 1, Storyboard 2, Timeline 3, a rule, then
Render / Library / Voiceover as tools. Their `4` `5` `6` badges advertised keyboard shortcuts that
were never implemented.

`tests/test_frontend_controls.py` is the **first test to guard the frontend**, which is why seven
dead buttons survived. It asserts every button calls a function that exists.

### `c14ec96` — the GPL blockers go, so the app can be sold

**edge-tts was GPL-3.0 and imported directly** (`import edge_tts`), making all of Smart Studio a
derivative work. It was also the catch-all every unrecognised voice fell into, and it called a
private Microsoft endpoint. Kokoro took over via `FALLBACK_VOICE`; saved `edge:` and `gemini:`
voices resolve there rather than raising.

`vendor/piper/` deleted — `espeak-ng.dll` inside it is GPL-3. Nothing invoked `piper.exe`.
Also deleted: `vcomp140d.dll` (Microsoft's **debug** runtime, which their terms forbid
redistributing) and `onepiece_demo.mp4` (copyrighted anime footage from the Real-ESRGAN release).

`THIRD-PARTY-NOTICES.txt` is new, covering 19 components. Nothing under `vendor/` had carried a
licence file, so the permissive dependencies were quietly out of compliance too.

### `184409c` — Slice D: the Timeline plays

One concatenated narration file per film, one `<audio>` element. `audio.currentTime` **is** the
playhead, so there is nothing to keep in sync.

`pipeline/timeline_audio.py` builds it with the ffmpeg concat demuxer and a stream copy, cached
against segment ids, audio paths and mtimes. **Drift on the owner's real film: 2.0 ms across 347
segments and 19 minutes.** A re-encode fallback stands behind it past 100 ms.

### `e90b5fb` — fast export, and audio the window will actually play

**The WolfCut timeline no longer costs a render.** This was Task 11 of the old plan and had never
been built. `write_wolfcut_project` measures nothing and `timing_maps` already returned its two
arguments; the two functions had simply never been introduced. **Measured: 0.09 seconds** for 347
segments, 18 picture clips, 554 KB.

**Slice D did not play in the desktop app.** The cause was already documented at `app.py:405` —
WebView2 refuses `file://` URLs as subresources, which is why every image in this app is a base64
data URI — and the audio src was built with `pathlib.as_uri()`. Media now goes over HTTP from
`media_server.py`: ephemeral port on 127.0.0.1, daemon thread, started once, serving only
`projects/`, `cache/` and `output/` with a startup token. `tools/devserver.py` shares the same
handler.

Verified against the real 27,833,517-byte track: served whole; a range request returned 206 with
bytes matching that slice exactly; seeking ten minutes in played on from there; `settings.json`
and a missing token both refused 403.

---

## The three-stage pipeline, and where it stands

```
STAGE 1  Script      narration, voice, formats        →  Plan storyboard →
STAGE 2  Storyboard  prompts out, images in, check    →  Open in Timeline →
STAGE 3  Timeline    watch it, fix it, render it      →  Render film
```

| | |
|---|---|
| ✅ Slice A | dead controls, rail, stage handoffs |
| ✅ Licence cleanup | GPL blockers gone |
| ✅ Slice D | playback built, media served over HTTP |
| ✅ Fast export | `.wolfcut` in 0.09s |
| ⏳ **ffmpeg** | **decided, unbuilt** — last shipping blocker |
| ⏳ Slice B | camera amount slider + window size persistence |
| ⏳ Slice C | move `Measure narration` to the Script screen |
| ⏳ Slice E | drag boundaries while listening |
| ⏳ Slice F | music + SFX tracks |
| 🔜 Slice G | Lemon Squeezy, after the product works |

---

## Open items, in the order they matter

### 1. Nobody has pressed play in the real window

Everything about playback was verified through the dev server and by driving the media server
directly. `http://127.0.0.1` is the ordinary case that `file://` was not, but **it is unconfirmed.**
The owner must restart the desktop app — Python loads once at launch — and press play. If it is
silent, that is the first thing to debug and it is not a guess about anything else.

His film `projects/Before_Adam_The_Story_of_Iblis` has all 347 lines measured and
`timeline_narration.mp3` built beside it, 1159.7 seconds. Nothing needs rebuilding.

### 2. ffmpeg — decided, not built

`vendor/ffmpeg/bin/` is a GPL-3 build (`--enable-gpl --enable-version3`). **The owner chose:
do not bundle it.** The app looks for ffmpeg on PATH with a friendly first-run check.

**The trap:** there is a *second* GPL ffmpeg. `moviepy` depends on `imageio_ffmpeg`, which ships
its own at `site-packages/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe` — also
`--enable-gpl`. PyInstaller would sweep it into the installer. Any fix must handle both.

There are also **three** ffmpeg finders now: `composer._find_ffmpeg`, `stitcher._find_ffmpeg`, and
the vendor-first logic in each. They should collapse to one.

### 3. Music, SFX and "make it a real editor"

The owner asked whether the Timeline can take **external audio, background music, sound effects,
and external video** — a full editing surface.

**Most of the audio half already exists in the render pipeline and has no UI:**

- `pipeline/sound.py` — ambient beds, matched on the query a sound was fetched with, ducked under
  the voice. Its docstring says the schema carried an `sfx` field and the compositor an
  `_overlay_sound_effects` mixer for a long time, and nothing ever chose a sound.
- `pipeline/stitcher.py` takes `background_music` and mixes it in a second ffmpeg pass.
- `orchestrator.py:466` passes `sfx=seg.get("sfx")`; `:510` passes
  `background_music=proj.get("background_music")`.
- The Library screen already has a Sounds tab and `library/sounds/manifest.jsonl`.

So **Slice F is smaller than it looks** — it is mostly a Timeline UI over a working backend.

**External video and general clip editing is a different question and should not be assumed in.**
That is what Concat (formerly WolfCut) *is*: a Rust engine plus a React front end. The `.wolfcut`
export now costs 0.09 seconds, so the cheap answer is to finish in Concat. This is an open
decision for the owner, recorded here rather than settled.

### 4. Supertonic vs Kokoro

Both work. Measured 3 Sep on this machine, first call in a fresh process:

| | cold start | languages | licence |
|---|---|---|---|
| **Supertonic** | **4.7 s** | **English + Arabic** | code MIT, **weights OpenRAIL-M** |
| **Kokoro** | 27.3 s | en-US / en-GB only | Apache-2.0 |

Supertonic loads nearly six times faster and speaks Arabic, which matters for Islamic-history
films. Kokoro's licence is cleaner: OpenRAIL-M permits commercial use but **requires attribution
and requires its use restrictions to be passed to end users**, which is marked `TODO(owner)` in
`THIRD-PARTY-NOTICES.txt` and needs an EULA clause.

`FALLBACK_VOICE` is currently `local:kokoro-bm_george`. Whether Supertonic should be the default
is the owner's call and has not been made.

### 5. Known, deliberately untouched

- **`app.py:445` still returns `file://` URLs for images**, directly contradicting the docstring at
  `app.py:405`. Same bug class as the playback failure. The media server is now the clean fix.
  If storyboard thumbnails ever show as grey placeholders in the desktop app, this is why.
- **`civil_war_sample.json` names `edge:en-US-BrianNeural`** — an engine that no longer exists. It
  works through the Kokoro fallback, so `test_parallel.py`'s real-render test is quietly exercising
  a migration path rather than a voice.
- **`Measure narration` is slow** — 347 lines synthesised one at a time, plus a cold model load. Two
  levers: a worker pool (ONNX is capped to 2 threads, so there is headroom) and skipping unchanged
  lines. Neither chosen.
- **Slice C is blocked on a real change.** `Measure narration` cannot simply move to the Script
  screen: it needs `currentScriptData.segments`, which do not exist until `parse_plain_text()` runs
  — and that call parses *and* plans in one step. Splitting them is the actual task.

### 6. Payment

**Lemon Squeezy**, chosen over Paddle and Paystack because it has a real licence-key API
(activate / validate / deactivate with seat limits) and is merchant of record. **Deliberately
deferred until the product is complete.** Nothing is built. The owner must verify payout support
for his country before committing, and both vendors want a live product page before they approve
a seller.

Trial design discussed, not built: 14 days **and** 3 renders, whichever comes first; meter only the
trial, because "unlimited after subscription" means the server only answers *is this licence
active*. Three routes and a small table. Never upload script content.

### 7. Phosphor Icons

Downloaded to `C:\Users\HomePC\Documents\Design_Assets\Phosphor_Icons\` (9,072 SVGs plus web
fonts). Use the **web font**, not the SVGs — `index.html` is already 52 KB and at its inline-style
cap. Copy only `regular` and `duotone` into `frontend/vendor/phosphor/`, because the page loads
from `file://`. **No LICENCE file came with the download**; Phosphor is MIT and needs its text in
`THIRD-PARTY-NOTICES.txt` before shipping.

---

## Ground rules

- **Never `git add -A`** — stages ~816 MB including two 310 MB ONNX models. Explicit paths only.
- **Do not push.** The owner tests first and will say when.
- **`config/settings.json` is gitignored and holds live API keys.** Never print or commit it.
- **`config/settings.backup-20260902-010212.json` is NOT gitignored and contains real keys.** It
  sits untracked in the working tree. One `git add -A` puts his keys in history.
- `config/series_overrides/` is gitignored — his niches exist nowhere else.
- **`vendor/` and `projects/` are gitignored.** Deletions there never appear in a diff, so say what
  was deleted.
- **Do not weaken a test.** If one must change, quote it before and after and justify it.
- **Repo files are CRLF.** The Edit/Write tools sometimes write LF — check byte counts.
- **Inline `style="` in `index.html` is capped at 19 and is at 19.** Layout goes in `style.css`.
- **Restarting matters.** The desktop app loads Python once at launch; the dev server imports
  `app.py` once at startup. Say so whenever asking him to retest.
- **Do not run the suite while doing anything else heavy.** `test_parallel.py` runs a real
  two-minute render and will fail if starved of CPU. It did on 3 Sep, purely from concurrent
  testing, and nothing was wrong with the code.

## How to report to him

Lead with the verdict, then **✅ What's done** (in terms of the film, not the code) ·
**⏳ What's left** · **▶️ What we can do now** (one next action). Numbers not adjectives. No jargon
without a plain-English gloss. Say plainly when something is broken or unverified. Full `C:\...`
paths, literal commands in code blocks.

## Where the code is

| What | Where |
|---|---|
| **Media over HTTP to the page** | `media_server.py` — `start_media_server`, `serve_media`, `is_path_allowed` |
| **The film's single narration track** | `pipeline/timeline_audio.py` — `build_timeline_audio` |
| Measured seconds and the two maps | `pipeline/narration_timing.py` — `measure_narration`, `timing_maps`, `segment_seconds` |
| Split / join one boundary | `pipeline/picture_plan.py` — `split_picture`, `merge_picture`, `picture_boundaries` |
| Numbered folder images → pictures | `pipeline/library.py` — `number_pictures_from_folder` |
| Voice routing and the fallback | `pipeline/voiceover.py` — `generate_voiceover`, `FALLBACK_VOICE` |
| Ambient sound beds (no UI yet) | `pipeline/sound.py` |
| Background music mix | `pipeline/stitcher.py` — `background_music` |
| WolfCut document | `pipeline/wolfcut_export.py` — `write_wolfcut_project` |
| Timeline endpoints | `app.py` — `prepare_timeline_audio`, `export_wolfcut_timeline`, `_resolve_project_dir` |
| Timeline UI and playback | `frontend/app.js` — `renderTimelineScreen`, `timelineTogglePlay`, `tlAnimLoop`, `timelineSeek` |
| Storyboard UI | `frontend/app.js` — `renderStoryboardScreen`, `picturesFromScript`, `replanPictures` |
| **Run the app in a browser** | `tools/devserver.py` — then `http://127.0.0.1:8765/` |
