# Brief: Slice I — Timeline NLE Keyboard Transport, Shuttle Controls & 3-Stage Navigation

Hand this whole file to Antigravity.

**Read `ANTIGRAVITY-RULES.md` first — its standing rules apply.**

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget`. **Do not commit. Do not push.**
**Baseline: 1265 passed, 1 xfailed, 0 failures.** Roughly 11 minutes.
Python: `C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe` (not on PATH).
Prefix anything printing prompt text with `PYTHONIOENCODING=utf-8`.

---

## Where this sits in Milestone 3

Milestone 2 concluded the core audio/visual synchronization engine: effects fire on the clock, music fades honestly, captions light up in real time, and timeline layout is stable.

Milestone 3 is **Visual & Interactive Polish**. Its goal is to make Smart Studio feel like a responsive, professional editing suite.

Slice I delivers the **NLE Keyboard Transport, Shuttle Controls & 3-Stage Navigation**. It gives the user instant keyboard control over playback, nudging, clip stepping, and screen switching without hunting for buttons.

---

## What is actually true today

1. **Spacebar playback toggle exists** in `document.addEventListener('keydown')` (~L3949) for `.pane[data-pane="timeline"][data-on="1"]`.
2. `Escape` cancels clip drag; `Delete`/`Backspace` deletes selected SFX.
3. Arrow keys currently only work on slider handles (`timelineHandleKeyDown`), not globally on the timeline playhead.
4. No keyboard shuttle (J/K/L) exists.
5. No quick stage switching (1: Script, 2: Storyboard, 3: Timeline) exists.
6. `openTimelineFromBoard` (~L4180) switches pane and renders, but does not focus the timeline for immediate keyboard control.
7. Transport controls have tooltips, but there is no keyboard shortcuts HUD indicator.

---

## Job 1 — NLE Keyboard Transport & Shuttle Controls

In `frontend/app.js`, enhance the global `keydown` event listener (~L3949):

- **Strict Input Guard:** If `document.activeElement` is an `INPUT`, `TEXTAREA`, `SELECT`, or has `isContentEditable`, do not intercept any shortcuts (keep existing `isInput` guard).
- **Stage Navigation (Global when not in an input):**
  - Key `'1'`: Switch to Script screen (`switchPane('script')`).
  - Key `'2'`: Switch to Storyboard screen (`switchPane('board')`).
  - Key `'3'`: Switch to Timeline screen (`switchPane('timeline')`).
- **Timeline Transport & Shuttle (When Timeline pane is active, `data-pane="timeline"` and `data-on="1"`):**
  - `Space` / `' '`: Toggle play/pause (`timelineTogglePlay()`).
  - `ArrowLeft`: Nudge playhead backward 1s (`timelineNudge(-1)`). If `e.shiftKey` is held: nudge backward 5s (`timelineNudge(-5)`).
  - `ArrowRight`: Nudge playhead forward 1s (`timelineNudge(1)`). If `e.shiftKey` is held: nudge forward 5s (`timelineNudge(5)`).
  - `ArrowUp`: Step to previous picture clip (`timelineSeekPicture(-1)`).
  - `ArrowDown`: Step to next picture clip (`timelineSeekPicture(1)`).
  - `Home`: Jump playhead to start of film (`timelineSeek(0)`).
  - `End`: Jump playhead to end of film (`timelineSeek(total)`).
  - `j` / `J`: Step / shuttle backward 2s (`timelineNudge(-2)`).
  - `k` / `K`: Pause playback (`timelinePauseAudio()`).
  - `l` / `L`: Play / toggle playback (`timelineTogglePlay()`).
- Prevent default browser behaviors (`e.preventDefault()`) on handled shortcut keys.

---

## Job 2 — Storyboard-to-Timeline 1-Click Hand-Off

In `frontend/app.js`:
- In `openTimelineFromBoard()`:
  - Switch pane to `'timeline'`.
  - Call `renderTimelineScreen()`.
  - Automatically set focus on the timeline scroll container (`#tl-scroll` or `#tl-lanes`) so keyboard shortcuts respond immediately without requiring a preliminary mouse click.

---

## Job 3 — Discoverable Keyboard Shortcuts HUD

- In `frontend/index.html`:
  - Add a `.tl-shortcuts-hint` badge inside `.tl-transport`.
  - Maintain strict inline style budget: **inline `style="` count must remain <= 19** (currently 15). Zero inline styles added.
- In `frontend/style.css`:
  - Style `.tl-shortcuts-hint` with subtle, readable, brass-accented styling matching the NLE design aesthetic.

---

## Job 4 — Contract Tests & Verification

- Author `tests/test_timeline_keyboard.py`:
  - Test nudge arithmetic (+/-1s, +/-5s, -2s).
  - Test bounds clamping (playhead clamped to [0, total]).
  - Test picture clip stepping clamping.
  - Test input focus guard.
  - Test stage navigation mappings.
  - Test static code structure in `frontend/app.js` and `frontend/index.html`.
  - Test inline style budget ratchet (<= 19).
- Run Rule 4 deliberate break mutations to verify tests fail when logic is missing.
- Verify full test suite passes.
