# Handoff — the image problem, and the plan that replaces it, 1 Sep 2026

Paste this whole file into a new chat to pick the work up cold.

## Which document goes where

There are two documents. They have different readers.

| Document | Who reads it | How |
|---|---|---|
| **This file** — `HANDOFF-PICTURE-BOUNDARIES.md` | **The new Claude chat** | The owner pastes it in. It is the only thing he pastes. |
| **The plan** — `docs/superpowers/plans/2026-09-01-model-chosen-picture-boundaries.md` | **Antigravity** | The owner gives it to Antigravity to write code from. |

**Claude: do not ask him to paste the plan.** It is 77 KB of code and pasting it would waste the
context this handoff exists to save. Open it from disk yourself when you need it:

```
C:\Users\HomePC\Documents\GitHub\Smart-Studio\docs\superpowers\plans\2026-09-01-model-chosen-picture-boundaries.md
```

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget` — **113 commits, none pushed.** This machine holds the only copy.
**Python:** `C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe` (not on PATH).
Prefix anything printing prompt text with `PYTHONIOENCODING=utf-8`.
**Suite:** **549 tests in 43 files, ~8–14 minutes.** Last full run: **548 passed, 1 xfailed, 0 failures.**

> If a test report says "30 passed" it ran one file, not the suite. Antigravity reported exactly
> that as a "clean baseline" — it is not, and a run under 500 has not tested anything.

---

## Where this stands in one paragraph

The owner's films came out with generic, drifting image prompts. Three separate defects were found
and fixed today, in order of discovery, and each was hiding the next. The last one is not a wording
problem at all: **picture boundaries are cut by a clock, so 18 of his 60 pictures are assigned to
stretches of narration with nothing in them to photograph.** No instruction text fixes an empty
span. A 13-task plan replaces clock-cut boundaries with boundaries a model chooses from the whole
script. **Nothing has been executed yet.** The plan is written, reviewed and ready.

---

## The evidence, so nobody re-litigates it

Measured on `projects/Before_Adam_The_Story_of_Iblis` — 347 segments, ~18 minutes, 60 pictures:

| Claim | Truth |
|---|---|
| "The app forces one image per sentence" | **False.** 347 segments → 60 pictures, **mean 18.8s, median 20.2s** on screen. Already cinematic pacing. |
| "The script is being truncated" | **False.** 16,215 chars against a 60,000 cap. The model sees all 347 lines. |
| "The prompts are vague" | **Symptom.** 18 of 60 spans contain almost nothing photographable — **7 of them in the first 15 pictures**, which is exactly where the owner stopped generating. |

Picture 9 covers script lines 41–44 in full:

```
[41] Some describe him as belonging to a group of creatures associated with the angels and called jinn.
[42] Other reports describe him as having been among the most devoted and knowledgeable worshippers.
[43] And the reports differ over exactly how his position should be understood.
[44] But they converge on something important.
```

No subject, no action, no place. A model ordered to illustrate that returns "a commanding, imposing
cloaked figure on a ridge" because that is all the span supports. **That is the root cause.**

---

## What was fixed today — all uncommitted, all in the working tree

### 1. The description request was rebuilt around pictures, not sentences
`pipeline/shot_description.py`

- The narration excerpt is **no longer pasted** under the instruction as the thing to illustrate.
  A picture is named by its number and its span (`Picture 7 — script lines 31-36`); the lines
  themselves are already in the full-script block above.
- The film's picture count and the **whole plan** travel with every batch, so a batch writing
  41–60 knows 1–40 exist.
- Replies are parsed by **picture number**, not batch position. Previously a reply numbered 41–60
  against a 20-item batch was discarded whole and those shots fell to keyword search.
- Only picture-owning shots are described. It used to send all 347 for a 60-picture film and throw
  287 away.
- `RICH_WORD_CAP` 150 → 220. An over-cap description is **discarded**, not trimmed, so the richer
  output contract would have silently undone itself.

### 2. Depiction rules — the reason images were unusable
`pipeline/shot_description.py`, `pipeline/library.py`, and the niche config

The owner's own prompts end with exclusions on **60 of 60** lines. The app's ended with them on
**0 of 60** — and the niche has held a 234-character `negative_block` all along that was never
shown to the model.

- `negative_block` now reaches the model as *"Standing exclusions for this film"*.
- Every description must end with what must not appear. *"A picture with nothing excluded is not finished."*
- **New `never_show_face` list**, a sibling of `never_depict`. `never_depict` removes a figure
  (right for the Divine); `never_show_face` keeps it present but never identifiable — for Iblis,
  Shaytan, Satan, the jinn, angels, Adam. Without it the model wrote *"a figure's tense, furrowed
  brow, cold eyes staring with bitter envy"*, which renders as a photographed human model.
- **Bug fixed:** `save_series_override` kept a fixed key list that never included `never_depict`.
  Editing any other niche field would have silently erased the only rule keeping faces off the
  Divine. Both lists are on the list now, with a round-trip test.

### 3. Pacing — the tail collapse
`pipeline/text_parser.py` → `plan_image_budget`

A run closed on the first segment past `total / N` and **reset the counter**, so every run finished
long, the surplus accumulated, and the segments ran out before the runs did. The film ended in a
burst of one-segment pictures: 1.2s, 1.6s, 3.6s. It got **worse** the more images were asked for
(20 → 0 bad, 40 → 3, 60 → 7, 80 → 13), which is why raising the budget made pacing feel worse.

Fixed by cutting at cumulative boundaries. Budget 60: nothing under 10.8s, spread halved.

> **The owner's critique of this fix is correct and worth carrying forward:** it made the runs
> *more even*, and evenness is not editorial judgement. It removed an indefensible defect
> (1.2-second pictures) without addressing the real problem. That is what the plan is for.

### 4. Niche config — the owner's content, backed up first
`config/series_overrides/pre_islamic_prophetic___global_history.json` (**gitignored — exists nowhere else**)

- Added `never_show_face: ["Iblis", "Shaytan", "Satan", "the jinn", "angels", "Adam"]`
- Added a `NON-HUMAN BEINGS AND THE UNSEEN` section to `prompt_recipe` (5,277 → 6,487 chars):
  smokeless fire for Iblis and the jinn, light rather than bodies for angels, unformed clay for
  Adam before the breath, the Divine shown only by its effect. Prohibitions alone produced "a
  cloaked figure"; the model needed somewhere to put the meaning.

**Backup:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio\config\_backups\niche-pre_islamic-2026-09-01.json`

