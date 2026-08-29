# Brief: fix the layout, once, properly

Hand this whole file to Antigravity.

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget` — stay on it. **Commit** when done. **Do not push.**
**Never** run `git add -A` — it stages ~816 MB including two 310 MB ONNX models.

This is a **UI-only** job. Do not change pipeline behaviour, prompts, rendering or tests that
cover them. If a Python file needs touching, you have misread the brief.

---

## The complaint

> "I don't have to be scrolling scrolling in order to understand what I'm seeing. The arrangement
> of the app is very poor. Everything is just big big. I have to scroll scroll scroll, and this is
> not how a premium app should look. It's not just in the settings, even in the storyboard and the
> script, everywhere."

He is right, and the cause is findable rather than a matter of taste. Start with the measured bug
below before changing anything by eye.

---

## The bug that makes everything enormous

`frontend/style.css`:

```css
label.f {
  display: flex;
  flex-direction: column;
  flex: 1 1 190px;      /* ← intended as a WIDTH basis */
}
```

`190px` is a **flex-basis**, and flex-basis applies along the container's main axis. In a normal
`.row` (`flex-direction: row`) that means "at least 190px wide" — correct, and it is why fields
wrap nicely on the Script screen.

But six places force the container to a column:

```html
<div class="row" style="flex-direction:column; gap:10px">
```

In a column container the main axis is vertical, so `flex: 1 1 190px` now means **"at least 190px
tall, and grow to fill"**. Every single-line text input becomes a ~190–280px block of mostly empty
space. That is the "everything is big big" the owner is describing, and it is why Settings needs so
much scrolling.

**Find all six** (`grep -n 'flex-direction:column' frontend/index.html`) and fix each properly —
not by overriding the height, but by using a layout that is correct for stacked fields. A simple
`display: grid` with `gap` is the honest fix for a stacked form; `.row` + `.f` was designed for
horizontal wrapping and should keep doing that job.

**Verify with numbers, not by eye.** Before and after, report the pixel height of the
"Visual style per niche" card body and how many fields are visible without scrolling.

---

## The systemic cause

`frontend/index.html` contains **110 `style="` attributes.** Layout is being decided element by
element, inline, which is why it is inconsistent between screens and why each fix creates a new
oddity somewhere else.

Do not attempt to remove all 110 in one pass. Do this instead:

1. Fix the six column-rows first (above). Measure. That alone should remove most of the scrolling.
2. Then take the inline styles that are **layout** (`flex-direction`, `width`, `height`, `margin`,
   `padding`, `gap`, `flex`) and move them into named classes in `style.css`. Leave inline styles
   that are genuinely one-off (a specific colour on one element) alone.
3. Do not invent a new design system, do not add a CSS framework, do not restyle components that
   are not broken. The visual language — dark theme, mono labels, amber accent — stays exactly as
   it is. This is an **arrangement** job, not a redesign.

---

## The three screens, in priority order

Work through them in this order and report each separately.

### 1. Settings — worst offender

- The six column-rows are here and on other screens; fix them all.
- Field labels are two lines each ("DISPLAY NAME" then "(name shown in dropdowns)"). Put the hint
  on one line with the label, or make it the input's placeholder, so a label costs one line.
- Long single-line inputs (Display Name, Brief Subject) are ~300px wide inside a ~1300px card.
  Let them use the width available.
- Cards should be able to sit **two across** when the window is wide enough, instead of one
  enormous column.
- The Prompt Recipe textarea is the exception: it holds a document of tens of kilobytes and should
  be **tall and full width**, with its own scroll. Do not shrink that one.

### 2. Storyboard

- Shot cards should tile in a responsive grid, not stack one per row.
- A shot card should show its thumbnail, query and controls without the card being taller than it
  needs to be.

### 3. Script screen

- The Narration card row now holds four selects (Narrator, Tone, Visual type, Camera motion) at
  `flex: 1 1 190px`. That is correct and wraps properly — leave it.
- Check the rest of the screen for the same column-row bug.

---

## Rules

1. **UI only.** No Python, no prompt text, no pipeline behaviour.
2. **Do not change the theme.** Colours, fonts and the general look stay.
3. **`node --check frontend/app.js`** must pass.
4. The window is often **1900×1000 or smaller** — the owner runs it on a laptop. Test at that size,
   not on a large monitor.
5. Nothing may require horizontal scrolling at 1280px wide.
6. **Do not weaken or delete a test to make a change pass.** If a test genuinely encodes behaviour
   that is deliberately changing, rewrite it to assert the new contract and **say so prominently in
   your report.** Silently relaxing an assertion has happened on this repo before and was caught.

---

## What "done" looks like

- **Screenshots before and after** for each of the three screens, at 1900×1000, saved to disk with
  their paths in the report.
- **Measured**: the pixel height of the Settings "Visual style per niche" card body before and
  after, and the number of fields visible without scrolling.
- A count of inline `style="` attributes before and after.
- A plain statement of anything you did not do and why.

Finish with the full suite — it should be untouched by a UI job:

```
PYTHONIOENCODING=utf-8 <python> -m pytest tests/ -q
```

Baseline: **430 passed, 1 xfailed**.

---

## Committing

Commit when green. **Commit is local — it does not touch GitHub.** Do not push.

Stage explicit paths only — `frontend/index.html`, `frontend/style.css`, `frontend/app.js`.
One commit per screen if the changes are large enough to read separately, otherwise one commit for
the lot. Write the message the way the repo does: a short summary line, then what was wrong and
what the measurement showed. `git log` shows the shape.
