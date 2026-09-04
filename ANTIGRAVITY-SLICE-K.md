# Brief: Slice K — The Live Window: Verification Gate, Zoom Floor & Tail Anchoring

Hand this whole file to Antigravity.

**Read `ANTIGRAVITY-RULES.md` first — its standing rules apply.**

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget`. **Do not commit. Do not push.**
**Baseline: 1283 passed, 1 xfailed, 0 failures.** Roughly 11 minutes.
Python: `C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe` (not on PATH).
Prefix anything printing prompt text with `PYTHONIOENCODING=utf-8`.

---

## Why this slice is not a feature slice

Slice J's code was clean. Ten of ten independent mutations were caught, the no-film
crash mode that broke Slice I was correctly guarded, and review found nothing to fix.
That is the best result of the run so far, and it is worth saying plainly.

But **Slices I and J have never been touched by a real browser.** Both were proved in
the Node DOM harness. `RELAY-STATE.json` has carried
`frontend_verification.status = "PENDING_FOR_SLICE_I"` since Slice I, Slice J's brief
required a live check and none was recorded, and `reports/verification_gate/` still ends
at `slice_h_dom.json`. Two slices of keyboard and viewport work now rest on a mock.

That matters here more than usual, because the harness cannot model the one thing Slice J
depends on. In `tests/test_timeline_zoom.py` the scroll mock is:

```
clientWidth: 800,
scrollLeft: 0,
```

`scrollLeft` is a plain number. **A real browser clamps it to `[0, scrollWidth - clientWidth]`.**
So `scroll.scrollLeft = Math.max(0, (tlPlayhead * newZoom) - offsetPx)` can be silently
truncated near the end of a film, and every test would still pass. That is not a
hypothetical — it is the exact shape of bug the mock is blind to.

`ROADMAP.md` B1 has said this since August: *"Tests pass; tests are not eyes."* This slice
is the eyes.

---

## Job 1 — The live verification gate. Do this first, before any code change.

Open the live WebView2 window against `baseline_commit` and load the owner's real film,
`Before Adam` (347 lines, ~18 minutes). Record measured DOM values to
`reports/verification_gate/slice_k_dom.json`. Do not paraphrase — write the numbers.

Confirm and record, for **Slice I**:

1. `Space` toggles playback. Record `audio.paused` before and after.
2. `ArrowRight` moves `tlPlayhead` by exactly 1.0s; `Shift+ArrowRight` by 5.0s.
3. `ArrowUp` / `ArrowDown` step pictures. Record the two `startsAt` values.
4. `Home` and `End` land on 0 and the film's total. Record both.
5. `J` / `K` / `L` behave as -2s / pause / play.
6. Typing into the Script pane's textarea does **not** move the playhead — press
   `1`, `j`, `k`, `l`, `0` inside a focused field and record that `tlPlayhead` is unchanged.
7. `3` leaves `document.activeElement` on `#tl-scroll`. Record the id.

And for **Slice J**:

8. Zoom from 8 to 30 with the playhead mid-film. Record `scrollLeft` before and after and
   the playhead's on-screen x. It must hold its screen position.
9. Press `0`. Record the resulting `tlZoom`, `lanes.scrollWidth` and `scroll.clientWidth`.

**If any of these fail, stop and write `RELAY-FEEDBACK.md` rather than pressing on.**
A failure here is more valuable than the rest of this brief.

## Job 2 — Tail anchoring, where the mock is blind

With the film loaded, put the playhead in the **last 20 seconds** and zoom from 1 to 60.

The requested `scrollLeft` will exceed `scrollWidth - clientWidth`, so the browser will
clamp it and the playhead will drift from its anchored screen position. Measure the drift
in pixels and record it in the same artifact.

If the drift is more than a few pixels, fix `setTimelineZoom` to clamp its own target the
way the browser will — compute `maxScroll = lanes.scrollWidth - scroll.clientWidth` after
the re-render and, when the anchored target exceeds it, keep the playhead correct against
the clamped position instead of the requested one.

