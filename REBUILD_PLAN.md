# S2V Rebuild — Master Plan

Hand this to Antigravity **one phase at a time**. Each phase is self-contained: scope,
files, acceptance criteria. Do not start a phase until the one before it passes.

**Baseline measured 2026-08-06** on i5-8265U / MX230 / UHD 620:

| Metric | Now | Target |
|---|---|---|
| 52-segment render (23.8 min video) | 24–52 min | **under 3 min** |
| Compose one 13.8s segment | 43.0s | 5.8s (measured) |
| Wasted NVENC attempts per render | 156 | 0 |
| Re-render after a one-word edit | full 24 min | seconds |

---

## Image library targets

| | Count |
|---|---|
| In `library/images/` today | **461** |
| Prompts queued in `library/IMAGE_QUEUE.md` | **2,050** (82 batches, 28 themes) |
| Cross-product available to `build_library.py` | 6,000 |
| **Working target before retrieval beats generation** | **1,500** |
| Stretch target for full coverage | 3,000 |

Retrieval measured at 461 images: lift **+0.107** over random, mean z-score **3.05**,
100% of queries land >2sd above library mean. Only 44 distinct images ever returned as
top-1 — that concentration is a library-size problem and resolves as the count grows.

**Split:** Antigravity works `IMAGE_QUEUE.md` from the top (A1 downward). Manual work
goes bottom-up (MO1 upward) via `library/image-studio.html`. Both save to
`library/images/`. Always dedupe against `library/manifest.jsonl` first.

---

## PHASE 0 — Clear the ground

**Why first:** there are 960 uncommitted lines and three dead UIs. Building on top of
that guarantees merge pain later.

**Scope**
1. Commit or discard the pending changes in `app.py`, `frontend/app.js`,
   `pipeline/{composer,orchestrator,stitcher,visuals,voiceover}.py`, and the skill doc.
2. Delete `api/` entirely — it is dead code. It calls `generate_voiceover(huggingface_api_key=…)`
   and `generate_storyboard_plan(hf_token=…)`; neither parameter exists, so every request
   raises `TypeError`. Also delete `vercel.json` and `.vercelignore`.
3. Delete `s2v_script_to_video_agent_ui.html`, `stitch_s2v_ai_video_studio/`,
   `stitch_s2v_ai_video_studio.zip`, `animated_drawings.zip`, `temp_animated_drawings/`, `scratch/`.
4. Fix the slug bug in `pipeline/visuals.py`: `re.sub(r'[^\w\-]', '_', title)` produces three
   different folders for `S2E3 — Fire in Every Direction` because the em-dash encodes
   inconsistently. Add `unicodedata.normalize("NFKD", title)` before slugifying. Merge the
   duplicate `S2E3___*` and `S2E4___*` folders.
5. Merge `requirements-desktop.txt` into `requirements.txt` — the root file is missing
   moviepy, whisper, Pillow, and pywebview. Add `open-clip-torch`.
6. Update `README.md`: output is **1280×720**, not 1080p; sourcing is Google Imagen with a
   Pollinations fallback, not Pexels/Pixabay. Delete the Pixabay key instructions.

**Acceptance:** `git status` clean; `python cli.py samples/sample_script.json` still renders;
no folder in `projects/` differs from another only by dash encoding.

---

## PHASE 1 — The schema

**Why now:** everything downstream reads it. Locking it late means rewriting the compositor.

**Scope** — extend the script JSON so a segment can hold a **shot list** rather than a single visual.

```json
{
  "project": {
    "title": "S2E6 — The Long Retreat",
    "output_filename": "s2e6.mp4",
    "aspect_ratio": "16:9",
    "resolution": "1920x1080",
    "voice": "google:en-GB-Neural2-D",
    "voice_rate": "+0%", "voice_pitch": "+0Hz",
    "background_music": null, "music_volume_db": -20,
    "disable_captions": false,
    "visual_style": "vintage_documentary",
    "character_bible": { "Ali": "an elderly man, white beard, plain dark robes" }
  },
  "segments": [
    {
      "segment_id": 1,
      "type": "hook",
      "narration": "<speak>...</speak>",
      "voice_steering": "grave, unhurried",
      "shots": [
        {
          "shot_id": "1a",
          "duration": null,
          "source": "library",
          "query": "lone rider on a ridge at dusk",
          "pin": null,
          "motion": { "kind": "ken_burns", "effect": "zoom_in" },
          "treatment": { "filter": "vignette", "grade": null }
        },
        {
          "shot_id": "1b",
          "duration": 6.0,
          "source": "generate",
          "query": "war banners raised before an advance, storm light",
          "motion": { "kind": "generative", "provider": "auto", "seconds": 5 }
        }
      ],
      "text_overlay": null,
      "transition_in": "fade",
      "transition_out": "cut",
      "sfx": []
    }
  ]
}
```

