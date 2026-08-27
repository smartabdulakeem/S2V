# What FFmpeg can bring to Smart Studio

**Measured on this machine, 27 Aug 2026.** Every claim below was checked against
`vendor/ffmpeg/bin/ffmpeg.exe` and the current code, not recalled from memory.

---

## First, a correction

**FFmpeg is not something to add. It is already the engine of the entire render.**

`vendor/ffmpeg/bin/ffmpeg.exe` — version **8.1.1**, a full gyan.dev build, 101 MB, on disk
now. Every segment, every concat, every mux already goes through it. `_find_ffmpeg()` in
`pipeline/composer.py` locates it, and the compositor shells out to it constantly.

So the question is not "what would FFmpeg give us". It is **"what is this build capable of
that we are not asking it to do"** — and the answer is a lot, including two things that solve
problems already on the roadmap.

The build has everything: `libass`, `libx264`, `libx265`, `librubberband`, `libvidstab`,
`libvmaf`, `libmp3lame`, `libopus`, plus hardware encoders.

---

## What is already wired

Worth knowing so nobody rebuilds it:

| Capability | Where | State |
|---|---|---|
| Ken Burns motion | `zoompan`, 7 uses in `composer.py` | working |
| Burned-in captions | `ass=` / `subtitles=` via libass | working |
| Loudness normalisation | `loudnorm=I=-16:TP=-1.5:LRA=11` (`voiceover.py:118`) | working, EBU R128 |
| **Music beds** | `pipeline/sound.py` — `pick_bed`, `build_bed_track`, `mix_bed_under_narration` | **written and called** from `composer.py:160-180` |
| **Music ducking** | `sidechaincompress`, 2 uses | **working** — music dips under narration automatically |
| Music over the finished film | `stitcher.py:98`, `amix` | working, driven by `project.background_music` |
| Fades within a shot | `afade`, `transition_in/out` | working |
| Text overlays | `drawtext`, 3 uses | working |
| Final stitch | concat demuxer, `-c copy` | working |

**Background music and sound effects are not missing.** `pipeline/sound.py` matches a bed to
each scene's text, loops it to length, and ducks it under the narration with a sidechain
compressor. The library reports **87 sounds and 12 music beds**. What is missing is not the
capability — it is **control**: nothing in the UI lets you choose a bed, set its level, mute it
for one scene, or place a specific sound effect at a specific moment.

That reframes the work. It is a control-surface problem, not an audio-engineering one.

---

## The seven things not being used

Ordered by what they are worth.

### 1. A post-render edit pass — the thing you actually asked for

Everything needed already exists in this build. A finished MP4 can be edited without
re-rendering anything:

| Edit | How |
|---|---|
| Replace a bad shot | `-ss`/`-to` trim either side, concat the replacement between them |
| Extend or shorten a shot | re-encode that range only, concat back |
| Drop a segment | two trims and a concat |
| Lay music over a section | `amix` with `-itsoffset` on the music input |
| Place a sound effect at 04:12 | `-itsoffset 252 -i sfx.wav` then `amix` |
| Fix a level | `volume` or a second `loudnorm` pass |
| Re-cut captions | burn a new `.ass` over the existing video |

**Cuts on keyframe boundaries are lossless and near-instant** (`-c copy`, no re-encode). Only
the touched range needs re-encoding, and only when a cut falls mid-GOP.

This is the highest-value item: it turns a 30-minute render from all-or-nothing into something
repairable. Today, one bad shot means re-rendering the film.

### 2. Automatic QA — catches the placeholder-card bug

ROADMAP B1 records that **46 placeholder cards survived into a finished 30-minute video**
because "tests pass; tests are not eyes."

This build has the eyes:

- **`freezedetect`** — a shot that never moves. A placeholder card is a frozen frame.
- **`blackdetect`** — black or near-black stretches.
- **`silencedetect`** — narration that failed and left dead air.
- **`blackframe`**, **`signalstats`** — per-frame brightness and colour statistics.

