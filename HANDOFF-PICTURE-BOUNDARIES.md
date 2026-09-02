# Handoff — Smart Studio, 2 Sep 2026

Paste this whole file into a new chat to pick the work up cold. It replaces the earlier
handoff of the same name.

## Which document goes where

| Document | Who reads it |
|---|---|
| **This file** | **The new Claude chat.** The owner pastes it in, and it is the only thing he pastes. |
| `docs/superpowers/plans/2026-09-01-model-chosen-picture-boundaries.md` | **Claude, from disk.** 80 KB. Never ask the owner to paste it. |
| `STITCH-BRIEF-SMART-STUDIO.md` | The design brief that produced the Stitch mockups. |
| `TASK-N-FOR-ANTIGRAVITY.md` | Antigravity, one task at a time. Tasks 1–10 are done. |

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget` — **many commits ahead of origin, nothing pushed. Do not push.**
**Python:** `C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe` (not on PATH).
Prefix anything printing prompt text with `PYTHONIOENCODING=utf-8`.
**Suite: ~660 tests, 8–10 minutes.** Last full run: **615 passed, 1 xfailed, 0 failed**, before
the last four prompt commits (which added ~45 tests, all green in their own files).

**Gemini works.** `google_api_key` is set and answering on `gemini-2.5-flash`. Anthropic and
OpenAI keys were dead (401) and have been **cleared** — backup at
`config/settings.backup-20260902-010212.json`. DeepSeek is configured but never reached.
Provider chain: anthropic → openai → gemini → deepseek.

---

## THE OPEN BUG — start here

The owner reported this and it is **not diagnosed**. It is the most important thing outstanding.

**What he did:** opened the app → **Re-plan** → got **15 pictures** → copied all prompts →
generated 15 images externally → put them in a folder → **Work from this folder** → came back.

**What he saw:** the board now showed **30 pictures, not 15**. Of his 15 generated images, only
**2** were picked up. He set it back to 15 and then **no** images were picked up.

**Ruled out already:**
- `choose_working_folder` in `app.py` does **not** re-cut the plan — no call to
  `plan_image_budget`, `set_image_count`, or anything touching `share_with`.
- `syncImageCountControl` (`frontend/app.js`) only *writes* the count box and the rhythm
  slider; setting `.value` from script does not fire `oninput`.

**Prime suspect, unproven:** the old clock-cut path is still wired to the UI and can silently
overwrite a model-made plan.
- `#image-count` has `onblur="onImageCountCommit(this.value)"` → `applyImageBudget()` →
  **`set_image_count`** → `plan_image_budget` — the clock-cut method the whole project
  replaced. It rewrites every `share_with` in the script.
- `#shot-rhythm-slider` has `oninput="onRhythmSliderInput(...)"` → also calls
  `applyImageBudget()` after a 450 ms timer.
- Either would re-cut the film by clock, destroy the model's boundaries, and break the
  numbered-folder binding (his `1.jpg`…`15.jpg` no longer line up with picture slots).

**How to prove it:** instrument `applyImageBudget` and `set_image_count` to log every call with
a stack trace, then reproduce his sequence. If it fires during "Work from this folder", that is
the bug.

**Likely fix:** the old count box and rhythm slider should not be able to silently re-plan a
film the model planned. Either remove them from the Storyboard, or make them re-plan through
`plan_pictures_for_script` instead of `set_image_count`.

**Second, possibly separate:** only 2 of 15 images bound from the folder. Folder binding is
`plan_shots` → numbered folder (`1.jpg` → picture 1). If the plan had already been re-cut to 30
that explains it; if not, folder matching needs its own look.

---

## What was built, and why

### The original defect
The owner's films had generic, drifting image prompts. Root cause: **picture boundaries were cut
by a clock**, so 18 of his 60 pictures were assigned to stretches of narration with nothing in
them to photograph. Measured on `projects/Before_Adam_The_Story_of_Iblis` — 347 segments,
~18 min. **Success is the empty-span count falling, NOT a lower picture count.** The film was
already 60 pictures at a mean of 18.8s. There is no "one image per sentence" problem and never
was; judging on count would let a worse film pass.

### Tasks 1–10 of the plan (all committed)
1–2 Measured narration seconds via TTS + ffprobe, with a word-count fallback.
3–4 `repair_spans`: any model reply, however broken, becomes a legal plan covering every line
exactly once. Exact count honoured from 1 to one-per-line.
5–8 `build_plan_request` / `parse_plan_reply` / `plan_pictures` / `apply_spans` /
`plan_pictures_for_script`. Boundaries are chosen by a model reading the whole timed script.
9 Motion travel clamp verified — travel maxes out at **4.8 s**, so a 75 s hold drifts nine
times slower than an 8 s one. Nothing to fix; the tests stop anyone removing it.
10 The prompt export carries real timecodes: `02:14 to 02:34 (script lines 7-13)`.

