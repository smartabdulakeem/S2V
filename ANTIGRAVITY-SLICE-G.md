# Brief: Slice G — the Timeline tells the truth about what the film sounds like

Hand this whole file to Antigravity.

**Read `ANTIGRAVITY-RULES.md` first — its standing rules apply.**

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget`. **Do not commit. Do not push.**
**Baseline: 1249 passed, 1 xfailed, 0 failures.** Roughly 9 minutes. HEAD is `12e6d9b`.
Python: `C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe` (not on PATH).
Prefix anything printing prompt text with `PYTHONIOENCODING=utf-8`.

---

## Where this sits in Milestone 2

Milestone 2 is **Timeline Live Playback & Audio Sync**. Slice D built playback, the media-server
fix made it work inside WebView2, and Slice F added the Music and Sound effects lanes.

What is left is the *sync* half, and it is all one complaint: **the Timeline plays a different
film from the one that renders.** Three specific ways, all verified in the code below.

After this slice, Milestone 2 has one plausible slice left (caption lane timing and
picture-change accuracy against the audio). If Slice G lands clean and those turn out to be
already correct, the milestone is done and the relay stops for the owner.

---

## What already works — do not rebuild or "fix" these

Read them before writing anything.

| What | Where | Status |
|---|---|---|
| One concatenated narration mp3 driving the playhead | `pipeline/timeline_audio.py`, `frontend/app.js` `tlAnimLoop` (~L2479) | Correct. `audio.currentTime` **is** the playhead. |
| Media over localhost, range requests, WebView2-safe | `media_server.py` | Correct. Use it for every new sound. |
| Music element pauses and resumes with narration | `initTimelineAudio` (~L2514) | Correct. |
| Film time ⇄ segment + `offset_ms`, both directions | `filmTimeToSfx` (~L2891), `sfxToFilmTime` (~L2920) | Correct, and tested. **Reuse them. Do not write a third conversion.** |
| One-shot SFX audition in the modal and inspector | `sfxAuditionAudio` (~L4528) | Correct for auditioning. Not a scheduler. |

**In particular, `timelineSeek` at L2798 is already right.** The music seek is guarded by
`(!opts || !opts.fromAudio)`, so it does *not* reassign `mAudio.currentTime` on every animation
frame during playback. That guard is load-bearing. Do not remove it, and do not "fix" a stutter
bug there — there isn't one.

---

## The three defects

### 1. Sound effects are silent during playback

Slice F placed effects on a lane, drew them, dragged them, saved them — and deliberately did not
play them. Its brief said so plainly, and invited disagreement: *"If you disagree after building
the rest, say so in your report rather than building it anyway."*

This slice is that disagreement, from the owner. The whole reason the Timeline exists is to press
play and judge the film without a nine-minute render. An effects lane you cannot hear fails that
on its own terms, and the milestone is literally named *Audio Sync*.

`composer._overlay_sound_effects` mixes each effect with `adelay` at `offset_ms` from **its own
segment's** start. The preview must fire the same effect at the same film time.

### 2. Music fades exist in the render and are a lie in the preview

`pipeline/stitcher.py:24-28` applies real `afade` in and out:

```
afade=t=in:st=0:d={music_fade_in}
afade=t=out:st={film_duration - music_fade_out}:d={music_fade_out}
```

The preview sets a **flat** volume from dB at three sites — `frontend/app.js:2389`, `:2403`,
`:3264` — and never touches it again:

```js
musicAudio.volume = Math.min(1.0, Math.max(0.0, Math.pow(10, db / 20)));
```

The lane block even prints `· in 3s, out 4s` in its title (L2713-2715). So the UI tells the owner
there is a fade, and the preview does not have one. That is the same class of defect as the fake
Sounds tab that Slice F deleted: the screen asserting something the product does not do.

### 3. Music drifts away from the narration over a long film

The music element is seeked once on `play` (L2433) and then free-runs, looped, for the length of
the film. Two independent `HTMLMediaElement` clocks do not stay together for eighteen minutes.
Nothing resyncs it. On the owner's 347-line film this is minutes of playback, and the drift is
cumulative and unbounded.

---

## Job 1 — Sound effects fire during playback

Build the scheduler in `frontend/app.js`.

**Design, so this is not over- or under-built.** Use a small pool of preloaded
`HTMLAudioElement`s keyed by filename, fired from the **existing** `tlAnimLoop`. Do not add a
second rAF loop, and do not reach for the Web Audio API. Web Audio buys roughly 1 ms scheduling
accuracy against rAF's ~16 ms, and costs a decode-and-buffer rewrite of a working audio path. For
sound effects in a documentary, 16 ms is inaudible. If you find a case where it is not, say so in
the report rather than rewriting the audio path on your own authority.

Requirements:

- **Build the schedule once**, when playback starts or the effects change: a flat list of
  `{filmTime, name, src}` sorted by `filmTime`, derived with the existing `sfxToFilmTime`.
  Do not recompute per frame.
- **Fire on crossing.** Each frame, play every effect whose `filmTime` falls between the previous
  frame's playhead and this one. Keep a cursor into the sorted list; do not scan it every frame.
- **Seeking must not machine-gun.** Scrubbing from 0:00 to 12:00 crosses two hundred effects and
  must fire **none** of them. On any seek, reset the cursor to the new position without firing.
  This is the bug that will happen if the crossing test is written carelessly.
- **Pause stops effects in flight.** A two-second effect fired at 4:59 does not keep playing after
  pause at 5:00.
- **Preload through the media server.** Resolve each distinct filename once via the same path the
  audition uses, not once per fire. An effect used forty times loads once.
- **Volume.** Effects play at full level, which is what `_overlay_sound_effects` does — it mixes
  without attenuation. If that turns out to be too loud against narration, report it with a
  suggested default; do not invent a gain control this slice.

Delete the "effects are heard in the render" note Slice F added to the UI. It is no longer true.

## Job 2 — The music preview honours its own fades

Drive `musicAudio.volume` from the playhead instead of setting it once.

- One function: `musicGainAt(filmTime, totalSeconds, project) -> number`, pure, no DOM. It applies
  `music_volume_db` as the base level, ramps linearly from 0 across `music_fade_in` seconds at the
  start, and ramps to 0 across `music_fade_out` seconds at the end.
- Call it from `tlAnimLoop` and on seek. Setting `.volume` every frame is fine — it is a property
  assignment, not an allocation.
- **Linear is the deliberate choice.** ffmpeg's `afade` defaults to a triangular/linear curve, so
  linear is what the render does. Matching it matters more than sounding sophisticated.
- The three existing flat-volume sites should end up calling this one function with the current
  playhead, so there is exactly one place that knows what music level means.

## Job 3 — Music stays with the narration

Resync the music element against the narration clock during playback, with a deadband.

- In `tlAnimLoop`, compute where the music *should* be: `narrationTime % musicDuration`.
- If it is off by more than **0.25 s**, correct it. Below that, leave it alone.
- The deadband is the point. Assigning `currentTime` every frame is what causes audible stutter,
  which is exactly why the `fromAudio` guard at L2798 exists. Do not remove that guard to do this
  job — add the corrected resync inside the playback loop where the drift actually accumulates.
- Report the measured drift on the owner's film: how far the music had wandered after ten minutes
  before this fix, and after.

---

## Tests

Rule 4 in `ANTIGRAVITY-RULES.md` applies to every one of these: **break it on purpose and confirm
it fails.** A test that passes against the current code is not testing this slice.

Job 1:

1. **Schedule construction.** A script with effects in three different segments produces a sorted
   film-time list whose values round-trip through `filmTimeToSfx` unchanged.
2. **Crossing fires once.** Advancing the playhead across an effect fires it exactly once, not on
   every subsequent frame.
3. **Seeking fires nothing.** Jumping the playhead from before two hundred effects to after them
   fires zero. This is the machine-gun guard and it is the most important test in the slice.
4. **Pause stops effects in flight.**

Job 2:

5. `musicGainAt` at t=0 with a 2 s fade-in returns 0 (or near it); at t=1 returns about half the
   base gain; past the fade returns the base gain exactly.
6. With `music_fade_out=4` on a 100 s film, t=98 is about half base and t=100 is 0.
7. With both fades 0, the function returns the flat dB conversion at every time — the current
   behaviour, unchanged.

Job 3:

8. Given a narration time and a shorter looped music duration, the target music position is the
   modulo, and a delta under the deadband produces **no** correction.

`tests/test_frontend_controls.py` asserts every button calls a function that exists — extend it if
you add controls. Put the Node-run JS tests where `test_music_and_sfx.py` and
`test_narration_timing.py` already put theirs; do not invent a fourth pattern.

---

## Acceptance

**The verification gate in `RELAY-STATE.json` is `required_before_build` and was recorded as
`NOT_RUN` for Slice C. It was skipped, and that was noticed.** This slice is entirely about what
the owner hears. Open the live WebView2 window against `12e6d9b` and confirm playback works
*before* you change anything, and say in the report that you did.

Paste real output, not a description of it.

1. **Full suite green.** Expect **1249 + your new tests, 1 xfailed, 0 failures.** Do not run it
   while anything else heavy is running — `test_parallel.py` does a real render and starves.

2. **On the owner's film**, `projects/Before_Adam_The_Story_of_Iblis`:
   - Place two effects at known times, press play, and confirm you **hear both at those times**.
     Report the times and whether they landed where the lane drew them.
   - Scrub the playhead across the whole film at speed. Confirm no burst of effects. Say so.
   - Set a 3 s music fade-in, press play from 0:00, and say whether the music rises rather than
     starting at level.
   - Play ten minutes and report the music drift, before and after Job 3, in seconds.

3. **Say what it sounds like.** You are mixing audio. A green suite is not a film that sounds
   right. If effects are too loud against the narration, say so and say what you would change.

4. **Say whether the preview now matches the render.** Render a short section with music and one
   effect, listen to both, and answer plainly: does the Timeline now tell the truth? If it does
   not, name the remaining gap — that is the next slice.

Name anything you skipped. Silence is not a report.

## Out of scope

Do not touch: ambient beds or `pipeline/sound.py` matching (automatic, and it works), the narration
concat in `pipeline/timeline_audio.py`, picture boundaries and the Slice E drag, the camera slider,
voice selection, `library/index.npz`, or the Phosphor icons.

**Do not build:** ducking music under narration in the preview (the render does not duck either —
matching it is the goal), positioned music clips, multi-track mixing, a waveform display, or an
SFX gain control. Each is a product decision the owner has not made.

---

**Stop when the report is written. Do not commit. Do not push.**
