# Smart Studio — Image Prompt Work Handoff

**Last updated:** 26 Aug 2026 · **Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`

Paste this into a new chat to pick the work up cold.

---

## Environment

Python is **not** on PATH. Always the full path:

```
C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe
```

Prefix any command that prints a prompt with `PYTHONIOENCODING=utf-8` — the Windows console
dies on `₦` and `—`, which looks like an engine failure but is not.

Run the app with `run.bat`. Full test suite takes about 6 minutes.

**Current green baseline: `313 passed, 2 skipped, 1 xfailed`.** The 2 skips are
`test_composer.py` needing a cached segment; they are expected.

---

## Branch state

| Branch | What it is |
|---|---|
| `feat/niche-visual-type` | **All the work below. Not merged, not pushed.** |
| `rebuild/phase-0` | The owner's main working branch. Pushed to GitHub. Untouched by this work. |
| `main` | 41 commits behind `rebuild/phase-0`. Pushed. |

Remote is `https://github.com/smartabdulakeem/S2V.git`. To merge when the owner is happy:

```bash
git checkout rebuild/phase-0 && git merge feat/niche-visual-type
```

⚠️ **`git add -A` in this repo stages 816 MB** including two 310 MB ONNX models, unless the
`.gitignore` additions from `ANTIGRAVITY-PUSH-BRIEF.md` are present. They are, as of the last
push — but re-check before any bulk staging.

---

## What this work was

The visual style picked on the planning board changed **nothing** about the image prompt. Every
series pack defined a `style_presets` block and nothing had ever read it. Prompts also quoted
narration verbatim, cut it mid-phrase at 34 words, and printed the world anchor twice.

### Now working

- **55 niche-specific presets** across 10 packs, plus **6 universal looks** merged into every
  niche (photoreal, cinematic, black & white, stylised illustration, cartoon, 3D render).
  11 visual types per niche. A pack overrides a universal one by reusing the key.
- The picked type supplies the prompt's **medium text** *and* the **post-processing treatment**.
- Prompts are built from **eight named slots** (`pipeline/prompt_slots.py`): project brief,
  framing, subject, motion, ground, atmosphere, setting, medium. Narration is never quoted.
- A **`project_brief`** opens every prompt in one film so images generated across sessions
  belong together. Capped at 30 words, cut on a clause boundary.
- Measured: **84 words → 60**, anchor **2 → 1**, no truncation.

### Key files

| File | Role |
|---|---|
| `pipeline/prompt_slots.py` | The `(regex, phrase)` vocabulary tables. **This is the file to edit when prompt wording needs tuning.** |
| `pipeline/library.py` | `compose_gap_prompt`, `resolve_style_preset`, `style_presets_for`, `draft_project_brief`, `ensure_project_brief`, `cap_project_brief`, `UNIVERSAL_STYLE_PRESETS` |
| `pipeline/composer.py` | `treatment_for_style`, `resolve_default_treatment` |
| `config/series/*.json` | 10 packs. `style_presets`, `brief_subject`, `world_anchor`, calibration |
| `scripts/author_style_presets.py` | Rewrites all presets. Idempotent. |
| `scripts/author_brief_subjects.py` | Rewrites all `brief_subject` fields. Idempotent. |
| `docs/superpowers/specs/2026-08-26-niche-visual-type-design.md` | The design contract |
| `docs/superpowers/plans/2026-08-26-niche-visual-type.md` | The 11-task plan, all executed |

---

## Traps — do not regress these

1. **`visual_style` is prose, `visual_type` is a key.** `#pt-style` holds the snake_case key.
   `planStoryboard` sends the **label** as `visual_style` and the **key** as `visual_type`.
   Sending the key as `visual_style` leaks it into prompts as a world anchor —
   `"a case file on a desk, courtroom_sketch, deep night"`. `compose_gap_prompt` now rejects a
   bare snake_case anchor as a second line of defence.

