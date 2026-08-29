# Brief: let the owner teach the AI how to write image prompts

Hand this whole file to Antigravity. Everything it needs is here.

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget` — stay on it. **Commit** when green. **Do not push.**
**Never** run `git add -A` — it stages ~816 MB including two 310 MB ONNX models.

**Test baseline before you start: `425 passed, 1 xfailed`.** Anything else is yours.

---

## The problem, in one screenful

This is the complete instruction the app gives DeepSeek and Gemini when planning a video's
visuals — `pipeline/text_parser.py`, `BATCH_PLANNING_SYSTEM_PROMPT`:

```
You are S2V's visual director and shot planner.
You receive a batch of narration segments from a video script.
Your job is to propose B-roll shot queries, shot counts, and voice steering per segment.

STRICT CONSTRAINTS:
1. Do NOT rewrite, alter, or regenerate narration text. Narration is handled externally.
2. For each segment, output 1-3 shot queries describing specific, historically/visually
   accurate B-roll visuals.
3. Keep shot queries concise and visually descriptive (5-12 words).
```

Nine lines, and the operative one asks for **5–12 word fragments**. The models comply. That is why
the images look generic — not because the models are weak, but because nobody ever asked them for
a real prompt.

The owner has written a 48-section prompt recipe for his Islamic-history channel covering entity
control, gender control, subject counts, sacred-figure representation, negative control and
copy-ready output. It is far better than the nine lines above, and there is nowhere to put it.

**Both jobs below exist to fix that.** Job 1 is the one the owner has approved and is the priority.

---

## Environment

Python is NOT on PATH:
`C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe`

Prefix anything printing prompt text with `PYTHONIOENCODING=utf-8` — the Windows console dies on
`₦` and `—`, which looks like an engine failure but is not.

Run the app with `run.bat`. Check JS with `node --check frontend/app.js`. Suite ~7 minutes.

---

# JOB 1 — a niche manager, with an editable prompt recipe

## 1a. The new field

Add `prompt_recipe` to a series pack: a long free-text instruction that **replaces**
`BATCH_PLANNING_SYSTEM_PROMPT` for that niche when it is non-empty. When it is empty or absent,
behaviour is exactly as today.

It must comfortably hold **50 KB or more**. The owner's recipe is a full document, not a sentence.
Do not truncate it, do not word-wrap it into the prompt, do not summarise it.

## 1b. ⚠️ The trap that will break the app if you miss it

A recipe like the owner's produces **full cinematic image prompts** — 60 to 100 words, with
negative clauses and entity control. Those are excellent for an image generator and **useless as
library search text**: CLIP truncates at 77 tokens and a long prompt embeds to mush.

The library search was repaired two days ago to search on the planner's sentence. If the planner
now returns 90-word prompts into the same field, that repair is undone.

**So the planner must return two things per shot:**

| Field | Length | Used for |
|---|---|---|
| `query` | 5–12 words | Library search (CLIP), filename matching |
| `visual_description` | full prompt, any length | The text sent to the image generator |

Update `BATCH_PLANNING_SCHEMA` accordingly, and make the recipe's contract explicit when you
assemble the system prompt: *whatever the recipe says, you must also return a short `query` of
5–12 words per shot for library retrieval.* Append that requirement to the recipe rather than
trusting the recipe to include it — the owner's document knows nothing about this app.

Verify after: print a real planned script and show both fields populated, with `query` short.

## 1c. The Settings tab

Extend the existing **"Visual style per niche"** card (`frontend/index.html` around line 511,
`frontend/app.js`) into a full niche manager:

- **Pick** any niche, shipped or user-made
- **Edit** `display_name`, `medium_block`, `palette_block`, `era_block`, `negative_block`,
  `brief_subject`, and the new `prompt_recipe`
- **Create a new niche** — slug plus display name, seeded from `default.json` so it is usable
  immediately
- **Delete** a user-created niche. Shipped niches can only be reset, never deleted
- **Reset to default** — as today, deletes the override file
- Keep the live prompt preview that already exists

**Storage, unchanged from the existing mechanism:** `config/series_overrides/<slug>.json`, already
in `.gitignore`. Shipped packs in `config/series/` are **never written to** — an app update must
not destroy the owner's work, and his work must not block an update. A user-created niche is a
full pack file in the overrides folder.

New niches must appear in the Script screen's niche dropdown and everywhere else niches are
listed. `get_series_config()` (`pipeline/library.py:183`) is the single seam — packs and overrides
already merge there.

**Ship the owner's recipe as the default for `islamic_history`.** He will paste it in; put it in
the pack file so it survives a reset. Ask him for the text — it is in a Google Doc titled
"HOUSE OF WISDOM — CINEMATIC VISUAL PROMPT GENERATOR".

---

# JOB 2 — paste external prompts, match images by number

The owner generates prompts elsewhere (Gemini Gem, ChatGPT), generates images from them, drops
them all in one folder, and points the app at it with "work from this folder". Today the app
cannot tell which image belongs to which shot.

## 2a. The paste tab, on the storyboard

Not in Settings. A tab or panel on the board:

- A large textarea. The owner pastes the prompts he used, in order.
- **Split on blank lines.** His recipe (§31–33) forbids numbering or labelling the prompts and
  emits each as its own block, so blank-line separation is the format that actually arrives.
- Prompt *i* binds to image slot *i*. Order is the contract — his recipe §37 requires chronological
  order and §5 requires exactly N prompts.
- Store the prompt on the shot so it is used verbatim for generation and for matching.

## 2b. Matching images from the work folder — by number, not by guessing

- An image whose filename starts with a number — `3_whatever.jpg`, `3-whatever.jpg`, `3.jpg` —
  belongs to **slot 3**. Nothing else is consulted.
- No leading number: fall back to sorted filename order, and say so in the UI.
- **Never fall back to similarity scoring here.** The owner chose these files deliberately.

Why numbers: the existing `prompt_name_match` needs three identifying words from a filename, and
image tools truncate names to about twenty characters —
`6_a_massive__rhythmic_.jpg` yields two words and fails. Numbers do not truncate.

## 2c. ⚠️ The mapping must be visible before it is used

This is the part the owner is worried about, and the reason to build it this way. Show a table
before anything renders:

| Slot | Prompt (first 60 chars) | Image found | Status |
|---|---|---|---|
| 1 | "A vast ancient desert at dawn…" | `1_a_vast_ancient_dese.jpg` | ✓ |
| 2 | "One adult male figure alone…" | `2_one_adult_male_fig.jpg` | ✓ |
| 3 | "Overwhelming celestial light…" | — | **missing** |

Report counts plainly: *"7 prompts, 6 images matched, slot 3 missing."* A missing slot is named by
number so he knows exactly which prompt to regenerate. Nothing silent, nothing guessed.

## 2d. Remove the per-shot "Edit prompt" button

`frontend/app.js` around line 1364 — `toggleEditPrompt` and the textarea. The owner has asked for
it to go; prompt authoring belongs in the recipe and the paste tab, not on each card. Leave
`shot.prompt_override` in the data model — the paste tab writes to it — but remove the per-card
editing UI and its handlers.

---

## Traps

1. **The shot cache key is `v6`** (`pipeline/composer.py`, `_get_shot_cache_key`). If what a shot
   renders can change, **bump it to `v7`**, or cached clips are served back and your work looks
   like a no-op.
2. **The image cache too.** A new prompt must re-fetch the picture, not reuse the old file in
   `cache/`.
3. **`compose_gap_prompt` has several call sites** across `library.py` and `visuals.py`. Grep for
   all of them; a missed one fails only at render.
4. **`visual_style` is prose, `visual_type` is a key.** The board sends the *label* as
   `visual_style`; sending the key leaks it into prompts.
5. **Setting `.value` in JS fires no `change` event.** Restore the niche, `await loadStylePresets()`,
   *then* dependent dropdowns.
6. **A stale `cache/`** causes phantom test failures — delete it if `test_parallel.py` fails for no
   code reason.
7. **A git worktree has no gitignored assets** (`vendor/ffmpeg`, `library/images`); render tests
   always fail there. Work in the main tree.
8. **Do not weaken an existing test to make a change pass.** If a test encodes behaviour that is
   deliberately changing, rewrite it to assert the new contract and **say so prominently in your
   report**. Silently relaxing a threshold has happened here before and was caught.

---

## What "done" looks like

The owner verifies everything. Report so he can check without redoing the work.

- **Print a real planned script** for `islamic_history` with the owner's recipe installed, showing
  for two or three shots: the full `visual_description` and the short `query`. This is the proof
  that Job 1 worked and did not break retrieval.
- **Show a created niche surviving a restart**, and `git status` proving `config/series/` is
  untouched.
- **Show the mapping table** with a deliberate gap — 7 prompts, 6 images — and the missing slot
  named.
- **Show a pasted prompt reaching the picture**: render one shot, confirm the image changed and no
  cache served the old one.
- State plainly anything you did not do, and why.

Finish with the full suite:

```
PYTHONIOENCODING=utf-8 <python> -m pytest tests/ -q
```

Add tests for: a recipe replacing the system prompt, an absent recipe leaving behaviour unchanged,
the planner returning both a long description and a short query, a created niche resolving through
`get_series_config`, number-prefix matching, and a missing slot being reported rather than filled.

---

## Committing

Commit when green. **Commit is local — it does not touch GitHub.** Do not push.

Two commits, so the recipe work can be read apart from the paste-and-match work:

1. the niche manager and the prompt recipe
2. the paste tab, numbered image matching, and removing the per-shot edit button

Stage explicit paths only. Write messages the way the repo does — a short summary line, then what
was wrong and what the measurement showed. `git log` shows the shape.
