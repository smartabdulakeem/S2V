# Smart Studio — Session Handoff

Paste this to start a fresh session. Everything below is measured on this machine, not assumed.

---

## The project

`C:\Users\HomePC\Documents\GitHub\S2V` — Windows desktop app (PyWebView) that turns a text
script into a narrated, captioned video. Local rendering, cloud AI optional. I make long-form
Islamic-history documentaries (~24 min, ~52 segments) plus shorter series, and I publish to
YouTube. **The app is now called Smart Studio.** The repo folder is still `S2V`; only the
display name changed.

Working on branch **`rebuild/phase-0`**. Do not merge to main.

**Read these first, in order:**

| File | What it is |
|---|---|
| `REBUILD_PLAN.md` | Eight-phase rebuild plan |
| `DESIGN_SPEC.md` | All interface and feature decisions — **the design contract** |
| `SCHEMA.md` | Script JSON schema v2 + series pack schema |
| `design/app-design.html` | Five-screen mockup — open in a browser |
| `design/storyboard-review.html` | Storyboard interaction detail |

Published design artifacts (same content, viewable in a browser):
- App Design — https://claude.ai/code/artifact/5bbd91d4-795e-41e8-a64c-69388aca15df
- Storyboard Review — https://claude.ai/code/artifact/5d7daf01-0a76-41f1-b545-574e8cfa85a3
- Image Studio — https://claude.ai/code/artifact/98ff271c-9be8-45f6-b790-590e4acc92ac

---

## How we work

**Antigravity (Gemini, separate app) writes the code. Claude specifies, verifies, and fixes.**

I paste task briefs into Antigravity, it implements and reports back, I paste its report to
Claude. **Claude checks the claims independently and fixes what is wrong directly** — I do not
want a round trip of corrective briefs for small errors.

**Antigravity has reported work as complete when it was not, repeatedly:**

1. Rendered against `anullsrc` silence it generated itself, then reported the render passing
2. A caption-drift test whose "Whisper reference" was a hardcoded string literal
3. Claimed all 8 watermark-flagged images had watermarks — **0 of 8 did**
4. Reported "Match: Yes" on 15 retrieval results without opening a single image
5. Weakened an assertion (`library.STYLE_BLOCK in composed` → a substring every pack satisfies)
   so a test would pass, then reported the suite green
6. "Verified" against an old commit using a worktree **inside** the repo, so Python imported the
   new code — its "before" run was the new code tested against itself
7. Two OCR reports in one session with contradictory numbers (1309/19 burned vs 1070/91),
   neither matching the raw cache (1060 scanned, 87 burned)
8. Rated 5 sampled sounds "Exact Match" with prose descriptions of audio it cannot hear
9. Hardcoded `sounds_count: 87, beds_count: 12` in the API so the Library screen advertised a
   collection ten times its real size

**So: never accept a report at face value.** Run the tests. Open the images. Probe the API.
Every real bug this project has been found by looking, not by reading a log.

**Verification rules Antigravity must follow (state them in every brief):**
- Worktrees for testing an old commit go **outside** the repo, and you `cd` into them
- Paste terminal output verbatim, never hand-edited
- Never weaken an assertion to make a test pass
- Commit and report the hash

---

## Current state — the engine works

**A real 25-minute episode has already been produced with this app.** The pipeline is not
speculative.

| Phase | State |
|---|---|
| 0 — Clear the ground | ✅ |
| 1 — Schema + validator | ✅ |
| 2 — Library retrieval, gap detection, niche packs | ✅ |
| 3 — FFmpeg compositor | ✅ **43.0s → 2.62s per segment** |
| 4 — Parallelism | ✅ |
| 5 — Captions from TTS timings | ✅ |
| — LLM provider seam + 10 niche packs | ✅ |
| — Front end rebuilt to the five-screen design | ✅ (rough edges, see below) |

**Test suite: 54 tests, ~4 min.** Run: `python -m pytest tests -q`

Render a sample: `python cli.py samples/sample_script.json`
Coverage report:  `python -m pipeline.library coverage samples/sample_script.json`

Output is **1920×1080**, 30 fps. A 65s sample renders in ~1m15s cold, seconds when cached.

---

## Open problems — start here

1. **Console window flashes on voice preview.** `pipeline/noconsole.py` patches
   `subprocess.Popen` globally at startup and is installed in `app.py` and `cli.py`, but a flash
   still appears. Not yet traced. Suspect a path that does not go through `Popen` —
   `asyncio` proactor subprocess, or something inside pywebview/WebView2. **Diagnose before
   patching further.**
2. **"Replace" on the storyboard does not replace.** The modal offers three outcomes; the
   selection does not take effect on the board.
3. **Image quality at 1080p.** 96% of the library is under 1080 tall; 68% is 1024×576. With Ken
   Burns at 1.15× zoom the peak upscale is **2.16×** and visibly soft. Options: accept it,
   reduce zoom from 0.15 to 0.08, or generate new images larger. Recommendation: accept now,
   fix at the source going forward.
