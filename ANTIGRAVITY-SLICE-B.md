# Brief: Slice B — the camera amount, and a window that remembers

Hand this whole file to Antigravity.

**Read `ANTIGRAVITY-RULES.md` first — its standing rules apply.**

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget`. **Do not commit. Do not push.**
**Baseline commit:** `d05586a`. **Baseline suite: 734 passed, 1 xfailed, 0 failures.** ~9 minutes.
Python: `C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe` (not on PATH).

---

## Where this actually stands

Everything below was read in the current tree, not remembered. Line numbers are from `d05586a`.

**The camera moves already work.** `pipeline/motion.py` holds four styles — Static, Gentle drift,
Ken Burns, Dynamic — each with `rate`, `min`, `max`, `pad` and an `effects` cycle.
`travel_for(style, duration)` returns `clamp(rate * seconds, min, max)`, which is what stops a
19-second hold from crawling and a 2-second cut from lurching. `assign_effects` alternates zoom and
pan across the whole film so no two consecutive shots repeat a move. None of this needs rebuilding.

**What is missing is the amount.** The dropdown at `frontend/index.html:128` (`id="pt-motion"`,
populated from `get_motion_styles`, `app.py:595`) picks a style and nothing scales it. "Ken Burns,
but less" is not currently sayable.

### Four things to know before you start

**1. `pad` is a hard constraint, not a preference.** `motion.py`'s own docstring says it: zoompan
crops out of the padded frame, so `1 + travel` must stay inside `pad`. Dynamic's max travel is 0.34
against a pad of 1.36; Ken Burns' 0.24 against 1.25. **An amount that only scales travel *down* is
always safe. An amount above 100% walks the crop off the edge of the picture.** This is why the
slider is capped at 100% in Job 1 — do not "improve" it to 150%.

**2. The shot cache key must be bumped, or this slice will look like it does nothing.**
`_get_shot_cache_key` (`pipeline/composer.py:303`) currently hashes `v9|...|{style_key}`. The style
name is in the key; an amount is not. Change the amount, and every clip renders from cache at the
old travel — the slider moves and the film does not. **Bump `v9` to `v10`, add the amount to the
hashed string, and add a comment line to the version list the way v2–v9 each did.**
`ANTIGRAVITY-RULES.md` calls this out as a standing rule.

**3. One existing test will legitimately fail, and it must not be quietly weakened.**
`tests/test_motion.py:104`, `test_a_picture_held_for_minutes_barely_moves`, asserts:

```python
ceiling = MOTION_STYLES["ken_burns"]["max"]
assert travel_for("ken_burns", 600.0) == ceiling
```

It compares against the **raw** profile max. If the default amount is anything below 100%, this
fails — correctly, because the ceiling has genuinely moved. The test's intent is "the clamp still
holds over long durations", and that intent survives. **Update it to assert the clamp at the amount
in force, quote it before and after in your report, and justify it in one sentence.** Do not delete
it, do not loosen it to `<=`, and do not set the default to 100% to dodge it.

**4. The camera style is already not remembered, and nobody noticed.** `UI_FIELDS` in
`frontend/app.js:132` maps `motion_style: "pt-motion"`, so the Script screen dutifully sends the
choice to `save_ui_defaults`. But `UI_DEFAULT_KEYS` (`app.py:627`) is
`("voice", "series_slug", "tone", "visual_style", "visual_type", "captions_enabled",
"shot_rhythm_seconds", "image_count", "formats")` — no `motion_style`. The backend loops over that
tuple and silently drops anything not in it. The value is sent, accepted, and thrown away. Job 2.

---

## Job 1 — the camera amount

Add an **amount** that scales the chosen style, expressed as a percentage.

- `travel_for` takes a new optional `amount` argument, defaulted so existing callers are unchanged
  in behaviour. Scale `rate`, `min` and `max` by it, then clamp as now. Order matters: scaling
  after the clamp would let a long shot exceed the scaled ceiling.
- `pad_factor_for` keeps returning the profile's `pad`. It is already large enough for any amount
  at or below 100%, and test 2 below is what proves that stays true.
- Range **0–100%**, step 5. **Default 60%**, which is the "reduce the default travel" the plan
  asked for. That number is a taste call on the owner's film, not a fact — render with it, look at
  it, and if 60 is wrong say what you would set it to and why. Do not change it silently.
- Static at any amount is still perfectly still. 0% on any style is a held frame.

**Where the control lives.** Put it directly under the Camera motion dropdown on the Script screen
(`frontend/index.html:127-134`), as a range input with a live value readout. The plan said
Settings; an amount that sits on a different screen from the style it scales is two trips for one
decision, and the `<p class="hint">` at `:134` already explains travel right there. **If you think
Settings is right after building it, say so in the report rather than moving it.**

**Where the value lives.** `motion_style` is a project field, read by `motion.style_of` from
`project.motion_style`. Follow that exactly: write `project.motion_amount` at plan time so a
rendered film stays reproducible, and thread it to `_get_shot_cache_key` alongside `motion_style`.

**Layout goes in `frontend/style.css`.** Inline `style="` in `index.html` is at **15** and capped at
19. A slider does not need one.

## Job 2 — make the camera choice actually stick

Add `motion_style` and `motion_amount` to `UI_DEFAULT_KEYS` in `app.py:627`, so the value the
frontend has been sending all along is stored and restored. Confirm the dropdown and the slider
both come back after a restart. This is three lines and a test; it is in this slice because the
amount is worthless if it resets on every launch, and the same bug is why the style does.