To revert both niche changes:

```bash
copy "C:\Users\HomePC\Documents\GitHub\Smart-Studio\config\_backups\niche-pre_islamic-2026-09-01.json" "C:\Users\HomePC\Documents\GitHub\Smart-Studio\config\series_overrides\pre_islamic_prophetic___global_history.json"
```

Note: `config/_backups/` is **not** gitignored, unlike `config/series_overrides/`. That backup is
currently untracked. Committing it would put a copy of his niche in git — protective, since his
niches exist nowhere else, but it is his call, not a default. Nothing was committed.

---

## The plan — 13 tasks, nothing executed

`docs/superpowers/plans/2026-09-01-model-chosen-picture-boundaries.md`

Hand the **whole file** to Antigravity. It contains every file path, the actual code, exact
commands and expected output.

**What it does:** time stops choosing where pictures go and only constrains how long one may hold.
The model that already reads the whole script returns the boundaries.

| Phase | Tasks | |
|---|---|---|
| 1 | 1–4 | Measured narration seconds + audio paths; **deterministic span repair** (built before anything asks a model, so a mangled reply can never break a film) |
| 2 | 5–8 | Ask the model where pictures belong; parse; spans → `share_with`; app endpoint |
| 3 | 9–11 | Motion clamp verified; timecodes in the export; **WolfCut timeline with no video encode** |
| 4 | 12–13 | The whole chain in order; acceptance on the real film |

**Start with Phase 1.** It needs no API key, so it builds and tests entirely offline.

### Decisions already settled — do not re-open

- **Exact count beats the holding range.** Auto mode: 8–75s per picture, count falls out of the
  story. Manual mode: the owner asks for N and gets exactly N, down to **one picture for a whole
  20-minute film**. The ceiling must not quietly split it back.
