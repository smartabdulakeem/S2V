# Brief: stop shipping GPL ffmpeg, and make the installer work

Hand this whole file to Antigravity.

**Read `ANTIGRAVITY-RULES.md` first — its standing rules apply.**

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget`. **Do not commit. Do not push.**
**Baseline: 708 passed, 1 xfailed, 0 failures.** Roughly 11 minutes.
Python: `C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe` (not on PATH).

---

## What is wrong

The owner decided Smart Studio will **not bundle ffmpeg**. It will use the copy already on the
user's machine. That decision is made and is not reopened by this brief.

The reason is licensing. Both ffmpeg builds on this machine report the same thing:

```
configuration: --enable-gpl --enable-version3 ...
```

Verified 3 Sep by running each binary with `-version`:

| Binary | Version | Flags |
|---|---|---|
| `vendor/ffmpeg/bin/ffmpeg.exe` | 8.1.1 essentials (gyan.dev) | `--enable-gpl --enable-version3` |
| `imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe` | 7.1 essentials (gyan.dev) | `--enable-gpl --enable-version3` |

Shipping either one attaches GPL-3 to everything in the box. Personal use is fine. Selling it is
not. **The app invoking an ffmpeg the user installed themselves carries no such obligation** —
that is the whole point of the change.

An LGPL build is not the escape hatch it looks like. LGPL ffmpeg builds cannot contain libx264
(that codec is GPL-only), and `pipeline/composer.py:70` `_get_best_encoder` hardcodes
`libx264` at CRF 18. Swapping builds would quietly change render quality. Do not attempt it.

### Six defects, all verified

1. **CI deliberately bundles the GPL binary.** `.github/workflows/build.yml:30-41` is a
   *"Download FFmpeg"* step that fetches the gyan.dev GPL zip into `vendor\ffmpeg\bin\`, and
   line 51 passes `--add-data "vendor;vendor"` to PyInstaller. Deleting `vendor/` locally fixes
   nothing — CI recreates it every build.

2. **`vendor/` is not only ffmpeg.** It holds `ffmpeg` (292 MB) and `realesrgan` (51 MB).
   Real-ESRGAN is BSD-3 and **must keep shipping**. Removing the whole `--add-data "vendor;vendor"`
   line would break upscaling. Only ffmpeg comes out.

3. **The build still references edge-tts,** removed from the code on 2 Sep in `c14ec96`.
   `build.yml:63` `--hidden-import "edge_tts"` and `build.yml:68` `--collect-all "edge_tts"`.
   The package is still installed on this machine, which hides it locally. On a clean CI runner
   this is either dead configuration or a hard build failure. **Nobody has run PyInstaller to find
   out which.** It comes out either way.

4. **`moviepy` exists to serve one function that nothing calls.** `pipeline/voiceover.py:1059`:

   ```python
   def get_audio_duration(mp3_path: str) -> float:
       from moviepy.editor import AudioFileClip
       with AudioFileClip(mp3_path) as clip:
           return clip.duration
   ```

   `grep -rn "get_audio_duration"` across the repo returns **exactly one line — that definition.**
   Zero call sites. This dead function is the only reason `moviepy` is in `requirements.txt`, and
   `moviepy` is the only reason the second GPL ffmpeg binary is on disk.

5. **`setup.bat` fails for every fresh install.** Step 3 runs
   `pip install -r requirements-desktop.txt`. That file was deleted on 8 Aug in commit `9ab69aa`
   ("a strict subset of requirements.txt") and setup.bat was never updated. Both current ffmpeg
   error messages tell the user *"Please run setup.bat first"* — pointing them at a broken script.

6. **ffmpeg is absent from `THIRD-PARTY-NOTICES.txt`.** The file covers 19 components and omits
   the largest binary in the box.

### And three finders, not two

| Where | Order | On failure |
|---|---|---|
| `pipeline/composer.py:28` | env → vendor → PATH | returns the bare string `"ffmpeg"` |
| `pipeline/stitcher.py:12` | vendor → PATH | raises `FileNotFoundError`, "run setup.bat" |
| `pipeline/voiceover.py:51` | env → vendor → PATH | raises `RuntimeError`, "run setup.bat" |

All three prefer the vendor copy. `composer.py:45` `_find_ffprobe` is the only ffprobe finder and
is imported by `captions.py`, `narration_timing.py`, `orchestrator.py` and four test files.

---

## Job 1 — One finder, PATH first

Create `pipeline/ffmpeg_locate.py`. It exports exactly two public functions:

```python
def find_ffmpeg() -> str:
    """Absolute path to an ffmpeg binary. Raises FFmpegMissing if there is none."""

def find_ffprobe() -> str:
    """Absolute path to an ffprobe binary. Raises FFmpegMissing if there is none."""
