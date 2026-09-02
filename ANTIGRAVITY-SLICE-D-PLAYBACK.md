# Brief: Slice D — the Timeline plays

Hand this whole file to Antigravity.

**Read `ANTIGRAVITY-RULES.md` first — its standing rules apply.**

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget`. **Do not commit. Do not push.**
**Baseline:** 692 passed, 1 xfailed, 0 failures.

---

## What this is for

This is the feature the owner asked for before any other. He wants to **press play, hear the
narration, and watch the pictures change**, so he can see with his own eyes whether each picture
is in the right place — and fix the ones that are not.

Today the Timeline scrubs and previews. It does not play. There is no `<audio>` element on it and
no sound anywhere except the Voiceover Studio.

---

## The design decision, already made

**One concatenated narration file per film, and one `<audio>` element that drives everything.**

Do not chain 347 per-segment files. Gapless playback across hundreds of mp3s produces clicks and
accumulating drift, and it would make the playhead a second source of truth that disagrees with the
audio. With a single element, `audio.currentTime` **is** the playhead. There is nothing to keep in
sync because there is only one clock.

Everything else follows from that: seeking is an assignment to `currentTime`, the picture on screen
is a lookup against it, and pause is pause.

## What already exists — do not rebuild these

Read them before writing anything, and do not duplicate their logic:

| What | Where |
|---|---|
| Per-segment narration mp3s and real seconds | `pipeline/narration_timing.py` — `measure_narration` writes `narration_audio` and `narration_seconds` onto each segment |
| The two maps keyed by segment id | `pipeline/narration_timing.py` — `timing_maps` |
| The picture model with `startsAt` and `seconds` | `frontend/app.js` — `picturesFromScript` (~L1691) |
| Playhead state and seeking | `frontend/app.js` — `tlPlayhead`, `timelineSeek` (~L2404), `timelineNudge`, `timelineSeekPicture` |
| Which script line is under a time | `frontend/app.js` — `tlLineAt` (~L2461) |
| The preview frame and transport row | `frontend/index.html`, `.tl-preview` / `.tl-frame` / `.tl-transport` |
| ffmpeg concat demuxer, used for video | `pipeline/composer.py` ~L930 — the same pattern, for reference |

---

## Job 1 — build the film's narration track

Create `pipeline/timeline_audio.py` with one entry point:

```python
def build_timeline_audio(script_data: dict, project_dir: str) -> dict:
    """
    Concatenate every segment's narration into one mp3 for playback.

    Returns {"path": str, "seconds": float, "offsets": {segment_id: float},
             "segments": int, "rebuilt": bool}
    """
```

- Output goes to `<project_dir>/timeline_narration.mp3`.
- Use the ffmpeg **concat demuxer** with `-c copy`. Every input is TTS output in the same format,
  so a stream copy is correct and is far faster than re-encoding an 18-minute film.
- `offsets[segment_id]` is the running sum of the preceding segments' measured seconds — where that
  line begins in the concatenated file.
- Resolve ffmpeg through `pipeline.composer._find_ffmpeg`. **Do not write a third ffmpeg finder** —
  there are already two, and a later task is removing them.

**Caching, because this must not run on every visit to the screen.** Write
`<project_dir>/timeline_narration.json` beside the mp3 holding the segment ids, their audio paths
and their `st_mtime` values. On a later call, if that fingerprint matches and the mp3 still exists,
return the existing file with `"rebuilt": False`. A changed or re-measured narration must rebuild.

**Segments with no audio.** A film may be half-measured. Skip any segment with no
`narration_audio` on disk, and return the count in the result so the UI can say so. Do **not**
insert silence for it and do **not** fail the whole build.

### The correctness risk, and the test that catches it

The playhead is `audio.currentTime`, but the picture boundaries come from summing
`narration_seconds`. **If the concatenated file's real duration disagrees with that sum, every
boundary drifts, and it gets worse further into the film.** That is the defect this job can produce
and it would look like "the pictures are slightly wrong near the end".

After building, `ffprobe` the output and compare it to the sum of the measured seconds. Return both
numbers in the result. Write a test asserting they agree within **100 ms** on a real multi-segment
build, and say plainly in the report what the real difference was on a long film.

## Job 2 — deliver the file to the page

The desktop app loads `frontend/index.html` from **`file://`** (`app.py` ~L1736). The dev server
serves over **http://**. Playback has to work in both, and only one of them is easy to test.

Add to `app.py`, near the other Timeline endpoints:

```python
def prepare_timeline_audio(self, script_data: dict, project_dir: str) -> dict:
    """Build (or reuse) the narration track and tell the page where it is."""
```

Return the absolute path **and** a `src` the page can put straight on an `<audio>` element. In the
desktop app that is a `file:///` URL with backslashes converted to forward slashes and the path
percent-encoded. In dev-server mode it is a URL the dev server can serve.

**`tools/devserver.py` must serve the mp3.** It already guesses content types (~L148); make sure a
project audio path is reachable and returns `audio/mpeg`. Range requests matter for seeking — if
the dev server cannot do partial content, say so in the report rather than pretending seeking works.

**Do not base64 the file into the page.** An 18-minute mp3 is roughly 17 MB, and about 23 MB once
base64-encoded. Pushing that through the JS bridge on every visit is not acceptable. Base64 is the
existing pattern for a *three-second voice preview* (`app.py` ~L1211) and it does not generalise
to a whole film.

**This is the part that cannot be proven on the dev server.** `file://` media loading is a
different code path from `http://`. See the reporting requirements.

## Job 3 — make it play

