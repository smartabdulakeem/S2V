# Handoff — why the prompts are still vague, 31 Aug 2026

Paste this into a new chat to pick the work up cold. The subject is **prompt quality only**. The
plumbing is fixed; this is about what the app asks the model for.

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget` — 48 commits, **none pushed**. This machine holds the only copy.
**Python:** `C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe` (not on PATH).
Prefix anything printing prompt text with `PYTHONIOENCODING=utf-8`.
**Suite:** ~8 minutes. Baseline **517 passed, 1 xfailed, 0 failures**.

---

## The complaint

Every image comes out generic. The owner has a 5,277-character prompt recipe for his niche. He
exported the app's own request, pasted it into ChatGPT by hand, and **got the same weak prompts
back**. So this is not Gemini being weak, and not the API being broken. The request itself is the
defect, and it can be tested for free in any chat window with no credits.

---

## What the attached PDF argues

`C:\Users\HomePC\Downloads\Strategy prompt assessment.pdf` — 27 pages, a ChatGPT conversation.
Extracted text is in this session's scratchpad as `strategy_pdf.txt`. Its argument, fairly summarised:

**The core claim.** A selected script line is a *location marker*, not a visual description. The app
(and any AI reading it naively) treats "Iblis saw Adam" as the whole brief for that image and returns
something like *"Iblis looking at Adam, ancient setting, dramatic lighting"* — technically related,
completely underdeveloped.

Its slogan, worth keeping:

> The segment is an anchor. The complete script is the context. The visual direction is the
> treatment. **Never confuse the selected script segment with the complete visual description.**

**Its three layers.**
1. **Full script = story brain.** Read all of it first: characters, chronology, cause and effect,
   turning points, what the audience knows at this point.
2. **Image positions = anchors.** They say *where* a picture is needed, not *what* it shows.
3. **Visual direction = treatment.** Supplied per niche; the model must not substitute its own taste.

**Its per-prompt construction checklist** — the part with real teeth. Every prompt should resolve:
subject, visible action, setting, historical/cultural context, period material culture, clothing,
composition, viewpoint, foreground, background, lighting, atmosphere, emotional tone, restrictions,
visual style. Plus a 17-question quality check before output, and a hard ban on camera movement and
cross-shot references ("as seen in the previous image").

**Its one architectural suggestion we should reject for now.** It proposes the AI also *choose* the
moments (Phases 2–3: identify visual moments, distribute across the narrative). Smart Studio already
chooses positions deterministically from the shot rhythm and image budget, and the owner has said he
wants that placement to stay the app's job. Adopt the PDF's Phases 4–6 (what to show, how to
describe it, how to construct the prompt) and leave placement alone.

---

## What is ALREADY built — do not rebuild this

The PDF's authors could not see the code. Three of its recommendations are already implemented:

- **The whole script already travels with every batch.** `_build_batch_prompt` in
  `pipeline/shot_description.py` emits a `THE FULL SCRIPT` block with every line numbered, then
  `THE MOMENTS TO DESCRIBE` with each excerpt tagged by its script line.
- **It already says the line is not the description.** Verbatim from that function: *"Place the
  moment in the story first — what has just happened, what is about to — and describe that moment,
  not the sentence on its own."*
- **The still-frame rule already exists** (commit `7af2afa`): no pan, zoom, tracking, dolly, cut or
  sequence, and no reference to another shot.

So the architecture the PDF asks for is largely present. **That is the important finding: the
missing piece is not the shape of the request, it is what the request leaves unsaid.**

---

## Four defects, verified against the code today

### 1. The model is never told how many pictures the film needs, or that this is one coordinated set

Descriptions are generated in **batches of 20** (`BATCH_SIZE` in `shot_description.py`). Each batch
gets the whole script but only its own 20 moments, and nothing states the total. A film of 55
pictures is written as three unrelated conversations. The model cannot balance coverage, vary
framing across the film, or know that picture 40 exists — the PDF's whole "coverage" argument is
unreachable from inside a batch.

### 2. The app appends its own slots afterwards, and never tells the model

After the model writes a description, `compose_gap_prompt` in `pipeline/library.py` appends:
framing (from a **four-entry cycle indexed by picture number**), the project brief, motion, ground,
atmosphere, setting, light, character bible, medium, era, negative prompt.

The model does not know this. So it writes its own composition and the app contradicts it. Real
output from the owner's film:

```
An expansive, untouched primordial landscape stretches to the horizon under a clear, ancient sky,
devoid of any human structures or presence, cinematic medium shot, subject filling much of the frame, ...
```

A landscape stretching to the horizon, described as a medium shot filling the frame. The framing was
chosen by `picture_index % 4`, not by what the picture shows.

### 3. There is no per-prompt completeness requirement

The recipe describes the world. Nothing forces each individual prompt to resolve subject, action,
environment, period, material culture, light, viewpoint. The model satisfies the recipe and still
returns something thin. This is the PDF's strongest contribution and the app has no equivalent.

### 4. The exported request drops the count above the fold

`write_prompt_request` in `pipeline/visuals.py` writes usage instructions, then a `======` line, then
the payload. It tells the owner *"copy everything below the line"* — and the sentence *"This film
needs exactly 55 pictures. Keep the numbering"* sits **above** it. Checked today: the phrase
`Keep the numbering` does not appear below the line. When he pasted it into ChatGPT, the AI was
never told the count. This is a bug in something I wrote yesterday.

---

## The decision that has to be made first

**Who owns the prompt — the model or the composer?** Right now both do, and they fight.

- **Option A — the model writes the whole prompt.** The request states the niche's look, the model
  returns a complete, production-ready prompt, and `compose_gap_prompt` stops appending slots for
  LLM-written shots. Matches the PDF. Loses the app's deterministic consistency.
- **Option B — the model writes only the scene; the composer owns the look.** The request explicitly
  tells the model what will be appended and forbids it from writing framing, medium or style. The
  composer's framing cycle must then become content-aware rather than `index % 4`.

Everything else follows from this. Do not start writing instruction text before it is settled.

---

## How to test this for free

**There are no API credits.** Anthropic and OpenAI both return **401** through the owner's gateway
(`api-router.opustokens.workers.dev`) — his credit is exhausted, confirmed by him. Gemini still
answers 200 on a separate Google key, but the point is that this work needs no key at all:

```bash
PYTHONIOENCODING=utf-8 "C:/Users/HomePC/AppData/Local/Programs/Python/Python312/python.exe" -c "import json; from pipeline.visuals import write_prompt_request; print(write_prompt_request(json.load(open('projects/Before_Adam_The_Story_of_Iblis/script.json',encoding='utf-8'))))"
```

That writes `prompt_request.txt`. Paste it into any chat, read what comes back, change the request,
repeat. **Iterate on the request text in a browser, then land it in the code.** Judge a change by
reading ten returned prompts, not by whether the suite is green.

---

## Two regressions to check first

1. **The owner's project lost all its descriptions again.** Backfilled to 347/347 at 06:05 today;
   `script.json` was rewritten at 09:03 and now has **0 of 347**. Cause not established — most
   likely a re-plan in the app. Whatever the reason, descriptions do not currently survive whatever
   he did, and that is worth finding before anything else.
2. **`era_block` is back to 136 characters** in
   `config/series_overrides/pre_islamic_prophetic___global_history.json` and is appended to every
   prompt: *"Antiquity to pre-Islamic Late Antiquity, from early human settlement through ancient
   Near Eastern civilizations up to 6th-century Arabia."* The 30 Aug session emptied it deliberately
   — that niche spans pre-human antiquity to 6th-century Arabia, so no fixed era line is true for
   most shots. It is a syllabus, not a scene. Confirm with the owner before removing it again.

---

## Ground rules

- **Never** `git add -A` — stages ~816 MB including two 310 MB ONNX models. Stage explicit paths.
- **Never** `git checkout -- library/index.npz`. If modified, commit it.
- **Do not push.** The owner tests first and will say when.
- `config/settings.json` is gitignored and holds live API keys. Never print or commit it.
- `config/series_overrides/` is gitignored — his niches exist nowhere else. **Back up before
  editing.** Backups from today are in this session's scratchpad.
- Inline `style="` in `frontend/index.html` is capped at **19** and is at 19. Layout goes in
  `style.css`.
