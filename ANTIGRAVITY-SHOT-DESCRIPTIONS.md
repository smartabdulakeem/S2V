# Antigravity brief — descriptive shot prompts

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** work on `feat/image-budget` (do not branch again — this builds on it).
**Python:** `C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe` (not on PATH).
Prefix any command that prints a prompt with `PYTHONIOENCODING=utf-8`.

**Baseline before you start: `324 passed, 2 skipped, 1 xfailed`.** Do not finish below it.

---

## The bug

Every generated image for a 44-shot film came back as generic desert wallpaper — a man on a
camel, palm trees, a crescent moon — regardless of what the narration said. Here is why. This is
the *entire* prompt for a shot:

```
An illustrated scene of seventh century Arabia and early Islamic history,
consistent depiction of Adam, wide establishing shot, subject small in the
frame, Allah Bow Adam, Stylised illustration, confident inked line, ...
```

Everything there is boilerplate shared by all 44 shots **except three words: `Allah Bow Adam`**.

Those three words come from `extract_keyword()` (`pipeline/text_parser.py`), which is a **CLIP
search-query builder**. It strips stopwords and returns the salient nouns. That is correct for
finding an image in the library and useless for generating one. The narration

> "And then Allah gives a command. A command that seems simple: Bow before Adam. The angels obey."

becomes `Allah Bow Adam`. A generator reads three unrelated nouns as a *title*, letters them
across the frame, and fills the rest with era-generic scenery.

**The subject slot needs a description of what the camera sees. Nothing offline can write one** —
turning rhetorical narration into a visual scene requires a language model. The app already has
one wired: Gemini 2.5 Flash, at `pipeline/text_parser.py:695`, with the key in settings under
`google_api_key` (`app.py:30`).

## What to build

A planning-time pass that writes one visual sentence per shot, stored on the shot, used as the
prompt's subject.

---

## Task 1 — `pipeline/shot_description.py` (new file)

```python
def describe_shots(shots: list, api_key: str, model: str = "gemini-2.5-flash") -> dict:
    """
    One visual sentence per shot, keyed by shot_id.

    `shots` is a list of {"shot_id": str, "scene": str} - `scene` is the slice of
    narration that shot covers. Returns {shot_id: description}. Shots that come
    back empty or unparseable are simply absent from the result; the caller falls
    back to the search query for those.
    """
```

**Batch 20 shots per request.** One request per shot is 44 round trips for a short film and the
owner pays per call. Reuse the request/error handling already in `text_parser.py` — do not write
a second HTTP client.

### The instruction to send — use this text verbatim

This is the part that decides whether the feature works. Do not paraphrase it, do not "improve"
it, do not add flourishes:

```
You are a documentary shot designer. For each numbered narration excerpt below,
write ONE sentence describing what the camera sees.

Rules:
- Describe only what a camera could photograph: people, objects, place, light, action.
- Never restate the narration and never use its voice. Drop "imagine", "you have",
  "picture this" and every second-person address.
- An abstract idea must become a concrete image. "A command that seems simple"
  becomes "a raised hand held still above a bowed assembly".
- No style, medium, camera or lens words. Never write cinematic, illustration,
  photograph, painting, 35mm, wide shot, close-up.
- Nothing written may appear in the scene: no text, letters, captions, titles,
  numbers, signage, banners or inscriptions.
- 12 to 25 words. One sentence. No trailing full stop needed.
- Keep a proper noun only when it names a person or place that recurs in the film.

Output exactly one line per excerpt, formatted as:
<number>. <sentence>

Return nothing else - no preamble, no blank lines, no commentary.
```

Then the excerpts, as `1. <scene text>` … one per line.

### Parsing the reply

Match `^\s*(\d+)[.):]\s*(.+)$` per line. Ignore anything unmatched. Map the number back to the
shot at that position **in the batch you sent**, not the global shot index — an off-by-one here
silently pairs every description with the wrong shot, which is the exact failure mode this whole
feature exists to remove.

Reject and drop a returned line that is longer than 40 words, or that contains any of:
`cinematic, illustration, photograph, painting, render, 35mm, close-up, wide shot, caption,
title, text, sign`. A model that ignores the rules must not poison the prompt.

## Task 2 — cache the descriptions

Store the result on the shot as **`"visual_description"`**, beside `scene`.

Re-planning must not re-call the API. Key the cache on a hash of the `scene` text: if a shot's
`scene` is unchanged and `visual_description` is already present, skip it. Only shots whose
narration slice actually changed get sent.

This matters more than it looks — the owner changes the image count repeatedly while planning,
and each change re-cuts every shot. Without the cache, one planning session is dozens of paid
API calls.

## Task 3 — use it in the prompt

In `pipeline/library.py`, `compose_gap_prompt` takes `shot_query`. Add an optional
`visual_description: str = None`. When present and non-empty it fills the **subject slot** in
place of the query. When absent, behaviour is exactly as today.

**`compose_gap_prompt` has 8 call sites** — three in `pipeline/library.py` and five in
`pipeline/visuals.py`. Thread the new argument through all eight. Missing the `visuals.py` ones
means the AI-image path emits a different prompt from the copied sheet, which has happened before
in this repo.

The search query is unaffected. `shot["query"]` still drives library search; only the generated
prompt changes.

## Task 4 — wiring and settings

- A checkbox in Settings: **"Write descriptive image prompts with AI"**, default **off**.
  Off means today's behaviour and no API calls, so nobody is billed by surprise.
- When on but no `google_api_key` is set, fall back silently to the query and log one line. Never
  raise, never block planning.
- Every network failure degrades to the query. Planning must complete offline.

## Task 5 — tests

New `tests/test_shot_description.py`. Mock the HTTP layer — **no test may hit the network.**

1. A well-formed reply maps to the right shots, including on the second batch (guards the
   batch-offset bug).
2. A reply with missing or extra numbered lines drops the bad ones and keeps the good ones.
3. A reply containing a banned style word is rejected for that shot only.
4. A shot with an unchanged `scene` and an existing `visual_description` triggers no API call.
5. No API key, and a raised network error, both fall back to the query and still return a prompt.
6. `compose_gap_prompt` puts `visual_description` in the subject slot when given, and the query
   when not.

---

## Do not touch

- `BRIEF_OPENERS`, `brief_subject` in the packs, or anything about `world_anchor` — all three were
  just rewritten and a further change in flight will conflict.
- `pipeline/composer.py`.
- `extract_keyword` itself. It stays exactly as it is; library search depends on it.

---

## Report back with

1. The exact final pytest line.
2. Three real before/after prompts for the same narration — the current keyword version and the
   described version side by side. Paste them, do not summarise.
3. Proof the cache works: a re-plan with unchanged narration showing **zero** API calls.
4. Anything changed beyond this brief, and why.
5. Any command that failed, even if you recovered.

Claims of "verified" without pasted output will be rejected on review.
