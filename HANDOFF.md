# S2V — Session Handoff

Paste this to start a fresh session. Everything below is measured on this machine, not assumed.

---

## The project

`C:\Users\HomePC\Documents\GitHub\S2V` — Windows desktop app (PyWebView) that turns a text
script into a narrated, captioned video. Local rendering, cloud AI for content. I make
long-form Islamic-history documentaries (~24 min, ~52 segments) plus shorter series.

Working on branch **`rebuild/phase-0`**. Do not merge to main.

**Read these first, in order:**

| File | What it is |
|---|---|
| `REBUILD_PLAN.md` | Eight-phase rebuild plan, with what's done |
| `DESIGN_SPEC.md` | All interface and feature decisions |
| `SCHEMA.md` | Script JSON schema v2 |
| `design/app-design.html` | Five-screen mockup — open in a browser |
| `design/storyboard-review.html` | Storyboard interaction detail |

---

## How we work

**Antigravity (Gemini, separate app) writes the code. Claude specifies and verifies.**

I paste task briefs into Antigravity, it implements and reports back, I paste its report to
Claude, Claude checks the claims independently and writes the next brief.

**Antigravity has reported work as complete when it was not, four times:**

1. Rendered against `anullsrc` silence it generated itself, then reported the render passing
2. A caption-drift test whose "Whisper reference" was a hardcoded string literal
3. Claimed all 8 watermark-flagged images had watermarks — **0 of 8 did**
4. Reported "Match: Yes" on 15 retrieval results without opening a single image

**So: never accept a report at face value.** Run the tests yourself. Open the images. Probe
the API. Every real bug this session was found by looking, not by reading a log.

---

## Done and verified

| Phase | State | Result |
|---|---|---|
| 0 — Clear the ground | ✅ | dead code removed, slug bug fixed, 96 MB untracked from git |
| 1 — Schema + validator | ✅ | 13/13 adversarial cases caught, v1 scripts still load |
| 3 — FFmpeg compositor | ✅ | **43.0s → 2.62s per segment (16.4×)**, cached re-run 0.00s |
| 4 — Parallelism | ✅ | Stage A–F restructure, output identical serial vs parallel |
| 5 — Captions from TTS timings | ✅ | zero Whisper calls on Google TTS, last caption ends at audio duration |

Test suite: **28 tests, ~38s, no hangs.**

## In flight

**Phase 2 — CLIP retrieval + gap detection.** Backend built. The blocker (wrong CLIP model)
is fixed. **Three correctness bugs outstanding**, all visible in `samples/space_sample.json`:

1. Counter says `GAPS 0` then prints 3 gaps — `ranked_gaps` includes weak shots
2. Weak band hardcoded at 0.05 (`library.py:399`) — a Saturn V at 0.2355 is called "weak"
   instead of a gap. Calibration says the real band is 0.009 wide
3. Composed prompts append the hardcoded Islamic-history style/negative blocks to **every**
   series — producing "Saturn V rocket … 7th century Arabian Peninsula … no curved scimitars"

## Not started

- Storyboard UI (Phase 2 front end) — spec in `DESIGN_SPEC.md` + mockups
- Voice manifest, language packs, pronunciation dictionary
- Multi-format render (subject-aware crop for 9:16)
- Phase 7 — 1080p default, credential store, docs
- Ambient sound beds — needs a schema field and composer work
- Phase 6 — generative motion, deferred pending a shot-strategy decision

---

## Hardware facts — do not rediscover these

- i5-8265U, 4 cores / 8 threads · 11.8 GB RAM · Windows 11
- **NVIDIA MX230 (2 GB) has no NVENC encoder at all** — GP108 silicon, plus a 2019 driver.
  It can never work. It was failing 156× per render before Phase 3.
- Intel UHD 620 Quick Sync works but benchmarked **slower** than libx264 — the bottleneck is
  the filter chain, not the encoder. Default is `libx264 -preset veryfast -crf 21`.
- **Real-ESRGAN is a dead end.** Tile 256/192 exhaust VRAM; 128/96 produce visible tile seams.
  FFmpeg Lanczos looked better and takes 0.4s. Do not reintroduce.
- Local image or video generation is impossible — needs 6–24 GB VRAM.

## API facts — hard-won

- **Google TTS timepointing requires `v1beta1` AND the field `enableTimePointing` (capital P).**
  Every other combination returns HTTP 400.
- **Journey and Studio voices do not support SSML `<mark>`** — no word timings. Neural2 and
  Wavenet do.
- **Python's dual-stack DNS fails for `*.googleapis.com` on this machine.** IPv4-only works.
  `pipeline/net.py` installs an IPv4 fallback — keep it, do not revert it.
- `faster-whisper` was **removed**: its 145 MB model never downloaded (HF CDN runs at
  ~96 KB/s here) and every load hung forever on a CLOSE_WAIT socket, creating 2.5-hour
  zombie processes. Standard `openai-whisper` is cached and loads in 6.3s.
- **ImageMagick is not installed.** `magick_processor.py` was ported to pure Pillow.
- **CLIP must be `ViT-B-32-quickgelu`** with `pretrained="openai"`. Plain `ViT-B-32` silently
  degrades embeddings — real and fake query distributions overlap and gap detection stops working.
- Pollinations returns **1024×576** regardless of requested size. Imagen returns **1408×768**.

## Content facts

- Library: **1,309 images** in `library/images/`, indexed. Calibrated `min_score` **0.2796**.
- Sound library: 3 files. Freesound token is in `config/settings.json`; CC0 filter works.
- Real 52-segment film: median segment **25.1s**, max 100.7s. Generative video clips cap at
  5–10s, so every segment needs 3–5 clips — **168–312 clips, $156–655 per render.** That is
  why the content-hash cache was a prerequisite.
- Pollinations is weak on mid-distance people and animals; wide shots and silhouettes are
  fine. 219 living-subject prompts were re-routed to Imagen.
- Depicting the Prophet ﷺ and the Rashidun caliphs is avoided. Prompts use backs turned,
  silhouettes, hands, crowds — which also happens to be what the models render best.

---

## What I want next

Land the three Phase 2 fixes, then build the storyboard UI to `DESIGN_SPEC.md`.

Keep the working pattern: **backend before UI**, because backend is verifiable without
clicking. Every phase that went well this session was measurable; every phase that went
wrong hid behind something that looked fine.
