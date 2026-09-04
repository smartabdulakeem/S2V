# Brief: Slice K (revised) — Zoom Floor. Job 1 is done; Job 2 is withdrawn.

Hand this whole file to Antigravity. **This replaces the earlier Slice K brief.**

**Read `ANTIGRAVITY-RULES.md` first — its standing rules apply.**

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget`. **Do not commit. Do not push.**
**Baseline: 1283 passed, 1 xfailed, 0 failures.** Roughly 11 minutes.
Python: `C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe` (not on PATH).

---

## Job 1 — DONE. Do not repeat it.

`reports/verification_gate/slice_k_dom.json` is written and committed at `73fb44e`.
It is the first live WebView2 evidence since Slice H and it clears the debt Slices I
and J were carrying. **Every Slice I check passed in the real window**, and Slice J's
mid-film anchoring drifts 0.22px zooming 8 to 30. Good work — this was the most
valuable thing in the slice.

## Job 2 — WITHDRAWN. The measurement disproved the premise.

The brief predicted the browser would clamp `scrollLeft` at the film's tail and break
anchoring. **Your own measurement shows it did not, and the note in the artifact
contradicts the numbers directly above it.**

```
scrollLeft_after       : 68167.3359375
max_scrollLeft_possible: 68758
drift_px               : 0.2737
```

`68167 < 68758`, so no clamping occurred. And 0.27px is the same order as the
mid-film case's 0.22px — that is sub-pixel rounding, not truncation. The note saying
*"Browser clamped scrollLeft... causing playhead screen position to drift"* is not
supported by its own data. Please fix that note; a wrong conclusion sitting next to
correct numbers is worse than no note, because the next reader trusts it.

The premise is also wrong in principle, which is my error in writing it. If the
target ever does exceed `max`, the browser clamps to `max` and the playhead lands at
`playhead_px - max = playhead_px - laneWidth + clientWidth`, which is `<= clientWidth`.
**The playhead therefore always stays on screen.** At the very end of a film it sits
at the right edge instead of its requested offset, which is unavoidable — you cannot
scroll past the end. There is nothing to fix. Do not change `setTimelineZoom`'s
anchoring, and do not add a clamping setter to the scroll mock.

## Job 3 — The one real bug. This is the whole slice now.

Confirmed live on the owner's film, in the artifact you wrote:

```
resulting_tlZoom  : 1
lanes_scrollWidth : 1160
scroll_clientWidth: 823
actually_fits     : false
```

`fitTimelineToWindow` computes `(clientWidth - 24) / total`. For `Before Adam` that is
`799 / 1159.677 = 0.689` px/s, below the `[1, 60]` floor, so it clamps to 1 and the
lane stays 1160px inside an 823px window. The button says Fit and does not fit.

**This is a fault in Slice J's brief, not in Slice J's code.** The clamp was specified
there and implemented exactly as written. The floor is simply wrong for the length of
film this app is for.

- Lower the floor from `1` to `0.2` px/s in `setTimelineZoom` **and** in `#tl-zoom`'s
  `min` attribute in `index.html` (currently `min="1"`). Both must move together or the
  slider cannot reach what the keyboard can.
- Give the slider `step="0.1"`. It has none today, so it snaps to whole numbers while
  `tlZoom` stays fractional after a fit or a `* 1.5` keyboard step.
- Confirm `tlTickInterval()` still behaves: at 0.2 px/s, `wanted = 90 / 0.2 = 450`,
  which selects the 600s entry from the existing table. No change expected — confirm it.
- Clip widths use `Math.max(2, pic.seconds * tlZoom)`, so short clips floor at 2px.
  Acceptable for a whole-film overview. Confirm the lane does not visually collapse.

Then verify live that `0` on the owner's real film gives
`lanes_scrollWidth <= scroll_clientWidth`, and append the result to
`reports/verification_gate/slice_k_dom.json`.

## Job 4 — Slider honesty

With `step="0.1"`, confirm the slider and `tlZoom` agree to within one step after a fit
and after three keyboard zoom-ins. Record both numbers.

---

## Rule 4 — prove every test can fail

Slice J scored ten of ten on independent mutation. Hold that standard.

1. Zoom floor left at 1 in `setTimelineZoom` — the fit test must fail.
2. Slider `min` lowered but `setTimelineZoom`'s floor left at 1 — must fail.
3. `step` left off the slider — Job 4's test must fail.
4. `(clientWidth - 24)` gutter removed — must fail.

**Anchor mutations on CRLF.** Bare `\n` will not match in this repo.

---

## Finishing the slice — this is the part that did not happen last time

You wrote the artifact and stopped, leaving the working tree clean and
`RELAY-STATE.json` still saying `ready_for: ANTIGRAVITY`. The token never came back,
so the relay sat idle until the owner noticed.

When the report is written:

1. Set `phase` to `ANTIGRAVITY_WORK_READY` and `ready_for` to `CLAUDE` in
   `RELAY-STATE.json`, and append a history entry.
2. Arm the watcher so you are woken when Claude hands back:
   `python tools/relay_watch.py --target ANTIGRAVITY --interval 5`
3. Name anything you did not do. A skipped check reported as skipped is a good
   report; silence is not.

Then stop. Do not commit. Claude reviews the working tree and commits.