**Tasks 11–13 were never done.** 11 was to write a `.wolfcut` file; the owner has since decided
to build his own Timeline instead (see below), so 11 should be **repurposed** into producing the
timeline data that screen will read. 12 (whole chain in order) and 13 (acceptance: re-measure
the empty-span count) are still worth doing.

### Frontend slices (Slices 1–3 committed)
1. **Auto / Exact number** planning controls on the Storyboard, wired to
   `plan_pictures_for_script`. Auto: the story decides, 8–75 s holds. Exact: N exactly, and one
   picture for a whole film is a legitimate answer the UI does not argue with.
2. **The board shows pictures, not shots.** One row per picture with
   `PICTURE 07 · 02:14 → 02:34 · holds 20.2s · script lines 31-36` and the whole narration that
   picture must illustrate. Previously 347 rows for 60 pictures, mostly repeats.
3. **Measure narration** button with per-segment progress, and a status pill reading
   `timings measured` / `N of M measured` / `estimated from word count`. It writes into the same
   project cache key the renderer uses, so it moves work earlier rather than adding it.

**Slices 4–6 not built:** Split/Merge on a picture row, Timeline read-only, Timeline editing.

### The prompt fixes (all committed 2 Sep, after Slice 3)
Every one of these was found by reading real exported prompts, **after the suite was green**.

1. **Every picture reaches the prompt builder with a description.** Splitting a span to meet an
   exact count gave the description to the first piece and nothing to the rest;
   `compose_gap_prompt` then fell back to raw search keywords. His real export: asked for 30,
   got **3 written prompts and 27 noun piles** (`Iblis Allah Adam`). `describe_missing_spans`
   asks again for exactly the blanks; `fill_undescribed` borrows a neighbour as last resort.
2. **`1: 1-6: description`** — the model numbers its own answers, and the leading number was
   read as the whole span. 30 pictures became 29 single-line ones plus a 317-line remainder.
3. **Negations removed.** The 31 Aug instruction had told the model to end every description
   with `no ..., no ...`. Text encoders do not parse negation, so that *raises* the odds of the
   excluded thing. Instruction rewritten to affirmative framing, plus `strip_negations` as a
   deterministic guard on every description the app accepts.
4. **The project brief no longer rides on model-written prompts.** `real people and places,
   consistent depiction of Adam, Iblis, Paradise` was on all 19 prompts of one export. An image
   model has no memory between pictures, so it can never act on it.
5. **Cross-references rewritten.** `The same primordial landscape, but now with embers` was
   picture two of a real export. Detected and asked for again from its own narration.
6. **`PLAN_REPLY_CEILING` 8192 → 32768.** One description ended `"and a single, distant,"`.
7. **A reply that numbers pictures instead of giving ranges is spread across the script.**
   Gemini returns `1.  1-4: …` on some runs and `1: …` on others — *the same request, different
   shape on consecutive runs*. That is why one export was clean and the next was wrong with
   nothing changed in between.

**Measured before → after on his real script, live Gemini:** blank descriptions 27/30 → 0;
brief tail 19/19 → 0; negations 15/15 → 0; cross-references 1 → 0; truncated 1 → 0.

---

## Commercial readiness — checked, and good

The app is going to be sold, so this was verified rather than assumed:
- **No niche config was edited.** Every fix is in shared code.
- All **10 shipped niches** build instructions successfully.
- A **brand-new empty niche** builds (1,038 chars). A niche with no exclusions builds.
- The guards are subject-agnostic: the scrubber cleans *"a red fox in snow, without any human
  tracks"*; the reference check catches *"the same laboratory, now with the centrifuge running"*.
- None of the shipped niches even has `prompt_recipe` / `never_depict` / `never_show_face` —
  those are optional extras only his custom override uses.

---

## The frontend redesign

The owner's decision: **stop exporting to WolfCut and build the timeline inside Smart Studio**
(he raised a licensing concern; it was not independently verified). The app gains a **Timeline**
screen. He is emphatic that work must be **testable by him at every step** — he is not a
programmer and cannot verify backend-only progress.

**Stitch mockups** are extracted at
`…\scratchpad\stitch\stitch_smart_studio_management_system\` (source ZIP in his Downloads).
All six screens plus Settings, both themes for Storyboard and Timeline, empty/busy states, and a
component sheet. **The design is good and worth following closely.** The *code* is not usable:
it loads Tailwind, Google Fonts and its images from the internet, and this app runs offline in a
desktop window. Port the design into `frontend/style.css` by hand.

**Remaining slices, in order:** 4 Split/Merge on a picture row · 5 Timeline read-only ·
6 Timeline editing. The owner has approved a **faithful port of the Stitch Storyboard and
Timeline** rather than more incremental patching of the old CSS.

**Known UI faults to fold in:**
- The Auto/Exact toggle resets to Auto on load while the *saved plan* does not, so the label can
  contradict the plan on screen.
- Clearing an API key in Settings does nothing: `frontend/app.js` ~836 has `if (keyVal) { …save… }`,
  so an emptied field skips the save call. **Do not "always save"** — `get_settings` deliberately
  never sends real keys to the browser, so the fields are blank on load and always-saving would
  wipe a working key. Add an explicit **Remove key** button.
- `frontend/index.html` inline `style="` is capped at **19** and is at 19. Layout goes in `style.css`.

