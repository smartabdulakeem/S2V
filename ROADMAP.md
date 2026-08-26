# Smart Studio — Roadmap & Status

The single tracked list of everything known to be broken, missing, or planned.
**Every claim here was verified against the code or measured on this machine.**
Where a document disagrees with a measurement, the measurement wins.

- **Last verified:** 2026-08-15
- **Branch:** `rebuild/phase-0`
- **Tests:** 216 passing + 5 new (`test_shot_count_floor.py`), 1 deliberate xfail

## How to use this file

Update the Status column when something changes. Do not delete rows — a fixed row
with its measurement is the record that it was fixed.

| Status | Meaning |
|---|---|
| ✅ FIXED | Done and verified. The verification is written in the row. |
| 🔧 PARTIAL | Some of it works. The row says which part does not. |
| ❌ OPEN | Not started. |
| 🎭 MOCKUP | **The UI shows this but nothing is behind it.** Most dangerous category. |
| ⏸ PARKED | Deliberately not doing. Reason given. |

---

## A. Housekeeping

| ID | Item | Status | Detail |
|---|---|---|---|
| A1 | Commit the pending work | ❌ OPEN | +3,644/−500 across 17 files, 16 new test files, one new module (`pipeline/sound.py`). Split by area: motion/compositing, retrieval/assignment, library/folders, UI/persistence. |
| A2 | Push to GitHub | ❌ OPEN | `rebuild/phase-0` exists **only on this laptop**. `git ls-remote` shows only `main` on origin. Local `main` is also 10 commits ahead of `origin/main`. One disk failure loses everything. |
| A3 | Stale image manifest | ❌ OPEN | `library/manifest.jsonl` holds 869 entries; **849 point at `library/_inbox/`, a folder that no longer exists**. `index.npz` (523 paths, all present) is the real source of truth. |
| A4 | **Split project folders — do NOT delete** | ❌ OPEN | Earlier described here as deletable duplicates. **That was wrong.** Each pair is one project cut in half by the old slug bug: the dash folder holds the **images**, the other holds only `script.json`. Measured: `THE_BATTLE_OF_THE_MUD_-_…` = 48 numbered images, 46 MB; `…_MUD_THE_…` = `script.json` alone. `THE_LONELY_CALIPH_-_…` = 72 images, 59 MB; its twin = `script.json` alone. Deleting a dash folder destroys ~105 MB of generated artwork. Both scripts currently point `image_folder` elsewhere (`library/images`, `library/new image`), so those images are orphaned but intact. Fix by repointing or merging — never by deleting. |
| A5 | `scipy` missing from requirements | ✅ FIXED | `pipeline/library.py` imports `scipy.optimize` for optimal assignment (the 65.6%→83.3% win). A clean install would have crashed on the Storyboard. Added `scipy>=1.11` and `numpy>=1.26`; removed `Flask`, which nothing imports since `api/` was deleted. Verified: `import pipeline.library` succeeds. |
| A6 | `config/last_project.json` tracked | ✅ FIXED | Machine-specific state holding an absolute path. Added to `.gitignore`; verified it no longer appears in `git status`. |
| A7 | Docs carry wrong numbers | 🔧 PARTIAL | HANDOFF said 390 images (really **523**) and 189 tests (really **216**). `REBUILD_PLAN.md` still says 461 images and 1280×720 output — it is a historical plan, kept as-is. This file supersedes it for status. |

---

## B. Verification debt

| ID | Item | Status | Detail |
|---|---|---|---|
| B1 | **Watch a full render end to end** | ❌ OPEN | Never done. This is how burned-in captions and 46 placeholder cards survived into a finished 30-minute video. Tests pass; tests are not eyes. **Highest value item in this file.** |

---

## C. Image count and rhythm

This is the section the user raised as most crucial.