- **Every failure has one home.** Dead provider, refusal, garbled reply — all end at one picture
  over the whole film. The parser never guesses; `repair_spans` decides.
- **`plan_image_budget` is not deleted.** It stays as the offline fallback.
- **Automatic image selection is untouched.** `plan_shots` still binds pin → numbered folder →
  CLIP retrieval → gap. It binds to model-chosen boundaries instead of clock-cut ones. Task 12
  proves it.
- **Motion needs no work.** `travel_for` already clamps travel (`ken_burns` max 0.24), so an image
  held 70s moves nine times slower than one held 8s. Task 9 exists so nobody removes that.

### Success criterion — the one thing that matters

**The empty-span count dropping from 18 of 60.** Task 13 re-measures it.

**Success is NOT a lower picture count.** An external report claimed the app forces one image per
sentence and that the fix should yield "15–30 instead of 60–100". That is false — see the evidence
table. Judging on picture count would let a *worse* film pass.

---

## Open items, in the owner's own priority

1. **Nothing from today is committed.** 6 modified source files, 2 new test files, the plan.
   `library/index.npz` is modified — commit it, never `git checkout --` it.
2. **`library/new image/`** holds 60 images generated from the owner's *own* prompt list, numbered
   to *his* cut of the script, not the app's — 60 of 60 filenames match his prompts, 0 of 60 match
   the app's. They cannot bind to the app's slots. Git also shows 47 deletions there from a previous
   project; the folder is reused as scratch. **His decision what happens to them — nothing has been
   deleted or moved.**
3. **`era_block` is 136 chars** and appended to every prompt: *"Antiquity to pre-Islamic Late
   Antiquity… up to 6th-century Arabia."* No single era line is true across a film spanning
   pre-human antiquity to 6th-century Arabia. A previous session emptied it deliberately. **Ask
   before removing it again.**
4. **WolfCut has never been opened.** The export writes a real timeline and Task 11 makes it
   available without a render, but no `.wolfcut` file has ever been loaded in WolfCut itself. That
   is the one test only the owner can run.
5. **Background music is not exported.** WolfCut gets T1 pictures, T2 narration, T3 captions. Music
   and SFX are added by hand — which is the human-touch window the owner wants, but he should know
   it before opening the file. A T4 music track is a small addition if he asks.

---

## How the work actually runs — read this before doing anything

**The loop, and it does not vary:**

```
1. YOU write the instruction        a task from the plan, or a smaller piece of one
2. Antigravity writes the code      one task, then it STOPS — see ANTIGRAVITY-RULES.md.
                                    It does not commit.
3. The owner brings you the report  test output, git diff, changed files
4. YOU verify and fix               read the code, find the errors, edit them yourself
5. Next task                        break it into smaller pieces if Antigravity struggled
```

**You are the one who verifies. Not him.** This is the single most important thing in this file.
He is not a programmer and does not review code, prompts or test output. He relays. When he pastes
a report, a diff, or a set of generated prompts, he is handing you evidence to judge — he is not
telling you it is correct, and he is not asking you to confirm his reading of it. Read it yourself
and say plainly what is right and what is wrong.

**That includes the prompts.** He pastes `prompt_request.txt` into a browser chat because there are
no API credits — Anthropic and OpenAI both return 401 through his gateway, Gemini answers on a
separate Google key. He performs the paste; **you** read what comes back and judge whether it is
good. Judge by reading the prompts, never by a green suite. A passing suite has never once meant
the prompts were usable.

**Antigravity is less capable than you.** That is the point of the split — it is cheap hands, you
are the judgement. Expect it to: report a subset of the suite as a full run, misread which claims
about the app are true, drift from the plan's exact code, and stop early. When a task defeats it,
**break that task into smaller steps and hand it back** rather than doing it yourself. Rewriting
its work silently defeats the token-management reason the split exists.

**Ask one focused question when something is ambiguous.** Do not guess his intent. Explain in plain
terms; never hand-wave a path or a command — always the full `C:\...` path and the literal command.

---

## How to report back to him — required shape

