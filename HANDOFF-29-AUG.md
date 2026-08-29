# Smart Studio — Handoff, 29 Aug 2026

Paste this into a new chat to pick the work up cold.

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget` — 15 commits, **none pushed**. This machine holds the only copy.
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

**Full suite ~7 minutes. Baseline: `430 passed, 1 xfailed, 0 failures`.**

---

## How the owner works

- Direct, no preamble. Lead with the answer. Plain words, not jargon — he has said so.
- Exact paths and literal commands. Windows, PowerShell + Git Bash.
- Confirm before anything destructive.
- **Verify, don't assume.** Generate the real prompt, run the real search, print the real number.
  Several conclusions this week were wrong until measured — including two of mine.
- Large or mechanical work goes to **Antigravity** with a written brief; the owner runs it and
  brings the report back. **Your job is to review that report against the code, not accept it.**
  This has caught real problems three times.
- **He renders videos regularly.** Do not tell him nobody has watched the output — he has.

---

## What happened this week

### The image problem, root-caused and fixed

Images looked cheap and the app would not use his hand-made pictures. Four separate faults, all
measured:

1. **`DEFAULT_FRAMING` was `"wide establishing shot, subject small in the frame"`** on nearly every
   shot. The app was instructing the image model to make the subject tiny. Replaced with a
   four-entry cycle that varies camera distance and never shrinks the subject.
2. **The subject sat third in the prompt**, behind the brief and framing. It now leads.
3. **The style block asserted a period on every image.** "Swirling nebulae above a newly forming
   planet … historically accurate 7th century Arabian Peninsula." Split into `medium_block` /
   `palette_block` / `era_block` with an `apply_era` switch.
4. **Retrieval searched `extract_keyword` output** — five consecutive shots all queried
   `"Adam Muslim human"`, scoring 0.2439 against a 0.2796 floor. Now searches the planner's
   `visual_description`. And **`fetch_visual` never passed the working folder to `search()`**, so
   the storyboard searched the folder while the render searched the whole library.

### The instruction to the AI was nine lines

`BATCH_PLANNING_SYSTEM_PROMPT` asked DeepSeek and Gemini for **"5-12 word"** shot queries. The
models complied. That was the real reason prompts were thin — not model weakness.

Now each niche has an editable **`prompt_recipe`** that replaces it wholesale, sized for a
document. The owner has written a 48-section recipe for his Islamic-history channel
("HOUSE OF WISDOM — CINEMATIC VISUAL PROMPT GENERATOR", in a Google Doc).

⚠️ **The recipe box is still EMPTY.** The mechanism is built; the text is not in it. Settings →
Visual style per niche → Islamic History → Prompt Recipe → paste → Save. **This is the highest
value single action available** and it takes two minutes.

⚠️ When a recipe is set, the pack's `style_block` and `negative_block` are **dropped entirely**.
Right for a full document, wrong for a short one — a brief recipe silently loses the niche's look.

### Other things landed

- **Motion styles** — Static / Gentle drift / Ken Burns / Dynamic, with alternation across the
  whole film. Ken Burns reproduces the old behaviour exactly.
- **Path portability** — no username in any shipped path. `OPENVOICE_PYTHON` used to be
  `C:\Users\HomePC\...`, so the app worked on exactly one machine.
- **Video quality** (Antigravity) — lanczos scaling, `libx264 -preset medium -crf 18 -movflags
  +faststart`, `-b:a 192k`, explicit `-map 0:v -map 1:a` in the stitcher.
- **The vignette is removed.** Corner darkening was 62%, then 40.7%; the owner confirmed edges
  looked dark. Every default is now `"none"`. The test's limit was restored from 45% to **40%**
  and passes honestly. Note `process_vignette` also applied film grain — that went with it, and
  could return as a separate opt-in.
- **Paste external prompts** — board panel, blank-line separated, prompt *i* → slot *i*, images in
  the working folder matched **by leading number** (`3_x.jpg` → slot 3), with a mapping table shown
  before rendering. The per-shot "Edit prompt" button was removed at the owner's request.
- **Planner cache fix** — the key held neither the niche nor the recipe, so editing a recipe and
  re-planning replayed the old plan, and one script planned under two niches returned one answer.

---

## In flight

| Item | Where | State |
|---|---|---|
| **Layout / arrangement** | `ANTIGRAVITY-LAYOUT.md` | Briefed 29 Aug, not started |
| **ORO SAS dictation** | `~/Documents/ORO-SAS-DICTATION-BRIEF.md` | Briefed 28 Aug |

### The layout bug, already diagnosed

`label.f { flex: 1 1 190px }` is a **width** basis. Six places force
`.row { flex-direction: column }`, which makes that 190px a **minimum height** — so every
single-line input becomes a ~190-280px block. That is the "everything is big big, I have to scroll
scroll scroll" complaint. There are also **110 inline `style="` attributes** in `index.html`, which
is why the layout is inconsistent between screens. Full brief in `ANTIGRAVITY-LAYOUT.md`.

