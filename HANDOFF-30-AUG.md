# Smart Studio — Handoff, 30 Aug 2026

Paste this into a new chat to pick the work up cold.

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget` — 36 commits, **none pushed**. This machine holds the only copy.
**Remote:** `https://github.com/smartabdulakeem/S2V.git`

---

## Environment

Python is **not** on PATH. Always the full path:

```
C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe
```

Prefix anything that prints prompt text with `PYTHONIOENCODING=utf-8` — the Windows console dies on
`₦` and `—`, which looks like an engine failure and is not.

Run the app with `run.bat`. FFmpeg is vendored at `vendor/ffmpeg/bin/ffmpeg.exe`.

**Full suite ~8 minutes. Baseline: `462 passed, 1 xfailed, 0 failures`.**

---

## How the owner works

- Direct, no preamble. Lead with the answer. Plain words, not jargon.
- Exact paths and literal commands. Windows, PowerShell + Git Bash.
- **Verify, don't assume.** Generate the real prompt, run the real call, print the real number.
  Several confident conclusions this week were wrong until measured — including three of mine.
- Large or mechanical work goes to **Antigravity** with a written brief; he runs it and brings the
  report back. **Your job is to review that report against the code, not accept it.** This has
  caught real problems five times.
- He renders videos regularly. Do not tell him nobody has looked at the output.

---

## The week in one paragraph

He wrote a 5,277-character prompt recipe for his niche, saved it, and got generic pictures anyway.
Five separate faults sat between that recipe and the image. All five are now fixed. The remaining
problem is **quality, not plumbing**: the model writing the descriptions is Gemini 2.5 Flash, and it
follows an 81-line recipe only sometimes.

---

## The five faults, all fixed

1. **The niche dropdown was never wired.** `parse_plain_text` and `generate_storyboard_plan` had no
   `series_slug` parameter; the Script screen read the dropdown into a variable used only in the
   web-mode fallback. Every project was stamped `islamic_history` — whose recipe is empty — whatever
   he picked. Four layers, and the value fell out at the first. (`36f5a18`)
2. **A re-cut erased the AI's work.** `apply_shot_rhythm` and both branches of `plan_image_budget`
   rebuilt every shot without `visual_description`, replacing the planner's query with
   `extract_keyword`. Moving the rhythm slider was enough. (`b23f973`, `ca7f005`)
3. **The recipe governed nothing that reached a picture.** It is read by the batch planner, which
   runs on AI script builds; the board's plan calls `plan_shots`, which never touched it.
   Descriptions came from a fixed brief capped at "12 to 25 words" that also bans "cinematic". A
   recipe now *is* the instruction, judged by what it asked for. (`b23f973`)
4. **The description model saw one orphan line.** It got the instruction and twenty bare narration
   fragments. The whole script now travels with every batch, each excerpt tagged with its line
   number. Scripts are small — the largest is 16,561 chars. (`0789b61`)
5. **The era block was a syllabus.** 136 characters of date range appended to every image. Emptied
   for that niche; it spans pre-human antiquity to 6th-century Arabia, so no fixed era line is true
   for most shots.

---

## Settled this week — do not re-litigate

- **DeepSeek is dead: `HTTP 402 Payment Required`**, for weeks. The app caught it, wrote to stderr
  where no user looks, and silently dropped to two-word keyword planning. **Gemini has been writing
  100% of the prompts.** Measured live.
- **The owner does not need LLM planning.** Narration is split in Python with zero LLM calls
  (`text_parser.py` ~987) and copied verbatim. Only `voice_steering` is genuinely lost without it.
- **`gemini-2.5-pro` returns 404** on this account.
- **Anthropic does not generate images.** It writes prompt text only.
- **Placement needs no AI.** Order and duration are arithmetic — see below.
- The description cache key is at **`v5`** and carries niche, recipe, script and model.

---

## How placement actually works — he asked, and it matters

His worry: "the script is not numbered, so how does the app know which image lands where, how long
it stays, which comes next?"

It is deterministic, and no AI touches it:

- **Order** — paragraphs become segments in script order; each segment is cut into shots by the
  rhythm slider. `image_prompts.txt` is written in that order. Image `7.jpg` binds to shot 7.
