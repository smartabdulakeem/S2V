# Brief: Slice J — Timeline Zoom Behaviour: Anchored Zoom, Fit-to-Window & Keyboard Zoom

Hand this whole file to Antigravity.

**Read `ANTIGRAVITY-RULES.md` first — its standing rules apply.**

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget`. **Do not commit. Do not push.**
**Baseline: 1274 passed, 1 skipped (network-gated Google TTS), 1 xfailed, 0 failures.** Roughly 11 minutes.
Python: `C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe` (not on PATH).
Prefix anything printing prompt text with `PYTHONIOENCODING=utf-8`.

---

## Where this sits in Milestone 3

Milestone 3 is **Visual & Interactive Polish** — making Smart Studio feel like a responsive,
professional editing suite.

Slice I gave the keyboard the transport: play, nudge, clip-step, Home/End, J/K/L, and 1/2/3 stage
navigation. Slice J gives the keyboard and the eye the **viewport**. Transport without zoom control
is half an NLE: on an eighteen-minute film at the default 8 px/s the lane is 8,600 px wide inside a
790 px window, so the user is looking at 9% of their film with no way to see the whole thing.

---

## What is actually true today

Every claim below was read out of the code on 2026-09-04. Verify before trusting.

1. `tlZoom` is pixels-per-second, default `8`, declared at `app.js:2324`.
2. A zoom **slider already exists**: `#tl-zoom`, `index.html:282`, `min=1 max=60 value=8`,
   `oninput="setTimelineZoom(this.value)"`. Do not add a second zoom control — improve this one.
3. `setTimelineZoom` (`app.js:3062`) is three lines: clamp to `[1, 60]`, then `renderTimelineScreen()`.
4. **Ruler tick density already adapts to zoom.** `tlTickInterval()` (`app.js:2329`) picks from
   `[1,2,5,10,15,30,60,120,300,600,900]` to keep ~90 px between labels. Leave it alone.
5. **`renderTimelineScreen` never writes `scroll.scrollLeft`.** Grepped: the only writers are
   `timelineSeek` (`app.js:3109`) and the Slice H caption auto-scroll (`app.js:2605`).
6. **There is no fit-to-window.** `grep -c "fitTimeline\|tlFit\|fit-to-window" frontend/app.js` = 0.
7. There is no keyboard zoom. Slice I bound Space, arrows, Home/End, J/K/L and 1/2/3 only.

---

## Job 1 — Zoom must stay anchored on the playhead

**The bug.** `setTimelineZoom` changes the pixels-per-second mapping and re-renders, but leaves
`scroll.scrollLeft` at its old **pixel** value. The pixel no longer means the same second, so the
viewport jumps to unrelated footage. Concretely: playhead at 15:00 of an 18-minute film, zoom 8 →
30 px/s. The playhead moves from x=7,200 to x=27,000 while `scrollLeft` stays at ~7,000. The user
zooms in to inspect a cut and lands eleven minutes away from it.

Fix `setTimelineZoom` so the **playhead holds its screen position** across a zoom change:

1. Before re-rendering, record the playhead's offset within the viewport:
   `offsetPx = (tlPlayhead * oldZoom) - scroll.scrollLeft`.
2. Apply the new clamped zoom and re-render.
3. Restore: `scroll.scrollLeft = Math.max(0, (tlPlayhead * newZoom) - offsetPx)`.

If the playhead is outside the current viewport, centre it instead of preserving a nonsense offset.
Keep the existing `[1, 60]` clamp and the existing `parseFloat(value) || 8` fallback — the slider
passes strings.

## Job 2 — Fit-to-window

Add `fitTimelineToWindow()`:

- Read `#tl-scroll` `clientWidth`; compute `zoom = (clientWidth - 24) / total` where `total` is the
  film's duration in seconds.
- Clamp into `[1, 60]` exactly as `setTimelineZoom` does, and route through `setTimelineZoom` so the
  slider's own `value` is updated too — a fit that leaves the slider showing a stale number is a bug.
- No film loaded (`tlPictures().length === 0`) must be a no-op, not a divide-by-zero. Slice I landed
  two crashes of exactly this shape; do not add a third.
