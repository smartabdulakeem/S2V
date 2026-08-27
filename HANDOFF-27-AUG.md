# Smart Studio — Handoff, 27 Aug 2026

Paste this into a new chat to pick the work up cold.

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget` — the working branch. Not merged, not pushed.
**Remote:** `https://github.com/smartabdulakeem/S2V.git`

---

## Environment

Python is **not** on PATH. Always the full path:

```
C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe
```

Prefix any command that prints prompt or narration text with `PYTHONIOENCODING=utf-8` — the
Windows console dies on `₦` and `—`, which looks like an engine failure but is not.

Run the app with `run.bat`. FFmpeg is vendored at `vendor/ffmpeg/bin/ffmpeg.exe` (8.1.1).

**Full suite takes ~7 minutes. Last measured: `366 passed, 1 failed, 1 xfailed`.**
The one failure is real and pre-existing — see Open Items.

---

## What was completed in the last session

### Narration tone now changes how the script is read

The Tone dropdown was three fixed strings that reached only the LLM planner. It changed the
visual keywords the planner invented and **nothing about the audio** — a motivational speech
and a war documentary came out of Supertonic identical.

A tone is now a **delivery profile** in `pipeline/delivery.py`: reading speed, sentence-end
silence, paragraph silence. Eight tones. Each niche offers the ones written for it under
"Best for this niche"; nothing is hidden.

| Tone | Speed | Sentence gap | Block gap |
|---|---|---|---|
| Urgent news | 1.12× | 0.16s | 0.32s |
| Grave documentary | 0.94× | 0.42s | 0.85s |
| Motivational | 0.96× | 0.60s | 1.60s |

Measured on identical words, three blocks:
`Kokoro urgent 6.51s │ grave 8.27s │ motivational 8.89s`
`Supertonic urgent 7.45s │ grave 8.85s │ motivational 8.64s`

**How each engine gets it:** Supertonic already accepted `silence_duration` and chunks text
itself, so it takes the profile directly. `kokoro-onnx` has no such parameter, so narration is
spoken a block at a time and real silence is stitched between blocks
(`split_blocks` / `join_with_silence`).

Cached audio records its tone in a `segment_N_audio.mp3.tone` sidecar, so changing the tone
re-records instead of replaying the old delivery. The filename is deliberately unchanged —
`app.py` and the caption tests both look for `segment_N_audio.mp3`.

Locked by `tests/test_delivery.py` (28 tests). Commit `cd15f6e`.

### Earlier in the same session

- The **Civil War** niche was removed (10 remain). `civil_war_sample.json` was repointed at
  `world_military_history` because it drives the parallel and validator tests.
- **Six universal visual types** — photoreal, cinematic, black & white, stylised illustration,
  cartoon, 3D render — merge into every niche. 11 types per niche. A pack overrides one by
  reusing the key.
- The **prompt-opening box** no longer fills itself from the coverage pass. It starts blank,
  follows the niche and visual type whenever either changes, and stops updating once the user
  types their own wording.

---

## FFmpeg analysis — read this before starting

**`FFMPEG-CAPABILITIES.md` in the repo root.** Written this session, every claim measured.

The headline: **FFmpeg is already the engine of the whole render**, not something to add. And
**background music and sound effects already work** — `pipeline/sound.py` matches a bed per
scene, loops it, and ducks it under the narration with `sidechaincompress`. The library holds
87 sounds and 12 music beds. What is missing is **control**, not capability: nothing in the UI
lets you pick a bed, set its level, or place a sound effect at a moment.

Recommended order from that document:

1. **Automatic QA pass** — `freezedetect` + `blackdetect` + `silencedetect` over the master.
   All three confirmed present. This catches the ROADMAP B1 bug class directly: 46 placeholder
   cards once survived into a finished 30-minute film because "tests are not eyes". One FFmpeg
   invocation and a parser. Cheapest high-value item on the list.
2. **Quick Sync encoding.** `h264_qsv` **works on this machine** (measured). `h264_nvenc` and
   `h264_amf` both fail. Meanwhile `_get_best_encoder` (`composer.py:61`) claims in its
   docstring to "probe system once at startup" and then probes nothing — it hardcodes
   `libx264 -preset veryfast -crf 21`. Free speed, and it takes load off the CPU, which the
   owner cares about.
   ⚠️ Do not confuse this with the older handoff's "stay on CPU" conclusion. That was about
   **CUDA for the ML models** on a 2 GB MX230 and remains correct. Quick Sync is the Intel
   iGPU's fixed-function video encoder — different chip, different job.
