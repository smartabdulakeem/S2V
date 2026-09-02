# Handoff — Smart Studio, 2 Sep 2026 (overnight session)

Paste this whole file into a new chat to pick the work up cold. It replaces the earlier
handoff of the same name.

## Which document goes where

| Document | Who reads it |
|---|---|
| **This file** | **The new Claude chat.** The owner pastes it in, and it is the only thing he pastes. |
| `ACCEPTANCE-FINDINGS.md` | **Read this second.** Task 13's result, and why its metric was wrong. |
| `docs/superpowers/plans/2026-09-01-model-chosen-picture-boundaries.md` | **Claude, from disk.** 80 KB. Never ask the owner to paste it. |
| `STITCH-BRIEF-SMART-STUDIO.md` | The design brief that produced the Stitch mockups. |

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget` — **84 commits ahead of origin, nothing pushed. Do not push.**
**Python:** `C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe` (not on PATH).
Prefix anything printing prompt text with `PYTHONIOENCODING=utf-8`.
**Suite: 683 tests, ~8 minutes.** Last full run: **683 passed, 1 xfailed, 0 failed.**

**Gemini works** on `gemini-2.5-flash`. Anthropic and OpenAI keys are cleared (they were dead).
DeepSeek is configured but never reached. Provider chain: anthropic → openai → gemini → deepseek.

**Antigravity is out of the loop.** The owner is not relaying tasks any more; Claude writes the
code directly, as this session did.

---

## You can now run the app yourself

This is the biggest change. `tools/devserver.py` serves `frontend/` and turns
`window.pywebview.api.<name>(...)` into `POST /api/<name>` against the same `Api` object
`app.py` hands the window — same code, same settings, same projects on disk.

```bash
C:/Users/HomePC/AppData/Local/Programs/Python/Python312/python.exe tools/devserver.py
```

Then open `http://127.0.0.1:8765/`. It is registered in `.claude/launch.json` as
`smart-studio-dev`, so `preview_start` opens it directly.

Two things a browser cannot do: native file dialogs (`POST /dev/pick {"path": "..."}` sets what
the next dialog returns) and `window.evaluate_js` (queued, the page polls `/dev/js`).

**Restart the dev server after any `app.py` change** — it imports `app` once at startup.
This found the thinking-budget defect within a minute of first running, from a line of stderr
no test would ever have printed. Use it before believing any frontend claim.

---

## What was fixed tonight, and how it was proved

### 1. The open bug — diagnosed, fixed, verified

**It was two faults, both proved from the owner's own files.**

**The re-plan race.** The count box is read by "Re-plan pictures", and clicking that button
blurs it — and `onblur` ran the *old clock cut*. One gesture started two planners on the same
script: `set_image_count` → `plan_image_budget` (fast, local) and `plan_pictures_for_script`
(slow, two model calls). Both assigned `currentScriptData`, both saved, so whichever finished
last won the film. On his film the clock cut won: all 347 shots carried `run_index`, which only
`plan_image_budget` writes; the 15 runs were near-uniform (19,18,19,21,22,24,22,25,25,23,32,26,
27,25,19); and **26 of the model's 30 descriptions were stranded** on shots carrying
`share_with`, where no prompt can reach them. The rhythm slider could do the same through a
450 ms timer. Both are gone from the Storyboard; nothing in `frontend/` can reach
`set_image_count` now. `plan_image_budget` and its tests are untouched.

**The folder binding.** `plan_shots` called `match_shots_by_number` with `len(all_shots)` — one
entry per *script line* — so his `1.jpg`…`15.jpg` were paired with lines 1–15, of which only
line 1 owned a picture. `picture_owning_shots` had already written the rule down: slot *n* is
the *n*th picture the film makes. Fixed as `number_pictures_from_folder`.
**Verified live on his real film and folder: 2 of 15 bound → 15 of 15, each picture to its own
numbered file, in order.**

### 2. Thinking was eating the answer (found by running the app)

On Gemini 2.5, thinking is on by default and its tokens are billed against `maxOutputTokens`.
The board asks for 8 descriptions at 4096. Four consecutive runs on his real narration:

| described | thinking used |
|---|---|
| 7 of 8 | 2866 of 4096 |
| 1 of 8 | 3928 |
| 7 of 8 | 2701 |
| 1 of 8 | 3931 |