- Wire it to a **Fit** button in the transport bar beside the existing zoom slider.

## Job 3 — Keyboard zoom

Extend the Slice I `keydown` listener. These are timeline-only, so they belong **after** the
`isTimelineActive` gate, alongside the transport keys — not in the global 1/2/3 block:

- `+` / `=`: zoom in one step.
- `-` / `_`: zoom out one step.
- `0`: fit to window.

A step is multiplicative, not additive: `zoom * 1.5` in, `zoom / 1.5` out. Additive steps crawl at
the top of the range and leap at the bottom. Respect the same input-focus guard Slice I established
— these must not fire while the user is typing in a field.

**Note the collision:** `0` is a digit, and Slice I put `1`/`2`/`3` in the *global* block above the
timeline gate. Keep `0` below the gate so it only means "fit" on the Timeline, and confirm with a
test that `0` does nothing on the Script pane.

## Job 4 — Measure the re-render cost before deciding anything about it

`oninput` on a range slider fires on **every pixel of drag**, and each event runs a full
`renderTimelineScreen()` — rebuilding every clip, caption and tick in the DOM.

Measure it on the owner's real film (`Before Adam`, 347 lines):

- Time a single `renderTimelineScreen()` call at zoom 8 and at zoom 60.
- Count how many `oninput` events one slider drag across the full track produces.

**Report the numbers. Do not optimise yet.** If a single render is under ~16 ms this is a
non-problem and we will not spend a slice on it. If it is over ~50 ms, say so and we will schedule
debouncing as its own slice. This job is a measurement, not a change.

## Job 5 — Close the Slice H caption auto-scroll gap

`RELAY-STATE.json` has carried this in `known_gaps` since Slice H: the caption auto-scroll
(`app.js:2603-2605`) has no automated test. Slice J touches scroll behaviour, so close it now.

Write a test that the active caption is scrolled into view when it falls outside the viewport, and
that an already-visible caption does **not** move the scroll position. The Node DOM harness at the
top of `tests/test_timeline_keyboard.py` is the pattern to copy — it loads the real `app.js`.

---

## Rule 4 — prove every test can fail

`ANTIGRAVITY-RULES.md`: *a test that cannot fail is worse than no test.* This is not a formality
here. Slice G shipped two tests that could not fail, Slice H shipped one, and Slice I's review
caught a real crash that eight passing tests had missed.

For **each** test you add, break the code on purpose, paste the failure, restore, and paste the pass.
Mutations that must be caught, at minimum:

1. Zoom anchoring removed (drop the `scrollLeft` restore) — Job 1's test must fail.
2. Anchor restored with the **old** zoom instead of the new one — must fail.
3. `fitTimelineToWindow` off by the 24 px gutter — must fail.
4. Fit not clamped, so a 3-second film asks for zoom 260 — must fail.
5. Fit on an empty timeline divides by zero — must fail.
6. `+`/`-` made additive instead of multiplicative — must fail.
7. `0` moved above the timeline gate so it fires on the Script pane — must fail.
8. Caption auto-scroll disabled — Job 5's test must fail.

A mutation that does not break a test means the test is decoration. Say so and replace it.

**Anchor your mutations on CRLF.** Multi-line string anchors written with bare `\n` will silently
fail to match in this repo and report as "skipped" rather than "escaped" — that happened during
Slice I's review and cost a rerun.

---

## Budgets and ratchets

- **Inline `style="` in `index.html` is at 15, cap 19.** The Fit button goes in `style.css`.
  Note: the ruler/clip `style="left:..."` strings are written from `app.js`, not `index.html`, and
  do not count against this. Do not "helpfully" refactor them.
- **Shot cache key stays `v10`.** Nothing here changes what a shot renders.
- **CRLF everywhere.** 0 bare LF in every file you touch.
- Do not touch `library/index.npz`. Never run `git add -A`.

---

## Report

1. The Job 4 numbers as raw pasted output, not prose.
2. Every mutation from the Rule 4 list: the break, the failure, the restore.
3. Full suite output, pasted.
4. Anything you did not do, named as not done.

Then stop. Do not commit. Claude reviews the working tree and commits.
