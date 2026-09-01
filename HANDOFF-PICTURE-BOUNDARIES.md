# Handoff — model-chosen picture boundaries, 1 Sep 2026

Paste this whole file into a new chat to pick the work up cold. It replaces the earlier
handoff of the same name.

## Which document goes where

| Document | Who reads it |
|---|---|
| **This file** | **The new Claude chat.** The owner pastes it in, and it is the only thing he pastes. |
| **The plan** — `docs/superpowers/plans/2026-09-01-model-chosen-picture-boundaries.md` | **Claude, from disk.** 80 KB. Never ask the owner to paste it. |
| **`TASK-N-FOR-ANTIGRAVITY.md`** in the repo root | **Antigravity.** Claude writes these one at a time. |

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget` — **57 commits ahead of `origin/feat/image-budget`, nothing pushed today.**
**Python:** `C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe` (not on PATH).
Prefix anything printing prompt text with `PYTHONIOENCODING=utf-8`.
**Suite: 46 files, 574 tests, ~44 minutes.** Last full run: **569 passed, 1 xfailed, 0 failed**
— that run predates Tasks 4–5, which added 5 + 14 tests, all passing in their own files.

> The old handoff said the suite takes 8–14 minutes. It does not — it takes **44** on this
> machine. A report claiming a full clean run in ten minutes has not run the suite.

---

## Where this stands

The root cause was never wording: **18 of the owner's 60 pictures were assigned to stretches of
narration with nothing in them to photograph**, because boundaries were cut by a clock. A
13-task plan replaces clock-cut boundaries with boundaries a model chooses from the whole
script. **Tasks 1–5 are built, verified and committed. Task 6 is written and waiting.**

Do not re-litigate the evidence. Measured on `projects/Before_Adam_The_Story_of_Iblis` (347
segments, ~18 min, 60 pictures): mean 18.8s per picture, median 20.2s — there is no "one image
per sentence" problem and never was. The script is not truncated (16,215 chars against a 60,000
cap). **Success is the empty-span count dropping from 18 of 60. Success is NOT a lower picture
count** — judging on count would let a worse film pass.

## Commits so far, newest first

```
64f4259  Task 5  ask the model where pictures belong, parse spans from the reply
8756727  Task 4  exact picture count holds from one to one-per-line
4e466ad  ——————  fix(voiceover): re-record a line when its words change
1bffbcd  Task 3  deterministic span repair guaranteeing a legal picture plan
d2a3267  Task 2  narration timing pass writes measured seconds and audio paths
77d6301  Task 1  measured narration seconds with word-count fallback
d8a3c4d  ——————  the three prompt-quality fixes from 31 Aug (see that commit body)
```

## Two things fixed beyond the plan — do not revert them

1. **`parse_plan_reply` tolerates markdown.** The plan's regex dropped every span from a
   bulleted reply, a bold reply, or one labelled `Picture 1 (1-4):`. A reply whose every line is
   dropped parses as nothing, which `repair_spans` answers with **one picture for the whole
   film** — so a correct answer became an eighteen-minute still, silently. Since there are no
   API credits and the request is pasted into a browser chat, that was the likeliest real
   outcome, not an edge case. Five tests cover the formats.

2. **`generate_voiceover` re-records when the words change.** It keyed its cache on segment
   number and tone only, so rewording a line returned the previous recording of the previous
   words. Since Task 2 that stale duration also decides where a picture starts and ends. Fixed
   with a `.text` fingerprint beside the existing `.tone` marker. Audio cached before the fix is
   **adopted and stamped, not re-recorded**, so existing films do not all regenerate; the cost
   is that an already-stale segment stays stale one more time.

## What is left

| Phase | Tasks | State |
|---|---|---|
| 1 | 1–4 | **Done.** Measured seconds, audio paths, deterministic span repair, exact count. |
| 2 | 5–8 | **5 done.** 6 written and waiting. 7 spans → `share_with`. 8 app endpoint. |
| 3 | 9–11 | Motion clamp verified; timecodes in the export; WolfCut timeline with no video encode. |
| 4 | 12–13 | The whole chain in order; acceptance on the real film. |

**Next action: hand `TASK-6-FOR-ANTIGRAVITY.md` to Antigravity.**

### Decisions already settled — do not re-open

- **Exact count beats the holding range.** Auto: 8–75s per picture, count falls out of the
  story. Manual: N exactly, down to one picture for a whole 20-minute film. Proven in Task 4.
- **Every failure has one home** — dead provider, refusal, garbled reply all end at one picture
  over the whole film. The parser never guesses; `repair_spans` decides.
- **`plan_image_budget` is not deleted.** It stays as the offline fallback.
- **Automatic image selection is untouched.** `plan_shots` still binds pin → numbered folder →
  CLIP retrieval → gap, now against model-chosen boundaries. Task 12 proves it.
- **Motion needs no work.** `travel_for` already clamps travel; Task 9 only stops anyone
  removing that.

---

## How the work runs — read this before doing anything

```
1. YOU write the instruction     generate TASK-N-FOR-ANTIGRAVITY.md from the plan
2. Antigravity writes the code   one task, then it STOPS. It does not commit.
3. The owner says "antigravity is done"
4. YOU verify from disk          read the files yourself — he does not paste them
5. YOU commit, then write Task N+1
```

**You verify. Not him.** He is not a programmer and does not review code, prompts or test
output. He relays. Read the files off disk yourself; **do not ask him to paste file contents
into the chat** — he is managing tokens and asked for this explicitly.

**The verification that actually works,** in this order:

1. `git status --porcelain` — only the intended files changed?
2. `grep -c "^def test_"` on any file being appended to — did the existing tests survive?
3. First three bytes of every new file — `efbbbf` means Antigravity used
   `[System.Text.Encoding]::UTF8` and left a BOM. No other file in this repo has one.
4. **Mechanically diff its transcription against the plan's code block.** It has been exact
   five times running; a difference is the thing to look for, not to assume.
5. Run the tests yourself.
6. **Then judge the thing itself.** A green suite has never once meant the prompts were usable.
   Render the actual request text and read it; probe the parser with the formats a browser chat
   really produces. Both fixes above were found this way, *after* the suite was green.

**Antigravity is less capable than you.** That is the point of the split. Every task file must
repeat: do not commit, never `git add -A`, no BOM, append don't regenerate, name the exact test
count to preserve, and report **file paths only, never file contents**.

## How to report to him — required shape

Lead with the verdict. Then three headings, a few lines each:

- **✅ What's done** — in terms of the film, not the code. Name the task number.
- **⏳ What's left** — how much of the plan remains; what is blocking, and who unblocks it.
- **▶️ What we can do now** — **one** next action and who does it. If there is a real choice,
  ask one focused question with a recommendation.

Rules: numbers not adjectives ("18 of 60 spans had nothing to photograph"). No jargon without a
plain-English gloss. Never let "the tests pass" stand for "it works". Say plainly when something
is broken — he would rather read "Antigravity got this wrong, I fixed it" in the first line.
Full `C:\...` paths, literal commands in their own code block. Keep it short.

**Give him a fresh handoff at 50% context without being asked.**

## Ground rules

- **Never `git add -A`** — stages ~816 MB including two 310 MB ONNX models. Explicit paths only.
- **Do not push.** He tests first and will say when.
- `config/settings.json` is gitignored and holds live API keys. Never print or commit it.
- `config/series_overrides/` is gitignored — his niches exist nowhere else. Back up before
  editing. A backup sits at `config/_backups/niche-pre_islamic-2026-09-01.json`, **deliberately
  left uncommitted** — putting his niche in git is his call, not a default.
- Inline `style="` in `frontend/index.html` is capped at **19** and is at 19. Layout goes in
  `style.css`.