All confirmed present. A post-render check running these three over the master and reporting
timestamps would have caught all 46 automatically, in seconds, without watching the film.

**This is the cheapest high-value item on the list.** It is one FFmpeg invocation and a
parser.

### 3. Hardware encoding — free speed, currently thrown away

Measured on this machine just now:

```
h264_nvenc     FAILS      (MX230 is GP108 — no NVENC silicon)
h264_amf       FAILS      (no AMD GPU)
h264_qsv       WORKS      ← Intel Quick Sync, available and unused
```

Meanwhile `_get_best_encoder` (`composer.py:61`) says in its own docstring that it will
*"Probe system once at startup to select the fastest reliable H.264 encoder"* — and then
**probes nothing**. It hardcodes `libx264 -preset veryfast -crf 21` and returns.

Quick Sync typically encodes several times faster than `libx264 veryfast` at similar quality,
and offloads the CPU — which matters here, because the owner has repeatedly asked that nothing
peg the machine. The function already exists and already caches its answer; it just needs to
actually probe.

Note this is the **opposite** of the GPU conclusion in the older handoff. That analysis was
about *CUDA for the ML models* on a 2 GB MX230 with a 2020 driver, and it was correct. Quick
Sync is the Intel iGPU's fixed-function video encoder — a different chip, a different job, and
it works right now.

### 4. Real transitions between scenes

`stitcher.py` joins segments with the **concat demuxer and `-c copy`**. That is a hard cut,
always. The `transition_in` / `transition_out` fields only fade *within* a shot; they cannot
cross a segment boundary, because the demuxer never decodes.

`xfade` (video) and `acrossfade` (audio) are both present. A crossfade, dissolve, wipe or fade
through black between scenes needs a `filter_complex` pass instead of the demuxer — slower,
because it re-encodes, but it is the difference between a slideshow and a film.

### 5. Fitting narration to a target duration

- **`atempo`** — change speed without changing pitch. Fit a 43-second narration into a
  40-second music phrase.
- **`librubberband`** — change **pitch without changing speed**. Confirmed present.
- **`apad`** — pad to an exact length.
- **`silenceremove`** — trim the dead air Supertonic and Kokoro leave at chunk ends.

`librubberband` pairs directly with the delivery profiles just built: pitch is the one
expressive dimension neither offline engine exposes. A grave documentary read could sit a
couple of semitones lower than a motivational one, from the same voice, with no retraining and
no cloud call.

### 6. Two-pass loudness

`loudnorm` is currently applied single-pass per narration segment. Single-pass is a live
estimate; two-pass measures first, then corrects. For the final master — where consistency
across a 30-minute film matters — two-pass is meaningfully more accurate. Cheap: one extra
analysis pass over audio only.

### 7. Motion smoothing

`minterpolate` can interpolate frames so a slow Ken Burns push stops stepping. It is expensive
and should be a per-project option, not a default. Listed for completeness rather than
recommended.

---

## What is not worth doing

- **`libvmaf`** — perceptual quality scoring. Interesting, no practical use here.
- **`libvidstab`** — stabilisation. There is no shaky footage; every source is a still image.
- **NVENC / AMF** — measured, both fail on this hardware. Do not revisit.
- **x265 / AV1** — smaller files, much slower encodes, and YouTube re-encodes everything
  anyway. No benefit.

---

## Recommended order

1. **Automatic QA pass** (`freezedetect` + `blackdetect` + `silencedetect`). Smallest change,
   catches a bug class that has already shipped in a finished film.
2. **Quick Sync encoding** — make `_get_best_encoder` do what its docstring claims. Pure speed,
   no behaviour change, easy to verify by timing a render.
3. **Post-render edit pass.** The largest piece, and the one asked for. Worth its own spec.
4. **Sound control surface** — expose the beds and SFX that already work.
5. **Cross-segment transitions** via `xfade`.
6. Pitch and duration fitting, two-pass loudness.

Items 1 and 2 are each an afternoon. Item 3 is a project.