| ID | Item | Status | Detail |
|---|---|---|---|
| C1 | **48 images in a 9.4-minute video** | ❌ OPEN | **Root cause found and proved.** `apply_shot_rhythm` (`text_parser.py:188`) computes `wanted = max(1, round(est_seconds / seconds_per_shot))` **per segment**. One shot per segment is a hard floor. Measured on the real project `THE_BATTLE_OF_THE_MUD`: 47 segments, 1,404 words, ~9.4 min → 12s/shot gives 48 images, and 20s, 30s, 40s, 60s **all give 47**. The user wants 15–21, i.e. ~31s of screen time per image. **Unreachable without letting a shot span segments.** Locked by `tests/test_shot_count_floor.py` (xfail strict). |
| C2 | Rhythm slider ran backwards | ✅ FIXED | Slider was `min=1 max=5` mapped `{1:12, 2:9, 3:7, 4:5, 5:3}` — **descending**, while the label beside it read "~Ns per shot". Dragging right to hold pictures longer cut the film *faster*. Remapped ascending `{1:3, 2:5, 3:7, 4:9, 5:12}`. Also now stores **seconds** rather than slider position, so the saved preference cannot silently change meaning when the range is edited (`app.js`, `app.py:UI_DEFAULT_KEYS`). Verified: `node --check` clean, direction locked by `test_a_faster_rhythm_yields_more_images_not_fewer`. |
| C3 | Slider range too narrow | ❌ OPEN | Tops out at 12s per shot. 15–21 images over 9.4 min needs ~31s. Pointless to widen until C1 is fixed — the floor swallows it. Do both together. |
| C4 | Per-niche image density | ❌ OPEN | A motivational speech wants 1 image or a slow moving background; a battle documentary wants a cut every 4–6s. `shot_rhythm_seconds` already exists in every series pack and is respected as a default — but C1 caps what it can deliver. |
| C5 | **Niche -> visual type -> image prompt** | OK FIXED | `style_presets` existed in all 11 packs and **nothing had ever read it** - picking a visual style changed nothing about the prompt. Now: 55 niche-specific presets authored (`scripts/author_style_presets.py`), the picked type supplies the prompt's medium text **and** the post-processing treatment (`resolve_default_treatment`), and the pack is validated so a malformed one fails loudly. Measured on `islamic_history`: prompt went **84 words -> 60**, world anchor **2 occurrences -> 1**, no mid-phrase truncation. |
| C6 | Prompts were narration, not image direction | OK FIXED | `scene_from_narration` quoted the script verbatim and hard-cut at 34 words, so prompts ended `"...sank to the knee in churned,"` and carried story a generator cannot photograph ("reaching the Jordan valley"). Replaced by eight named slots in `pipeline/prompt_slots.py` - framing, subject, motion, ground, atmosphere, setting, light, medium - each a `(regex, phrase)` table. Locked by `tests/test_prompt_slots.py`. |
| C7 | Every image in a film now shares one opening | OK FIXED | New per-project `project_brief`, drafted once from the script and capped at 30 words, opens every prompt so a folder generated across sessions reads as one film. Opener tracks the treatment: "Documentary still from" / "Illustration plate from" / "Silhouette study from". An edited brief survives re-planning. Verified: `distinct openings: 1` across a whole script. |
| C8 | **Motivational niche crashed the planner** | OK FIXED | Not a missing dropdown entry as previously recorded - `get_series_packs` always read it from disk. `config/series/motivational.json` carried **0 `real_queries` and 0 `fake_queries`** where 10 of each are required, and `get_series_config` re-raises rather than falling back, so selecting it threw `ValueError` on plan. Ten of each authored. Locked by `tests/test_series_packs.py`, which now parametrises over every pack on disk so the next bad pack fails immediately. |

**Recommended fix for C1** (specify to Antigravity, do not let it improvise):
group *consecutive* segments into a scene when the requested seconds-per-shot
exceeds a segment's narration length, and let the whole group share one image.
The compositor still composes per segment, so nothing downstream changes — the
picture simply does not change between them. The one visible risk is the Ken
Burns move restarting at each segment boundary; the move must be given a start
offset so it continues across the group.

---

## D. Image identification and library strategy

