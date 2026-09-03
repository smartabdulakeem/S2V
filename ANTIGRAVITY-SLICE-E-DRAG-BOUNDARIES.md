# Brief: Slice E — move a picture boundary while the film is playing

Hand this whole file to Antigravity.

**Read `ANTIGRAVITY-RULES.md` first — its standing rules apply.**

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget`. **Do not commit. Do not push.**
**Baseline: 713 passed, 1 xfailed, 0 failures.** Roughly 8.5 minutes.
Python: `C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe` (not on PATH).

---

## What the owner hit

He pressed play on the Timeline, heard his film, and could not change anything.

The controls were on screen the whole time. `Cut here` and `Join to picture NN` live in the
Inspector, and the Inspector is empty until you click a picture in the Pictures lane. Even then,
`Cut here` is disabled unless the playhead already sits inside that picture past its first line
(`frontend/app.js` ~L2692, `canCutHere`). He almost certainly selected a picture with the playhead
at zero and saw a dead button with no explanation.

**So this slice is not "add cutting". Cutting works and is proven on his 347-line film.** It is
about making the boundary something you grab while the audio runs, instead of a three-step hunt
through a panel.

The gesture: **drag the left edge of a picture in the Pictures lane. It snaps to narration lines.
Release commits.** The audio never stops.

---

## The one thing that will go wrong if you skip it

**Moving a boundary is not `merge_picture` followed by `split_picture`.** That is the obvious
implementation and it is wrong, destructively so.

Read the two functions in `pipeline/picture_plan.py` (L607 and L644) and look at what they discard:

- `split_picture` pops `visual_description` and `prompt` off the new picture — correct for a
  *split*, because the new picture carries narration nobody has described yet.
- `merge_picture` pops `visual_description` and `prompt` off **everything it folds in** — correct
  for a *merge*, because that stretch of narration no longer exists.

Compose them to nudge a boundary two lines and you have thrown away the descriptions on **both**
sides of a picture that barely changed. That is the exact failure the comment block at
`picture_plan.py:580` was written about — the owner lost 26 of 30 descriptions to a re-plan, and
this whole subsystem exists so it cannot happen again.

**A moved boundary keeps its picture's identity.** The picture still exists, still has the same
number, still means the same thing — only its first line changed. Its description, its prompt and
the image already bound to it all travel with it.

---

## Job 1 — `move_picture_boundary` in `pipeline/picture_plan.py`

Put it beside `split_picture` and `merge_picture`, under the same comment block.

```python
def move_picture_boundary(script_data: dict, from_line: int, to_line: int) -> dict:
    """
    Move the boundary where a picture starts, keeping both pictures' identity.

    The picture that starts at `from_line` starts at `to_line` instead. It keeps
    its description, its prompt and whatever image is bound to it — only the
    narration it covers changes. The picture before it keeps everything too; it
    simply holds for longer or shorter.
    """
```

**Rules, all of which need a test:**

| Case | Result |
|---|---|
| No picture starts at `from_line` | `{"success": False, "error": ...}` |
| `from_line` is the first boundary | refuse — picture 1 starts at line 1 and cannot move |
| `to_line` at or before the previous boundary | **clamp** to previous boundary + 1 |
| `to_line` at or after the next boundary | **clamp** to next boundary − 1 |
| `to_line` outside the script | clamp into range |
| `to_line == from_line` | succeed, change nothing |

Clamp rather than refuse: a drag that overshoots should stop at the neighbour, not throw an error
at someone who is holding the mouse down. **A boundary never reorders or swallows its neighbours.**

Mechanically this is still just `share_with`. The shot at `to_line` becomes the owner (its
`share_with` goes to `None`); the shot at `from_line` and every line between the two boundaries
point at whichever picture now owns them. Carry `visual_description`, `prompt`, and the binding
keys (`resolved`, `resolved_score`, `run_index`, `run_position`) from the old owner shot to the
new one — **do not drop them**, which is the whole difference from split and merge.

Return the same shape as its two neighbours: `{"success": True, "script_data": ..., "pictures":
<count>, "moved_from": <int>, "moved_to": <int>}`. `moved_to` is the **clamped** line, because the
front end needs to know where the boundary actually landed, not where the mouse was.

## Job 2 — the endpoint

`move_picture_boundary_to(self, script_data, from_line, to_line)` on the `Api` class in `app.py`,
directly after `merge_picture_at` (L995). Mirror those two exactly, including the
`assign_effects(script_data, style_of(script_data))` call on success and the `try/except`.

## Job 3 — the drag

In the Pictures lane (`#tl-lane-pictures`), every picture except the first gets a **grab handle**
on its left edge.

- **Pointer events, not mouse events.** `pointerdown` on the handle, `setPointerCapture`, then
  `pointermove` / `pointerup`. It must work with a trackpad and survive the pointer leaving the
  lane.
- **`stopPropagation` on `pointerdown`.** The lanes carry `onclick="timelineScrubFrom(event)"`
  (`index.html:316`). Without this, grabbing a handle also jumps the playhead.
- **Snap to lines.** A boundary can only sit where a narration line starts. Convert x → seconds
  with the same `tlZoom` mapping `timelineScrubFrom` uses, then seconds → line with the existing
  `tlLineAt` (`app.js:2666`). Do not invent a second mapping.
