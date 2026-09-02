# Plan revision — front end first, audio first

Written 2 Sep 2026. Supersedes the ordering and scope decisions in
`docs/superpowers/plans/2026-09-01-model-chosen-picture-boundaries.md`.
That plan's engine work stands. Its ordering and its scope lines do not.

**Nothing here is approved yet.** It is the plan put in front of the owner to sanctify.

---

## Why the old plan needs revising

Three of its decisions are now wrong, and each one is wrong in the owner's favour.

**1. "No frontend work" is obsolete.**
The plan says frontend work is "deliberately out of scope." The owner is not a programmer and
can only test through the front end. Every defect found on 1–2 Sep was found by running the app
and reading real output, not by reading code. That scope line is deleted.

**2. Audio-first was written into the plan and never enforced.**
The plan's own order of operations is `1. Audio rendered → 2. Boundaries chosen`. It was never
made to happen. Measured today on `projects/Before_Adam_The_Story_of_Iblis/script.json`:

| | |
|---|---|
| segments | 347 |
| with a measured `narration_seconds` | **0** |
| with a `narration_audio` file | **0** |

Every picture boundary in that film stands on a word-count guess. The owner asking for audio
first is not a change of direction — it is the plan finally doing what it said.

**3. WolfCut is no longer the destination.**
The plan's step 5 was "Timeline exported → WolfCut." The Timeline is now screen 3 inside the
app. The `.wolfcut` export drops from the spine of the plan to an optional side door.

**4. Task 13's metric is dead** — see `ACCEPTANCE-FINDINGS.md`. Success is measured by the
*starved* count (pictures whose narration names fewer than two photographable things), and on
this script the usable range is **10–20 pictures**. A random partition beat both real methods
on the old metric, which is how it was caught.

---

## The new order of work

Every slice below is testable by the owner in the front end on the day it lands. That is the
selection rule, and it is the only one.

### Slice A — Trim the front end

92 `<button>` elements across 7 screens (Script, Storyboard, Timeline, Render, Library,
Voiceover, Settings).

- Produce a **kill / keep / move list** covering all 92, with what each one does in one line.
- **The owner approves the list before a single button is removed.** Nothing goes on a guess.
- Removals land screen by screen so each is testable on its own.

Decision taken: **trim what exists.** The Stitch mockups are parked, not cancelled — the
owner's approval of a faithful port still stands and can be picked up later.

### Slice B — The camera, in both senses

**The camera move over the pictures.** `pipeline/motion.py` holds the styles (Static, Gentle
drift, Ken Burns, and others), each with a `rate`, `min` and `max`. There is a dropdown
(`get_motion_styles`, `app.py:556`) but no amount control.

- Reduce the default travel.
- Add an **amount slider** in Settings that scales `rate`/`min`/`max` on whichever style is
  chosen, so "Ken Burns at 40%" is a thing the owner can ask for.
- `test_motion.py` already holds the long-hold clamp. It must still pass at every slider value.

**The app window.** Hardcoded **1000 × 900** at `app.py:1738`.

- The window remembers its size and position between launches.
- A reset in Settings for when it ends up somewhere useless.

### Slice C — Audio first, made the actual order

`Measure narration` already exists (`frontend/index.html:198`). It renders a real mp3 per line
via `generate_voiceover` and measures it with `ffprobe` — no video encode. It is simply
optional today, and so never run.

- The Storyboard states plainly, before planning, whether the film has real seconds or guesses.
  The Timeline already colours narration **green** where measured and **amber** where guessed;
  the Storyboard should not be quieter than the Timeline about the same fact.
- Planning on guesses stays *possible* — it must not become a wall — but it stops being silent.
- **Run it on Before Adam.** 347 lines. This is the first real test of the pass at full length.

### Slice D — The Timeline plays

This is the slice the owner actually asked for: push play, hear the narration, watch the
pictures change, see with his own eyes whether each one is in the right place.

- Serve the narration mp3s to the page. The app already plays mp3 audio at
  `frontend/app.js:670`; the dev server can serve files.
- Play / pause / space bar. The playhead follows the audio rather than a timer.
- The picture under the playhead is shown large as it plays.
- Scrubbing already works and does not regress.

### Slice E — Adjust while listening

Cut and join already exist on the Timeline and are proven on the real 347-line film. What is
missing is doing it *without stopping*.

- Move a boundary while the audio is running.
- Nothing re-plans. A boundary is one `share_with` field; `split_picture` / `merge_picture`
  already flip it without touching descriptions. That is what saved the 26 stranded ones.

### Slice F — Music and sound effects

Two more tracks under the narration. Add a file, position it, set its volume, fade it.

This is where the WolfCut idea lands — **in our own code**. See the licence note below.

---

## Demoted, not dropped

| | |
|---|---|
| **Task 12** (whole chain, in order) | Never written. One test, cheap. Write it during Slice C. |
| **WolfCut `.wolfcut` export** | Kept and working. Not developed further. |
| **Task 13's metric** | Replaced by the starved count in `ACCEPTANCE-FINDINGS.md`. |
| **Full Stitch port** | Parked. Approval stands for later. |

## Untouched, deliberately

`plan_image_budget`, `plan_shots`, image binding (pin → numbered folder → CLIP → gap prompt),
and the 683-test suite. Slice A removes buttons from screens; it does not remove capability.

## Outstanding, and owed to the owner

His film still needs **one re-plan** to repair. `script.json` is byte-identical to the state he
left it in — 15 clock-cut pictures, 30 written descriptions of which 26 are stranded on shots
carrying `share_with` where no prompt can reach them. Backup sits beside it as
`script.backup-before-claude-test-20260902.json`.

---

## Licence note — WolfCut, and the bigger one

**WolfCut renamed.** `jub0t/WolfCut` is now **`jub0t/Concat`**, "formerly WolfCut", still
**MPL-2.0**. `pipeline/wolfcut_export.py` pins commit `cad030dabc18f4013855c9fe89ca3688e8a5298d`
from the old name. If the format is ever re-read, re-read it from `jub0t/Concat`.

- **Taking the idea** — an audio track under the picture track, a playhead, music and SFX
  tracks, trimming a clip — **carries no obligation.** Workflow and layout ideas are not
  copyrightable.
- **Copying their code** — any `.rs`, `.tsx` or `.css` file — would. MPL-2.0 is file-level
  copyleft: those files stay MPL and their source must be published. Nothing in this repo does
  this, and Slice F must not start.
- Writing a `.wolfcut` JSON in their documented format carries no obligation. Formats are not
  protected.
- Do not use "WolfCut" or "Concat" as a product or UI name.

**The real exposure is ours, not theirs.** `vendor/ffmpeg/bin/ffmpeg.exe` is a **GPL v3 build**:

```
--enable-gpl --enable-version3
```

Personal use, no obligation. The day Smart Studio is sold or handed to anyone, GPL-3 attaches
to what is shipped. The fix is swapping in an LGPL build of ffmpeg, which costs a download and
a re-test of the render path. Not urgent. Should not be discovered at launch.

*Not legal advice — the facts are stated so the owner can decide.*