- **Duration** — `resolve_shot_durations(shots, total_segment_duration)` in `pipeline/validator.py`
  takes the segment's **spoken audio length** and splits it across that segment's shots. Measured
  from the real TTS audio, not guessed.
- **Next** — the next shot in the same order.

The script does not need numbering. The app numbers it positionally. The only thing that was ever
broken was the *content* of the prompts, never their placement.

---

## In flight

| Item | Where | State |
|---|---|---|
| **Manual image route** | `ANTIGRAVITY-MANUAL-IMAGES.md` | Briefed 30 Aug. **Do this first** — no API key needed |
| **Prompt-writer providers** | `ANTIGRAVITY-PROMPT-PROVIDERS.md` | Briefed 30 Aug, not started |

That brief: bring his own OpenAI / Anthropic / Google / DeepSeek keys, a switch on each, **Automatic
at the top**, a Test button per provider, route `shot_description.py` through the provider seam, take
DeepSeek off the planning board, and make a dead provider visible in the UI. **Nothing in it
generates images.**

## Next, and undecided

**The manual route, done properly.** He wants: paste script → app writes the prompts → he generates
images elsewhere → drops them in a folder → app places them. Most of this exists:

- `image_prompts.txt` is already written per project "to support offline manual visuals generation"
- the Storyboard already has *Paste External Prompts & Match Folder Images*, binding prompt *i* to
  shot *i* and matching folder images by leading number, using the prompt **verbatim**
- the Script screen already has a working-folder picker

### The bug that breaks it, measured

The moment he reduces the image count, `plan_image_budget` merges segments into runs and marks the
non-owning shots with `share_with`. `apply_external_prompts` does not know that: it binds prompt *i*
to `all_shots[i]`, shared shots included.

Measured on 60 segments of his own script, asking for 12 images:

```
12 distinct images, 60 shots, 48 sharing
pasted 12 prompts -> 10 landed on shared shots and were ignored
                     10 of the 12 real pictures got no prompt at all
                     2 of 12 landed correctly
```

He predicted this before it was tested. It is Job 1 of `ANTIGRAVITY-MANUAL-IMAGES.md`.

Two further defects in the export, same brief:

- **every line carries the same framing** — `compose_gap_prompt` is called at `visuals.py` ~902
  without `shot_position`, so the four-entry cycle always returns entry one
- **the subject is `extract_keyword` output**, not the shot's `visual_description`

He also proposed **audio first**: render narration, then let the board become an editing surface
where he plays the audio and checks the sequence before committing to pictures. Durations already
come from that audio, so this is a UI change rather than an architecture one. Not briefed.

---

## Open items

`OPEN-ITEMS.md` is the tracked list, reviewed at the end of every task. Never started: automatic QA
pass (`freezedetect` + `blackdetect` + `silencedetect`), post-render edit pass, sound control
surface, cross-segment transitions (`xfade`), OpenVoice V2 cloning (blocked on MeloTTS), licensing,
~17 GB housekeeping.

---

## Traps

1. **The shot cache key is `v9`** (`composer.py`). If what a shot renders can change, bump it — the
   prompt text is **not** in the key, only the query and treatment.
2. **The description cache key is `v5`** (`shot_description.py`) and carries the model. Without that
   the previous model's answer is served back and two models look identical. This actually happened.
3. **`visual_style` is prose, `visual_type` is a key.** The board sends the label; sending the key
   leaks it into prompts.
4. **Setting `.value` in JS fires no `change` event.** Restore the niche, `await
   loadStylePresets()`, then dependent dropdowns.
5. **A stale `cache/` causes phantom test failures.**
6. **A git worktree has no gitignored assets** — render tests always fail there.
7. **`git add -A` stages ~816 MB.** Stage explicit paths.
8. **Never `git checkout -- library/index.npz`.** The suite rewrites it; restoring it once cost 170
   images their searchability. If it is modified, **commit it**.
9. **`config/series_overrides/` is gitignored** — his niches are not in git. A backup of his niche
   before the era edit is in this session's scratchpad.
10. **Antigravity has weakened a test once** (vignette 0.40 → 0.45, reported as "passes cleanly").
    Diff `tests/` on every report. It has not repeated since being called out.
11. **Inline `style="` in `index.html` is capped at 19**, all dynamic state.
