# Brief: Slice L — The Timeline at Low Zoom

Hand this whole file to Antigravity.

**Read `ANTIGRAVITY-RULES.md` first — its standing rules apply.**

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget`. **Do not commit. Do not push.**
**Baseline: 1286 passed, 1 xfailed, 0 failures.** Roughly 11 minutes.
Python: `C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe` (not on PATH).

---

## Why this slice exists

Slice K lowered the zoom floor from 1 px/s to 0.2 so Fit could actually fit an
18-minute film. That fixed the view and broke the controls, and this slice is the
other half of the change.

**Magnetic snapping is deliberately not in this brief.** Picture boundaries already
quantise: `timelineHandlePointerMove` converts the cursor to a time, `tlLineAt` maps
that to a narration line, and `tlLineStartTime` maps back. Boundaries can only land on
line starts, so they are snapped to the script by construction. A second snap-to-playhead
layer on top would fight the grid the data already has. If snapping is still wanted later,
it should snap the *playhead* to boundaries, not boundaries to the playhead — a different
slice.

---

## What is actually true today

Read out of the code on 2026-09-04. Verify before trusting.

1. Clip width is `Math.max(2, pic.seconds * tlZoom)` (`app.js:2929`).
2. `.tl-clip` sets `overflow: hidden` (`style.css:2373`).
3. `.tl-clip-handle` is `width: 10px` at `left: 0`, **nested inside the clip**
   (`style.css:2492-2497`). Because the parent hides overflow, **the handle is clipped
   to the clip's own width**. A 3px clip has a 3px grab target.
4. `narrow = w < 78` (`app.js:2932`) already drops the duration and shortens the label.
   There is no second threshold below it.
5. Drag resolution is `seconds = (e.clientX - rect.left) / tlZoom` (`app.js:3330`).
   At 0.2 px/s **one pixel of mouse travel is five seconds**.
6. No snapping exists: `grep -c "snap\|Snap" frontend/app.js` returns 0.
7. The first picture has no handle at all (`idx > 0`, `app.js:2937`), which is correct —
   there is no boundary before picture 1.

At the fit zoom this enables for `Before Adam` (0.689 px/s), a 17.57s picture is **12.1px**:
the handle survives, the label does not. At the 0.2 floor the same picture is **3.5px**.

---

## Job 1 — Measure it live before changing anything

Open the live WebView2 window on `Before Adam`, press `0` to fit, and record to
`reports/verification_gate/slice_l_dom.json`:

- `tlZoom` after fit, and `lanes.scrollWidth` vs `scroll.clientWidth`.
- The rendered `offsetWidth` of the narrowest and widest `.tl-clip`.
- The rendered `offsetWidth` of a `.tl-clip-handle` on a narrow clip. **This is the
  number the slice turns on** — if it is not being clipped, say so and Job 2 changes shape.
- Whether `.tl-clip-head` text visibly overflows or is cut mid-character.

Paste the numbers. Do not paraphrase them.

## Job 2 — A handle you can actually hit

Give the boundary handle a usable target at every zoom. The constraint is that it lives
inside a clip with `overflow: hidden`, so widening it alone will not help.

Preferred approach: let the handle escape its clip. Position it so it straddles the
boundary rather than sitting inside one side of it — for example render handles into the
lane rather than the clip, at `left: (pic.startsAt * tlZoom)` with a fixed width and
`transform: translateX(-50%)`. A boundary belongs to the seam between two clips, not to
the clip on its right.

Whatever you choose:

- The handle's hit area must be **at least 8px wide at any zoom**, and must not be
  clipped by the parent.
- Handles must not overlap each other. When two boundaries are closer together than the
  hit area, the later one wins and the earlier is not rendered — an unreachable handle is
  better than two stacked handles that grab the wrong boundary.
- Keyboard access must survive: `tabindex="0"`, `role="slider"`, the `aria-valuemin` /
  `aria-valuenow` / `aria-valuemax` triple, and `onkeydown="timelineHandleKeyDown(...)"`
  all still work. **The keyboard path is the accessible one and must not regress** —
  arrow keys on a focused handle move the boundary a line at a time regardless of zoom,
  which is the precise control the mouse loses at 0.2 px/s.

## Job 3 — Labels that do not render into a 3px box

`narrow` at 78px is one threshold; a 3px clip needs another. Below roughly 24px, drop
`.tl-clip-head` entirely rather than painting a clipped glyph. The clip still carries its
`title` attribute, so hovering still identifies it.

Confirm the lane does not visually collapse at the 0.2 floor: clips should read as a
dense strip of distinct blocks, not one continuous bar.

## Job 4 — Zoom to selection

Fit surveys the whole film; there is no way back down to one cut. Add
`zoomTimelineToSelection()`:

- Zoom so the selected picture fills the viewport with a small margin, using the same
  `(clientWidth - 24) / seconds` shape `fitTimelineToWindow` uses.
- Route it through `setTimelineZoom` so the slider follows and the playhead stays anchored.
- Clamp through the same `[0.2, 60]` the setter owns. Do not add a second clamp.
- No selection, or no film, must be a no-op — not a divide-by-zero. Slice I shipped two
  crashes of exactly that shape; do not add a third.
- Bind it to `.` and add it to the shortcuts HUD tooltip, beside the existing
  `+/-/0: Zoom`. Keep it **below** the timeline-active gate with the other zoom keys.

---

## Rule 4 — prove every test can fail

Slice J scored ten of ten on independent mutation and Slice K's floor fix scored five of
five. Hold that standard. Break the code on purpose, paste the failure, restore, paste
the pass. At minimum:

1. Handle minimum hit area removed — Job 2's test must fail.
2. Overlap suppression removed so two handles stack — must fail.
3. `tabindex` or `onkeydown` dropped from the handle — must fail. This one matters most:
   it is the regression that would make the timeline unusable without a mouse.
4. The new label threshold removed — Job 3's test must fail.
5. `zoomTimelineToSelection` clamp bypassed — must fail.
6. `.` hoisted above the timeline gate so it fires on the Script pane — must fail.
7. `zoomTimelineToSelection` with no selection — must fail before its guard exists.

**Anchor mutations on CRLF.** Bare `\n` will not match in this repo and reports as
"skipped" rather than "escaped".

---

## Budgets and ratchets

- **Inline `style="` in `index.html` is at 15, cap 19.** Handle and label rules go in
  `style.css`. The per-clip `style="left:...; width:..."` strings are written from
  `app.js` and do not count against this.
- **Shot cache key stays `v10`.** Nothing here changes what a shot renders.
- **CRLF everywhere.** 0 bare LF in every file you touch.
- Do not touch `library/index.npz`. Never run `git add -A`.

---

## Finishing the slice

Slice K's report stopped after the artifact was written, leaving a clean tree and
`ready_for` still `ANTIGRAVITY`, so the token never came back and the relay sat idle
until the owner noticed. Close the loop this time:

1. Set `phase` to `ANTIGRAVITY_WORK_READY` and `ready_for` to `CLAUDE` in
   `RELAY-STATE.json`, and append a history entry.
2. Arm the watcher: `python tools/relay_watch.py --target ANTIGRAVITY --interval 5`
3. Name anything you did not do. A skipped check reported as skipped is a good report;
   silence is not.

Then stop. Do not commit. Claude reviews the working tree and commits.