2. **`world_anchor` is not a place.** In most packs it carries medium language
   ("… Matthew Brady tintype archival photograph"). Never open a prompt with it — that fights the
   picked visual type. `brief_subject` exists for that and carries subject only. The pack anchor
   defers to the brief; an **explicitly passed** `world_anchor` is always honoured.

3. **Setting `.value` in JS fires no `change` event.** `applyUiDefaults` must restore the niche,
   `await loadStylePresets()`, *then* restore `visual_type` — in that order, or the dropdowns
   desync and the whole feature silently falls back to `style_block`.

4. **`visual_type` means two different things.** In `pipeline/visuals.py` it is the image
   *source* (`"ai_image"` / `"stock_photo"`). The project's chosen look is threaded through as
   **`style_preset`**. Do not merge them.

5. **`compose_gap_prompt` has 8 call sites**, not 3 — three in `pipeline/library.py` and five in
   `pipeline/visuals.py`. Miss the `visuals.py` ones and the AI-image path emits a different
   prompt vocabulary from the copied sheet.

6. **The shot cache key is `v3` and includes the treatment.** Drop that and changing the visual
   type reuses the cached clip, so the picture never changes.

7. **Kokoro takes every core unless handed a configured session.** `kokoro-onnx` builds its own
   `InferenceSession` with no `SessionOptions`, so env vars and the `SessionOptions` monkeypatch
   never reach it. `_build_kokoro` in both `pipeline/voiceover.py` and `pipeline/voice_studio.py`
   uses `Kokoro.from_session` with `intra_op_num_threads=2`. Do not "simplify" it back.

8. **A stale `cache/` directory causes phantom test failures.** `test_parallel.py` failed with
   "Segment composition failed" for reasons unrelated to any code change; deleting the 2.2 GB
   `cache/` fixed it. Suspect this before suspecting a regression.

9. **A git worktree has no gitignored assets.** `vendor/ffmpeg` and `library/images` are ignored,
   so render tests always fail in a fresh worktree. That proves nothing — test the base branch in
   the main tree with a stash instead.

---

## Open items

### 1. Settings screen accordion — briefed, not started

The owner wants the Settings screen collapsed by default: each card, and each voice engine inside
the Voice catalogue, opening only when clicked. **The brief is written and ready to hand to
Antigravity: `ANTIGRAVITY-SETTINGS-ACCORDION.md`.** The one thing likely to bite is that
`renderVoiceCatalogueSettings()` rebuilds the container on every voice toggle, so an open engine
must survive the re-render.

### 2. Prompt vocabulary tuning

`pipeline/prompt_slots.py` handles literal language well and figurative language by exclusion
("a burning desire" no longer produces smoke). It is a heuristic and will keep needing entries.
Edit the tables; the tests in `tests/test_prompt_slots.py` cover both directions.

### 3. Known cosmetic limitation

`consistent depiction of Baghdad` — the brief counts recurring proper nouns and cannot tell a
person from a place or a title offline. Harmless, occasionally odd.

### 4. Printed-matter presets

`newsprint_profile`, `newspaper_archive`, `propaganda_poster` describe printed artefacts;
generators render illegible pseudo-text. Deliberate — cut the preset if it proves unusable rather
than weakening `negative_block`, which is off by default anyway.

### 5. Untouched from the older roadmap

ROADMAP C1 (the one-shot-per-segment floor giving 48 images in a 9.4-minute video) is unrelated
and still open. So is C3. `ROADMAP.md` is the tracked list.

---

## How the owner works

- Direct, no preamble. Lead with the answer.
- Show exact paths and literal commands. Windows, PowerShell + Git Bash.
- Confirm before anything destructive.
- **Verify, don't assume.** Generate real audio, print a real prompt, read it. This session
  declared the feature complete once while it was silently wrong end to end; a review caught nine
  defects, four of them severe, two of them errors in the spec rather than the code.
- Large or mechanical work goes to Antigravity with a written brief; the owner runs it and brings
  back the report for review. Tricky work stays here.
