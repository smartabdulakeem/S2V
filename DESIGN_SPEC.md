# S2V Interface & Feature Spec

Decisions, not prose. Mockups in `design/` are the visual reference:

- `design/app-design.html` — five screens, settings, voice catalogue
- `design/storyboard-review.html` — the storyboard interaction in detail

Governing principle: **the app never asks for input it can decide itself.** Every prompt,
every dialog, every setting has to justify existing.

---

## 1. Screens

| Screen | Job |
|---|---|
| **Script** | Paste, title, series, output formats, narrator, captions → plan |
| **Storyboard** | Review suggested shots; fill gaps; approve |
| **Render** | Progress, multi-format outputs, completion actions |
| **Library** | Search, coverage, housekeeping. **Only place deletion lives** |
| **Settings** | Keys, voice catalogue, language packs, defaults, spend, performance |

Left rail, no timeline, no track editor. This is not an NLE and must not look like one.

---

## 2. Output formats — a checklist, not a dropdown

One script → many renders, from the same shots and narration.

| Format | Resolution | Use |
|---|---|---|
| Long 16:9 | 1920×1080 | YouTube long-form |
| Short 9:16 | 1080×1920 | Shorts / Reels / TikTok |
| Square 1:1 | 1080×1080 | feed |
| Feed 4:5 | 1080×1350 | Instagram portrait |

Frames render at their true proportions in the picker.

**Vertical requires subject-aware re-framing.** A centre crop from 16:9 to 9:16 discards
two-thirds of the frame and decapitates people. Implement saliency-based crop: find the
subject, crop around it, fall back to centre only when nothing is detected. **Blind cropping
is not acceptable.**

**Shorts are proposed, not guessed.** Segment boundaries are known, so the app suggests
self-contained 45–60s spans (hook, a complete beat) and the user ticks which to render.

---

## 3. Captions

One word throughout: **captions**. Never "subtitles". Mixed terminology reads as unfinished.

- **Master toggle** on the Script screen. Off hides all caption options — nested, never sibling.
- Styles: `documentary lower-third` · `kinetic word-by-word` · `bold centre`
- Size: **`auto`** by default, scaling per format
- **Vertical always gets larger, higher captions. No toggle.** There is no case for phone-sized
  text on a phone; removing the decision is better than exposing it.
- Timings come from the voice engine's word marks (Phase 5). Whisper only as fallback.

---

## 4. Voices

**47 voices across 5 engines.** All in Settings; only enabled ones on the Script screen.

| Engine | Voices | Type | Word timings |
|---|---|---|---|
| Google Cloud | 20 | cloud | yes (Neural2, Wavenet) / no (Journey, Studio) |
| Gemini Flash TTS | 5 | cloud | yes |
| **Kokoro** *(new)* | 3+ | offline | no |
| Supertonic | 10 | offline | no |
| Edge Neural | 12 | cloud, free | no |

**Voice metadata must live in a JSON manifest**, not hardcoded — `config/voices.json` with
id, engine, label, language, gender, timings capability, offline size. Otherwise every
provider change is a code edit. Same lesson as `tools/taxonomy.py`.

**Kokoro:** add it. Apache-2.0, 82M params, best offline quality for the size, CPU-friendly.
**Verify its language list before building — it does not support Arabic.**

**Language packs** — download offline weights per language. English (primary, installed),
Arabic (secondary), French (secondary), Spanish. Cloud voices need no download. Each pack
serves every offline engine supporting that language.

**Every voice needs a Preview button.** Every key needs a Test button.

---

## 5. Pronunciation dictionary

Per series. **This is how Arabic names get pronounced correctly** — not by switching voices.

Switching to an Arabic voice fixes the name and wrecks the English sentence. Instead wrap each
entry in SSML on the way to the TTS engine:

```xml
The Caliph <phoneme alphabet="ipa" ph="alˈmansˤuːr">Al-Mansur</phoneme> sent word
```

- Stored per series alongside the character bible
- Columns: written form, IPA, which episodes use it, **Test button per entry**
- **"Import from script"** scans a new script for unfamiliar proper nouns and asks for
  confirmation on each, so the dictionary grows as the series does
- Applies only to engines that support SSML phonemes (Google Cloud). Skip silently elsewhere.

---

## 6. Series memory

The user is making a series, not files. Persist per series: character bible, pronunciation
dictionary, narrator, tone, visual style, grade, brand kit. Episode 7 opens where 6 finished.

---

## 7. Settings

**Keys** — table with Used-for column and a **Test button per row**. Google AI, Google Cloud
TTS, DeepSeek, Freesound, ElevenLabs (optional). **Store in the Windows credential store, not
plaintext JSON** — required for commercial release.

**Defaults** — resolution, fps, caption style, grade.

**Spending** — cap per video, warn threshold, month-to-date, last video. Estimate shown before
every render. **No paid call without that estimate appearing first.**

**Performance** — encoder (probed at startup), parallel shot count. Never attempt NVENC on
hardware that lacks it.

---

## 8. Retention features

| Feature | Why |
|---|---|
| **Shot rhythm slider** | Segments run ~25s; broadcast cuts every 4–6s. One slider splits segments into more shots and pulls from the library. Largest quality gain per unit of work, no extra generation. |
| **Grade presets** | `documentary` · `illustration` · `silhouette` · `none`, applied at render time. Illustration and silhouette make weak AI anatomy read as style. |
| Kinetic captions | Word-by-word highlight, driven by TTS timings. Strongest on vertical. |
| Ambient sound beds | Per-scene ambience ducked under narration. **Needs a schema field and composer work — not yet built.** |

---

## 9. Deferred, deliberately

- **Deletion on the storyboard.** Rejecting a shot is about *fit*, not quality. Three outcomes:
  *not here* (stays), *never for this query* (blocked for that query), *retire* (out of search,
  recoverable). True deletion lives in Library only.
- Timeline editing. Out of scope — the value is not editing.
- Local image or video generation. 2 GB VRAM cannot run it.
- Real-ESRGAN upscaling. Tested: tile seams at every VRAM-safe tile size, and Lanczos looked
  better. Do not reintroduce.

---

## 10. Build order

1. **Phase 2 backend** — CLIP retrieval, gap detection, diversity. No UI. Testable alone.
2. **Storyboard screen** — consumes it.
3. **Voice manifest + Settings** — catalogue, packs, pronunciation dictionary.
4. **Multi-format render** — subject-aware crop, Shorts proposal.
5. **Phase 7** — 1080p default, credential store, docs.
6. Sound beds (schema + composer) whenever the sound library lands.

Backend before UI at every step: it can be verified without clicking.