| ID | Item | Status | Detail |
|---|---|---|---|
| D1 | Numbered-folder matching | ✅ FIXED | Images named `1_`, `12_` map onto shots 1, 12. Measured: **47 of 48 shots** got their own numbered image. Safeguards verified against all 523 files: **0 false matches**. |
| D2 | Prompt-name matching | ✅ FIXED | Filename repeating the first 3–5 words of the prompt claims the shot. `shot.prompt` is stored so an image generated hours later is still claimed on Refresh. |
| D3 | Optimal assignment | ✅ FIXED | Whole board solved at once via `scipy.linear_sum_assignment`. Greedy 65.6% → **83.3%**. |
| D4 | Description matching threshold | ✅ FIXED | Filename↔query at **0.85**, calibrated so unrelated control queries rescue **zero** images. Re-measure if the library changes character. |
| D5 | **Standing prompt pack** | ✅ FIXED | `tools/build_prompt_pack.py` → **1,606 prompts** (970 universal + 636 niche) in `library/PROMPT_PACK.md` + `prompt_pack.jsonl`, plus a copy-in-batches page at `library/prompt-pack.html`. **First version claimed 2,000 and was wrong**: it crossed subject × framing × lighting, so 1,218 of them were the same picture under different light, and the uniqueness check only compared whole strings so it passed. Now one prompt per **(subject, framing)** pair, audited at build time (`audit()` prints near-duplicates; currently 0). Subject leads the prompt so a generator's truncated filename still carries the subject. Negative prompts removed — the budget goes to positive detail. **The count is the vocabulary's honest ceiling; to grow it, add subjects, never lighting variants.** |
| D6 | Grow the library | ❌ OPEN | 523 today. Working target **1,500**; stretch 3,000. Retrieval cannot pick an image that does not exist — this is the largest single lever on output quality. |
| D7 | Generate images from inside the app | ❌ OPEN | Today the user copies prompts out and pastes images back. |
| D8 | Retrieval at 3,000+ images | ❌ OPEN | See "Scaling note" below. Not yet a problem; will become one. |
| D9 | `sentence-transformers` for text matching | ❌ OPEN | Installed (5.7.0), unused. **Measure before adopting** — the last two "obvious" upgrades did not survive measurement. |
| D10 | SigLIP | ⏸ PARKED | Measured on 96 real images: top-1 16.7%→22.9%, top-5 flat, mean rank slightly *worse*, 2.7× indexing cost. Do not revisit. |
| D11 | Upscale softness | ⏸ PARKED | 2.16× peak upscale on 1024×576 originals. Self-resolving as new images arrive at 1920×1080. |

### Scaling note — what happens at 3,000–4,000 images

The current search is a brute-force dot product over an in-memory matrix. At 523
images the matrix is 523×512 floats (~1 MB) and search is instant. At 4,000 it is
~8 MB and still instant. **Vector search is not the thing that breaks.**

What breaks is *precision*: more images means more near-ties, and CLIP's margin
between rank 1 and rank 10 is already thin. The fix is not a bigger model — it is
that the two matchers which do not use CLIP at all (numbered folder, prompt-name)
are exact and stay exact at any library size. **Filename discipline is what scales,
not the embedding.** That is why `PROMPT_PACK.md` assigns every prompt a permanent
id and a subject-word filename: `U0142_hands_open_in_prayer.jpg` is matchable by
number *and* by name, which is precisely the "number plus name" approach requested.

**Should the library be dropped for pure on-demand generation?** No. Generation
costs money and time on every render and produces a different image for the same
sentence each run, so re-rendering a fixed typo changes the film. A library is a
cache with a fixed cost that trends to zero. The correct arrangement is the one
already built — library first, generate only on a real miss, and the generated
image joins the library — with the missing half being D7.

---

## E. Visual style and niche

| ID | Item | Status | Detail |
|---|---|---|---|
| E1 | Visual style drives *prompts* | ❌ OPEN | `visual_style` currently only picks a **render-time treatment** (`composer.treatment_for_style`) and acts as a fallback world anchor. It does **not** change the prompts the app proposes. The user's ask — realistic vs cartoon vs illustration deciding the generated prompt — is unbuilt. Vocabulary is ready: `VISUAL_STYLES` in `tools/build_prompt_pack.py` (realistic, cinematic, illustration, cartoon, silhouette, archival). Wire that same table into prompt building so picker and pack cannot drift. |
| E2 | Style dropdown options | 🔧 PARTIAL | The Script screen offers only "Vintage documentary / Vox paper-collage / Vector editorial". Needs to become the six styles above once E1 lands. |
| E3 | Motivational niche | ✅ FIXED | `config/series/motivational.json` added. Appears in the dropdown automatically (populated from `config/series/*.json`). **Its `shot_rhythm_seconds: 30` cannot be honoured until C1 is fixed** — noted inside the file itself. **Not calibrated:** `min_score`/`weak_band` are inherited defaults; re-calibrate after generating its images. |
| E4 | Niche drives the render phase | 🔧 PARTIAL | Series packs already supply voice, grade, caption style, world anchor, style block, negative block and seed queries. What they do not yet control is image *density* (C4) and prompt *style* (E1). |