He is not a programmer. He is deciding what to build next and whether the last thing worked. A
report he cannot act on is a failed report, however accurate it is.

**Every time you finish verifying a task, answer these three questions in this order, under these
headings, in plain English:**

### ✅ What's done
What now works that did not work before, said in terms of the film — not the code. Name the task
number so he can track it against the plan.

### ⏳ What's left
What has not been built yet, and roughly how much of the plan remains. If something is blocked, say
what is blocking it and who has to unblock it — him, Antigravity, or you.

### ▶️ What we can do now
The single next action, and who does it. One thing, not a menu. If there is a real choice to make,
ask it as one focused question with a recommendation.

**Rules for the whole report:**

- **Lead with the verdict.** "Task 3 is correct and I fixed two things" — not a narrative of what
  you read.
- **No jargon without a plain-English gloss.** Not "the cumulative partition prevents tail
  collapse" — say "the film no longer ends with eight images flashing past in half a minute."
- **Never let "the tests pass" stand for "it works."** A green suite has never once meant the
  prompts were usable. If you have not looked at real output, say so.
- **Say plainly when something is broken.** Do not soften it, do not bury it under what went well.
  He would rather hear "Antigravity got this wrong, I fixed it" in the first line.
- **Full paths, literal commands.** Always `C:\Users\HomePC\...`, never "your config file". Put any
  command he should run in its own code block.
- **Numbers, not adjectives.** "18 of 60 spans had nothing to photograph" beats "the pacing was
  poor." He makes decisions from numbers.
- **Keep it short.** Three headings, a few lines each. Detail lives in the plan and the code; he
  does not need it recited.

**Worked example of a good report:**

> **Task 3 is done and correct.** Antigravity got the merge logic backwards — it folded short
> pictures into the *longer* neighbour instead of the shorter one, which would have made your
> uneven pictures worse, not better. Fixed and re-tested.
>
> **✅ What's done** — The app can now take any picture plan, however broken, and turn it into a
> legal one: no missing narration, no two pictures claiming the same line. This is the safety net
> everything else sits on. Tasks 1–3 of 13.
>
> **⏳ What's left** — 10 tasks. Next up is the manual override, so you can ask for exactly one
> picture across a 20-minute film and get it.
>
> **▶️ What we can do now** — Send Task 4 to Antigravity. It needs no API key, so it can build and
> test it offline.

## Ground rules

- **Never `git add -A`** — stages ~816 MB including two 310 MB ONNX models. Stage explicit paths.
- **Do not push.** He tests first and will say when.
- `config/settings.json` is gitignored and holds live API keys. Never print or commit it.
- `config/series_overrides/` is gitignored — his niches exist nowhere else. **Back up before editing.**
- Inline `style="` in `frontend/index.html` is capped at **19** and is at 19. Layout goes in `style.css`.
- A stale `cache/` causes phantom failures. Tests touching `describe_shots` must patch
  `_load_disk_cache` / `_save_disk_cache`.
- **Do not weaken a test.** If one must change, quote it before and after and justify it.

## Where the code is

| What | Where |
|---|---|
| Instruction sent to the model | `pipeline/shot_description.py` → `_build_instruction`, `RECIPE_OUTPUT_CONTRACT` |
| Depiction rules | `pipeline/shot_description.py` → `_never_depict_rule`, `_never_show_face_rule` |
| The batch text: script + picture plan | `pipeline/shot_description.py` → `_build_picture_prompt` |
| Final prompt assembly, slot order | `pipeline/library.py` → `compose_gap_prompt` |
| Who owns the camera | `pipeline/library.py` → `compose_gap_prompt`, `model_owns_camera` |
| Picture runs and spans | `pipeline/library.py` → `picture_runs`, `picture_owning_shots` |
| The clock-cut budget being replaced | `pipeline/text_parser.py` → `plan_image_budget` |
| Image binding (unchanged by the plan) | `pipeline/library.py` → `plan_shots` |
| The no-key export | `pipeline/visuals.py` → `write_prompt_request` |
| WolfCut timeline | `pipeline/wolfcut_export.py` → `write_wolfcut_project` |
| Motion travel clamp | `pipeline/motion.py` → `travel_for` |
