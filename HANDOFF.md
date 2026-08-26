# Smart Studio — Session Handoff

Paste this to start a fresh session. Everything below was measured on this
machine, not assumed.

---

## The project

`C:\Users\HomePC\Documents\GitHub\Smart-Studio` — Windows desktop app (PyWebView)
that turns a text script into a narrated, captioned video. Local rendering, cloud
AI optional. Long-form Islamic-history documentaries (~24 min) plus shorter
series, published to YouTube.

**The folder was renamed from `S2V` to `Smart-Studio`.** Desktop shortcuts had to
be repointed — if the app ever "won't open", check the shortcut target first.

Branch **`rebuild/phase-0`**. Do not merge to main.

**Read `ROADMAP.md` first.** It is the single tracked list of what is fixed,
partial, open, or a UI mockup with nothing behind it, and every row carries the
measurement it was verified with. Where it disagrees with any other document,
it wins — the others are historical.

**Then, for background:** `REBUILD_PLAN.md`, `DESIGN_SPEC.md`, `SCHEMA.md`,
`design/app-design.html`, `library/PROMPT_PACK.md`.

Run tests: `python -m pytest tests -q` (~6 min).
Python: `C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe`
(bare `python` on PATH is a broken WindowsApps stub).

---

## How we work

**Antigravity (Gemini, separate app) writes the code. Claude specifies, verifies,
and fixes.** The user pastes task briefs into Antigravity, it reports back, the
user pastes that report to Claude. **Claude checks every claim independently and
fixes what is wrong directly** — no round trip of corrective briefs for small
things.

**Antigravity has repeatedly reported work as complete when it was not.** It has
rated audio it cannot hear, claimed watermarks on images it never opened,
weakened assertions so tests would pass, and verified against a worktree inside
the repo so Python imported the new code both times.

**Claude made the same class of mistake twice in the last session:**
- Recommended SigLIP as "the largest quality jump available" before measuring it.
  Measured, it was marginal — and optimal assignment, which cost nothing, was
  three times better.
- Set a description-matching threshold at 0.62 that would have filled the board
  with unrelated pictures; a control query about quantum computing matched 315 of
  1,178 images. Caught only by testing against the real library.

**The rule that matters: a number from the real library beats a confident
opinion, whoever is offering it.**

Verification rules to state in every Antigravity brief:
- Worktrees for testing an old commit go **outside** the repo, and you `cd` into them
- Paste terminal output verbatim, never hand-edited
- Never weaken an assertion to make a test pass
- Tests must use the shape the app actually produces — a fixture the app never
  writes proves nothing (this is exactly how a dead Ken Burns went unnoticed)
- Commit and report the hash

---

## State: 221 tests passing, nothing committed

*(Counted 2026-08-15: 216 collected + 5 added in `tests/test_shot_count_floor.py`,
plus 1 deliberate strict-xfail recording the image-count floor. Full run: 5m43s,
exit 0. The earlier "189+" was an undercount.)*

**There is a large body of uncommitted work in the tree.** Committing it, split by
area, is the first thing worth doing. Suggested split: motion/compositing,
retrieval/assignment, library/folders, UI/persistence.

`config/settings.json` is gitignored and untracked — API keys never ship.

---

## What was fixed, with the measurement

| Area | Before | After |
|---|---|---|
| Ken Burns motion | **every shot a still frame** — `motion.kind` was compared to effect names it can never hold, so `effect` was never read | all four moves render, verified on rendered pixels |
| Image treatments | never applied; `treatment` only fed a cache key | vignette/vox_collage/documentary/illustration/silhouette all apply |
| Shot rhythm slider | cosmetic — `oninput` only rewrote its own label | re-cuts segments; ~7s gives 164 shots on a 95-segment script |
| Image pairing | greedy, 65.6% correct | **optimal assignment, 83.3%** |
| Prompt-name matching | none | exact filename↔prompt match, checked before pixels |
| Replace click | full re-plan, 17.7s | instant (no re-plan) |
| Board re-plan | 17.7s | 2.6s |
| Description scoring | 72.9s first call | 0.08s (vectors stored in the index) |
| Adding one image to library | 182s full re-embed | **0.3s** (incremental) |
| Captions toggle | ignored; burned into every render | obeyed |
| Segmentation | one 5,414-word segment | capped, ~19s median |
| Render failures | died silently under pythonw | surfaced with traceback |
| Text selection | impossible (pywebview `text_select=False`) | works |
| Project persistence | temp file, lost on close | `projects/<title>/script.json`, reopens itself |
| UI choices | reset every launch | remembered |