In `frontend/index.html`, add one `<audio id="tl-audio" preload="metadata">` inside `.tl-preview`,
and a play/pause button as the **first** control in `.tl-transport`, before the existing four:

```html
<button type="button" id="btn-tl-play" onclick="timelineTogglePlay()" title="Play / pause" aria-label="Play">&#9654;</button>
```

In `frontend/app.js`:

- `timelineTogglePlay()` — plays or pauses. On first play, calls `prepare_timeline_audio` and sets
  the source. Show a busy state while the track builds; on a long film this takes a few seconds.
- **The playhead follows the audio.** While playing, a `requestAnimationFrame` loop sets
  `tlPlayhead = audio.currentTime` and redraws. **Cancel the loop on pause and when leaving the
  screen** — a loop left running on a hidden pane burns CPU for nothing.
- **Seeking goes the other way.** `timelineSeek`, `timelineNudge`, `timelineSeekPicture` and
  clicking the lanes must set `audio.currentTime`. They already move `tlPlayhead`; make that one
  assignment the single place the audio is told, rather than repeating it in four functions.
- The button glyph and `aria-label` swap between play and pause, driven by the audio's own `play`
  and `pause` events — not by a variable you maintain, which will disagree with reality the first
  time playback ends.
- **Spacebar toggles play** when the Timeline pane is showing. It must **not** fire while focus is
  in an `<input>`, `<textarea>` or `<select>` — the app is full of number boxes and the owner will
  be typing in them. There is an existing keydown listener at `app.js` ~L579; look at how it
  guards before adding another.
- At the end of the film, pause and leave the playhead at the end. Do not loop.

## Job 4 — show the picture that is on screen

`.tl-frame` currently holds placeholder text. While playing, it must show **the picture the viewer
would be seeing at that moment** — the image for the picture containing the playhead.

`timelineSeek` already finds that picture (~L2428). Use the same resolution the Storyboard cards
use for a picture's image, so a pinned image, a numbered folder image and a library match all
appear the same way here. If a picture has no image yet, say so in the frame — "Picture 7 has no
image yet" — rather than showing an empty box.

Do not re-render the whole frame on every animation tick. Redraw it only when the picture number
under the playhead **changes**.

## Job 5 — be honest when there is no audio

The owner's film has **0 of 347 lines measured**. This is the normal first-run state, not an edge
case, and it is what he will see when he first opens the screen.

When no segment has a `narration_audio` file, the play button is disabled and `#tl-status` says
what to do: that narration has not been recorded yet, and that **Measure narration** on the
Storyboard will do it. The Timeline already colours the narration track amber for estimated
timings — this message must agree with that, not contradict it.

If **some** segments are measured, play what exists and say how many are missing. Do not silently
play a film with holes in it.

---

## Tests

Add `tests/test_timeline_audio.py`:

1. **Concatenation covers every measured segment.** Six segments in, one output, and the
   `offsets` map is the running sum of the measured seconds.
2. **Duration agrees with the sum, within 100 ms.** The drift test above. This is the important one.
3. **The cache is honoured.** Two calls in a row: the second returns `"rebuilt": False` and does not
   invoke ffmpeg. Assert ffmpeg was not called — patch the runner and count.
4. **A changed narration rebuilds.** Touch one segment's mp3 so its mtime moves; the next call
   returns `"rebuilt": True`.
5. **A half-measured film still builds.** Three of six segments have audio; the build succeeds and
   reports three skipped.
6. **A film with no audio at all** returns a clear failure the UI can show, and does not raise.

**Do not** write a test that asserts a file merely exists — the WolfCut exporter once wrote
zero-byte files so its own path assertions would pass. Assert the **duration** of what was written.

Break the offsets calculation on purpose once (add a second to one offset) and confirm tests 1 and
2 fail. Paste that.

## Traps

1. **`-c copy` on mp3 can shift duration slightly.** That is exactly what test 2 is for. If the
   drift exceeds 100 ms, report the real number and stop — do not "fix" it by loosening the test.
   Re-encoding with `libmp3lame` is the fallback, and it is slower; say so if you need it.
2. **Repo files are CRLF.** Check byte counts before and after.
3. **Inline `style="` in `index.html` is capped at 19 and is at 19.** Layout goes in `style.css`.
4. **Do not touch the render path** — `composer.py`, `orchestrator.py`, `stitcher.py`, or the shot
   cache key. This slice adds a preview; it changes nothing about what a render produces.
5. **`config/settings.json` is gitignored and holds live API keys.** Never print or commit it.
6. Do not change `measure_narration`, `timing_maps`, `picturesFromScript` or `tlLineAt`. Read them.

## Explicitly NOT in this brief

- **Music and sound-effect tracks.** Slice F.
- **Dragging clip boundaries.** Slice E. `Cut here` and `Join to picture` already work and must
  keep working.
- **Waveform drawing.** Later, and only if the owner asks.
- **Moving `Measure narration` to the Script screen.** Slice C.
- **The ffmpeg licence work.** A separate brief. Use `composer._find_ffmpeg` as it stands today.

## What to report

1. The real duration difference between the concatenated file and the sum of measured seconds, on
   a film of at least 50 segments. The actual number in milliseconds.
2. Tests 1 and 2 failing when you break the offsets, then passing. Paste both.
3. **Confirmation that you played audio in the real desktop app**, not only the dev server — the
   `file://` path is the one that cannot be proven any other way. Say which you tested. If you
   could only test the dev server, **say so plainly**; that is a useful report and silence is not.
4. Whether the dev server serves range requests, so seeking works there.
5. `git diff --stat`.
6. The full suite: `pytest tests/ -q`. Baseline 692 passed, 1 xfailed.
7. Anything you could not do, and why.