Every one hit `MAX_TOKENS`; the pictures that fell off dropped silently to two-word keyword
search. **This is why one export was clean and the next was not with nothing changed between
them.** The provider now adds headroom on top of whatever the caller asks for — unused output
tokens are not billed. Same four runs after: **8, 8, 8, 8.** A cut-off reply now says so on
stderr with what the thinking cost.

### 3. A whole film's plan was timing out

The read timeout was a flat 60s. `PLAN_REPLY_CEILING` is 32768 — every boundary and every
description for an 18-minute film in one reply — which does not arrive in a minute. Running
the acceptance check timed out three times in one run, each time printing "the picture plan
fell back to one image" and dropping descriptions to keyword search. The timeout now follows
the budget sent (floor 60, cap 600). After: all 60 pictures described, twice.

### 4. Slice 4 — split and join a picture, without re-planning

Re-planning to move one boundary costs two model calls, rewrites every other picture, and
throws away good descriptions — which is how the 26 were lost. A boundary is `share_with` on
the segment where a picture starts, so this flips that one field.

Each picture row has **"Join to picture NN"** and **"Split into two…"**. Splitting opens the
picture's own narration, one line per row, so the cut is chosen against the words the new
picture would carry. `pipeline/picture_plan.py` — `split_picture`, `merge_picture`,
`picture_boundaries`. 21 tests.

**Verified on the real 347-line film:** split at line 23 took it 15 → 16 with the boundary
exactly there, line 24 following the new picture, and the four surviving descriptions
untouched; joining it back reproduced the original boundary list exactly.

### 5. Slices 5 and 6 — the Timeline

A new screen, third in the rail. Built from the plan already in memory — no render, no second
pass over the library. This is what Task 11 was for, now that WolfCut is not the destination.

- ruler whose tick spacing follows the zoom (1–60 px/s)
- **Pictures**: one clip per picture, width is the time it holds, with its image
- **Narration**: one block per script line, green where measured, amber where still a
  word-count guess — so a boundary standing on a guess is visible
- **Captions**: the lines themselves once the zoom gives them room
- a playhead the view follows, and click-anywhere scrubbing
- **Inspector**: in, out, hold, script lines, state, and the narration the picture carries
- editing: **"Cut here"** splits at the line under the playhead, **"Join to picture NN"** folds
  this one into the last

**Verified:** cut at 10:13.1 resolved to line 181 and took the film 15 → 16 correctly; joining
it back restored the plan.

### 6. The two known UI faults

- **A key can be removed.** Clearing the field did nothing because saving is guarded by
  `if (keyVal)` — and that guard has to stay, since `get_settings` never sends real keys to the
  browser, so an always-save would wipe a working key on the first Test of any other provider.
  There is now a **Remove** button per provider, with confirmation, and `remove_api_key`. A test
  holds every secret the Settings screen can set to also being removable.
- **The Auto/Exact toggle no longer contradicts the plan.** The plan records how it was asked
  for; the toggle and hold range are restored from it. The count box is deliberately *not*
  restored — it shows the pictures the film has now, so a film split by hand reads 16 rather
  than the 15 once requested.

---

## Task 13 — read `ACCEPTANCE-FINDINGS.md`

Short version: **Task 13's metric does not work, and picture count — not boundary placement —
is what decides whether a picture has anything to photograph.**

A random partition into 60 scores *better* (mean 8.8 over 400 trials) than the clock cut (11)
or the model (mean 12.2 over four runs). The metric rewards cutting small. Its 18-of-60
baseline does not reproduce either; the real `plan_image_budget` at 60 gives 11.

Measured with something length cannot flatter — how many photographable things each picture's
narration names:

| pictures | avg hold | starved | starved % |
|---|---|---|---|
| 10 | 108.7s | 1 | 10% |
| 15 | 72.5s | 2 | 13% |
| 30 | 36.2s | 16 | 53% |
| 60 | 18.1s | 47 | 78% |

At 60 pictures the film has nothing to give however it is cut (clock 47, random 45.3, model
43–44). **The owner cutting his film from 60 pictures to 15 was the fix.** The plan's assertion
that success is the empty-span count falling and *not* a lower picture count is, on this
script, backwards.

The model route is still worth keeping — for the descriptions, not the boundaries: 60 of 60
come back described where the clock cut supplies no words at all.

---

## What is left

- **The owner has tested none of this.** Everything above was verified by Claude through the
  dev server and on his real project files. He needs to run the real desktop app.