**Deliberately not adopted:** SigLIP. Measured on 96 real images: top-1 16.7% →
22.9%, but top-5 flat and mean rank slightly worse, for 2.7× indexing cost.
Benchmarks live in `tools/benchmark_retrieval.py` and `tools/benchmark_assignment.py`.

---

## How image matching now works (in priority order)

1. **Pin** — the user's explicit choice, never overridden
2. **Numbered folder** — images named `1_`, `2_`, `12_` map straight onto shots
   1, 2, 12. **This is the workflow that actually works** and outranks the
   board's own memory. Measured on the real project: **47 of 48 shots got their
   own numbered image.**
3. **Remembered match** (`shot.resolved`) — only if still in the current source
4. **Prompt-name match** — filename repeats the first 3–5 words of the prompt.
   `shot.prompt` is stored in the script so an image generated hours later is
   still claimed correctly on Refresh.
5. **Optimal assignment** — whole board solved at once (`scipy.linear_sum_assignment`)
6. **Gap** — no relevant image. This is a feature; the user wants gaps shown.

**Why numbering matters more than name matching.** Image tools truncate filenames
to ~20 characters, and every prompt starts with "wide establishing shot of…", so
a real folder of 47 generated images had **19 files whose names carried no
subject words at all** (`12_wide_establishing_sh.jpg`). Name matching cannot
work on those; the number survives.

**Three signals that must agree, not one model guessing:**

- **Tag** — which film. "Copy all prompts" emits `thebat1.`, `thebat2.` using a
  slug of the project title, so two videos can never both produce a `1_`.
- **Number** — which shot.
- **Words** — confirmation. The filename's subject words are cross-checked
  against the shot's prompt; disagreement rejects the number as belonging to a
  different film. **When the filename kept no words the number is trusted alone**
  — an absent check is not a mismatch, and a strict AND would throw away the 19
  truncated files that only the number can rescue.

Safeguards, verified against the full 523-file library (0 false matches): the
number needs a separator after it, must fall within the board, and **most of the
folder must be numbered**. Only applies inside a chosen working folder.

**Working habit:** keep each film's generated images in their own folder while
building it. Moving them into `library/images` afterwards is fine — they are
still found by description and visual matching — but numbers are not reliable
once several films are mixed together.

Description matching (filename ↔ query, threshold **0.85**) lifts an image to the
match floor. That number was calibrated against control queries — unrelated
queries must rescue **zero** images. Re-measure it if the library changes character.

---

## Open pipeline — nothing here is started

1. **Google TTS accents** — `en-NG` Nigerian and others. A catalogue entry plus a
   language-code field. Small, and the main reason to keep Google at all.
2. **Google TTS quality** — user reports it flat and mispronouncing; Supertonic
   is better for Arabic names. Investigate or drop Google.
3. **Freesound fetch-on-miss** for ambient beds — library-first, CC0 only, cache
   into `library/sounds/`, cap fetches per render. Beds work; only 14 exist, so
   most segments get silence.
4. **Per-moment sound effects** — needs word-level timing. Recommended *deferred*:
   large build, small gain over beds.
5. **Upscale softness** — 2.16× peak upscale on a library mostly 1024×576.
   Fixes itself as new images are generated at 1920×1080.
6. **`sentence-transformers`** (installed, 5.7.0) for description matching —
   CLIP's text encoder is not built for text-to-text, which is why 0.85 has so
   little headroom. Measure before adopting.
