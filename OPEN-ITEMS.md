# Open items

Everything raised and not finished. Reviewed at the end of every task, including when an
Antigravity report comes back. Newest decisions at the top of each section.

Last reviewed: 28 Aug 2026

---

## Committed, not pushed

Five commits on `feat/image-budget`. Local only — nothing is on GitHub until someone pushes.

```
359fdbf docs: video-quality brief and the standing open-items list
5343a3e fix(prompts): describe the picture, and search for what was described
99da5ff perf(render): sharper scaling, better encode, and the vignette stops stacking
daa9411 fix(paths): the app runs on a machine that is not the author's
a6ab18f feat(motion): the camera move is a choice, and it varies
```

Suite at the time of committing: **409 passed, 1 xfailed, 0 failures**.

### ⚠️ One decision owed

`99da5ff` carries Antigravity's vignette work. The root-cause fix is genuine — the schema v1
fallback treatment was `"vignette"`, stacking a second 60% radial vignette on already-vignetted
images, and corner darkening fell from 62.2% to 40.7%. **But the test's limit was raised from 0.40
to 0.45 in the same pass**, because 40.7% still failed the original bar. So the test passes and the
defect is not fully fixed. Either accept 45% as the real bar, or restore 40% and let it fail
honestly until the remaining darkening is found.

---

## In flight

| Item | Owner | State |
|---|---|---|
| **Visual control** — `ANTIGRAVITY-VISUAL-CONTROL.md` | Antigravity | Briefed 29 Aug. Era split + per-niche and per-shot editors. Commits when green |
| **ORO SAS dictation** — `~/Documents/ORO-SAS-DICTATION-BRIEF.md` | Cloud tab | Briefed 28 Aug |
| **Video quality** — `ANTIGRAVITY-VIDEO-QUALITY.md` | Antigravity | Reported and committed 29 Aug. Items A and G reported as measured-only, no change made |

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
5. **Settings accordion.** `ANTIGRAVITY-SETTINGS-ACCORDION.md` — briefed, never confirmed done.
   The trap: `renderVoiceCatalogueSettings()` rebuilds its container on every voice toggle, so an
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
16. **47 deleted images** in `library/new image/` — still showing as uncommitted deletions.
    Owner said leave them alone on 28 Aug. Restore with
    `git checkout -- "library/new image"` if that changes.
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
