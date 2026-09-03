# Brief: Slice C — audio first, proved at full length

Hand this whole file to Antigravity.

**Read `ANTIGRAVITY-RULES.md` first — its standing rules apply.**

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget`. **Do not commit. Do not push.**
**Baseline commit:** `cc23e43`. **Baseline suite: 1246 passed, 1 xfailed, 0 failures.** ~8 minutes.
Python: `C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe` (not on PATH).

---

## Read this before you build anything

**This slice is smaller than the plan implies, because most of it is already built.** I checked
rather than assumed, and you should not rebuild any of the following:

- **The Storyboard already states whether the film has real seconds or guesses.**
  `frontend/index.html:198` is `<span class="mono timing-pill warn" id="timing-pill">`, sitting
  directly beside **Re-plan pictures** and **Measure narration**. `updateTimingPill()`
  (`frontend/app.js:2250`) toggles `ok`/`warn` and writes one of "timings measured",
  "N of M measured", or "estimated from word count". It is called on script load
  (`app.js:1878`) and after a measuring pass (`app.js:2292`).
- **The measuring pass works.** `measure_narration_for_script` (`app.py:893`) renders a real mp3
  per line via `generate_voiceover` and measures it with ffprobe. No video encode.
- **The Timeline already colours narration green where measured and amber where guessed.**

So the plan's headline bullet — "the Storyboard should not be quieter than the Timeline about the
same fact" — is done. **Do not build a second pill.** What is actually outstanding is below, and
it is mostly proof rather than construction.

One thing I could not settle from the code, and you should check in the running app: the pill is
adjacent to *Re-plan pictures*, but `planStoryboard()` (the first plan, from the Script screen at
`index.html:173`) contains no reference to timings at all. Before the first plan there are no
segments yet, so there is nothing to measure — which may make that correct rather than a gap.
**Look at it in the window and say which it is.** If the first plan genuinely reads as silent
about something the owner should know, say so and propose the smallest honest fix. Do not build
one on a guess.

---

## Job 1 — Task 12, the test nobody wrote

`PLAN-REVISION-FRONTEND-FIRST.md:121` assigns this to Slice C, and
`HANDOFF-PICTURE-BOUNDARIES.md:190` records it as never written. The full specification, including
the test body, is in `docs/superpowers/plans/2026-09-01-model-chosen-picture-boundaries.md:1686`.
Read it there and follow it.

The question it answers is the owner's: **after the audio is rendered and the boundaries are
chosen, are images still picked automatically?** They are — `plan_shots` binds a pin, then a
numbered folder image, then CLIP retrieval, then a gap prompt. Nothing in the boundaries work
touched that. But `plan_shots` also calls `describe_shots`, and nothing proves it will not throw
away descriptions `apply_spans` already wrote and ask the model again. Every re-plan would then
pay twice, and the second answer would be written for a shot rather than for the span — which is
the exact defect the boundaries plan existed to remove.

Append it to `tests/test_span_apply.py`, as the specification says. The `_MustNotBeCalled` double
in that spec is the point: the test passes only if the model is never asked.

## Job 2 — run the measuring pass at full length

`Before Adam` is **347 lines**. The measuring pass has never been run at that size, and the plan
calls this "the first real test of the pass at full length."

Run it on `projects/Before_Adam_The_Story_of_Iblis` and report, with numbers:

- how long the whole pass took, wall clock;
- how many lines measured and how many failed (`measure_narration` returns
  `{"measured", "failed", "seconds"}` — paste it);
- what the pill said before and after;
- whether the UI stayed usable while it ran, or whether it locked up. `onTimingProgress`
  (`app.js:2265`) pushes one event per segment, so there is a progress path — say whether it
  actually reports smoothly across 347 lines or floods.

**If it is too slow to be usable, that is the finding.** Say so with the number rather than
quietly shipping it. Do not optimise it in this slice without saying what you changed and why.

## Job 3 — repair the owner's film

`PLAN-REVISION-FRONTEND-FIRST.md:132`: the film needs **one re-plan** to repair. Its `script.json`
is byte-identical to the state it was left in — 15 clock-cut pictures, and **30 written
descriptions of which 26 are stranded** on shots carrying `share_with`, where no prompt can reach
them.

- The backup already exists beside it as `script.backup-before-claude-test-20260902.json`.
  **Confirm that file is present and readable before you touch anything.** If it is missing, stop
  and say so — do not proceed without it.
- Re-plan the film once.
- Report how many descriptions are reachable afterwards, and how many pictures it now has.
- **Do not delete the backup.**

This is the owner's real project, not a fixture. If anything looks wrong mid-way, halt and write
`RELAY-FEEDBACK.md` rather than pressing on.

---

## Tests

1. **Task 12** as specified above. Run it against the current tree first — if it passes
   immediately, say so and explain why it still earns its place (a regression guard for a
   property that holds today is legitimate; claiming you fixed something you did not is not).
2. **The pill tells the truth.** Given a script with all, some and no segments carrying
   `narration_seconds > 0`, `updateTimingPill` produces the measured / partial / estimated text
   and the matching `ok`/`warn` class. Drive it in Node the way
   `tests/test_music_and_sfx.py::_run_node_expr` already does; do not invent a second harness.
3. Anything Job 2 or Job 3 turns up that is worth pinning.

Rule 4 in `ANTIGRAVITY-RULES.md` applies: **break each test on purpose and confirm it fails.**

Two recent shapes to avoid, both real and both from this repo:

- Slice F shipped a fade test that ran a hand-written ffmpeg string through ffmpeg. It proved
  ffmpeg has an `afade` filter and would have passed against no implementation at all.
- Slice F's sound-library test asserted `len(load_beds()) >= 14` against the developer's own
  library, so it reported on one machine's contents and would fail on a fresh clone.

---

## Acceptance

Paste real output, not a description of it.

1. **Full suite green.** Expect **1246 + your new tests, 1 xfailed, 0 failures.** Do not run it
   while anything else heavy is running — `test_parallel.py` does a real render and fails when
   starved of CPU.
2. **The 347-line measuring run**, with the numbers Job 2 asks for.
3. **The film repaired**, with the description counts before and after, and confirmation the
   backup is untouched.
4. **Say whether the first plan is silent about timings**, having looked at it in the running
   window — and if it is, what the smallest honest fix would be.
5. **Confirm CRLF.** Every file you touched must have 0 bare LF line endings.

Name anything you skipped. Silence is not a report.

## Out of scope

Do not touch: `plan_image_budget`, `plan_shots`, or image binding (pin → numbered folder → CLIP →
gap prompt) — Task 12 exists to prove those still work, not to change them. Also leave alone the
Slice B camera amount and window memory, the Slice F music and SFX lanes, picture boundaries and
the Slice E drag, and the Phosphor icons.

**Do not port anything from `jub0t/WolfCut` / `jub0t/Concat`.** It is MPL-2.0 and file-level
copyleft. Taking the layout idea carries no obligation; copying their `.rs`, `.tsx` or `.css`
does. Nothing in this repo does, and it stays that way.

---

**Stop when the report is written. Do not commit. Do not push.**