- A stale `cache/` causes phantom failures. Tests touching `describe_shots` must patch
  `_load_disk_cache` / `_save_disk_cache`.
- **Do not weaken a test.** If one must change, quote it before and after and justify it.
- Editing repo files from a Python helper: they are **CRLF**. Read bytes, normalise to `\n`,
  patch, write back as CRLF. Writing LF-only mangles the diff. Beware backslash escapes when
  generating test source through a shell heredoc — build them from `chr(92)` instead.

## Open items in his priority order

1. **`library/new image/`** holds 60 images from the owner's *own* prompt list, numbered to
   *his* cut of the script, not the app's — 60 of 60 filenames match his prompts, 0 of 60 match
   the app's, so they cannot bind to the app's slots. Git also shows 47 deletions there from a
   previous project; the folder is reused as scratch. **His decision. Nothing has been deleted
   or moved.**
2. **`era_block` is 136 chars** appended to every prompt: *"Antiquity to pre-Islamic Late
   Antiquity… up to 6th-century Arabia."* No single era line is true across a film spanning
   pre-human antiquity to 6th-century Arabia. A previous session emptied it deliberately.
   **Ask before removing it again.**
3. **WolfCut has never been opened.** Task 11 makes a timeline available without a render, but
   no `.wolfcut` file has ever been loaded in WolfCut itself. Only he can run that test.
4. **Background music is not exported.** WolfCut gets T1 pictures, T2 narration, T3 captions.
   Music and SFX are added by hand — the human-touch window he wants, but he should know it
   before opening the file. A T4 music track is a small addition if he asks.
5. **The `TASK-N-FOR-ANTIGRAVITY.md` files** accumulate in the repo root, untracked. Harmless;
   clear them when the plan is done.

## Where the code is

| What | Where |
|---|---|
| Boundary request + reply parser | `pipeline/picture_plan.py` → `build_plan_request`, `parse_plan_reply`, `_unformat` |
| Span repair, exact count | `pipeline/picture_plan.py` → `repair_spans`, `_force_count`, `_merge_short` |
| Measured narration seconds | `pipeline/narration_timing.py` → `segment_seconds`, `measure_narration`, `timing_maps` |
| Voiceover cache keys | `pipeline/voiceover.py` → `generate_voiceover`, `_write_marker` |
| Instruction sent to the model | `pipeline/shot_description.py` → `_build_instruction`, `RECIPE_OUTPUT_CONTRACT` |
| Depiction rules | `pipeline/shot_description.py` → `_never_depict_rule`, `_never_show_face_rule` |
| Final prompt assembly, slot order | `pipeline/library.py` → `compose_gap_prompt` |
| Picture runs and spans | `pipeline/library.py` → `picture_runs`, `picture_owning_shots` |
| The clock-cut budget being replaced | `pipeline/text_parser.py` → `plan_image_budget` |
| Image binding (unchanged by the plan) | `pipeline/library.py` → `plan_shots` |
| The no-key export | `pipeline/visuals.py` → `write_prompt_request` |
| WolfCut timeline | `pipeline/wolfcut_export.py` → `write_wolfcut_project` |
| Motion travel clamp | `pipeline/motion.py` → `travel_for` |