4. **249 library images were never OCR-scanned** and `library/text_scan.jsonl` appends without
   deduping (2,091 records for 1,060 unique paths). 20 flagged images still need review.
5. **`get_settings` returns API keys to the frontend.** Fine locally, wrong before release.

---

## Hardware facts — do not rediscover these

- i5-8265U, 4 cores / 8 threads · 11.8 GB RAM · Windows 11
- **NVIDIA MX230 (2 GB) has no NVENC encoder at all.** It can never work.
- Intel UHD 620 Quick Sync works but benchmarked **slower** than libx264. Default is
  `libx264 -preset veryfast -crf 21`.
- **Real-ESRGAN is a dead end.** Tile seams at every VRAM-safe size; Lanczos looked better.
- Local image or video generation is impossible — needs 6–24 GB VRAM.
- **DNS on this machine is unreliable.** Lookups for `speech.platform.bing.com` and
  `api.deepseek.com` fail intermittently and recover minutes later. `pipeline/net.py` installs
  an IPv4 fallback. A render that dies mid-way resumes from cache on re-run.

## API facts — hard-won

- **Google TTS timepointing requires `v1beta1` AND `enableTimePointing` (capital P).**
- **Journey and Studio voices do not support SSML `<mark>`** — no word timings. Neural2 and
  Wavenet do.
- **Edge TTS needs no API key.** It is what the samples use. Free.
- **Pollinations needs no API key.** Free image generation, returns 1024×576 regardless of
  requested size. Imagen returns 1408×768.
- **The DeepSeek key is out of credit** — returns `402 Payment Required`. Permanent provider
  errors (401/402/403/404) now fail fast instead of retrying three times.
- **CLIP must be `ViT-B-32-quickgelu`** with `pretrained="openai"`. Plain `ViT-B-32` silently
  degrades embeddings.
- `faster-whisper` was **removed** — its model never downloaded here. Standard `openai-whisper`
  is cached and loads in 6.3s.
- **ImageMagick is not installed.** `magick_processor.py` is pure Pillow.

## UI facts

- **WebView2 refuses `file://` subresources.** Images must be sent as base64 data URIs; see
  `Api._thumb()`. Two earlier attempts with relative paths and then `file://` URLs both
  produced broken-image icons.
- The window must be raised explicitly on launch or it opens behind other apps.
- The desktop shortcut runs `pythonw.exe app.py` so no terminal appears.

## Content facts

- Library: **1,242 images** in `library/images/`, indexed. 54 quarantined in
  `library/_quarantine/` (render leftovers with burned-in episode titles and narration, plus 2
  third-party YouTube thumbnails). 13 of my own title-card artworks moved to
  `library/_thumbnails/`, out of the retrieval pool.
- **Do not quarantine on text area alone.** Labelled battle maps have text and are content;
  my own thumbnails have text and are valuable. What separates damage from content is *what the
  text says*: garbled words or my own narration means damage.
- Sounds: **0 promoted, 14 awaiting review** in `library/sounds/_inbox/`. Roughly half of the
  fetched batch is unusable — a freight train, traffic with car bass, a plastic bag, a
  glockenspiel. Freesound needs a modern-noise filter before the next fetch.
- Real 52-segment film: median segment **25.1s**, max 100.7s.
- Depicting the Prophet ﷺ and the Rashidun caliphs is avoided. Prompts use backs turned,
  silhouettes, hands, crowds.

---

## The zero-cost path — this works today

Every paid piece has a free equivalent that is installed and working:

| Job | Free way |
|---|---|
| Split script into segments | Plain Python (`split_into_segments`) |
| Pick shot search terms | `extract_keyword` — weaker than AI, but free |
| Narration voice | Edge TTS, no key |
| Find images | Local CLIP over my own library |
| Fill missing images | Pollinations, no key — or make them myself |
| Captions | Local Whisper |
| Render | Local FFmpeg |

Optional AI planning costs about **$0.22 per 52-segment film** on Claude Sonnet 5 with a JSON
schema enforced. Worth it only because the free planner writes poor queries
("Weight Mantle Abu" for a segment about Abu Bakr).

`config/settings.json` → `auto_generate_missing_images` (default false). Off, a render stops at
a gap and hands over the composed prompt. On, gaps are filled by Imagen when a key is set and
Pollinations otherwise.

---

## What I want next

1. Fix the three UI faults above (console flash, Replace, then judge 1080p softness by eye)
2. Render one real episode end to end and watch it
3. Sound: modern-noise filter, then fetch the `oneshots` batch for combat effects
4. Finish the OCR sweep (249 unscanned, dedupe the cache, review the 20)
5. Commercial layer: credential store, licence keys, merchant of record

Keep the working pattern: **backend before UI**, because backend is verifiable without clicking.
Every phase that went well was measurable; every phase that went wrong hid behind something that
looked fine.
