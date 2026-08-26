# Brief: make the Settings screen collapse into sections

Hand this whole file to Antigravity. Everything it needs is here.

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/niche-visual-type` — stay on it. Do not switch branches. Do not push.
**Never** run `git add -A`. Stage only the files listed at the end.

---

## The problem

The Settings screen is one long scroll. Everything is expanded at once: the API keys table,
then 58 voices across four engines, then language packs, pronunciation, defaults, spending and
performance. The owner wants it to open **fully collapsed**, and to expand only what they click.

Two levels need collapsing:

1. **Each card on the Settings screen** — "Keys & services", "Voice catalogue", "Language packs",
   "Pronunciation dictionary", "Defaults", "Spending", "Performance".
2. **Each voice engine inside the Voice catalogue** — Google Cloud, Gemini Flash TTS, Kokoro,
   Supertonic. Clicking "Kokoro" reveals only Kokoro's voices.

Everything starts closed on every launch. No persistence is wanted.

---

## Environment

Python is NOT on PATH. Use the full path when you need it:
`C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe`

Run the app with `run.bat`. Check JS with `node --check frontend/app.js`.

---

## Where things are

| What | Where |
|---|---|
| Settings pane markup | `frontend/index.html`, the block starting `<div class="pane" data-pane="settings">` (around line 435) |
| Each section | a `<div class="card">` whose first child is an `<h3>` |
| Voice catalogue container | `<div id="voice-engines-container">` inside the Voice catalogue card |
| Voice engine rendering | `frontend/app.js`, `renderVoiceCatalogueSettings()` (around line 405) |
| Engine header markup it builds | `<div class="eng-h"><b>${engGroup.engine}</b> … </div>` |
| Styles | `frontend/style.css` |

Note `renderVoiceCatalogueSettings()` **rebuilds `#voice-engines-container` from scratch**
(`container.innerHTML = ""`) every time a voice is toggled. Whatever you do to the engine groups
must survive that re-render — put the behaviour in the rendering function or use event
delegation on the container, not one-off listeners bound at page load.

---

## What to build

### 1. A reusable collapsible pattern

Add to `frontend/style.css`:

- a `.collapsed` state that hides the section body
- a caret/chevron on the header that rotates when open
- `cursor: pointer` on headers, and a visible `:focus-visible` outline
- respect `@media (prefers-reduced-motion: reduce)` — no transition under it

Match the existing dark theme. Use the CSS variables already defined in that file
(read the top of `style.css` first); do not introduce new hard-coded colours.

### 2. Collapse the Settings cards

In `frontend/index.html`, for each `.card` inside the settings pane, wrap everything after the
`<h3>` header row in a body element, e.g. `<div class="card-body">`. Give the header a
`toggle` affordance.

**Accessibility matters here.** The clickable header must be a real `<button>` (or carry
`role="button"` plus `tabindex="0"` and Enter/Space handling) and `aria-expanded="false"`,
with `aria-controls` pointing at the body's id. Screen-reader users and keyboard users must be
able to open a section.

**Do not change any input, id, table, or button inside the cards.** Every existing id must keep
working — `google-key-input`, `google-tts-key-input`, `elevenlabs-key-input`,
`voice-catalogue-count`, `voice-engines-container`, and the rest. Wrapping is all that is wanted;
the contents are not to be rewritten.

### 3. Collapse each voice engine

In `frontend/app.js`, in `renderVoiceCatalogueSettings()`, render each `.eng` block collapsed:
the `.eng-h` header stays visible, the `.tbl` table below it is hidden until the header is
clicked. Keep the existing per-engine counts in the header (`N voices`, `N enabled`) — those are
the useful part when everything is shut.

Use event delegation on `#voice-engines-container` so the behaviour survives the re-render that
`toggleVoiceEnable` triggers. If you bind listeners inside the render loop instead, make sure
they are re-bound on every render — but delegation is cleaner.

### 4. Keep the Keys & services card usable

That card holds three password inputs and their "Test & Save" buttons. Collapsed by default like
the rest, but make sure that when it is opened the existing "Test & Save" flow still works
unchanged. Do not touch the key-handling JavaScript.

---

## What must not change

- No Python file. This is HTML, CSS and JS only.
- No element ids, no input names, no existing event handlers.
- The Script, Storyboard, Render, Library and Voiceover panes — untouched.
- Do not "tidy" unrelated markup while you are in there.

---

## Verification — do all five, do not skip

1. `node --check frontend/app.js` exits 0.
2. Run `run.bat`, open **Settings**. Every section must be closed. The screen should be short
   enough to see all seven section headers without scrolling far.
3. Click **Voice catalogue** → it opens and shows four engine headers, all closed. Click
   **Kokoro** → only Kokoro's voices appear.
4. With Kokoro open, tick a voice checkbox. The list re-renders — confirm **Kokoro is still
   open** afterwards and the counts updated. This is the bug most likely to bite; the container
   is rebuilt on every toggle.
5. Tab through the Settings screen with the keyboard. Each section header must take focus, show a
   visible focus ring, and open with Enter or Space.
6. Run the Python suite once to prove nothing was disturbed:
   `"C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe" -m pytest -q`
   Expected: **313 passed, 2 skipped, 1 xfailed**. Anything else, stop and report it.

---

## Commit

```
git add frontend/index.html frontend/app.js frontend/style.css
git commit -m "feat(settings): collapse every section and voice engine until clicked"
```

---

## Report back

Paste the raw output of:

```
git log --oneline -1
git status --short
node --check frontend/app.js
```

and state:

- whether step 4 passed (does the open engine stay open after toggling a voice?)
- whether keyboard focus and Enter/Space work on the headers
- the exact pytest line
- anything you changed beyond what this brief describes, and why
- any command that failed, with its exact error text