---

## How the work runs

```
1. YOU write the instruction     generate TASK-N-FOR-ANTIGRAVITY.md from the plan
2. Antigravity writes the code   one task, then it STOPS. It does not commit.
3. The owner says "antigravity is done"
4. YOU verify from disk          read the files yourself — he does not paste them
5. YOU commit, then write the next task
```

**You verify. Not him.** He relays. **Never ask him to paste file contents** — he is managing
tokens and has asked for this explicitly. Read from disk.

**The verification that actually works,** in this order:
1. `git status --porcelain` — only the intended files changed?
2. `grep -c "^def test_"` on any appended file — did existing tests survive?
3. First three bytes of new files — `efbbbf` is a BOM from
   `[System.Text.Encoding]::UTF8`; no other file in this repo has one.
4. Mechanically diff the transcription against the plan's code block.
5. Run the tests yourself.
6. **Then judge the thing itself.** Every single defect found on 2 Sep was found by reading real
   exported prompts *after* the suite was green. A green suite has never once meant the prompts
   were usable. Render the real output and read it.

**Antigravity is capable but literal.** Every task file must repeat: do not commit, never
`git add -A`, no BOM, append don't regenerate, the exact test count to preserve, and report
**file paths only, never file contents**. It has twice done the right thing when the plan was
wrong (it corrected a false assertion in Task 9) — tell it to *report* such corrections, not
just make them.

## How to report to him

Lead with the verdict, then three headings, a few lines each:
- **✅ What's done** — in terms of the film, not the code. Name the task or slice.
- **⏳ What's left** — what remains; what is blocking, and who unblocks it.
- **▶️ What we can do now** — **one** next action. A real choice gets one focused question with
  a recommendation.

Numbers not adjectives. No jargon without a plain-English gloss. Never let "the tests pass"
stand for "it works". Say plainly when something is broken — he would rather read "I got this
wrong, I fixed it" in the first line. Full `C:\...` paths, literal commands in code blocks.
**Give him a fresh handoff at 50% context without being asked.**

## Ground rules

- **Never `git add -A`** — stages ~816 MB including two 310 MB ONNX models. Explicit paths only.
- **Do not push.** He tests first and will say when.
- `config/settings.json` is gitignored and holds live API keys. Never print or commit it.
- `config/series_overrides/` is gitignored — his niches exist nowhere else. Back up before
  editing. Backup at `config/_backups/niche-pre_islamic-2026-09-01.json`, deliberately
  uncommitted: putting his niche in git is his call.
- **Do not weaken a test.** If one must change, quote it before and after and justify it.
  (`test_every_description_is_required_to_exclude_something` was replaced this way when its
  requirement turned out to be harmful.)
- **Restarting the app matters.** It loads Python once at launch; code fixes do not reach a
  running session. Say so whenever asking him to retest.
- **Editing repo files from a Python helper:** they are **CRLF**. Read bytes, normalise to `\n`,
  patch, write back as CRLF.
- **Shell heredocs mangle backslash escapes.** Writing test files containing `\n` inside string
  literals through `cat <<'PYEOF'` silently produced real newlines and broke three test files
  today. Build them from `chr(92)` or use the Write tool directly.

## Where the code is

| What | Where |
|---|---|
| Boundary request, reply parser, scrubbers | `pipeline/picture_plan.py` — `build_plan_request`, `parse_plan_reply`, `_unformat`, `strip_negations`, `refers_to_another_picture`, `_spread_if_only_numbered` |
| Span repair, exact count, describe pass | `pipeline/picture_plan.py` — `repair_spans`, `_force_count`, `describe_missing_spans`, `fill_undescribed`, `apply_spans` |
| Measured narration seconds | `pipeline/narration_timing.py` — `segment_seconds`, `measure_narration`, `timing_maps` |
| Voiceover cache keys | `pipeline/voiceover.py` — `generate_voiceover`, `_write_marker` |
| Instruction sent to the model | `pipeline/shot_description.py` — `_build_instruction`, `RECIPE_OUTPUT_CONTRACT` |
| Depiction rules | `pipeline/shot_description.py` — `_never_depict_rule`, `_never_show_face_rule` |
| Final prompt assembly, slot order | `pipeline/library.py` — `compose_gap_prompt` |
| The auto-generated project brief | `pipeline/library.py` — `draft_project_brief` |
| The clock-cut budget (**still wired to the UI — see the open bug**) | `pipeline/text_parser.py` — `plan_image_budget` |
| Image binding, folder matching | `pipeline/library.py` — `plan_shots` |
| App endpoints | `app.py` — `plan_pictures_for_script`, `measure_narration_for_script`, `set_image_count`, `choose_working_folder` |
| Storyboard UI | `frontend/app.js` — `renderStoryboardScreen`, `picturesFromScript`, `replanPictures`, `measureNarration`, `syncImageCountControl` |
