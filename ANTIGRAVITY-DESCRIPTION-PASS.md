# Brief: the shot description pass must obey the niche

Hand this whole file to Antigravity.

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget` — stay on it. **Commit** when done. **Do not push.**
**Never** run `git add -A` — it stages ~816 MB including two 310 MB ONNX models. Stage explicit
paths only.
**Never** run `git checkout -- library/index.npz`. The test suite rewrites it. Restoring it once
cost 170 images their searchability. If it shows as modified, leave it and say so.

---

## The complaint

> "I have now tested the prompt niche creator. To me it's no different. It's like the AI is not
> listening to the prompts I just created. It's still hallucinating."

He is right, and it is not the model's fault. The niche he configured never reached the picture.

---

## The evidence, measured

The owner built a niche, `pre_islamic_prophetic___global_history`, with a 5,277-character
`prompt_recipe`. His last film came out generic anyway. Three facts, all verified on disk:

1. Every one of his 347 shots has **no `visual_description`**, and queries like
   `'fought defeated drove'` and `'Adam Muslim human'` — keyword-extraction output.
2. `cache/planning/shot_descriptions.json` holds **418 descriptions**, median 17 words, all in one
   voice: *"Ethereal light illuminates a vast, formless expanse where shimmering figures gather in
   silent reverence."* Not one of them knows about his niche, his era, or his recipe.
3. Those descriptions were written by `pipeline/shot_description.py`, whose `INSTRUCTION` (line 25)
   is **hardcoded** — "You are a documentary shot designer… 12 to 25 words" — and receives no niche
   configuration of any kind.

That vague, period-free quality **is** the hallucination he is describing.

---

## Job 1 — the description pass

`pipeline/shot_description.py`, called from `pipeline/library.py:2139–2158` behind the
`ai_shot_descriptions` setting. Three separate defects.

### 1a. It throws away the recipe's own work

`describe_shots()` line 176:

```python
existing_desc = shot.get("visual_description")
if existing_desc and is_valid_description(existing_desc):
```

`is_valid_description()` (line 77) rejects anything **over 40 words**, or containing **cinematic,
illustration, photograph, painting, render, 35mm, close-up, wide shot, caption, title, text, sign,
signage**.

Those are reasonable quality gates on text *this module generates*. Applied to a description the
niche's own recipe produced, they silently discard exactly what the user configured and replace it
with a generic sentence. A recipe written to produce cinematic prompts is guaranteed to trip them.

**Fix:** when the niche has a non-empty `prompt_recipe`, an existing `visual_description` is
authoritative and is kept unchanged. Validation applies only to text `describe_shots` itself
generated.

### 1b. The cache is blind to the niche

`_scene_hash()` (line 52) hashes **the narration text and nothing else**, and the cache at
`cache/planning/shot_descriptions.json` is shared across every niche and every recipe. Change
niche, change recipe, re-plan — the same sentence comes straight back.

This is the same defect that was fixed in the planner cache and must not be repeated here.

**Fix:** the key must cover `series_slug`, a hash of `prompt_recipe`, `era_block`, and a version tag
for `INSTRUCTION` so editing the instruction invalidates old entries. Old entries under the current
key format simply stop matching, which is correct; the file can be deleted safely.

### 1c. What it writes knows nothing about the niche

When the pass genuinely does need to write a description — no recipe, or a shot the recipe left
empty — it should still not be generic. Pass the niche's `era_block`, `world_anchor` and a short
lead from `prompt_recipe` into the instruction, so a shot in a seventh-century film is not described
as "a lone figure on a windswept hill".

**Signature:** extend to `describe_shots(shots, api_key, model=..., series_cfg=None)`. Keep
`series_cfg=None` working exactly as today, so nothing that does not pass it changes behaviour.
Update the call site in `library.py` to pass the resolved config it already has.

---

## Job 2 — a user-created niche never gets the override flag

Small, separate, and in the same area.

`get_series_config()` line ~425: when a niche exists only in `config/series_overrides/` — every
niche made with **+ New niche** — the file is returned directly:

```python
return data
```

It never passes through `_apply_series_overrides()`, so **`style_presets_is_override` is never
set** (verified `None` on the owner's niche). `style_presets_for()` then merges the six universal
visual types underneath, and deleting a universal type from a user-created niche does not stick —
it reappears on the next load.

**Fix:** set `style_presets_is_override = True` on that path when the file carries `style_presets`.

---

## The cache key

Bump the shot cache key **`v8` to `v9`** in `_get_shot_cache_key()` (`pipeline/composer.py`, the
literal is at line 356), and add a `# v9:` comment line in the existing style.

This one is easy to miss: the key is built from `query_or_pin`, and **`visual_description` is not in
it**. Descriptions are about to change for every shot while queries stay identical, so without the
bump every cached clip from the old behaviour is served back and the fix looks like it did nothing.

---

## Traps

1. **Do not weaken a test to make it pass.** The vignette limit was once raised from 0.40 to 0.45
   and reported as "passes cleanly". Every `tests/` diff is read.
2. **Do not work in a git worktree** — it has no gitignored assets (`vendor/ffmpeg`,
   `library/images`), so render tests always fail there.
3. **A stale `cache/` causes phantom failures.** Delete it and re-run before reporting a regression.
4. `is_valid_description` has **four call sites** — `shot_description.py` lines 176, 179 and 225,
   plus `tests/test_shot_description.py`. Line 225 validates freshly generated text and must keep
   its current meaning. Only the paths that judge an *existing* description change.
5. Do not change what `ai_shot_descriptions` defaults to. It is off by default in `app.py` and on in
   the owner's settings; both must keep working.

---

## Tests

**`tests/test_shot_description.py` already exists and has six tests. Add to it — do not create a
second file with a near-identical name.**

**Two of its tests cover exactly the behaviour this brief changes.** Read them before you start:

- `test_3_banned_style_words_and_length_rejection` — the gates must still apply to text
  `describe_shots` *generates*, so this should keep passing as written. If it fails, you have
  disabled the gates too broadly. Do not relax it to make it pass.
- `test_4_cache_skips_unchanged_scene` — the cache must still skip an unchanged scene **within one
  niche**. Update it to hold the niche constant. Do not delete it.

If any other existing test needs changing, say which and why in your report, and quote the before
and after. A test edit you cannot justify in one sentence is a test you should not have made.

New cases to add:

- A recipe-authored description of **60 words containing "cinematic"** survives untouched when the
  niche has a recipe.
- The same narration under **two different niches** produces two different cache entries — the
  proof that the key is no longer niche-blind.
- Editing a niche's `prompt_recipe` invalidates its cached descriptions.
- With `series_cfg=None`, behaviour is byte-for-byte what it is today.
- A niche with **no** recipe still gets the generated description, and the 40-word and banned-word
  gates still apply to it.
- A user-created niche has `style_presets_is_override` set, and a deleted universal type stays
  deleted across a reload.

---

## What to report

Numbers and literal strings, not adjectives.

1. For one shot in the owner's niche: the description **before and after**, both pasted.
2. The new cache key for one scene under two different niches, showing they differ.
3. Proof that a 60-word cinematic description authored by a recipe now survives.
4. The full suite count. Baseline to match or beat: **437 passed, 1 xfailed, 0 failures**.
5. Whether `library/index.npz` shows as modified, and confirmation you did not restore it.
