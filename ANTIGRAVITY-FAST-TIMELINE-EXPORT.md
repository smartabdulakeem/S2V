# Brief: export the WolfCut timeline in seconds, without a render

Hand this whole file to Antigravity.

**Read `ANTIGRAVITY-RULES.md` first — its standing rules apply.**

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget`. **Do not commit. Do not push.**
**Baseline:** 698 passed, 1 xfailed, 0 failures.

---

## What this is for

The owner wants to open his film in WolfCut to check the timeline. Today that costs a **full video
encode** of an 18-minute film, because the only thing that ever writes a `.wolfcut` file sits
inside the renderer. He is waiting minutes to inspect a JSON document.

**This was designed as Task 11 of the picture-boundaries plan and never built.** Do not redesign
it. The plan's reasoning still holds and is worth repeating because it is the whole point:

> `write_wolfcut_project(script_data, audio_paths_map, durations_map, project_dir)` **measures
> nothing.** It takes an audio path and a duration per segment and trusts them. It was only ever
> called from inside the encoder, so a timeline cost a full video pass.

`timing_maps()` in `pipeline/narration_timing.py` already returns exactly those two maps, keyed by
segment id, with no render. **This task connects two functions that already exist.** It is small.
If you find yourself writing a duration rule, an image resolver, or a second exporter, stop — you
have gone off the path.

## Facts, verified today. Do not re-derive, do not contradict.

1. `write_wolfcut_project` is called from **one** place: `pipeline/orchestrator.py:539`, inside the
   render. Leave that call exactly as it is.
2. `timing_maps(script_data)` returns `(audio_paths, durations)` — the exporter's two arguments.
3. **Captions degrade correctly on their own.** The exporter looks for an SRT with
   `os.path.exists` (`wolfcut_export.py` ~L274-292) and simply writes no caption clips when there
   is none. Before a render there is no SRT, so **the captions track will be empty and that is
   correct.** Do not generate captions to fill it.
4. Picture images resolve through `_shot_image` from `resolved`, `pin`, or a numbered file in the
   project folder — all of which exist after planning, before any render.
5. `app.py` already has `open_in_wolfcut()` (~L1437) and `_find_wolfcut_binary()`. **Reuse them.**
   Note `open_in_wolfcut` currently says *"Render a video first to export the timeline"* — that
   message stops being true and must change.

---

## Job 1 — the endpoint

Add to `app.py`, beside the other timeline endpoints:

```python
def export_wolfcut_timeline(self, script_data: dict, project_dir: str = "") -> dict:
    """
    Write a WolfCut timeline from the narration timing, with no video render.

    The exporter has always been able to do this - it takes an audio path and a
    duration per segment and measures neither. It was only ever called from
    inside the renderer, so a timeline cost a full encode.
    """
```

- Resolve `project_dir` the same way `prepare_timeline_audio` does, so both write beside the film.
- Call `timing_maps`, then `write_wolfcut_project`.
- If `audio_paths` is empty, return a failure saying narration has not been recorded yet and that
  **Measure narration** on the Storyboard will do it. Same prerequisite as playback, same wording.
- Return `{"success": bool, "path": str, "pictures": int, "segments": int, "captions": int}` so the
  UI can say what it wrote. `captions` will be 0 before a render; that is expected, not an error.

## Job 2 — the button

On the **Timeline** screen, beside `Render film`:

```html
<button type="button" class="ghost" id="btn-export-timeline" onclick="exportTimelineToWolfCut()">Export to WolfCut</button>
```

`exportTimelineToWolfCut()` calls the endpoint, then hands the returned path to the existing
`openInWolfCut()` flow — which already handles WolfCut not being installed by offering to show the
file. **Do not write a second "not installed" path.**

While it runs, show progress in `#tl-status`. On success say what was written, in the owner's
terms: how many pictures, and that captions come with the render.

Leave the Render screen's `Open in WolfCut` button alone. It stays for post-render use.

Fix the stale message in `open_in_wolfcut` (~L1461): a timeline no longer requires a render.

---

## Tests

Add to `tests/test_wolfcut_export.py`. The plan already specified the first one — use it as written:

```python
def test_a_timeline_can_be_built_from_timing_alone(tmp_path):
    """
    The editor bridge without a render. The narration is generated and probed,
    the picture boundaries come from the plan, and the timeline is written -
    no video encode anywhere in that sentence.
    """
```

Six segments at 5.0s each, `apply_spans` giving picture 1 lines 1-4 and picture 2 lines 5-6. Assert
**two** picture clips, the first with `duration == 20.0`, the second starting at `20.0`.

Then:

1. **No encoder runs.** Patch the ffmpeg runner and assert it was called **zero** times. This is
   the test that proves the feature — everything else is detail.
2. **A film with no narration audio** returns the clear failure, and does not raise.
3. **Captions are empty without an SRT**, and the document is still valid — every `mediaId` on a
   clip exists in `media[]`, every `trackId` exists in `tracks[]`.
4. **Picture clips collapse `share_with` runs.** A 60-segment script reduced to 12 pictures gives
   **12** picture clips, not 60. If `tests/test_wolfcut_export.py` already covers this, do not
   duplicate it — say so in the report.

Break the collapse on purpose once and confirm the clip-count test fails. Paste that.

## Traps

1. **Do not touch `pipeline/wolfcut_export.py`.** It is correct. This task calls it.
2. **Do not touch `pipeline/orchestrator.py`.** The render keeps exporting as it does now.
3. `doc["tracks"][0]` may not be the picture track — read `write_wolfcut_project`'s docstring, which
   names T1 Pictures, T2 Narration, T3 Captions, and index by that rather than changing the export.
4. Repo files are **CRLF**. Check byte counts before and after.
5. Inline `style="` in `index.html` is capped at **19** and is at 19. Layout goes in `style.css`.
6. `config/settings.json` is gitignored and holds live API keys. Never print or commit it.

## Explicitly NOT in this brief

- **A draft or fast-preview render mode.** Once this works, a timeline costs seconds and there is
  nothing left to speed up for this purpose. A low-quality render for checking motion and grade is
  a real but separate feature, and it is not this one.
- Reading a `.wolfcut` file back into Smart Studio.
- Bundling, downloading or installing WolfCut.
- The Phosphor icon work. Separate slice.

## What to report

1. The first 40 lines of a real exported `.wolfcut`, pasted.
2. **Wall-clock seconds** from clicking the button to the file existing, on the owner's real film.
   That number is the point of this task.
3. The zero-encoder-calls test failing when you break it, then passing.
4. Whether picture *n*, prompt *n* in `image_prompts.txt`, and `n.jpg` still name the same shot.
5. `git diff --stat`.
6. Full suite: `pytest tests/ -q`. Baseline 698 passed, 1 xfailed.
7. Anything you could not do, and why.
