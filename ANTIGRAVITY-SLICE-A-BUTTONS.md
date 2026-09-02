# Brief: Slice A — remove the dead controls, put the pipeline in order

Hand this whole file to Antigravity.

**Read `ANTIGRAVITY-RULES.md` first — its standing rules apply.** Two of them matter most here:
stop when the report is written, and inline `style="` in `index.html` is capped at 19 and is
currently at 19, so every layout change goes in `style.css`.

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget`. **Do not commit. Do not push.**
**Baseline:** 683 passed, 1 xfailed, 0 failures.
**Files you will touch:** `frontend/index.html`, `frontend/app.js`, `frontend/style.css`,
`tests/test_frontend_controls.py` (create).

---

## What this is for

The app has **106 buttons**. The owner has approved an audit of every one. Fourteen are dead or
duplicated, six are on the wrong screen, and one that the workflow depends on does not exist.

This brief is the approved list, nothing more. **Do not add, remove or rename any control that is
not named below.** The owner reviewed each row individually; anything else is out of scope even if
it looks obviously wrong to you. Say so in the report instead.

The shape being enforced is a three-stage pipeline:

```
STAGE 1  Script      write narration, pick voice and formats   →  Plan storyboard →
STAGE 2  Storyboard  prompts out, images in, check them        →  Open in Timeline →
STAGE 3  Timeline    watch it, fix it, render it               →  Render film
```

---

## Job 1 — delete five Settings sections that were never wired

All five are mockups: hardcoded values, no `id` on any control, and **zero references in
`app.js` or `app.py`**. Verify that for yourself before deleting — `grep` each `aria-controls`
id across both files and paste the counts in your report. If any one of them returns a hit,
**stop and report it** rather than deleting.

| Section | `aria-controls` | Buttons removed |
|---|---|---|
| Defaults | `card-body-defaults` | 1 (the section toggle) |
| Spending | `card-body-spending` | 1 |
| Performance | `card-body-performance` | 1 |
| Pronunciation dictionary | `card-body-pronunciation` | 8 (toggle + 4 × Test + Add entry + Import from script + Export) |
| Language packs | `card-body-lang-packs` | 1 |

Delete the whole `<div class="card collapsed">…</div>` wrapper for each — toggle, body and all.
**12 buttons go.**

Then delete the button on the **Script** screen at `index.html` ~L141,
`Pronunciation dictionary` (`onclick="switchPane('settings')"`). It exists only to jump to the
panel you just deleted.

**13 buttons removed so far.**

## Job 2 — remove the duplicated controls

**`Open in WolfCut` on the Storyboard** (~L206, `id="btn-open-wolfcut-board"`). The identical
button exists on the Render screen at ~L378. Delete the Storyboard copy only. **Leave
`openInWolfCut()` in `app.js` and leave the Render screen's button alone** — WolfCut export is a
kept, optional feature.

**14 buttons removed. That is all the deletions in this brief.**

**`Work from this folder…` and `Whole library` on the Script screen** (~L49, ~L50). The Storyboard
already has its own `Work from this folder…` at ~L202. Choosing which folder the image search is
scoped to is a picture decision, so it belongs on Stage 2 only.

- Delete both buttons and the `working-folder-label` span from the Script screen.
- On the Storyboard, add a `Whole library` button beside the existing folder button, calling the
  existing `useWholeLibrary()`.
- `chooseWorkingFolder()` and `useWholeLibrary()` both already update
  `working-folder-label-board`. Check what they do with the now-deleted `working-folder-label`
  and remove those lines rather than leaving them to throw.

## Job 3 — move the render out of the Storyboard

The owner does not render from the Storyboard any more. He goes to the Timeline, watches the film,
then renders.

- Delete `Render video →` from the Storyboard (~L209, `id="btn-start-render-board"`).
- Add it to the **Timeline** screen's control row as `Render film`, `class="primary"`,
  `id="btn-render-film"`, calling the **existing, unchanged** `startRenderFromBoard()`.
- Do not rename `startRenderFromBoard()` and do not change what it does.

## Job 4 — build the missing handoff

**`Open in Timeline →` does not exist.** Stage 1 → 2 has `Plan storyboard →`; Stage 2 → 3 has
nothing. Add it to the Storyboard control row:

```html
<button type="button" class="primary" id="btn-open-timeline" onclick="openTimelineFromBoard()">Open in Timeline &rarr;</button>
```

In `app.js`:

```javascript
async function openTimelineFromBoard() {
  if (!currentScriptData) {
    alert("Plan a storyboard first.");
    return;
  }
  switchPane("timeline");
  renderTimelineScreen();
}
window.openTimelineFromBoard = openTimelineFromBoard;
```

`switchPane` and `renderTimelineScreen` both already exist. Do not modify either.

## Job 5 — demote the paste-prompts route

`Paste external prompts…` (~L205) is the Option B workflow — the owner exports a file, pastes it
into an outside AI chat, and pastes the reply back. He works in Option A (Gemini in-app), so this
is a fallback, not a front-row action.

Keep the button and everything it opens. Move it out of `.board-controls-row` into a second,
quieter row below the main controls, styled with the existing `ghost` class. Nothing about
`togglePastePromptsPanel()`, `writePromptRequest()` or `submitPastedPrompts()` changes.

## Job 6 — two renames that stop the UI lying

**Label change only, both of them.** Do not change any `id`, any `onclick`, or any behaviour.

| Where | Now | Becomes |
|---|---|---|
| Storyboard ~L202 | `Work from this folder…` | `Drop image folder…` |
| Storyboard ~L204 | `Copy all prompts` | `Export prompts for Flux` |

**One function rename**, because the name is actively false: `refreshLibraryAndReplan()` in
`app.js` ~L2686 **does not re-plan anything** — it re-indexes the image library and refreshes the
board. Rename it to `refreshLibrary()`. Update the `onclick` at `index.html` ~L207 and the
`window.` export. The button's visible label, `Refresh library`, is already correct and stays.

## Job 7 — make the rail show the pipeline

The rail currently lists seven equal-looking screens. Three of them are the pipeline and four are
not. Keep all seven buttons — nothing is removed here — but separate them visually.

- `Script 1`, `Storyboard 2`, `Timeline 3` stay as a numbered group at the top.
- Insert a horizontal rule or spacer after `Timeline`.
- `Render`, `Library`, `Voiceover` sit below it as tools rather than steps. **Drop their `4`, `5`,
  `6` shortcut digits from the visible label** but keep the keyboard shortcuts working exactly as
  they do now — check how the `.k` span and the key handler relate before changing either.
- `Settings` stays where it is at the bottom.

Rule and spacing go in `style.css`.

---

## Tests

There is currently **no test anywhere that guards the frontend**, which is why seven buttons with
no click handler survived to production. Create `tests/test_frontend_controls.py`:

**Test 1 — every button does something.**
Parse `frontend/index.html`. For every `<button>`, assert at least one of:
- it has an `onclick="someFunction(...)"` whose `someFunction` is defined in `frontend/app.js`
  (match `function someFunction` or `someFunction = `), or
- it carries `class="card-toggle"` (wired by the delegated listener at `app.js` ~L540), or
- it carries `class="lib-tab"` or `class="plan-seg-btn"` or `class="nav"` (wired by their own
  handlers — confirm each of these is genuinely wired before adding it to this allow-list).

The failure message must name the offending button's label and line number. **Run this test
against the current `index.html` before you make any change** and paste the list of failures it
finds — that list is the proof the test works. It should catch the seven pronunciation buttons.

**Test 2 — the deleted sections are gone.**
Assert none of the five `aria-controls` ids appear in `index.html`.

**Test 3 — the handoff exists.**
Assert `index.html` contains `id="btn-open-timeline"` and `app.js` defines `openTimelineFromBoard`.

**Test 4 — the duplicates are gone.**
Assert `btn-open-wolfcut-board` and `btn-start-render-board` do not appear in `index.html`, and
that `btn-render-film` does.

Do not write a test that asserts a total button count. It will break on the next legitimate change
and tell you nothing about why.

---

## Traps

1. **`index.html` and `app.js` are CRLF.** Check the byte count before and after and normalise if
   your editor writes LF. A whole-file line-ending flip makes the diff unreviewable and it will be
   sent back.
2. **Inline `style="` in `index.html` is at its cap of 19.** Every one is dynamic state. Do not add
   a twentieth. New layout goes in `style.css`.
