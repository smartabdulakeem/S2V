# Open items

Everything raised and not finished. Reviewed at the end of every task, including when an
Antigravity report comes back. Newest decisions at the top of each section.

Last reviewed: 29 Aug 2026

---

## Committed, not pushed

**21 commits** on `feat/image-budget`. Local only — nothing is on GitHub until someone pushes.
This machine holds the only copy.

```
41d5ab4 fix(library): the index reaches every image again, not 573 of 743
18222c8 fix(ui): the 190px belongs to a row, not to every field
743a77b fix(ui): eliminate 190px flex-basis stacking bug, refactor settings and storyboard grids
060281a docs: layout brief and the 29 Aug handoff
e0c97db fix(look): stop darkening the corners of every image
   … 16 earlier commits
```

Suite verified after the last commit: **430 passed, 1 xfailed, 0 failures** in 9m03s.

### ✅ The vignette decision, settled

The limit was restored to **0.40** in `e0c97db` and passes honestly — every vignette default is
now `"none"`. Nothing is owed. Note that `process_vignette` also applied film grain, which went
with it; it could return as a separate opt-in.

### ⚠️ Standing warning — never `git checkout -- library/index.npz`

Running the test suite rewrites `library/index.npz`. Reverting that file looks like tidying and is
not: the committed index covered **573** paths against **743** files on disk, so 170 images — 23%
of the library — could not be retrieved by any prompt. It happened twice during the layout work.
If the file shows as modified after a test run, **commit it, do not restore it.**

---

## In flight

| Item | Owner | State |
|---|---|---|
| **Visual types** — `ANTIGRAVITY-VISUAL-TYPES.md` | Antigravity | Briefed 29 Aug. Per-niche visual type list; Brief subject, Medium and Palette leave the panel |
| **ORO SAS dictation** — `~/Documents/ORO-SAS-DICTATION-BRIEF.md` | Cloud tab | Briefed 28 Aug |

### Landed since the last review

| Item | State |
|---|---|
| **Layout / arrangement** — `ANTIGRAVITY-LAYOUT.md` | Done, `743a77b`. Inline `style=` 111 → 19; settings and storyboard on grids. The report claimed the 190px basis was eliminated — it was only contained, and was properly re-scoped in `18222c8` |
| **Visual control** — `ANTIGRAVITY-VISUAL-CONTROL.md` | Done. Era split, per-niche editor, prompt recipes |
| **Video quality** — `ANTIGRAVITY-VIDEO-QUALITY.md` | Done. Items A and G measured-only, no change made |

---

## Not started — Smart Studio

1. **Automatic QA pass.** `freezedetect` + `blackdetect` + `silencedetect` over the master, parsed
   into a report. All three confirmed present in the vendored FFmpeg. Catches the ROADMAP B1 bug
   class directly — 46 placeholder cards once survived into a finished 30-minute film because
   "tests are not eyes". One FFmpeg invocation and a parser. **Cheapest high-value item on the
   list.**
2. **Post-render edit pass.** The owner's original request, and the largest piece. Needs its own
   spec. Everything required is present: keyframe-boundary cuts with `-c copy` are lossless and
   near-instant, `-itsoffset` places a sound effect at a timestamp, `amix` lays music over a range.
3. **Sound control surface.** Background music and SFX already work — `pipeline/sound.py` matches
   a bed per scene, loops it, and ducks it under narration with `sidechaincompress`, over a library
   of 87 sounds and 12 music beds. What is missing is **control**, not capability: nothing in the
   UI picks a bed, sets its level, or places an effect at a moment.
4. **Cross-segment transitions.** The stitcher uses the concat demuxer, so **every scene change is
   a hard cut**. `xfade` is available.
5. ~~**Settings accordion.**~~ **Done** — confirmed live 29 Aug. The Settings screen renders as a
   collapsed two-column card deck; sections expand on click. The trap still applies to any future
   work there: `renderVoiceCatalogueSettings()` rebuilds its container on every voice toggle, so an
   open engine must survive the re-render.
6. **ROADMAP C1 and C3.** C1 is the one-shot-per-segment floor giving 48 images in a 9.4-minute
   video. Both untouched.
7. **Pitch/duration fitting and two-pass loudness.** `librubberband` is present in the vendored
   build.

## Not started — commercial

8. **Licensing / anti-piracy architecture.** Discussed 28 Aug, nothing built. Recommendation on
   the table: proxy the LLM planning calls through an owned endpoint so a lapsed subscription
   stops the app working, plus a device-bound licence key with a 7–14 day offline grace period.
   ORO SAS is fully local so it has nothing to gate — price it as a one-time purchase.
9. **Never ship API keys in the client.** `config/settings.json` holds four live keys. It is
   gitignored and untracked (verified), but an installer must not bundle it.
10. **Kokoro realtime factor is unverified.** Claimed 3–5× realtime on CPU; the repo's own note
    says ~11s per clip. Needs measuring before it goes in a published spec sheet.
11. **Cross-platform is not real yet.** Windows-only: vendored `ffmpeg.exe` / `ffprobe.exe`,
    `piper.exe`, and font lookup that only searches the Windows font directory. Do not advertise
    macOS or Linux until this is done.

## Not started — voice

12. **OpenVoice V2 cloning.** The cloning path that actually fits 2 GB of VRAM, already wired into
    `pipeline/voice_studio.py`, blocked on the **MeloTTS** dependency. Chatterbox was ruled out:
    its lightest variant needs ~2.3 GB VRAM against 2.0 GB available.

## Machine housekeeping — owner's call

13. **Ollama** — 2.8 GB app + 5.3 GB models, and it auto-starts. Not ticked as used.
14. **Qwen3-TTS 1.7B** — 4.23 GB in the HF cache, needs far more than 2 GB VRAM, cannot run here.
    `~/.cache/huggingface/hub/models--Qwen--Qwen3-TTS-12Hz-1.7B-Base`
15. **OpenClawTray** — 5.05 GB across `AppData\Local` and `AppData\Roaming`, dormant.
16. **47 images in `library/new image/`** — the deletion scare is over: measured 29 Aug, 47 files
    tracked, 47 on disk, path clean. But the index covers **`library/images` only**, so these 47
    are not searchable — the app cannot pick any of them. Still the owner's call: move them into
    `library/images` and `reindex(force=True)`, or leave them out deliberately.
17. **Firefox 109.0.1** — a January 2023 browser, three years unpatched. Remove or update.

---

## Settled — do not revisit

- **NVENC.** The MX230 is GP108 and has no encoder silicon. Measured failing.
  `h264_qsv` (Intel Quick Sync) works and is the only hardware encoder on this machine.
- **CUDA for dictation.** CPU does 7.91× realtime on `base int8`, measured. The GPU adds nothing
  a user can perceive. `nvidia-cublas-cu12` / `nvidia-cudnn-cu12` serve CTranslate2 only — they do
  not accelerate video encoding, Kokoro, or image generation.
- **`float16` on this GPU.** Absent from CTranslate2's supported compute types. Pascal has
  crippled FP16. Use `int8`.
- **Chatterbox voice cloning.** Needs ~2.3 GB VRAM minimum against 2.0 GB available.