- **The preview is CSS only.** While dragging, move the block edges and show the candidate line
  and the resulting hold in seconds. **Make no backend call and no disk write until `pointerup`.**
  `applyBoundaryChange` (`app.js:1772`) calls `refreshStoryboardCoverage()` and
  `save_edited_script` on every change — running that per `pointermove` would be unusable.
- **Clamp in the UI too**, at the neighbouring boundaries, so the preview never shows a position
  the backend will refuse. The backend clamp stays as the guard; they must agree.
- **Commit on `pointerup`**, then re-render the lanes and the Inspector.
- **Escape mid-drag cancels** and restores the original position.

### The audio must not stop

This is the slice. Do not pause, reload, or reset `#tl-audio` at any point in the drag or the
commit. `pipeline/timeline_audio.py` builds one concatenated file from the narration, and **moving
a boundary does not change the narration at all** — same lines, same order, same seconds. The
track stays valid. Nothing needs rebuilding, and `prepare_timeline_audio` must not be called.

Check what `setBoardBusy` does before you use it for the commit; if it disables or re-renders
anything that would interrupt playback, do not use it here.

## Job 4 — keyboard

The handle is a real focusable control, not a bare `<div>`.

- `tabindex`, a visible focus ring, and `role`/`aria-label` naming which boundary it is
  ("Start of picture 07, line 214").
- **Left / Right arrow moves the boundary one line** and commits. Shift+Arrow moves five.
- Announce the result — the Inspector already shows in / out / holds, so re-rendering it is enough.

This is not decoration. It is the only version of this feature that can be driven from a test.

## Job 5 — the small fix that would have saved him the confusion

Two dead ends, both in `drawTimelineInspector` (`app.js:2675`):

- The empty state says `Click a picture on the timeline.` It should say what that gets you —
  that selecting a picture is how you cut, join or drag its start.
- The disabled button says `Cut at the playhead` with a `title` nobody hovers. When it is disabled,
  **say why on the face of it**: the playhead has to be inside this picture, past the line it
  starts on.

Keep it to those two strings and whatever markup they need. **`index.html` is capped at 19 inline
`style="` attributes and is at 19** — layout goes in `frontend/style.css`.

---

## Tests

Backend tests go in `tests/test_split_and_merge_pictures.py`, which already covers this subsystem.

1. **A moved boundary keeps the description.** Build a script with two described pictures, move the
   boundary two lines later, assert **both** `visual_description` values are still there and
   unchanged. Then assert the same script put through `merge_picture` + `split_picture` **loses**
   them — that second assertion is the reason this function exists, and it must be in the file.
2. **The bound image travels.** Set `resolved` on the picture that starts at `from_line`, move the
   boundary, assert `resolved` is on the shot at `to_line` and not left behind.
3. **Clamping.** Moving before the previous boundary lands on previous + 1; moving past the next
   lands on next − 1. Assert `moved_to` reports the clamped line, not the requested one.
4. **The count never changes.** `len(picture_boundaries(...))` is identical before and after every
   successful move. A move is not allowed to create or destroy a picture.
5. **Refusals.** No picture at `from_line`; `from_line` is the first boundary. Both return
   `success: False` with a message naming the line.
6. **A no-op move succeeds** and leaves the script byte-identical.

Every one of these must be checked by breaking the code on purpose — rule 4 in
`ANTIGRAVITY-RULES.md`. Test 1 in particular passes trivially if you assert the wrong shot.

`tests/test_frontend_controls.py` asserts every button calls a function that exists. Keep it
passing, and extend it if you add controls it does not reach.

---

## Acceptance

Paste real output, not a description of it.

1. **Full suite green.** Expect **713 + your new tests, 1 xfailed, 0 failures.** Do not run it
   while anything else heavy is running — `test_parallel.py` does a real render and fails when
   starved of CPU.

2. **On the owner's real film**, `projects/Before_Adam_The_Story_of_Iblis` — 347 lines, all
   measured, `timeline_narration.mp3` already built at 1159.7 seconds:
   - Press play. **While it is still playing**, drag a boundary. Say plainly whether the audio kept
     going. If it stopped, that is the bug and the slice is not done.
   - Confirm the picture on screen at the playhead updates to match.
   - Drag one boundary hard left past its neighbour and confirm it stops at the neighbour instead
     of reordering.
   - Report the description count before and after: `visual_description` present across all shots.
     **It must not drop.**

3. **Drive it from the keyboard alone** — tab to a handle, arrow it two lines, confirm the
   Inspector's `holds` value changed by the right number of seconds.

4. **Screenshot the Inspector** in both states: nothing selected, and a picture selected with the
   playhead outside it so the disabled button shows its new reason.

If you cannot do one of these, **say which and why**. A skipped check named as skipped is a good
report; silence is not.

## Out of scope

Do not touch: `pipeline/timeline_audio.py` or anything that rebuilds the narration track,
`plan_pictures` or any re-planning path, the Storyboard's own split/merge panel, voice selection,
`pipeline/sound.py` and music/SFX (Slice F), the camera slider (Slice B), and the Phosphor icons.

**Do not add an undo stack.** It is the right idea and it is a slice of its own — every boundary
change in the app would have to go through it, not just this one.

---

**Stop when the report is written. Do not commit. Do not push.**