**Rules**
- `shots` replaces the old flat `b_roll_keyword` / `visual_type` / `ken_burns` fields, but the
  loader must still accept old-style segments and upconvert them to a single-shot list.
- `duration: null` means "share the segment evenly with other null-duration shots".
  Explicit durations are honoured; the remainder is split among the nulls.
- `source`: `library` (retrieve) | `generate` (make new, then add to library) | `pin` (exact file).
- `motion.kind`: `ken_burns` | `static` | `generative`.

**Also rewrite `pipeline/validator.py`.** It currently validates none of `magick_filter`,
`sfx`, `level1_overlay`, `crop`, `character_bible`, `aspect_ratio`, `disable_captions` —
seven fields the pipeline actively consumes. Every field above must be validated with a
human-readable error naming the exact path (`segments[3].shots[1].motion.kind`).

**Acceptance:** old sample scripts in `samples/` still validate and render unchanged;
a new shot-list script validates; every malformed field produces a clear message, never a traceback.

---

## PHASE 2 — Library retrieval

**Scope** — create `pipeline/library.py`.

- Build/load a CLIP index (`ViT-B-32`, pretrained `openai`, CPU) over `library/images/`,
  cached to `library/index.npz`. Rebuild only when the folder mtime changes.
- `search(query, k=5, exclude=set(), min_score=0.26) -> [(path, score)]`
- **Diversity is required, not optional.** Pure top-1 returned only 44 of 461 images, with one
  image winning 13 queries. Penalise images by recent-use count within the current render,
  and never return the same image twice in one video.
- `add(path, prompt)` for incremental indexing when a shot is generated.
- CLI: `python -m pipeline.library reindex` and `... search "desert caravan at dusk"`.

Then wire into `pipeline/visuals.py`: **library-first, generate-on-miss, generated image joins
the library.** Below `min_score`, generate; above it, retrieve.

**Acceptance:** `reindex` completes on 1,500 images in under 5 min; searching a real script's
queries returns no duplicate image within one video; a generated image is retrievable on the next run.

---

## PHASE 3 — FFmpeg compositor (the big win)

**Scope** — replace the per-frame Python loop in `pipeline/composer.py`.

The current `make_frame` builds every frame in PIL: crop, resize, RGBA convert, allocate
overlay, alpha-composite, convert back, hand a NumPy array to the encoder. Roughly 3,000
chains for a 14s segment. **Measured: 43.0s versus 5.8s for FFmpeg-native output that is
visually equivalent.**

Map each feature to a native filter:

| Feature | Filter |
|---|---|
| Ken Burns | `zoompan` (pre-scale 1.25× so crops stay in bounds) |
| Captions | `subtitles` with ASS `force_style` |
| Text overlay | `drawtext` with `enable='between(t,0,N)'` |
| Fades | `fade=t=in` / `fade=t=out` |
| Sprites | `overlay` with time expressions for x/y |

**Also:**
- **Probe encoders once at startup and cache.** NVENC currently fails 3× per segment, 156
  times per render. The MX230 is GP108 silicon with no NVENC hardware at all, and the driver
  (26.21.14.4223) predates the 570.0 that FFmpeg 8.1.1 requires. It can never succeed. Note
  that `h264_qsv` works on the UHD 620 but benchmarked *slower* (5.4s vs 3.8s) — the filter
  chain is the bottleneck, not the encoder. Default to `libx264 -preset veryfast -crf 21`.
- **Content-hash the cache.** Key each shot on `(query|pin, duration, motion, treatment, resolution)`.
  Never re-encode an unchanged shot. Delete the cache-wipe loop at `orchestrator.py:107–114`,
  which currently destroys resume support at the start of every render.
