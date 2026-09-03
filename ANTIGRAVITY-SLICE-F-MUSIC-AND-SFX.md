# Brief: Slice F — music and sound effects on the Timeline

Hand this whole file to Antigravity.

**Read `ANTIGRAVITY-RULES.md` first — its standing rules apply.**

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget`. **Do not commit. Do not push.**
**Baseline: 719 passed, 1 xfailed, 0 failures.** Roughly 9.5 minutes.
Python: `C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe` (not on PATH).

---

## Where this actually stands

The plan said Slice F was "mostly a UI over a working backend". Half of that is true, and the
other half needs saying before anyone builds on it.

**What genuinely works:** ambient beds. `pipeline/sound.py` is wired in at `composer.py:151`,
gated on `settings.json → ambient_beds`, matched on the query each sound was fetched with, and
ducked under the voice. Beds are automatic and are **not part of this slice.** Leave them alone.

**What is wired but has no controls:** `orchestrator.py:467` passes `sfx=seg.get("sfx")` and
`:511-512` pass `background_music` / `music_volume_db`. `grep -n "background_music\|sfx"
frontend/app.js` returns **nothing**. No screen has ever written these fields.

### Three defects, all verified

**1. The background music mix is wrong, and has never been used to find out.**
`pipeline/stitcher.py` builds this filter:

```
[1:a][2:a]amix=inputs=2:duration=first:dropout_transition=3,volume={factor}[aout]
```

The comma chains `volume` onto the **output of the mix**, so `music_volume_db = -20` turns the
narration down by 20 dB along with the music. The music does not sit under the voice — the whole
film just gets quiet. On top of that, `amix` defaults to `normalize=1`, which scales every input
by 1/n, dropping the narration a further ~6 dB. A 19-minute film mixed this way comes out around
26 dB down with the music at full level relative to the voice.

**2. The Library's Sounds tab is a mockup.** `frontend/index.html:394` reads
`0 images · 87 sounds · 12 music beds`; `:440` says *"87 sound effects and 12 ambient sound beds"*;
`:445-447` are three invented rows — *Desert Wind Ambience 3:45*, *Horses Galloping*, *Sword Clash
Heavy*. **The real library has 14 files.** All 14 are `category: "beds"`, all sit in
`library/sounds/_inbox`, and the longest is 37 seconds. This is the same fabrication as the
Spending panel that Slice A removed, and it is about to sit next to a feature that is real.

**3. There are no sound effects in the library at all.** Every manifest entry is a bed. An SFX lane
that only offers the library would be an empty lane, so **adding your own file is the primary
path**, not an afterthought.

---

## Job 1 — Fix the music mix

In `pipeline/stitcher.py`, apply the gain to the **music input** and stop `amix` normalising:

```
[2:a]volume={factor:.4f}[music];[1:a][music]amix=inputs=2:duration=first:dropout_transition=3:normalize=0[aout]
```

Then add fades, driven by two new project fields (both optional, both seconds, both default 0):
`music_fade_in` and `music_fade_out`. Use `afade` on the music input before the mix. A fade-out
needs the film's duration; take it from the master audio rather than guessing.

`stitch_segments` keeps its current signature plus the two new keyword arguments, defaulted, so
nothing that calls it today breaks.

## Job 2 — Music on the Timeline

A **Music** lane under Narration. One bed for the film — it already loops via `-stream_loop -1`,
and one looped bed is what a documentary uses. Positioned music clips are a later slice; do not
build a general clip model here.

- **Add music** opens a file dialog (`create_file_dialog` is already used in `app.py` — follow that
  pattern), copies the chosen file into `<project>/assets/music/`, and writes
  `project.background_music` as a path relative to the project.
- **Volume** in dB, −40 to 0, default −20, written to `project.music_volume_db`.
- **Fade in / fade out** in seconds, written to the two new fields.
- **Remove music** clears all four fields and leaves the copied file on disk.
- The lane draws one block across the whole film showing the file name and the level. It is not
  draggable — it has no start to move.

### It must be audible while you place it

Add a second `<audio>` element for the music, looped, its `volume` set from the dB value, started
and stopped with the narration element and seeked with it.

This preview is honest, and that is worth knowing: the render does **not** duck music under the
narration — `stitch_segments` plainly mixes the two. Only *beds* duck, in `sound.py`, and beds are
not in this lane. So music at −20 dB in the preview is music at −20 dB in the film.

Do not rebuild `timeline_narration.mp3`. It is narration and nothing else, and it stays that way.

## Job 3 — Sound effects on the Timeline

A **Sound effects** lane under Music.

The backend shape already exists and constrains this: `composer._overlay_sound_effects` reads
`seg["sfx"]` as a list of `{"name": <filename>, "offset_ms": <int>}`, resolves `name` against
`<project>/assets/sfx/` (adding `.wav` if there is no extension), and mixes with `adelay`.
**`offset_ms` is measured from the start of its own segment, not the start of the film.**

So the lane's whole job is that conversion:

- Adding an effect at the playhead means: find the segment under the playhead, work out how far
  into that segment the playhead sits, and append `{name, offset_ms}` to that segment's `sfx`.
  `tlLineAt` and `tlLineStartTime` in `frontend/app.js` already do both halves of that arithmetic.
  Do not write a third version.
- Drawing an effect means the reverse: segment start time plus `offset_ms`.

Put that conversion in **one function each way**, and test both directly. Everything else in this
job is drawing.

- **Add a sound** offers both a file dialog and the library list (Job 4 makes that list real).
  Either way the file is copied into `<project>/assets/sfx/` before the field is written, because
  that is the only place the compositor looks.
- **Select** an effect to see its name and its time.
- **Drag** it along the lane to re-time it. **Reuse the pointer pattern Slice E just built** —
  `pointerdown` with capture, `stopPropagation` so the lane does not scrub, preview in CSS, commit
  once on `pointerup`. Do not write a second drag implementation. Unlike a picture boundary, an
  effect is not snapped to lines: it moves in time, and crossing into another segment is allowed —
  it simply changes which segment owns it.
- **Delete** the selected effect.

**SFX are not previewed in the Timeline.** Scheduling many short files against a running clock is a
different problem from one looped bed, and getting it slightly wrong would teach the owner to
distrust the playhead. Say plainly in the UI that effects are heard in the render. If you disagree
after building the rest, say so in your report rather than building it anyway.

## Job 4 — Make the Sounds tab real

In the Library screen:

- Delete the hardcoded `87 sounds · 12 music beds` from `#lib-counts-label` and the invented
  sentence and three rows at `index.html:440-447`.