Then write a test that fails without the fix. The existing mock cannot express this, so
**give the scroll mock a real `scrollLeft` setter that clamps against a `scrollWidth`**,
matching browser behaviour. Do not weaken the assertion to fit the mock; fix the mock.

## Job 3 — "Fit" does not fit the owner's film

Measured during Slice J's review, in the Node harness:

```
total=1080s  zoom=1  laneWidthPx=1080  viewportPx=800  actuallyFits=False
```

`fitTimelineToWindow` computes `(clientWidth - 24) / total`, which for an 18-minute film is
`766 / 1080 = 0.709` px/s — below the `[1, 60]` floor, so it clamps to 1 and the lane stays
wider than the window. The button says Fit and does not fit.

**This is a fault in Slice J's brief, not in Slice J's code.** The `[1, 60]` clamp was
specified there and was implemented exactly as written. The floor is simply wrong for the
length of film this app is for.

Lower the zoom floor so a fit is reachable:

- Drop the floor from `1` to `0.2` px/s in `setTimelineZoom` **and** in the slider's `min`
  attribute in `index.html` (`#tl-zoom`, currently `min="1"`). Both must move together or
  the slider cannot reach what the keyboard can.
- The slider needs a fractional `step` — it currently has none, so it snaps to whole
  numbers. Set `step="0.1"`.
- Check `tlTickInterval()` still behaves: at 0.2 px/s `wanted = 90 / 0.2 = 450`, which
  selects the 600s entry from the existing table. No change needed, but confirm it.
- Clip widths use `Math.max(2, pic.seconds * tlZoom)`, so short clips floor at 2px. That is
  acceptable for a whole-film overview. Confirm the lane does not visually collapse.

Then verify live that `0` on the owner's real film produces `lanes.scrollWidth <= scroll.clientWidth`,
and record it.

## Job 4 — A small honesty fix

`setTimelineZoom` syncs the slider with `slider.value = newZoom`. With `step="0.1"` from
Job 3 this gets closer, but fractional zooms from `fitTimelineToWindow` and from the
`* 1.5` keyboard steps will still round. Confirm the slider and `tlZoom` agree to within
one step after a fit and after three keyboard zoom-ins, and record both numbers.

---

## Rule 4 — prove every test can fail

Slice J scored ten of ten on independent mutation. Hold that standard.

For each test you add, break the code on purpose, paste the failure, restore, paste the pass.
At minimum:

1. Tail clamp fix removed — Job 2's test must fail.
2. Scroll mock's clamping setter reverted to a plain number — Job 2's test must pass
   again, which proves the mock was the blind spot. Say so explicitly.
3. Zoom floor left at 1 — Job 3's test must fail.
4. Slider `min` lowered but `setTimelineZoom`'s floor left at 1 — must fail.
5. `step` left off the slider — Job 4's test must fail.

**Anchor mutations on CRLF.** Bare `\n` will not match in this repo and reports as
"skipped" rather than "escaped".

---

## Budgets and ratchets

- **Inline `style="` in `index.html` is at 15, cap 19.**
- **Shot cache key stays `v10`.**
- **CRLF everywhere.** 0 bare LF in every file you touch.
- Do not touch `library/index.npz`. Never run `git add -A`.

---

## Report

1. `reports/verification_gate/slice_k_dom.json`, and the measured numbers pasted inline.
2. The tail-drift measurement in pixels, before and after any fix.
3. Every mutation: the break, the failure, the restore.
4. Full suite output, pasted.
5. **Anything you did not do, named as not done.** Slice J's report did not mention the
   verification gate at all, and its Job 4 benchmark left no script and no artifact — only
   a number. A named skip is a good report; silence is not.

Then stop. Do not commit. Claude reviews the working tree and commits.