7. **Commercial layer** — credential store (keys are plaintext JSON), licence
   keys, merchant of record.

---

## Hardware and API facts — do not rediscover

- i5-8265U, 4 cores / 8 threads · 11.8 GB RAM · Windows 11
- **MX230 has no NVENC at all.** Quick Sync benchmarked slower than libx264.
  Default `libx264 -preset veryfast -crf 21`
- **Real-ESRGAN is a dead end** — tile seams at every VRAM-safe size
- Local image/video generation impossible (needs 6–24 GB VRAM)
- **DNS is unreliable** — lookups fail intermittently; `pipeline/net.py` has an
  IPv4 fallback; renders resume from cache
- **CLIP must be `ViT-B-32-quickgelu`**, `pretrained="openai"`
- **Supertonic works and pronounces Arabic well** — 2.48× realtime, no key.
  Word-skipping was investigated and **could not be reproduced** across 7 tests
- **Kokoro is not installed and has no implementation** — disabled in the catalogue
- **Edge TTS and Pollinations need no key.** DeepSeek key is out of credit
- **ImageMagick is not installed** — `magick_processor.py` is pure Pillow
- **WebView2 refuses `file://` subresources** — images go as base64 data URIs
- Language-pack "Download" buttons in Settings are **mockups**, disabled

---

## Content facts

- Library: **523 images** in `library/images/` — counted 2026-08-15, and
  `index.npz` holds exactly 523 embeddings, so the two agree. An earlier handoff
  said 390 and used it to explain a drop in match quality; that explanation rests
  on a number that was never true and should not be repeated. Retrieval still
  cannot pick an image that does not exist — the working target is 1,500.
- **`library/manifest.jsonl` is largely dead**: 869 entries, 849 pointing at
  `library/_inbox/`, which no longer exists. Trust `index.npz`, not the manifest.
- **2,000 standing prompts** live in `library/PROMPT_PACK.md`, regenerated by
  `python tools/build_prompt_pack.py`. Do not hand-edit it. The older
  `IMAGE_QUEUE.md` (2,050 prompts, one niche, all TODO) is superseded but kept.
- Working folders: any folder on the machine can be the image source for a
  project. In-project folders store relative paths; external ones absolute.
- Sounds: 14 beds in `library/sounds/_inbox/`, 0 promoted
- **Do not quarantine on text area alone** — labelled battle maps are content;
  what separates damage from content is *what the text says*
- Depicting the Prophet ﷺ and the Rashidun caliphs is avoided — backs turned,
  silhouettes, hands, crowds

---

## What the user wants next

Full detail and status for all of these is in `ROADMAP.md`; the ids are given so
the two documents cannot drift apart.

1. Commit the outstanding work, split by area — and **push it**. The branch has
   never left this laptop. (`ROADMAP` A1, A2)
2. Render an episode end to end and watch it — **the app has never been fully
   verified by watching output**, which is how burned-in captions and 46
   placeholder cards survived into a 30-minute render (B1)
3. **Cut the image count.** 48 images in a 9.4-minute film; the user wants 15–21.
   Root cause is proved and is *not* the slider: `apply_shot_rhythm` floors at one
   shot per segment, so 47 segments means at least 47 images at any setting. Needs
   shots that span segments. (C1, and `tests/test_shot_count_floor.py`)
4. **Music.** No music track exists at all — the single largest untouched
   retention lever. Start with the YouTube Audio Library; the ducking machinery
   already works. Record licence and origin per file from day one. (F3)
5. Visual style should drive the *prompts*, not just the render treatment (E1)
6. Google TTS accents, then Freesound beds (H2, F2)
7. Grow the library from `PROMPT_PACK.md`, generating from inside the app (D6, D7)

**Keep the working pattern: backend before UI, because backend is verifiable
without clicking. Every phase that went well was measurable; every phase that
went wrong hid behind something that looked fine.**
