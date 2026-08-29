# Brief: make the finished film look sharp

Hand this whole file to Antigravity. Everything it needs is here.

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget` — stay on it. Do not switch branches. Do not push.
**Never** run `git add -A` — it stages ~816 MB including two 310 MB ONNX models.
Stage only the files listed at the end.

---

## The problem

Finished films look soft. The instinct is to blame the encoder. **The encoder is not the main
cause** — measured, and the numbers are below. Work the items in the order given, because item A
is worth more than B through G combined, and fixing the encoder first will make it look like
nothing changed.

---

## Environment

Python is NOT on PATH. Use the full path:
`C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe`

Prefix any command that prints prompt or narration text with `PYTHONIOENCODING=utf-8` — the
Windows console dies on `₦` and `—`, which looks like an engine failure but is not.

FFmpeg is vendored at `vendor/ffmpeg/bin/ffmpeg.exe` (8.1.1). Run the app with `run.bat`.
Full test suite takes ~7 minutes.

---

## A. The images are 1376×768 and get upscaled 1.74× ← START HERE

This is the dominant cause. Measured today:

| Stage | Size | Where |
|---|---|---|
| What the app **asks** Pollinations for | 1920×1080 | `pipeline/visuals.py:31-36`, `ASPECT_RATIOS` |
| What Pollinations **returns** | **1376×768** | measured across `library/new image/*.jpg` |
| What the compositor scales it to | **2400×1350** | `composer.py`, `pad = 1.25` for the default motion style |

That is **1.74× linear, 3.07× in area**, on every frame of every film, before the Ken Burns crop
even starts. Under the `dynamic` motion style the padding is 1.36, so it becomes 2611×1468 —
**1.90× linear**. No encoder setting recovers detail that was never in the source.

Verify it yourself first:

```
PYTHONIOENCODING=utf-8 <python> -c "from PIL import Image; import glob,os; [print(Image.open(f).size, os.path.basename(f)) for f in sorted(glob.glob('library/new image/*.jpg'), key=os.path.getmtime, reverse=True)[:6]]"
```

**Investigate, in this order, and report what each is worth:**

1. **Ask Pollinations for more pixels.** The URL template is `POLLINATIONS_URL` at
   `visuals.py:29` and takes `width`/`height`. Find out empirically what the endpoint actually
   honours — try 1920×1080, 2048×1152, 2400×1350. It may cap or snap to model-native sizes. If
   asking for 2400×1350 returns 2400×1350, item A is solved outright and B–G become polish.
2. **If the endpoint caps**, the padding is doing avoidable damage. The compositor scales the
   source to `pad × output` so the crop has room to travel. Consider capping `pad` at what the
   source can support, and reducing travel to match, rather than upscaling into a crop.
3. **Only then** consider an upscale step. There is no GPU headroom here (2 GB, see the rules),
   so any model-based upscaler must be CPU and will be slow. Measure before proposing it.

**Do not** change the motion travel numbers in `pipeline/motion.py` without saying so explicitly
in your report — they are locked by `tests/test_motion_style.py`, which asserts the rendered zoom
matches the declared travel to within 0.03.

---

## B. The scaler is FFmpeg's default, not lanczos

`pipeline/composer.py`, the filter chain starts:

```python
filters = [f"scale={pad_w}:{pad_h}"]
```

No `flags=`. On a 1.74× upscale of a detailed still, `flags=lanczos` is visibly sharper than the
default. One-line change, measurable. Try `scale={pad_w}:{pad_h}:flags=lanczos` and compare
frame grabs.

---

## C. The encoder is tuned for speed and lies about it

`pipeline/composer.py`, `_get_best_encoder()`:

```python
"""Probe system once at startup to select the fastest reliable H.264 encoder."""
best = ("libx264", ["-preset", "veryfast", "-crf", "21"])
```

The docstring says it probes. **It probes nothing** — the value is hardcoded.

- `-preset veryfast` trades compression efficiency for speed. For a final deliverable, `slow` or
  `medium` gives better quality at the same CRF, or the same quality at a smaller file.
- `-crf 21` is visibly lossy on gradients and slow pans. `18` is near-transparent.
- Missing `-movflags +faststart`, which YouTube and every web player want.

Video is encoded **once** (shot level) and then `-c copy` all the way through segment concat and
the final stitch — so there is only one generation to protect. Getting it right costs render time
and nothing else. Measure: encode the same segment at `veryfast/21` and `slow/18`, report render
time, file size, and frame grabs of the same timestamp.

---

## D. Audio has no bitrate set anywhere

`-c:a aac` appears with **no `-b:a`** in six places (`composer.py` ×4, `stitcher.py` ×2). That
takes FFmpeg's default, which is low for narration. Set `-b:a 192k` consistently.

---

## E. The stitcher picks its audio stream by luck

`pipeline/stitcher.py`, the **no background music** branch — which is the common case:

```python
cmd2 = [ffmpeg, "-y", "-i", temp_video, "-i", master_audio_path,
        "-c:v", "copy", "-c:a", "aac", output_path]
```

There is no `-map`. Two inputs each carry audio (`temp_video` has the concatenated segment audio,
`master_audio_path` is the master), and FFmpeg picks one by its own default rules rather than
because anyone chose. The music branch immediately below **does** map explicitly. Make both
explicit: `-map 0:v -map 1:a`.

Check whether the current behaviour is actually selecting the master or the segment audio before
changing it, and say which in your report — if it has been picking the wrong one, that is a
separate bug worth calling out.

---

## F. Corner darkening is applied twice — there is already a failing test

`tests/test_composer.py::test_composer_corner_brightness_vignette_check` fails, and has failed
since before this work started. It measures **62.2% corner darkening against a 40% limit**
(source 19.7% → output 81.9%). Corners come out much darker than intended.

The suspicion in the existing notes is the preset-treatment wiring meeting an already-vignetted
cached image. Confirm the mechanism before changing anything.

⚠️ **This test SKIPS when no cached segment of ≥10s exists**, so clearing `cache/` hides it
rather than fixing it. It is not flaky — it is being skipped. Make sure it is actually running
before you claim it passes.

---

## G. Suspected zoompan stepping — measure before assuming

`zoompan` computes its crop per frame and lands on integer pixel positions. On a slow zoom this
can produce visible stepping rather than smooth motion. Whether it is happening here is
**unverified** — do not fix it before you have shown it.

How to show it: render one shot with `motion_style="gentle_drift"` (the slowest, so stepping is
most visible), extract 30 consecutive frames, and measure the apparent size of a fixed feature
across them. Smooth motion gives an even progression; stepping gives repeated values followed by
a jump. `tests/test_motion_style.py` has a working marker-measurement helper you can copy —
`_marker_size()` and `_zoom_ratio()`.

If it is real, the usual mitigation is scaling well above the output before zoompan and
downscaling after, which conflicts with item A. Report the trade-off; do not pick unilaterally.

---

## Rules

1. **Do not add NVENC.** `FFMPEG-CAPABILITIES.md` line 99: `h264_nvenc FAILS (MX230 is GP108 —
   no NVENC silicon)`. Line 160: *"measured, both fail on this hardware. Do not revisit."* The
   card has no video encoder on the die. **`h264_qsv` (Intel Quick Sync) is measured working** and
   is the only hardware encoder available — it is a legitimate option for item C, but treat it as
   a separate experiment and report quality separately, since hardware encoders trade quality for
   speed at the same bitrate.
2. **Do not touch `pipeline/motion.py` travel values** without flagging it (see item A).
3. **The shot cache key is `v4`** and already includes duration, motion, treatment, resolution,
   fps and motion style. If you change how a shot renders, **bump it to `v5`** or every cached
   clip from the old behaviour is served back and your fix will look like a no-op.
4. A **stale `cache/`** causes phantom failures — `test_parallel.py` once failed with "Segment
   composition failed" for no code reason and deleting the 2.2 GB `cache/` fixed it.
5. **A git worktree has no gitignored assets** (`vendor/ffmpeg`, `library/images`), so render
   tests always fail there. That proves nothing — work in the main tree.

---

## What "done" looks like

The owner verifies everything, so the report has to let him check without redoing the work.

For **each** item you touch, report:

- the measurement **before** and **after**, with the actual numbers
- **frame grabs at the same timestamp**, before and after, as files on disk with their paths
- render time and output file size for the same input
- which of items A–G you did **not** do, and why

State plainly if an item turned out not to matter. A measured "this changed nothing" is a useful
result and will be believed; an unmeasured "improved quality" will not.

Finish with the full suite:

```
PYTHONIOENCODING=utf-8 <python> -m pytest tests/ -q
```

Baseline before you start: **406 passed, 1 failed, 1 xfailed**. The one failure is item F. If
your run shows more failures than that, they are yours.

---

## Files you may stage

```
pipeline/composer.py
pipeline/stitcher.py
pipeline/visuals.py
tests/
```

Nothing else. No `git add -A`. No push.
