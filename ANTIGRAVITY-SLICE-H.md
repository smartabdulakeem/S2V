# Brief: Slice H — the picture and the words keep up with the voice

Hand this whole file to Antigravity.

**Read `ANTIGRAVITY-RULES.md` first — its standing rules apply.**

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget`. **Do not commit. Do not push.**
**Baseline: 1258 passed, 1 xfailed, 0 failures.** Roughly 10 minutes.
Python: `C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe` (not on PATH).
Prefix anything printing prompt text with `PYTHONIOENCODING=utf-8`.

---

## Where this sits in Milestone 2

Slice G finished the **audio** half of Timeline Live Playback & Audio Sync: effects fire on the
clock, music fades honestly, and the music no longer drifts. That work is committed.

This is the **visual** half, and it is the last slice of Milestone 2. When it lands and is
verified, set `phase: "MILESTONE_COMPLETE"` and `ready_for: "OWNER"`. Do not begin Milestone 3.

**Do not declare the milestone complete on the strength of this brief alone.** The Slice G handoff
offered "caption and picture timing are already frame-accurate" as an option, and it is not true —
see below. Claims about this screen have been wrong before because nobody looked.

---

## What is actually true today

Verified in the working tree, not assumed:

**Pictures already follow the audio clock, and appear to do so correctly.** `timelineSeek`
(~L2782) picks the picture with
`pics.find(p => tlPlayhead >= p.startsAt && tlPlayhead < p.startsAt + p.seconds)` and only touches
the DOM when the picture number actually changes. `tlAnimLoop` calls it every frame with
`audio.currentTime`. That is the right shape. **Your job is to prove it, not to rewrite it.**

**Captions are drawn once and never move.** `laneC.innerHTML` is written in `renderTimelineScreen`
(~L2984) from static `.tl-cap` blocks positioned at `left: startsAt * tlZoom` (~L2913).
`tlAnimLoop` never touches `laneC`. Grep confirms: no active-line class, no highlight, nothing
keyed to the playhead. So during playback the caption lane is a static diagram of where lines
*would* be, next to a playhead that moves past them.

That is the gap. The owner is trying to judge whether a picture belongs against the line being
spoken, and the lane that shows the lines does not tell him which one that is.

---

## Job 1 — The spoken line highlights as it is spoken

Give `.tl-cap` an active state driven by the playhead.

- One function, pure, testable: `tlActiveCaptionIndex(seconds)` returning the index of the caption
  block containing that time, or `-1` before the first / after the last.
  **Use the existing `tlLineAt` arithmetic** (~L2871) rather than writing a fourth version of
  "which line is at time t". If `tlLineAt` already returns exactly this, call it and say so in the
  report instead of adding a wrapper for its own sake.
- Toggle a single `active` class in `tlAnimLoop`. **Only touch the DOM when the index changes** —
  the picture frame already uses that guard (`at.number !== tlCurrentFramePic`) and it exists
  because this loop runs sixty times a second. Do not rewrite the lane's HTML per frame.
- The highlight must also be correct after a **seek**, not only while playing forward, and when
  **paused** it shows the line under the playhead.
- Style the active state in `style.css`. **The inline `style="` budget in `index.html` is capped at
  19 and currently sits at 15** — this is a class toggle, not an inline style.

## Job 2 — The active line stays visible

When the highlight moves outside the visible scroll window during playback, bring it back.

`timelineSeek` already has this logic for the playhead (~L2806-2812) and the comment there records
why it exists — stepping to picture 12 of an eighteen-minute film put the playhead 9,000px along a
lane 790px wide. **Reuse that scroll behaviour.** Do not add a second, differently-tuned
auto-scroll that fights the first one.

If the two would ever disagree, the playhead wins. Say so in the report if you hit that case.

## Job 3 — Prove the picture changes on time

This job is measurement, not code. If it finds a defect, report it; do not fix it silently.

On the owner's film, `projects/Before_Adam_The_Story_of_Iblis`:

- Pick three picture boundaries spread across the film — one near the start, one mid-film, one past
  fifteen minutes, where accumulated error would show.
- For each, record the picture's `startsAt`, and the `audio.currentTime` at which `tl-frame`
  actually swaps during real playback.
- Report the three deltas in milliseconds.

**A delta under about 40 ms is two frames at 50 fps and is fine.** If any delta grows with position
in the film, that is accumulating drift and it is a real defect — say so plainly and stop rather
than papering over it. Slice G bounded the *music* drift; nothing has yet checked whether
`startsAt` accumulates error against measured narration.

---

## Tests

Rule 4 applies: **break each one on purpose and confirm it fails.** Slice G shipped two tests that
could not fail — one asserted a string that was already in the file, and one used a fixture where
the broken and correct implementations both produced zero. Both were caught in review. Do not make
a third.

For each test below, state in the report **what you broke and what error you saw.**

1. `tlActiveCaptionIndex` returns the right index at the start, middle, and end of a caption block.
2. It returns `-1` before the first caption and after the last.
3. **The boundary belongs to exactly one line.** At a time that is exactly a caption's `startsAt`,
   exactly one index is returned, and it is the starting line — not the one that just ended.
   Round-trip several boundaries.
4. **The DOM is only touched when the index changes.** Advance the playhead across many frames
   *within* one caption and assert the update ran once, not once per frame. Count the calls.
5. **Seeking backward updates the highlight.** This is the shape of bug Slice G's seek guard was
   written for; the caption highlight has the same failure mode in reverse.

A note on fixtures, learned the hard way this milestone: **choose values where a broken
implementation and a correct one give different answers.** A fixture where every caption sits
before the seek point cannot tell a positioned cursor from a parked one.

---

## Acceptance

Paste real output, not a description of it.

1. **Full suite green.** Expect **1258 + your new tests, 1 xfailed, 0 failures.** Do not run it
   while anything else heavy is running — `test_parallel.py` does a real render and starves.

2. **The live gate, and write the artifact.** Open the live WebView2 window and confirm before you
   change anything. Then, after the build, **write your DOM measurements to
   `reports/verification_gate/slice_h_dom.json`.**
   The Slice G handoff claimed `isPlayCovered: false` and a 10px gap, and no file in the repo
   recorded either number. The claim was probably true and it was still unverifiable. Numbers in a
   report are checked; numbers with no artifact cannot be.

3. **On the owner's film:** play from 0:00 and say whether the highlighted line matches the voice.
   Then seek to roughly 12:00 and say it again. Two sentences, plainly.

4. **The three picture deltas from Job 3**, in milliseconds, with the times you measured them at.

5. **Answer this directly:** watching the Timeline play, can the owner now tell whether a picture
   belongs against the line being spoken? That is the question the whole milestone exists to
   answer. If the answer is no, say what is still missing — that is more useful than a green suite.

Name anything you skipped. Silence is not a report.

## Out of scope

Do not touch: the SFX scheduler, `musicGainAt`, or `checkMusicDrift` — Slice G is committed and
verified. Do not touch the Timeline layout CSS; the transport fix is committed and its regression
test is scoped to those rules. Also leave alone `pipeline/timeline_audio.py`, picture boundaries
and the Slice E drag, `library/index.npz`, and the Phosphor icons.

**Do not build:** caption editing on the Timeline, per-word karaoke highlighting, subtitle export,
or a caption style editor. The lane highlights the current line. That is the slice.

---

**Stop when the report is written. Do not commit. Do not push.**
