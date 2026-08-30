# Brief: your own API keys, with a switch on each, writing prompts only

Hand this whole file to Antigravity.

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget` — stay on it. **Commit** when done. **Do not push.**
**Never** run `git add -A` — it stages ~816 MB including two 310 MB ONNX models. Stage explicit
paths only.
**Never** run `git checkout -- library/index.npz`. The suite rewrites it; restoring it once cost
170 images their searchability. If it shows as modified, leave it and say so.

---

## What this is for

The only job the owner wants an AI to do right now is **write the text-to-image prompt for each
shot**. He takes those prompts to an external image tool himself, generates the pictures, and brings
them back in a folder.

So this brief is about one thing: letting him bring his own keys, choose which provider writes the
prompts, and switch them on and off.

**Nothing here generates images.** Do not add an image generator, and do not offer Anthropic as one
— Anthropic has no image API.

---

## Job 1 — the provider list in Settings

Settings → **Keys & services**. Add a section, laid out top to bottom exactly like this:

```
Prompt writer
  ( ) Automatic            use the first working provider below
  [x] Anthropic   claude-sonnet-4      key: ●●●● set    [Test]
  [ ] OpenAI      gpt-4o               key: not set     [Test]
  [x] Google      gemini-2.5-flash     key: ●●●● set    [Test]
  [ ] DeepSeek    deepseek-chat        key: ●●●● set    [Test]
```

Rules:

- **Automatic is the first row.** It means: try the enabled providers in the order listed, and on a
  permanent failure — **401, 402, 403, 404** — move to the next enabled one. Record and display
  which provider actually answered. It never means "guess".
- **One on/off switch per provider.** A provider switched off is never called, even by Automatic.
- **A model name per provider**, editable. Do not offer a model without confirming the key can call
  it: `gemini-2.5-pro` returns **404 Not Found** on this account. Either list what the key really
  supports, or validate on selection and say so plainly.
- **A Test button per provider** makes one cheap call and reports the true result: working, bad key,
  or out of credit. This is the control that would have saved the owner a week.
- **DeepSeek stays in this list.** It is only being removed from *planning* (Job 3), not from the
  app. He may well want it writing prompts.

Keys live in `config/settings.json`, which is gitignored and stays that way. **Never** print a key
into a log, an error message, or the UI. Show "set" / "not set" and a length. Nothing else.

## Job 2 — route the prompt writer through the provider seam

`pipeline/shot_description.py` is hardcoded to Gemini:

```python
def _call_gemini_batch(prompt_text, api_key, model="gemini-2.5-flash")
```

This is the pass that writes every `visual_description`, which becomes the picture. Route it through
`pipeline/llm/factory.py` — there is already a `BaseLLMProvider` interface, one class per provider,
and `get_llm_provider()` reading settings.

- **OpenAI is missing.** Add `pipeline/llm/openai.py` following `deepseek.py` and `gemini.py`
  exactly: same `complete(system, user, json_schema, max_tokens)` signature, same structured-output
  handling, same error surface.
- **`AnthropicProvider` exists but is unverified.** Confirm it works, or say plainly in your report
  that it is untested.
- Keep `gemini-2.5-flash` as the default, so nothing changes for anyone who does not touch a switch.

The description pass already takes the whole script, the niche recipe and the era. None of that
changes — only who is asked.

## Job 3 — take DeepSeek off the planning board

DeepSeek has been returning `402 Payment Required` for weeks and the app carried on producing
videos, because narration is split in Python with **zero LLM calls** (`text_parser.py` ~987) and
copied verbatim. LLM planning is already optional in practice. Make it explicit.

- Add a setting to turn **LLM planning off**, and default it **off**.
- The Settings screen must say what that costs, in plain words:
  - **`voice_steering` per segment is lost.** This is the only real loss.
  - Shot `query` falls back to `extract_keyword`, two or three words. Retrieval prefers
    `visual_description` when there is one (`visuals.py` ~753), so the impact is small.
  - Shots per segment falls back to the rhythm slider, which the owner sets himself.
  - **Segmentation is unaffected.** Say so — he should not have to wonder.

## Job 4 — a dead provider must be visible

A permanent provider error must reach the **UI**, not stderr. Name the provider, the code, and what
it means:

> DeepSeek refused the request: 402 Payment Required. Your account is out of credit. Automatic moved
> to Anthropic.

The fallback may still happen. It must never happen quietly again.

`pipeline/text_parser.py` already classifies these as permanent in its
`permanent = any(code in str(e) ...)` block. Reuse that classification; do not invent a second one.

---

## Traps

1. **Do not weaken a test to make it pass.** The vignette limit was once raised from 0.40 to 0.45
   and reported as "passes cleanly". Every `tests/` diff is read. If an existing test must change,
   quote it before and after and justify it in one sentence.
2. **Do not work in a git worktree** — no gitignored assets there, so render tests always fail.
3. **A stale `cache/` causes phantom failures.** Delete it and re-run before reporting a regression.
4. **Setting `.value` in JS fires no `change` event.** Restore a select, repopulate its dependants,
   then set the dependent value — see `applyUiDefaults()` in `frontend/app.js`.
5. **Inline `style="` attributes in `index.html` are capped at 19**, all dynamic state. Layout
   belongs in `style.css`. A previous pass pushed it to 26 and had to be undone.
6. **The description cache key is at `v5`** (`_scene_hash`) and already carries the niche, recipe,
   script and model. Changing the provider changes the text, and the model is part of the key, so
   this should hold — but verify it, because this exact bug once made two different models return
   byte-identical output.

---

## Tests

- Each provider is built by the factory from its own settings key; an unknown name raises.
- The OpenAI provider returns the same shape as DeepSeek and Gemini for one mocked structured reply.
- A provider switched **off** is never called, including under Automatic.
- Automatic skips a provider returning 402 and uses the next enabled one, and reports which answered.
- The description pass honours the selected provider — two providers, same scene, different text.
- With LLM planning off, a script still segments correctly and still renders.
- No key value appears in any returned payload or log line.
- Defaults hold when nothing is touched.

## What to report

Numbers and literal strings, not adjectives.

1. The literal UI message shown when a provider returns 402, pasted.
2. One structured completion from the new OpenAI provider beside the Gemini one for the same input.
3. Two descriptions for the same scene under two different providers, pasted — proof the switch
   reaches the model rather than the cache.
4. The full suite count. Baseline to match or beat: **462 passed, 1 xfailed, 0 failures**.
5. Whether `library/index.npz` shows as modified, and confirmation you did not restore it.