---

## F. Music and sound — the retention gap

Raised as a priority and previously absent from every plan. Nothing in this
section is built beyond F1.

| ID | Item | Status | Detail |
|---|---|---|---|
| F1 | Ambient beds | 🔧 PARTIAL | `pipeline/sound.py` works and is wired into `composer.py:160`: picks a bed by word overlap, fits it, ducks it under narration at −26 dB. **Only 14 beds exist**, all unpromoted in `_inbox`, so most segments are silent. |
| F2 | Grow the sound library | ❌ OPEN | Freesound fetch-on-miss, **CC0 only**, cached to `library/sounds/`, hard cap on fetches per render. |
| F3 | **Background music** | ❌ OPEN | No music track exists at all. `background_music` and `music_volume_db` are in the schema and unused. Biggest single retention lever still untouched. |
| F4 | Per-moment sound effects | ⏸ PARKED | Needs word-level timing. Large build, small gain over beds. Revisit after F3. |
| F5 | Copyright safety | ❌ OPEN | Must be provable per asset, not assumed. See below. |

### Recommendation on music and copyright

**Do not use a general "AI music" API and assume it is safe.** The question that
matters for a YouTube channel is not whether the audio is AI-generated but who
holds the rights to the *output* and whether that survives Content ID. Terms
differ sharply by provider and change often — verify at signup, in writing.

**Google has no music-generation API suitable for this.** Its generative-audio
work has largely been research or consumer-facing rather than a licensed
commercial endpoint, and Google's TTS API covers speech only. Do not plan around
it. *(Verify current availability before ruling it out permanently — this is the
area of the roadmap most likely to be out of date.)*

Ranked, cheapest risk first:

1. **YouTube Audio Library** — free, explicitly cleared for YouTube use, no
   attribution on most tracks. Zero cost, zero strike risk on the platform that
   matters. Least interesting musically, and only safe *on YouTube*. **Start here.**
2. **CC0 / public-domain sources** (Freesound CC0 filter, Musopen for classical
   recordings) — free, usable anywhere, but quality is uneven and **the CC0 status
   of each file must be recorded in the manifest at fetch time**, not trusted later.
3. **A paid subscription library** (Epidemic Sound, Artlist, Uppbeat and similar)
   — a licence tied to the channel plus, importantly, a Content ID whitelist
   process. This is what most channels at scale actually use. Roughly $10–20/month.
   **This is the recommendation if the channel is monetised.**
4. **AI music generation** (Suno, Udio and similar) — only on a paid tier that
   grants commercial rights to outputs, and only after reading the current terms.
   The legal position on training data is unsettled and is *not* something to bet
   a monetised channel on yet.

**For sound effects**, F2 as planned is right: Freesound filtered to CC0, cached
locally, with the licence recorded per file.

**Suggested build order:** F3 first with the YouTube Audio Library (a music bed
under the whole film, ducked under narration — the ducking machinery from F1
already exists and is proven), then F2 to fill ambience, then reconsider paid
libraries once the channel earns. Whatever the source, **the manifest must record
licence and origin per file** — the cost of proving a licence later, without a
record, is far higher than recording it now.

---

## G. Things the UI shows that do not exist

The most dangerous category: a user can reasonably believe these work.