- **His film is untouched.** `projects/Before_Adam_The_Story_of_Iblis/script.json` is
  byte-identical to the state he left it in — 15 clock-cut pictures, 30 written descriptions of
  which 26 are stranded. A backup sits beside it as
  `script.backup-before-claude-test-20260902.json`. **It still needs one re-plan to repair.**
- **The Stitch port was not done.** Mockups are at
  `…\fb720164-134f-4559-9c11-56ceed5d2bba\scratchpad\stitch\stitch_smart_studio_management_system\`
  (source ZIP in Downloads). The Timeline was built in the app's existing visual language
  instead, because a full redesign of every screen is not something he could review overnight.
  His approval of a faithful port still stands.
- **Task 12** (whole chain, in order) was not written as a test.
- **Audio playback on the Timeline.** It scrubs and previews; it does not play. Real playback
  needs the narration mp3s served, and is a bigger feature than it looks.

---

## Ground rules

- **Never `git add -A`** — stages ~816 MB including two 310 MB ONNX models. Explicit paths only.
- **Do not push.** He tests first and will say when.
- `config/settings.json` is gitignored and holds live API keys. Never print or commit it.
- **`config/settings.backup-20260902-010212.json` is NOT gitignored and contains real keys.**
  It sits untracked in the working tree. One `git add -A` commits his keys to history — which
  is the sharpest reason the rule above exists. Adding `config/settings.backup-*.json` to
  `.gitignore` is his call and has not been done.
- `config/series_overrides/` is gitignored — his niches exist nowhere else. Back up before
  editing.
- **Do not weaken a test.** If one must change, quote it before and after and justify it.
- **Restarting matters.** The desktop app loads Python once at launch; the dev server imports
  `app.py` once at startup. Say so whenever asking him to retest.
- **Editing repo files:** they are **CRLF**. The Edit/Write tools sometimes write LF — check
  with a byte count and normalise before committing.
- **Shell heredocs mangle backslash escapes.** It ate the backslashes in a JSON path tonight.
  Use the Write tool for anything containing `\`.
- **A green suite has never meant the prompts were usable.** Every defect found on 1–2 Sep was
  found by reading real output. Now there is a dev server: run the app and look.

## How to report to him

Lead with the verdict, then three headings, a few lines each: **✅ What's done** (in terms of
the film, not the code) · **⏳ What's left** · **▶️ What we can do now** (one next action).
Numbers not adjectives. No jargon without a plain-English gloss. Say plainly when something is
broken. Full `C:\...` paths, literal commands in code blocks.

## Where the code is

| What | Where |
|---|---|
| Boundary request, reply parser, scrubbers | `pipeline/picture_plan.py` — `build_plan_request`, `parse_plan_reply`, `strip_negations`, `refers_to_another_picture` |
| Span repair, exact count, describe pass | `pipeline/picture_plan.py` — `repair_spans`, `_force_count`, `describe_missing_spans`, `apply_spans` |
| **Split / join one boundary** | `pipeline/picture_plan.py` — `split_picture`, `merge_picture`, `picture_boundaries` |
| **Numbered folder images → pictures** | `pipeline/library.py` — `number_pictures_from_folder`, `match_shots_by_number` |
| **Thinking headroom, read timeout, truncation warning** | `pipeline/llm/gemini.py` — `_with_thinking_headroom`, `_read_timeout`, `_warn_if_truncated` |
| Measured narration seconds | `pipeline/narration_timing.py` — `segment_seconds`, `measure_narration` |
| Instruction sent to the model | `pipeline/shot_description.py` — `_build_instruction`, `describe_shots` |
| Final prompt assembly | `pipeline/library.py` — `compose_gap_prompt` |
| The clock-cut budget (**no longer reachable from the UI**) | `pipeline/text_parser.py` — `plan_image_budget` |
| App endpoints | `app.py` — `plan_pictures_for_script`, `split_picture_at`, `merge_picture_at`, `remove_api_key`, `choose_working_folder` |
| Storyboard UI | `frontend/app.js` — `renderStoryboardScreen`, `picturesFromScript`, `replanPictures`, `splitPictureAt`, `mergePictureAt` |
| **Timeline UI** | `frontend/app.js` — `renderTimelineScreen`, `timelineSeek`, `drawTimelineInspector`, `tlLineAt` |
| **Run the app in a browser** | `tools/devserver.py` |