```

**Search order, and it matters:**

1. An explicit override — keep honouring `IMAGEIO_FFMPEG_EXE` / `IMAGEIO_FFPROBE_EXE` so nothing
   already set breaks.
2. **`shutil.which()` — the system PATH.** This is what the shipped app will find.
3. `vendor/ffmpeg/bin/` — **development convenience only.** The owner has it, and the suite needs
   it. It will not exist in a shipped build once Job 3 lands.
4. Raise `FFmpegMissing`.

PATH moves ahead of vendor deliberately: the order the customer runs should be the order that
gets tested. Note in your report that this changes which binary runs on any machine that has both.

Define one exception, in the same module:

```python
class FFmpegMissing(RuntimeError):
    """ffmpeg or ffprobe could not be found on this machine."""
```

Its message must name the program, say where to get it, and **must not mention `setup.bat`.**
Something a non-programmer can act on:

> FFmpeg is not installed on this computer. Smart Studio needs it to build video and to measure
> narration. Install it from https://ffmpeg.org/download.html, make sure it is on your PATH, then
> restart Smart Studio.

**Then delete all three old finders** and repoint every caller at the new module:

- `pipeline/composer.py` — `_find_ffmpeg`, `_find_ffprobe` (4 + 1 call sites in that file)
- `pipeline/stitcher.py` — `_find_ffmpeg`
- `pipeline/voiceover.py` — `_find_ffmpeg` (5 call sites)
- `pipeline/captions.py:24,101` · `pipeline/narration_timing.py:52` ·
  `pipeline/orchestrator.py:24,297` · `pipeline/timeline_audio.py:11`

`tests/test_composer.py`, `tests/test_parallel.py`, `tests/test_media_server.py` and
`tests/test_captions_tts_timings.py` import `_find_ffmpeg` / `_find_ffprobe` from
`pipeline.composer`. **Update the imports; do not keep a shim.** If a name survives in
`composer.py` purely so a test still passes, the job is not done.

When you are finished, `grep -rn "def _find_ffmpeg\|def _find_ffprobe" --include=*.py .` must
return nothing.

## Job 2 — Delete `get_audio_duration`, and moviepy with it

- Delete the function at `pipeline/voiceover.py:1059`. It has no callers. Do not "replace" it with
  an ffprobe version — nothing wants it. `pipeline/narration_timing.py:52` already reads durations
  with ffprobe and is the real implementation.
- Remove `moviepy==1.0.3` from `requirements.txt`.
- Remove `--hidden-import "moviepy"` from `build.yml:66`.
- `app.py:21` and `cli.py:8` both carry the comment *"Add vendor ffmpeg to PATH so moviepy/ffmpeg
  can find it"* and set `IMAGEIO_FFMPEG_EXE`. Once moviepy is gone that block has one job left —
  putting vendor ffmpeg on PATH for child processes. Keep that behaviour, fix the comment, and do
  not let it override an ffmpeg the user already has on PATH.

Do **not** touch `tools/fetch_sounds.py` or `tools/promote_sounds.py`. They call
`imageio_ffmpeg.get_ffmpeg_exe()`, they are developer tools, and they are not shipped. Say in your
report that you left them.

## Job 3 — Stop the build shipping it

In `.github/workflows/build.yml`:

- **Delete the entire "Download FFmpeg" step**, lines 30–41.
- **Replace `--add-data "vendor;vendor"` (line 51) with `--add-data "vendor/realesrgan;vendor/realesrgan"`.**
  Real-ESRGAN must still ship. ffmpeg must not.
- Delete `--hidden-import "edge_tts"` (63) and `--collect-all "edge_tts"` (68).
- Delete `--hidden-import "moviepy"` (66).

The shipped zip loses roughly 292 MB. Say the measured before/after in your report if you can get
it; if you cannot run the workflow, say that instead of guessing.

## Job 4 — Make `setup.bat` work

- **Step 3 must install `requirements.txt`.** `requirements-desktop.txt` does not exist.
  Fix both the `pip install` line and the error message below it that names the same missing file.
- **Step 2 must stop downloading ffmpeg.** Replace the download with a check:
  - ffmpeg on PATH → say so, continue.
  - not on PATH → print the same plain-English message as `FFmpegMissing`, and **do not fail the
    install.** Everything except rendering still works. The user can install ffmpeg and re-run.
- Leave step 4 (Whisper) and step 5 (validator) alone.

## Job 5 — Tell the owner before he hits it, not during a render

Right now a missing ffmpeg surfaces as a raised exception in the middle of a render, or — worse,
from `composer.py` — as the bare string `"ffmpeg"` handed to `subprocess`, which fails with
whatever Windows says about a missing executable.

- Add an Api method on the `Api` class in `app.py` that reports whether ffmpeg and ffprobe were
  found, returning the path of each and the plain-English message when they were not.
- The frontend calls it on load and shows a **banner** when either is missing: what is wrong, and
  the link. It must not block the app — Script and Storyboard work fine without ffmpeg. Only
  narration measurement and rendering do not.
- Follow the existing banner/notice pattern in `frontend/app.js` rather than inventing one.
  **`index.html` is capped at 19 inline `style="` attributes and is at 19.** Layout goes in
  `frontend/style.css`.