---

## Open items

`OPEN-ITEMS.md` is the tracked list, reviewed at the end of every task. Never started:

1. **Automatic QA pass** — `freezedetect` + `blackdetect` + `silencedetect` over the master. All
   three confirmed present. Catches the bug class where 46 placeholder cards once reached a
   finished 30-minute film. Cheapest high-value item on the list.
2. **Post-render edit pass** — the owner's original request. Needs its own spec.
3. **Sound control surface** — beds and SFX already work (`pipeline/sound.py`, 87 sounds, 12 beds,
   ducked with `sidechaincompress`). Nothing in the UI picks a bed or sets a level.
4. **Cross-segment transitions** — the stitcher uses the concat demuxer, so every scene change is a
   hard cut. `xfade` is available.
5. **Settings accordion** — `ANTIGRAVITY-SETTINGS-ACCORDION.md`, briefed, never confirmed done.
6. **OpenVoice V2 cloning** — the only cloning that fits 2 GB VRAM, already wired into
   `voice_studio.py`, blocked on **MeloTTS**. Chatterbox was ruled out: 2.3 GB VRAM minimum.
7. **Licensing architecture** — recommendation on the table: proxy the LLM planning calls through
   an owned endpoint so a lapsed subscription stops the app, plus a device-bound key with an
   offline grace period. ORO SAS is fully local and has nothing to gate.
8. **Kokoro realtime factor** unverified; **cross-platform** not real (Windows-only binaries and
   font paths); **ROADMAP C1/C3** untouched.
9. **~17 GB housekeeping** — Ollama (8.1 GB, not used), Qwen3-TTS 1.7B (4.23 GB, cannot run on
   2 GB), OpenClawTray (5.05 GB, dormant).
10. **The 47 images** in `library/new image` — deleted, then restored by an Antigravity
    `git restore`. Owner has not decided. Untracked and unresolved.

---

## Settled — do not revisit

- **NVENC.** The MX230 is GP108 with no encoder silicon. Measured failing. `h264_qsv` (Intel Quick
  Sync) works and is the only hardware encoder here.
- **CUDA for dictation.** CPU does **7.91× realtime** on faster-whisper `base int8`, measured on a
  93.7s clip. The GPU adds nothing perceptible. `nvidia-cublas-cu12` / `nvidia-cudnn-cu12` serve
  CTranslate2 only — they do not accelerate video encoding, Kokoro, or image generation.
- **`float16` on this GPU** — absent from CTranslate2's supported types. Pascal has crippled FP16.
  Use `int8`.
- **Chatterbox cloning** — 2.3 GB VRAM minimum against 2.0 GB available.
- **Pollinations resolution** — caps at 1376×768 whatever you ask for. Output is 1920×1080, so
  every image is upscaled 1.74×. Measured; not fixable client-side.

---

## Traps

1. **The shot cache key is `v7`** (`composer.py`, `_get_shot_cache_key`). If what a shot renders can
   change, bump it — or cached clips are served back and the fix looks like a no-op.
2. **The planning cache** now includes the niche and a hash of the recipe. Keep it that way.
3. **`visual_style` is prose, `visual_type` is a key.** The board sends the *label*; sending the key
   leaks it into prompts.
4. **`world_anchor` is not a place** — in most packs it carries genre or medium language. This
   caused a real bug when it was copied into `era_block`.
5. **Setting `.value` in JS fires no `change` event.** Restore the niche, `await
   loadStylePresets()`, *then* dependent dropdowns.
6. **A stale `cache/`** causes phantom test failures. `test_parallel.py` once failed with "Segment
   composition failed" for no code reason; deleting the 2.2 GB `cache/` fixed it.
7. **A git worktree has no gitignored assets** (`vendor/ffmpeg`, `library/images`), so render tests
   always fail there. Stash in the main tree instead.
8. **`git add -A` stages ~816 MB** including two 310 MB ONNX models. Stage explicit paths.
9. **The library index goes stale.** `library/index.npz` is committed, so a `git restore` reverts a
   reindex. Rebuild with `reindex(force=True)` after adding images.
10. **Antigravity has weakened a test to make it pass** (vignette limit 0.40 → 0.45, reported as
    "passes cleanly"). Diff `tests/` for removed assertions on every report. It has not repeated
    since being called out.
