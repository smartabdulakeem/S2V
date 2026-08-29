# Brief: let the owner control how images are described

Hand this whole file to Antigravity. Everything it needs is here.

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget` — stay on it. **Commit** when done (instructions at the end).
**Do not push.** Pushing is the owner's decision, not yours.
**Never** run `git add -A` — it stages ~816 MB including two 310 MB ONNX models.

**Test baseline before you start: `409 passed, 1 xfailed`.** Any other failure is yours.

---

## The problem

Two jobs, in this order. The first is a bug; the second is the feature the first makes possible.

### Job 1 — the prompt contradicts itself

Every series pack has one `style_block` that mixes three different kinds of instruction. From
`config/series/islamic_history.json`:

```
"Shot on 35mm film, cinematic documentary photography, natural directional light,
 shallow depth of field,                                    ← medium: how it is photographed
 muted earth palette of ochre sand, dust grey and deep indigo shadow, fine film grain,
                                                            ← palette: what it looks like
 historically accurate 7th century Arabian Peninsula, early Islamic era."
                                                            ← era: when and where it is
```

That whole blob is appended to **every** prompt in the film. Real prompts produced by the app,
from `projects/there_was_no_human_being/image_prompts.txt`:

> "Swirling nebulae glow in the vastness of space above a newly forming planet … **historically
> accurate 7th century Arabian Peninsula, early Islamic era.**"

> "Strange, winged creatures with shimmering scales soar through a misty canyon … **historically
> accurate 7th century Arabian Peninsula, early Islamic era.**"

The image model is told to render deep space *and* 7th-century Arabia in one picture. Diffusion
models resolve contradictions by producing mush. This is a real cause of "the images look poor".

### Job 2 — nothing lets the owner fix it himself

There is no way to edit how a niche describes its images, and no way to override one stubborn
shot. Every look is baked into pack JSON that ships with the app.

---

## Environment

Python is NOT on PATH:
`C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe`

Prefix anything that prints prompt text with `PYTHONIOENCODING=utf-8` — the Windows console dies
on `₦` and `—`, which looks like an engine failure but is not.

Run the app with `run.bat`. Check JS with `node --check frontend/app.js`.
Full suite ~7 minutes.

---

## Job 1: split the style block into three

Add three optional fields to every pack in `config/series/*.json`:

| Field | Holds | Example (islamic_history) |
|---|---|---|
| `medium_block` | How it is photographed | "Shot on 35mm film, cinematic documentary photography, natural directional light, shallow depth of field" |
| `palette_block` | Colour and grain | "muted earth palette of ochre sand, dust grey and deep indigo shadow, fine film grain" |
| `era_block` | When and where | "historically accurate 7th century Arabian Peninsula, early Islamic era" |

Rules:

1. **Keep `style_block` working.** Packs that have not been split must behave exactly as now.
   When the three new fields are absent, fall back to `style_block` unchanged. `validate_series_pack()`
   may reject unknown keys — check it and update it if so.
2. Split all ten packs. Some are contemporary (`motivational` is "contemporary, no fixed period
   or place") and should get an **empty** `era_block`, not an invented one.
3. In `compose_gap_prompt` (`pipeline/library.py`), the era goes **last** and must be omittable.
4. Add a project-level switch, `project.apply_era`, default **true**. When false, `era_block` is
   left out. This is what lets a cosmology episode run inside a history niche.
5. Surface that switch in the UI as a checkbox beside the existing brief box (`#pt-brief` in
   `frontend/index.html`), labelled something like "Apply the niche's period to every image".

**Do NOT attempt to detect the contradiction automatically.** Guessing whether "swirling nebulae"
belongs in 7th-century Arabia is unreliable and will fail in both directions. The owner decides
with the switch. That is the whole point of the feature.

---

## Job 2: the editor

### 2a. Per-niche editing, in Settings

A new Settings card, "Visual style per niche":

- a dropdown listing the ten niches
- editable text areas for `medium_block`, `palette_block`, `era_block`, `negative_block`
- **Save** and **Reset to default** buttons
- a live preview of a composed prompt using the current values, so the owner sees the effect
  before rendering anything

**Where edits are stored — this part matters.**

Write to `config/series_overrides/<slug>.json`, holding **only the keys the owner changed**.
`get_series_config()` (`pipeline/library.py:183`) loads the pack and then merges the override over
it, override winning per key. "Reset to default" deletes the override file.

**Never write to `config/series/*.json`.** Those ship with the app. Editing them in place means an
update either destroys the owner's work or cannot be applied at all. The override file is what
makes both possible.

Add `config/series_overrides/` to `.gitignore` — it is the user's data, like `config/settings.json`
which is already ignored.

### 2b. Per-shot override, on the board

- An "Edit prompt" control on each shot in the storyboard, revealing a textarea.
- Stored as `shot["prompt_override"]`.
- When non-empty it **replaces** the composed prompt entirely — no merging, no appending. The
  owner typed exactly what they want.
- Show the composed prompt as the textarea's placeholder so they have something to edit from
  rather than a blank box.

**Plumbing:** `fetch_visual` (`pipeline/visuals.py`) composes the prompt for generation. It already
receives `visual_description` from the orchestrator via
`(seg.get("shots") and seg["shots"][0].get("visual_description"))` — take `prompt_override` the
same way, and bypass `compose_gap_prompt` when it is set.

---

## Traps

1. **Cache keys, twice.** An edited prompt that renders the old picture looks like the feature is
   broken. The override must reach **both** the generated-image cache in `pipeline/visuals.py`
   **and** the shot-clip key `_get_shot_cache_key` in `pipeline/composer.py`, currently **`v5`** —
   bump it to `v6`.
2. **`compose_gap_prompt` has several call sites** across `library.py` and `visuals.py`. Grep for
   every one; a signature change that misses one fails only at render time.
3. **`visual_style` is prose, `visual_type` is a key.** `#pt-style` holds the key; the board sends
   the *label* as `visual_style`. Sending the key leaks it into prompts as a world anchor.
4. **Setting `.value` in JS fires no `change` event.** Restore the niche, `await loadStylePresets()`,
   *then* restore dependent dropdowns, or they desync silently.
5. **`renderVoiceCatalogueSettings()` rebuilds its container on every toggle** — if you follow the
   Settings card pattern, an open section must survive a re-render.
6. **A stale `cache/` causes phantom test failures.** If `test_parallel.py` fails with "Segment
   composition failed" for no code reason, delete `cache/`.
7. **A git worktree has no gitignored assets** (`vendor/ffmpeg`, `library/images`), so render tests
   always fail there. Work in the main tree.

---

## What "done" looks like

The owner verifies everything. Report so he can check without redoing the work.

- **Print real prompts, before and after**, for the same shot in `islamic_history`: one in-era
  scene and one out-of-era scene (a nebula). Show that `apply_era: false` removes the period text
  and nothing else.
- **Show a per-shot override reaching the picture** — set one, render that shot, confirm the image
  changed and the cache did not serve the old one.
- **Show an override surviving.** Edit a niche, save, restart the app, confirm the edit is still
  there and `config/series/*.json` is untouched (`git status` proves it).
- State plainly anything you did not do, and why.

Finish with the full suite:

```
PYTHONIOENCODING=utf-8 <python> -m pytest tests/ -q
```

Baseline is **409 passed, 1 xfailed**. Add tests for: the three-way split falling back to
`style_block`, `apply_era` omitting the era, an override beating the pack, and a per-shot override
replacing the composed prompt.

---

## Committing

Commit when the suite is green. **Commit is local — it does not touch GitHub.** Do not push.

Stage explicit paths only:

```
git add config/series pipeline/library.py pipeline/visuals.py pipeline/composer.py \
        frontend/index.html frontend/app.js app.py .gitignore tests/
git commit
```

Two commits, in this order, so the bug fix can be read apart from the feature:

1. the style-block split and the `apply_era` switch
2. the per-niche and per-shot editors

Write the message the way the repo does: a short summary line, then what was wrong and what the
measurement showed. Look at `git log` for the shape.