- `cli.py` gets the same check as a plain stderr line before it starts work.

## Job 6 — Notices

In `THIRD-PARTY-NOTICES.txt`:

- Remove the `moviepy` section (entry 1) and its table-of-contents line, then **renumber the
  remaining entries 1–18.** It is no longer a dependency, so its notice is no longer owed.
- Add a short **FFmpeg** note recording that Smart Studio calls an ffmpeg the user installs
  themselves, that no ffmpeg binary is distributed with the app, and that ffmpeg is licensed
  LGPL-2.1+ or GPL-2+ depending on the build. Put it in its own clearly-marked section — it is a
  statement about something *not* distributed, and it should not read as if it were.
- Leave the `TODO(owner): EULA clause` line for Kokoro alone.

---

## Tests

**`tests/test_licence_cleanup.py` already exists and is where this belongs.** It is the test that
should have caught defect 3 and did not: it checks `requirements.txt`, `app.py`, `pipeline/*.py`
and `config/voices.json`, and never opens the build workflow.

Add to it:

1. **The workflow ships no ffmpeg.** Read `.github/workflows/build.yml` as text and assert:
   no `gyan.dev`, no `ffmpeg-release-essentials`, no `--add-data "vendor;vendor"`, no `edge_tts`,
   no `moviepy`. Assert positively that `vendor/realesrgan` **is** still added — this test must
   fail if someone deletes upscaling along with ffmpeg.
2. **One finder.** Assert `pipeline/composer.py`, `pipeline/stitcher.py` and `pipeline/voiceover.py`
   contain no `def _find_ffmpeg` and no `def _find_ffprobe`.
3. **`setup.bat` names a file that exists.** Extract every `-r <name>.txt` from `setup.bat` and
   assert each named file is present in the repo. This is the general form of defect 5 and will
   catch the next one.
4. **moviepy is gone** — not in `requirements.txt`, not imported anywhere under `pipeline/`,
   not in `app.py` or `cli.py`.
5. **`find_ffmpeg` prefers PATH over vendor.** Point `shutil.which` at a temp file via monkeypatch
   and assert that path comes back even though `vendor/ffmpeg/bin/ffmpeg.exe` exists on this
   machine. Then make `which` return `None` and assert the vendor path comes back. Then hide both
   and assert `FFmpegMissing` is raised.

**One existing test must change.** `tests/test_licence_cleanup.py:135` lists `"moviepy"` in
`required_components` for the notices file. Once moviepy is not distributed, that notice is not
owed, so the entry comes out of the list. **Quote the assertion before and after in your report**
and say this sentence: the component was removed from the product, not the requirement removed
from the test. Nothing else in that list may change.

Rule 4 in `ANTIGRAVITY-RULES.md` applies to every one of these: **break the code on purpose and
confirm the test fails.** A test that reads a workflow file and asserts a string is absent passes
happily against an empty file. Assert the file is non-empty and that a known-good line is present.

---

## Acceptance

Run and paste the real output, not a description of it:

1. **Full suite green.** Expect **708 + your new tests, 1 xfailed, 0 failures.** Do not run it
   while anything else heavy is running — `test_parallel.py` does a real two-minute render and
   fails when starved of CPU. That happened on 3 Sep with nothing wrong with the code.

2. **A render still works end to end.** This is the check that matters most: Job 1 rewired every
   ffmpeg call site in the app. Render a short sample and paste the output path and its size.

3. **Prove the missing-ffmpeg path.** Temporarily rename `vendor\ffmpeg` and, with no ffmpeg on
   PATH, confirm: the app opens, the banner appears, Script and Storyboard still work, and the
   message names ffmpeg.org. **Rename it back.** Paste what the banner said.

4. **`grep -rn "def _find_ffmpeg\|def _find_ffprobe" --include=*.py .` returns nothing.**

5. **State whether you ran PyInstaller.** If you did, say whether `--collect-all "edge_tts"` was a
   warning or a failure — that question is currently unanswered and the answer is worth having.
   If you did not, say so plainly. Do not guess.

## Out of scope

Do not touch: `pipeline/motion.py` and the camera slider (Slice B), `Measure narration` and its
speed (Slice C), the Timeline UI (Slices D–F), `pipeline/sound.py`, `media_server.py`, voice
selection or `FALLBACK_VOICE`, and anything to do with Lemon Squeezy.

Do not delete `vendor/ffmpeg/` from this machine. The owner renders with it and the suite needs
it. This brief stops it being *shipped*; it does not remove it from his desk.

---

**Stop when the report is written. Do not commit. Do not push.**