| ID | Item | Status | Detail |
|---|---|---|---|
| G1 | Output format checklist | 🎭 MOCKUP | Buttons toggle and the choice is remembered, but `start_render(scriptPath)` takes no formats and the orchestrator reads **one** `aspect_ratio`. Ticking three boxes renders one video. |
| G2 | Subject-aware crop for vertical | ❌ OPEN | **Zero code** (0 matches for saliency/smart_crop). Without it, 16:9→9:16 is a blind centre crop that decapitates people. Vertical is not shippable until this exists. |
| G3 | Shorts proposal | 🎭 MOCKUP | The "0:45 · queued" row on the Render screen is hardcoded HTML. |
| G4 | Spending card | 🎭 MOCKUP | `$5.00` cap, `$3.12` this month, `$0.28` last video are **typed-in literals**. Nothing is tracked and **no spend limit protects the user today**, despite Settings implying one does. |
| G5 | Performance card | 🎭 MOCKUP | Static dropdowns. The underlying behaviour is correct and hardcoded (libx264 veryfast crf 21, no NVENC attempts) — it just is not user-controllable. |
| G6 | Grade dropdown in Settings | 🎭 MOCKUP | Static. Per-shot grades themselves do work. |
| G7 | Library "Coverage" card | 🎭 MOCKUP | "strong/thin" ratings are hardcoded HTML, computed from nothing. |
| G8 | Library series filter | 🔧 PARTIAL | Hardcodes 2 of 11 series. Should populate from `config/series/*.json` like the Script screen already does. |
| G9 | Language pack downloads | 🎭 MOCKUP | Known, and correctly disabled. |

---

## H. Voice and captions

| ID | Item | Status | Detail |
|---|---|---|---|
| H1 | Captions from TTS timings | ✅ FIXED | Google Neural2/Wavenet/Standard return SSML mark timepoints, used directly (`voiceover.py:579`). Whisper is a fallback only, loaded **once per process** behind a lock (`captions.py:54`). |
| H2 | Nigerian & other accents (`en-NG`) | ❌ OPEN | A catalogue entry plus a language field. Small. The main reason to keep Google at all. |
| H3 | Google TTS quality | ❌ OPEN | Reported flat and mispronouncing. Supertonic is better for Arabic names. Decide: fix or drop Google. |
| H4 | **Pronunciation dictionary** | ❌ OPEN | **Zero code.** The designed answer to Arabic names — wrap each name in SSML `<phoneme>` per series, rather than switching voice and wrecking the English sentence. A "Pronunciation dictionary" button exists on the Script screen and only switches panes. |
| H5 | Kokoro | ❌ OPEN | Catalogued, correctly marked unavailable, not installed. Verify its language list first — **it does not support Arabic**. |
| H6 | `faster-whisper` | ⏸ PARKED | ~4× faster fallback. Low value now that Google captions skip Whisper entirely. |

---

## I. Commercial readiness

| ID | Item | Status | Detail |
|---|---|---|---|
| I1 | API keys in plaintext | ❌ OPEN | `config/settings.json` holds live keys readable by anything on the machine. Move to the Windows credential store before any release. |
| I2 | Licence keys, merchant of record | ❌ OPEN | Not started. |

---

## J. Parked

| ID | Item | Status | Detail |
|---|---|---|---|
| J1 | Generative motion (AI video per shot) | ⏸ PARKED | Zero code. Measured at **$156–$655 per render** on the real 52-segment film. Park permanently unless economics change. |
| J2 | Local image/video generation | ⏸ PARKED | MX230 has 2 GB VRAM; needs 8–24 GB. |
| J3 | Real-ESRGAN upscaling | ⏸ PARKED | Tile seams at every VRAM-safe size; Lanczos looked better. |
| J4 | Timeline editing | ⏸ PARKED | Out of scope. The value is not editing. |

---

## Suggested order

1. **A1, A2** — the work is unbacked-up. Today.
2. **B1** — watch a full render. It will reshuffle everything below.
3. **C1 + C3** — image count. The user's stated top priority, root cause proved.
4. **F3** — music. Largest untouched retention lever.
5. **E1** — visual style drives prompts. Small, and unblocks the prompt pack's value.
6. **D6/D7** — grow the library from `PROMPT_PACK.md`.
7. **G4** — real spend tracking, before any of this costs money at scale.
8. **G1/G2** — multi-format, once vertical can crop safely.

**Backend before UI at every step: it can be verified without clicking.**
