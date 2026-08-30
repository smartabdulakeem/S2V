# Brief: make the manual image route actually land

Hand this whole file to Antigravity. **Do this before the provider work** — it needs no API key and
it is the owner's main workflow.

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget` — stay on it. **Commit** when done. **Do not push.**
**Never** run `git add -A` — it stages ~816 MB including two 310 MB ONNX models.
**Never** run `git checkout -- library/index.npz`. If it shows as modified, **commit it**.

---

## The workflow being supported

1. He pastes a script.
2. The app writes one image prompt per **picture the film actually needs**.
3. He takes those prompts to an external image tool and generates the pictures.
4. He drops them in a folder, numbered.
5. The app places each picture at the right moment, for the right length of time.

Steps 1, 4 and 5 work. **Steps 2 and 3 are broken**, and the breakage is silent.

---

## Job 1 — prompts bind to the wrong shots the moment images are shared

This is the bug. Everything else in this brief is smaller.

A 3,000-word script asks for ~200 images. The owner reduces that on the board, and
`plan_image_budget()` takes **Case B**: segments are merged into runs, one image per run, and every
other shot in the run carries `share_with` pointing at the run's first shot. Those shots do not get
their own picture.

`apply_external_prompts()` in `pipeline/library.py` (~1281) does not know that:

```python
all_shots = []
for seg in (script_data.get("segments") or []):
    for shot in (seg.get("shots") or []):
        all_shots.append(shot)          # every shot, shared ones included
...
for i in range(count_to_bind):
    all_shots[i]["prompt_override"] = prompts[i]
```

**Measured on 60 segments of his own script, asking for 12 images:**

```
12 distinct images, 60 total shots, 48 of them sharing
pasted 12 prompts -> bound to shots 0..11
   10 of those 12 shots are SHARED shots — the prompt is ignored
   10 of the 12 real images received no prompt at all
   only 2 of 12 prompts landed on a picture that gets made
```

**Fix:** bind prompts to the shots that actually own a picture — those **without** `share_with` —
in film order. The same list must drive the numbered folder matching, so prompt *n*, image `n.jpg`
and the *n*th picture in the film are the same thing.

Apply this to `apply_external_prompts()` and to `match_folder_images_by_slot()` together. They must
agree on what "slot *n*" means, or the mismatch simply moves.

## Job 2 — the exported prompts must match, one per picture

`initialize_project_sourcing()` in `pipeline/visuals.py` (~939) writes `image_prompts.txt`, the file
this whole route depends on. Today it emits **one line per segment**, so a 200-segment script
reduced to 40 images produces 200 prompts for 40 pictures — and the numbering means nothing.

It must emit **one line per distinct image**, numbered from 1, in film order, matching Job 1's list
exactly. `1.jpg` comes back to prompt 1.

Two more faults in the same file, both visible in his current export:

```
Segment 1: Adam ever walked, cinematic medium shot, subject filling much of the frame, ...
Segment 2: Adam ever walked, cinematic medium shot, subject filling much of the frame, ...
Segment 3: according reports corruption, cinematic medium shot, subject filling much of the frame, ...
```

1. **Every line carries the same framing.** `compose_gap_prompt` is called at `visuals.py` ~902
   **without `shot_position`**, so `default_framing_for(None)` returns cycle entry 0 every time. Pass
   the picture's index across the whole film so the four-entry cycle varies.
2. **The subject is `extract_keyword` output**, not the shot's `visual_description`. Prefer the
   description whenever there is one, as the composer already does.

## Job 3 — say what is going to happen, before it happens

The counts must be on screen before anything binds:

> This film needs **40 pictures** across 200 shots. You pasted **37 prompts**. Three pictures will
> fall back to library search.

Over-supply and under-supply both get named, with both numbers. Silence here is what let the
mismatch above go unnoticed.

---

## Job 4 — the timeline board

The owner wants the second board to work like a CapCut scene: play the narration, see which picture
sits where and for how long, remove or replace one, change the folder and have it re-pick.

**Scope this honestly and report before building it.** Most of the data already exists:

- **Durations are already real.** `resolve_shot_durations()` in `pipeline/validator.py` takes the
  segment's spoken audio length and divides it across that segment's shots. Nothing needs inventing.
- **The board already lists shots with thumbnails** (`.seglist`, `.seg`, `.thumb` in
  `frontend/style.css`), and already offers alternatives and pinning per shot.
- **The working-folder picker exists** on both screens, and re-picking is `refreshStoryboardCoverage()`.

What is genuinely missing is one pipeline change and one UI surface:

1. **Narration must be generated before the board, not at render.** Today the audio is made during
   the render. To play it on the board it has to exist earlier. This is the only real architectural
   change, and it costs TTS time up front.
2. **A timeline strip**: each picture as a block whose width is its real duration, a playhead
   following the audio, click to seek, and remove / replace / re-pick on a block.

**Do not build Job 4 in this pass.** Report what it would take — files, the audio-timing change, and
an honest estimate — so the owner can decide. Jobs 1 to 3 must land first and are worth having on
their own.

One thing worth saying plainly: a timeline would have made the Job 1 bug **visible immediately**.
Right now there is no screen anywhere that shows 48 shots sharing 12 pictures.

---

## Traps

1. **Do not weaken a test to make it pass.** The vignette limit was once raised from 0.40 to 0.45
   and reported as "passes cleanly". Every `tests/` diff is read. If an existing test must change,
   quote it before and after and justify it in one sentence.
2. **A pasted prompt must stay verbatim.** Nothing may be appended to `prompt_override` —
   `composed = override_prompt` at `library.py` ~2313 bypasses the composer, and that is the point.
3. **The shot cache key is `v9`** (`composer.py`). If what a shot renders can change, bump it.
4. **Do not work in a git worktree** — no gitignored assets, so render tests always fail there.
5. **A stale `cache/` causes phantom failures.**
6. **Inline `style="` in `index.html` is capped at 19**, all dynamic state. Layout goes in
   `style.css`.

## Tests

- With images shared, prompts bind **only** to shots without `share_with`, in film order.
- Prompt *n*, `n.jpg` and the *n*th picture in the film are the same shot — asserted together.
- `image_prompts.txt` emits exactly one line per distinct image, numbered from 1.
- Its framing varies across the film instead of repeating one phrase.
- It uses `visual_description` when present.
- More prompts than pictures, and fewer, both report the true counts and bind what they can.
- A pasted prompt reaches the image model **unchanged**.
- The measured case above is a regression test: 60 segments, 12 images, 12 prompts, all 12 landing
  on shots that own a picture.

## What to report

1. `image_prompts.txt` before and after, first eight lines of each, pasted.
2. The 60-segment / 12-image case: which shot each prompt bound to, and confirmation that none
   landed on a shared shot.
3. The on-screen count message, pasted.
4. For Job 4: what it would take, and what you did **not** do.
5. The full suite count. Baseline: **462 passed, 1 xfailed, 0 failures**.
6. Whether `library/index.npz` shows as modified, and confirmation you did not restore it.
