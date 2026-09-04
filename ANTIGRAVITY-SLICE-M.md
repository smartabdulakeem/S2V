# Brief: Slice M — Undo for Timeline Edits. Closes Milestone 3.

Hand this whole file to Antigravity.

**Read `ANTIGRAVITY-RULES.md` first — its standing rules apply.**

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget`. **Do not commit. Do not push.**
**Baseline: 1296 passed, 1 xfailed, 0 failures.** Roughly 12 minutes.
Python: `C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe` (not on PATH).

**This is the last slice of Milestone 3.** See the milestone gate at the bottom — it
changes what you do when the report is written.

---

## Why this slice

Milestone 3 gave the Timeline a keyboard, an anchored zoom, a floor low enough to see a
whole film, and handles you can grab at any zoom. Every one of those makes edits easier
to perform. **None of them makes an edit reversible.**

`grep -cin "undo\|redo" frontend/app.js` returns **0**. Drag a boundary to the wrong
line on a 347-line film and the only way back is to drag it again and hope you remember
where it was. That is the last thing standing between this Timeline and a usable editor,
so it closes the milestone.

---

## What is actually true today

Read out of the code on 2026-09-04. Verify before trusting.

There are **eight** timeline mutations, on **two** different paths.

Seven route through `persistCurrentScript()` (`app.js:3617`), a four-line function that
guards on web mode and calls `save_edited_script`:

| function | line of the persist call |
|---|---|
| `onTimelineMusicVolumeChange` | 3635 |
| `onTimelineMusicFadeChange` | 3647 |
| `timelineAddMusic` | 3675 |
| `removeTimelineMusic` | 3699 |
| `deleteSelectedSfx` | 3760 |
| `_insertSfxAtPlayhead` | 3872 |
| `timelineSfxPointerDown` | 3951 |

The eighth, `moveTimelinePictureBoundary`, **does not call `persistCurrentScript` at all**.
It calls `window.pywebview.api.move_picture_boundary_to`, replaces `currentScriptData`
wholesale with `res.script_data`, then calls `save_edited_script` directly.

Two consequences, and the slice fails if you miss either:

1. **Do not snapshot inside `persistCurrentScript`.** It is called *after* the mutation,
   so a snapshot taken there records the state you are trying to undo *to* nothing — the
   stack ends up one edit behind, and the first undo appears to do nothing. Snapshot
   **before** each mutation, at the eight call sites.
2. **A hook in `persistCurrentScript` would miss boundary moves entirely**, which are the
   most visible edit on the Timeline. That is the one users will reach for undo on first.

Also true:

3. `currentScriptData` is plain JSON, so a snapshot is `structuredClone` or
   `JSON.parse(JSON.stringify(...))`. No command objects, no inverse operations.
4. `moveTimelinePictureBoundary` also mutates `coverageReport.shot_reports` alongside the
   script. Restoring the script without it leaves the two disagreeing about which shot
   has which image. See Job 4.
5. The global `keydown` listener checks no modifiers at all — `grep -n
   "ctrlKey\|metaKey\|altKey" frontend/app.js` returns nothing — so `Ctrl+1` currently
   switches panes. This slice opens that listener, so it is the slice that fixes it.

---

## Job 1 — Measure before choosing a stack depth

Snapshots are whole scripts, so depth costs memory. Measure on `Before Adam` (347 lines)
and record to `reports/verification_gate/slice_m_dom.json`:

- `JSON.stringify(currentScriptData).length` in bytes.
- The time in ms to take one `structuredClone(currentScriptData)`.

**Report the numbers and pick the depth from them.** If a snapshot is under ~1MB, a depth
of 20 is cheap and 20 is the answer. If it is far larger, say so and propose a smaller
depth rather than silently shipping one. Do not guess before measuring.

## Job 2 — The undo stack

Add `pushTimelineUndo()` and `timelineUndo()`.

- `pushTimelineUndo()` deep-clones `currentScriptData` and pushes it onto a bounded stack.
  When the stack is full, drop the **oldest** entry, not the newest.
- Call it **before the mutation** at all eight sites listed above.
- `timelineUndo()` pops, assigns the snapshot to `currentScriptData`, persists it with
  `save_edited_script`, re-renders, and redraws the inspector. **An undo that changes the
  screen but not the file is a bug** — the next reload would bring the edit back.
- An empty stack is a no-op, not a crash. Slices I and J each shipped a crash of exactly
  the "read a field off nothing" shape; do not add a third.
- No project loaded is a no-op.

**Redo is out of scope.** Undo is the safety net; redo is a convenience, and adding it
means deciding what happens to the redo stack on a fresh edit — a decision worth its own
slice rather than a rushed clause in this one. Say in the report that redo was
deliberately not built.

## Job 3 — Bind it, and fix the modifier gap while you are in there

- `Ctrl+Z` triggers `timelineUndo()`, under the existing timeline-active gate and the
  existing input-focus guard. A user typing `Ctrl+Z` in a textarea must get the browser's
  own text undo, not a timeline undo.
- **Fix the standing modifier gap:** the bare keys must not fire when `ctrlKey`, `altKey`
  or `metaKey` is held. `Ctrl+1` must not switch panes; `Ctrl+0` must not fit. Guard the
  bare-key branches, not the whole listener — `Ctrl+Z` itself obviously needs `ctrlKey`.
- Add `Ctrl+Z: Undo` to the shortcuts HUD tooltip in `index.html`.
- Add a visible affordance: an Undo button in the transport row, disabled when the stack
  is empty. It goes in `style.css`; reuse the existing `ghost` class if it fits.

## Job 4 — Do not let the script and the coverage report drift apart

`moveTimelinePictureBoundary` updates `coverageReport.shot_reports` when it moves a
boundary. If undo restores the script alone, the coverage report still describes the
moved layout, so the Storyboard and the Timeline disagree about which shot holds which
image.

Snapshot `coverageReport` alongside the script and restore both together. If you conclude
that is unnecessary, **prove it in the report with the code path that makes it safe** —
do not simply leave it out.

---

## Rule 4 — prove every test can fail

Slice J scored 10 of 10 on independent mutation, Slice K 5 of 5, Slice L 9 of 10 with the
one escape being genuinely redundant code. Hold that standard.

Break the code on purpose, paste the failure, restore, paste the pass. At minimum:

1. `pushTimelineUndo` moved to *after* the mutation at any site — the stack is one edit
   behind and undo appears to do nothing. Must fail.
2. Boundary moves not snapshotted — undo silently skips the most visible edit. Must fail.
3. `timelineUndo` re-renders but never persists — must fail.
4. Stack drops the newest instead of the oldest when full — must fail.
5. Undo on an empty stack — must fail before the guard exists.
6. `Ctrl+Z` fires while a textarea is focused — must fail.
7. `Ctrl+1` still switches panes — must fail.
8. `coverageReport` restored from the wrong snapshot, or not at all — must fail.

**Anchor mutations on CRLF.** Bare `\n` will not match in this repo and reports as
"skipped" rather than "escaped".

---

## Budgets and ratchets

- **Inline `style="` in `index.html` is at 15, cap 19.** The Undo button goes in
  `style.css`.
- **Shot cache key stays `v10`.** Nothing here changes what a shot renders.
- **CRLF everywhere.** 0 bare LF in every file you touch.
- Do not touch `library/index.npz`. Never run `git add -A`.

---

## Milestone gate — this is different from every previous slice

Slice M closes **Milestone 3: Visual & Interactive Polish**. When the report is written:

1. Set `phase` to `MILESTONE_COMPLETE` and `ready_for` to `OWNER` in `RELAY-STATE.json`,
   **not** `ANTIGRAVITY_WORK_READY` / `CLAUDE`. Append a history entry.
2. Notify the owner's phone:
   `python tools/relay_notify.py --title "Milestone 3 complete" --message "Timeline polish done. Review and reply go to start Milestone 4."`
3. **Do not begin Milestone 4.** This gate exists to stop compounding direction drift, and
   it is the one place the relay is supposed to stop.

Claude will still review and commit Slice M first. The gate is for what happens after.

Name anything you did not do. A skipped check reported as skipped is a good report;
silence is not.

Then stop. Do not commit.