- Route every FFmpeg call through `_find_ffmpeg()`. Two calls (`composer.py:260` and `:381`)
  use a bare `"ffmpeg"` from PATH and break outside the GUI.

**Keep `stitcher.py` as it is** — it concats with `-c:v copy`, which is already correct and cheap.

**Acceptance:** a 13.8s segment composes in under 8s; output is visually equivalent to the old
path; a second render with no edits completes in seconds; zero NVENC attempts in the log.

---

## PHASE 4 — Parallelism

**Scope** — restructure `pipeline/orchestrator.py`.

The pipeline is serial because a segment's duration is only known after its audio exists,
forcing `audio → duration → compose` one segment at a time. Break that:

1. Synthesise **all** narration concurrently (async, respect provider concurrency caps).
2. Every duration is now known → build the complete timeline in one pass.
3. Composition becomes an embarrassingly parallel batch — `ProcessPoolExecutor`, 3–4 workers.

Also fan out all image API calls concurrently, with the existing retry/backoff per call.

**Acceptance:** a 52-segment render uses all cores during composition; wall time drops at least
2.5× beyond the Phase 3 gain; cancel still works mid-render.

---

## PHASE 5 — Captions from TTS, not Whisper

**Scope** — stop transcribing audio you just synthesised.

- Google Cloud TTS returns word timings via SSML `<mark>` timepoints, and the planner already
  injects SSML. Use them directly — more accurate than transcription, because they come from
  the source text rather than a guess at it.
- Keep Whisper as the fallback for engines with no timing data (Edge, Supertonic), but load
  the model **once at module level**. It is currently loaded inside the per-segment function,
  so a 52-segment video loads it 52 times.
- Prefer `faster-whisper` (CTranslate2) for that fallback — roughly 4× quicker on CPU.

**Acceptance:** captions on a Google-TTS render need no Whisper call at all; Whisper loads at
most once per render; caption timing is at least as accurate as before.

---

## PHASE 6 — Generative motion (opt-in per shot)

**Scope** — add a provider abstraction behind `motion.kind: "generative"`.

**Hardware reality:** local video diffusion is not possible on this machine. Wan2.1-14B wants
16–24 GB VRAM; even LTX-Video (2B) wants 8–12 GB. The MX230 has 2 GB. Local image diffusion is
also out. So the provider layer means *local TTS and captions today, API for everything visual*,
with local slots ready for a future 12 GB+ GPU.

**Cost reality, measured on the real 52-segment film:** median segment is 25.1s and models cap
at 5–10s clips, so every segment needs 3–5 clips. That is **168–312 clips**, roughly **$156 at
$0.10/s** or **$655 at $0.42/s**, per render. This is why cache hashing (Phase 3) is a hard
prerequisite — regenerating clips because of a typo is not affordable.

- `pipeline/providers/` with a common interface: `generate_clip(image, prompt, seconds) -> path`.
- Content-hash clips on `(prompt, seed, seconds, provider)`; never regenerate.
- Hard spend ceiling per render, configurable, with a confirmation prompt before exceeding it.

**Acceptance:** a script with one generative shot renders correctly; a second render regenerates
nothing; the spend ceiling blocks an over-budget render before any API call is made.

---

## PHASE 7 — Finish

- Raise default output to **1920×1080** (affordable once composition is FFmpeg-native).
- Encrypt `config/settings.json` at rest, or move keys to the OS credential store — three live
  API keys are currently plaintext.
- Tests: validator round-trip, filtergraph construction, cache-hash stability, retrieval
  determinism. There are currently none.
- Rewrite `skills/s2v-video-renderer/SKILL.md` — it still documents the removed Hugging Face flow.

---

## Order and dependencies

```
Phase 0  ──►  Phase 1  ──►  Phase 2  (library retrieval)
                    └────►  Phase 3  (compositor)  ──►  Phase 4  (parallelism)
                                                          └────►  Phase 6  (motion)
              Phase 5  independent, any time after Phase 1
              Phase 7  last
```

Phases 2 and 3 can run in parallel — they touch different files. Phase 3 is the one that
delivers the headline speed win; Phase 2 is the one that delivers the cost win.