3. **Post-render edit pass** — the owner's actual request, and the largest piece. Worth its own
   spec. Everything needed is present: keyframe-boundary cuts with `-c copy` are lossless and
   near-instant, `-itsoffset` places a sound effect at a timestamp, `amix` lays music over a
   range.
4. Sound control surface, then cross-segment transitions (`xfade` — the stitcher currently uses
   the concat demuxer, so **every scene change is a hard cut**), then pitch/duration fitting
   (`librubberband` is present) and two-pass loudness.

---

## Open items

### 1. Motion variety — asked for, not started

The owner's second request, deferred so the tone work could land first. `MOTION_EFFECTS` is
already `zoom_in / zoom_out / pan_left / pan_right` and `resolve_motion_effect` picks one, but
nothing lets the user choose and there is no variety policy, so a film repeats one move.

Proposal put to the owner, not yet approved: a **motion style** picked per project the way tone
is (Static / Gentle drift / Ken Burns / Dynamic), setting zoom strength and speed, plus
alternation so consecutive shots do not repeat the same move. This is compositor work.

### 2. `test_composer_corner_brightness_vignette_check` is failing

**Real, and pre-existing** — verified by stashing the session's changes and re-running; it
fails identically. The compositor adds **62.2% corner darkening against a 40% limit**
(source 19.7% → output 81.9%). Looks like vignette applied twice, plausibly the
preset-treatment wiring meeting an already-vignetted cached image.

Note this test **skips** when no cached segment of ≥10s exists, so clearing `cache/` hides it.
It is not flaky — it is being skipped.

### 3. 47 images staged for deletion

`library/new image/*.jpg` — the numbered `1_`–`47_` set from *The Battle of the Mud*, showing
as uncommitted deletions. Flagged to the owner twice; not acted on either way. If unintended:
`git checkout -- "library/new image"`

### 4. Settings accordion

Briefed but never confirmed done: **`ANTIGRAVITY-SETTINGS-ACCORDION.md`**. Collapse each
Settings card and each voice engine until clicked. The trap is that
`renderVoiceCatalogueSettings()` rebuilds its container on every voice toggle, so an open
engine must survive the re-render.

### 5. Older roadmap items still open

`ROADMAP.md` is the tracked list. C1 (one-shot-per-segment floor giving 48 images in a
9.4-minute video) and C3 remain untouched and unrelated to this work.

---

## Traps carried forward

1. **`visual_style` is prose, `visual_type` is a key.** `#pt-style` holds the key; the board
   sends the *label* as `visual_style`. Sending the key leaks it into prompts as a world anchor.
2. **`world_anchor` is not a place** — in most packs it carries medium language. Never open a
   prompt with it; `brief_subject` exists for that.
3. **Setting `.value` in JS fires no `change` event.** Restore the niche, `await
   loadStylePresets()`, *then* restore `visual_type`, or the dropdowns desync silently.
4. **`visual_type` means two things.** In `pipeline/visuals.py` it is the image *source*
   (`ai_image` / `stock_photo`). The project's look is threaded as `style_preset`.
5. **`compose_gap_prompt` has 8 call sites** — three in `library.py`, five in `visuals.py`.
6. **The shot cache key is `v3` and includes the treatment.** Audio cache is invalidated by a
   `.tone` sidecar. Both exist so changing a choice actually changes the output.
7. **Kokoro takes every core unless handed a configured session** — `_build_kokoro` uses
   `Kokoro.from_session` with `intra_op_num_threads=2`. Do not simplify it away.
8. **A stale `cache/` causes phantom test failures.** `test_parallel.py` once failed with
   "Segment composition failed" for no code reason; deleting the 2.2 GB `cache/` fixed it.
9. **A git worktree has no gitignored assets** (`vendor/ffmpeg`, `library/images`), so render
   tests always fail there. That proves nothing — stash in the main tree instead.
10. **`git add -A` stages ~816 MB** including two 310 MB ONNX models unless the `.gitignore`
    additions are present. Stage explicit paths.

---

## How the owner works

- Direct, no preamble. Lead with the answer.
- Exact paths and literal commands. Windows, PowerShell + Git Bash.
- Confirm before anything destructive.
- **Verify, don't assume.** Generate real audio, print a real prompt, read it. A feature was
  once declared complete while silently wrong end to end; a review found nine defects, two of
  them errors in the spec rather than the code.
- Large or mechanical work goes to **Antigravity** with a written brief; the owner runs it and
  brings the report back for review. Tricky work stays in-chat.