- A stale `cache/` causes phantom test failures. Tests touching `describe_shots` must patch
  `_load_disk_cache` / `_save_disk_cache`.
- Antigravity writes code from a brief, then **stops** — see `ANTIGRAVITY-RULES.md`. It does not
  commit. Review its working tree, fix, then commit.
- Do not weaken a test. If one must change, quote it before and after and justify it.

## Where the code is

| What | Where |
|---|---|
| Instruction sent to the model | `pipeline/shot_description.py` → `_build_instruction`, `RECIPE_OUTPUT_CONTRACT` |
| The batch text, script + moments | `pipeline/shot_description.py` → `_build_batch_prompt` |
| Batch size, reply budget | `pipeline/shot_description.py` → `describe_shots` |
| Final prompt assembly, slot order | `pipeline/library.py` → `compose_gap_prompt` |
| Framing cycle (`index % 4`) | `pipeline/prompt_slots.py` → `default_framing_for` |
| The no-key export | `pipeline/visuals.py` → `write_prompt_request` |
| One line per picture | `pipeline/visuals.py` → `initialize_project_sourcing` |
| The list everything counts from | `pipeline/library.py` → `picture_owning_shots` |

## Settled recently — do not re-litigate

- Prompts bind to shots that own a picture, never to `share_with` shots (`facbf61`).
- `image_prompts.txt` is one line per picture, numbered in film order.
- The description reply budget scales with the batch; a flat 2048 was truncating 17 of every 20
  descriptions (`4548806`). This was the single biggest cause of vague prompts and is fixed.
- The brief no longer names a medium; it carries subject and recurring figures only (`2bbeab4`).
- `never_depict` in the niche keeps named figures out of both the brief and the model instruction
  (`02273e4`).
- A custom niche validates and renders (`4df2d0a`).
- WolfCut export writes a real timeline; its acceptance test — opening the file in WolfCut — is
  **still outstanding**.