## Job 3 — the window remembers itself

`app.py:2048` hardcodes `width=1000, height=900, min_size=(900, 750)`. Every launch is that size,
wherever you left it.

Verified on the installed **pywebview 6.2.1**:

- `window.events` exposes `resized`, `moved`, `closing`, `closed`, `maximized`, `minimized`,
  `restored`. All of those are available to you.
- **`window.width` / `.height` / `.x` / `.y` are not readable on an unstarted window** — I probed a
  created-but-not-shown window and all four came back absent. Do not build persistence on reading
  them at exit and then discover this at runtime. Track geometry from the `resized` and `moved`
  **event payloads**, which carry the values. If you find the attributes readable on a *running*
  window, use them and say so in the report — but verify before relying on it.

- Persist to `config/settings.json` under its own key, next to `ui_defaults`, through the existing
  `_save_settings`. **That file is gitignored and holds live API keys — never print it, never
  commit it, never paste its contents into your report.**
- Restore at `create_window`. **Validate before applying:** a window restored to a monitor that is
  no longer attached is unreachable, and the app simply looks broken. Clamp to the current virtual
  screen and fall back to 1000 × 900 when the stored geometry does not fit. Never restore a size
  below `min_size`.
- Save on `closing`. Do not write on every `resized` event — one drag fires dozens.
- Add a **Reset window size** control in Settings (`data-pane="settings"`, `index.html:554`) that
  clears the stored geometry and resizes the running window back to 1000 × 900. This is the
  recovery route for when it does end up somewhere useless.
- Maximised is a state, not a size. Storing a maximised window's geometry as its size restores
  wrong. Either record the maximised flag separately or store the pre-maximise geometry.

---

## Tests

`tests/test_motion.py` and `tests/test_motion_style.py` already exist. Extend them; do not start a
third motion file.

1. **The clamp holds at every amount.** `travel_for(style, 600.0)` never exceeds `max * amount`,
   for all four styles across the slider range.
2. **The pad invariant.** For every style and every amount 0–100 in steps of 5:
   `1 + travel_for(style, duration) <= pad_factor_for(style)`, sampled across short and long
   durations. This is the test that makes the 100% cap safe rather than merely intended.
3. **The amount actually scales.** Ken Burns at 50% travels half as far as at 100% at the same
   duration, and 0% travels zero on every style.
4. **The cache key changes with the amount.** Same shot, same duration, same style, two different
   amounts — two different keys. Assert the keys *differ*; a test that only checks the key is a
   16-character hex string cannot fail.
5. **Existing callers are unchanged.** Calling `travel_for` without an amount returns exactly what
   it returns today, so nothing that does not opt in shifts.
6. **The camera choice round-trips.** `save_ui_defaults({"motion_style": ..., "motion_amount": ...})`
   then `get_ui_defaults()` returns both. Point the settings store at a temp path — do not write to
   the real `config/settings.json`.
7. **Window geometry is validated, not trusted.** Feed the restore path an offscreen rectangle
   (negative coordinates, and a position beyond the virtual screen) and a below-minimum size, and
   assert it falls back rather than applying them. Test the pure geometry function directly; do not
   open a window in the suite.
8. **`tests/test_frontend_controls.py`** asserts every button calls a function that exists. The
   Reset window size button must pass it.

Rule 4 in `ANTIGRAVITY-RULES.md` applies throughout: **break each test on purpose and confirm it
fails.** Slice F shipped a fade test that ran a hand-written ffmpeg string through ffmpeg and would
have passed against no implementation at all. That is the shape to avoid.

One more from Slice F, worth stating plainly: **a helper you call must be a helper you wrote.**
Slice F called `persistCurrentScript` from seven places and never defined it, so every music and
sound-effect edit died on a ReferenceError while the suite stayed green — the frontend test only
checks `onclick` targets, not functions called from inside other functions. If you add a helper for
the slider or the window reset, prove it exists.

---

## Acceptance

Paste real output, not a description of it.

1. **Full suite green.** Expect **734 + your new tests, 1 xfailed, 0 failures.** Do not run it while
   anything else heavy is running — `test_parallel.py` does a real render and fails when starved of
   CPU.

2. **Render the same shot at three amounts** — 0%, 60%, 100% — and report the measured travel for
   each. Numbers, from `travel_for`, plus confirmation that the three renders are actually different
   files. If they are identical, the cache key is not bumped.

3. **On the owner's film**, `projects/Before_Adam_The_Story_of_Iblis`: set the amount to 60%, render
   a short section, and say whether the move reads as too much, too little, or right. This is the
   only evidence that "reduce the default travel" was reduced to the right place.

4. **Restart the app twice.** Move and resize the window, close it, reopen it, and confirm it comes
   back where you left it. Then set the amount and the style, restart, and confirm both came back.

5. **Drag the window mostly off the bottom of the screen, close, reopen.** It must come back usable.
   Say what it did.

6. **Confirm CRLF.** Every file you touched must have 0 bare LF line endings.

Name anything you skipped. Silence is not a report.

## Out of scope

Do not touch: the effect cycle in `assign_effects` (it works, and which move follows which is not a
per-shot decision), `pipeline/sound.py` and ambient beds, the Slice F music and SFX lanes, picture
boundaries and the Slice E drag, the Timeline's playback, and the Phosphor icons.

**Do not build per-shot camera overrides.** One amount for the film is this slice. A per-shot camera
is a different product decision the owner has not made.

---

**Stop when the report is written. Do not commit. Do not push.**