- Add an Api method that reads `library/sounds/manifest.jsonl` and returns the real entries.
  `pipeline/sound.py` already has `load_beds()`, which reads that manifest and drops entries whose
  file is missing — **use it** rather than parsing the file again.
- Render the real rows: name, the `query` it was fetched with, `duration`, `category`, and
  `licence_type`. The counts come from the data.
- Every entry carries `attribution`. Show it. These are CC0 and legally need nothing, but the
  owner is going to ship films made with them and should be able to see where a sound came from.

If the manifest is empty or missing, say the library is empty. Do not fall back to a number.

---

## Tests

**Job 1's fix needs a real test, not a string comparison alone.** Do both:

1. **The filter is built correctly.** Assert `volume=` is applied to the music input and not to the
   mix output, and that `normalize=0` is present. Break it on purpose and watch it fail.
2. **The narration survives the mix.** Generate a short tone as narration and another as music with
   ffmpeg, stitch with `music_volume_db=-20`, and measure the result with
   `ffmpeg -af volumedetect`. **The narration's level must land within about 1 dB of the same
   render with no music.** Against the current code this test fails by roughly 26 dB, which is the
   point of writing it.
3. **Fades.** `music_fade_in=2` produces a quieter first second than the same render without it.

**Job 3's conversion, both directions:**

4. Playhead at a known film time lands on the right segment with the right `offset_ms`.
5. A segment plus `offset_ms` draws at the right film time. Round-trip a few values and assert they
   come back unchanged.
6. Dragging an effect past a segment boundary moves it to the new segment and recomputes
   `offset_ms` against that segment's start — the film time it was dropped at is what is preserved.

**Job 4:**

7. The Sounds tab reads the manifest. Point it at a temp manifest with two entries and assert both
   appear and the count says two. Then assert `index.html` contains no `87` and no
   `Desert Wind Ambience` — that second assertion is what stops the mockup coming back.

`tests/test_frontend_controls.py` asserts every button calls a function that exists. Extend it to
the new controls.

Rule 4 in `ANTIGRAVITY-RULES.md` applies throughout: break each one on purpose and confirm it
fails. Test 2 in particular is worthless if it passes against the current stitcher.

---

## Acceptance

Paste real output, not a description of it.

1. **Full suite green.** Expect **719 + your new tests, 1 xfailed, 0 failures.** Do not run it
   while anything else heavy is running — `test_parallel.py` does a real render and fails when
   starved of CPU.

2. **Render a short film with music** and report the measured level of the narration with and
   without music. Numbers, from `volumedetect`. This is the evidence Job 1 is actually fixed.

3. **On the owner's film**, `projects/Before_Adam_The_Story_of_Iblis`:
   - Add a music bed, set it to −20 dB, press play, and say whether you can hear both the narration
     and the music at sensible levels.
   - Place a sound effect at a known time, save, reload the project, and confirm it came back at
     the same time. Report the `segment_id` and `offset_ms` that were written.
   - Drag that effect across a segment boundary and confirm its film time is unchanged.

4. **Screenshot the Library Sounds tab** showing real entries from the 14-file manifest.

5. **Say what the film sounds like.** You are mixing audio; a passing test is not the same as a
   film that sounds right. If the music is too loud at −20 dB, say so and say what you would change
   the default to.

Name anything you skipped. Silence is not a report.

## Out of scope

Do not touch: ambient beds or `pipeline/sound.py`'s matching (it works, and it is automatic),
picture boundaries and the Slice E drag, `pipeline/timeline_audio.py` and the narration track,
voice selection, the camera slider (Slice B), and the Phosphor icons.

**Do not build positioned music clips, multi-track mixing, or external video.** One looped bed and
placed effects is this slice. The rest is a different product decision the owner has not made.

Also noticed and **deliberately left**: the Library's Images tab had its own hardcoded values —
a Coverage card reading strong/strong/thin/thin and `Retired 6`. Same class of fake as the Sounds
tab. **Since handled separately** — the Coverage card is gone (no image in the library carries a
category, so there was nothing to compute) and Retired now counts `library/_retired/`. Still yours
in this slice: `lib-counts-label` at the top of the Library screen and the whole Sounds tab.

---

**Stop when the report is written. Do not commit. Do not push.**