3. **Deleting a button is not deleting its function.** `openInWolfCut()` stays. `useWholeLibrary()`
   stays. Only `refreshLibraryAndReplan` is renamed, and nothing is deleted from `app.js`.
4. **`switchPane` numbering.** The panes are addressed by `data-pane="name"`, not by the digit in
   the label. Removing a visible `4` must not change any `data-pane` value or any `data-on`
   attribute.
5. Do not touch `app.py`, `pipeline/`, or any existing test file.

## What is explicitly NOT in this brief

- **Moving `Measure narration` to the Script screen.** It reads `currentScriptData.segments`, which
  do not exist until `parse_plain_text()` has run — and that call parses *and* plans in one step.
  Splitting them is Slice C. **Leave the button where it is on the Storyboard.**
- **Play / pause on the Timeline.** That is Slice D.
- **The motion slider and window sizing.** Slice B.
- Any redesign, restyle or Stitch port.

## What to report

1. The `grep` counts for all five `aria-controls` ids across `app.js` and `app.py`, pasted.
2. The output of Test 1 run **before** your changes — the list of dead buttons it found.
3. The output of the full new test file **after** your changes.
4. `git diff --stat` for the three frontend files.
5. The full suite: `pytest tests/ -q`. Baseline is 683 passed, 1 xfailed.
6. A count of `<button` in `index.html` before and after. Expected: 92 → 79.
   (92 − 14 deleted + 1 new `Open in Timeline` = 79.)
7. Anything in this brief you could not do, and why. Silence is not a report.
