# Brief: pick your AI, and be told when it fails

Hand this whole file to Antigravity.

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget` — stay on it. **Commit** when done. **Do not push.**
**Never** run `git add -A` — it stages ~816 MB including two 310 MB ONNX models. Stage explicit
paths only.
**Never** run `git checkout -- library/index.npz`. The suite rewrites it; restoring it once cost
170 images their searchability. If it shows as modified, leave it and say so.

---

## Why

The owner spent days believing the app ignored his prompts. It did not. **DeepSeek had been
returning `HTTP 402 Payment Required` and the app said nothing** — it caught the error, printed to
stderr where no user looks, and silently dropped to two-word keyword planning. Measured live:

```
LLM batch planning error on segments 1-5 (attempt 1/3): HTTP Error 402: Payment Required
  Permanent provider error — not retrying. Falling back to keyword-based planning
```

He wants two things: to choose which AI does the work, and to be told when one is not working.

---

## Job 1 — more providers, chosen from the UI

`pipeline/llm/factory.py` already has the seam. `get_llm_provider()` reads `llm_provider` from
settings and returns DeepSeek, Gemini or Anthropic; there is a `BaseLLMProvider` interface and one
class per provider in `pipeline/llm/`.

Two gaps:

1. **OpenAI is missing.** Add `pipeline/llm/openai.py` following the existing
   `pipeline/llm/deepseek.py` and `pipeline/llm/gemini.py` exactly — same `complete(system, user,
   json_schema, max_tokens)` signature, same structured-output handling, same error surface. Wire it
   into the factory as `"openai"`. `AnthropicProvider` already exists; verify it works and is
   reachable, or say plainly that it is untested.
2. **Nothing in the UI picks one.** Settings → **Keys & services** holds the key fields. Add:
   - a key field per provider (OpenAI and Anthropic alongside the existing DeepSeek and Google)
   - a **planning model** dropdown naming the provider *and* the model
   - a **description model** dropdown, separate — see Job 2

Keys live in `config/settings.json`, which is gitignored and must stay that way. **Never print a key
to a log, an error message, or the UI.** Show "set" or "not set" and a length, nothing more.

## Job 2 — the description pass is a second, separate choice

`pipeline/shot_description.py` is hardcoded to Gemini:

```python
def _call_gemini_batch(prompt_text, api_key, model="gemini-2.5-flash")
```

It is the model that actually writes what the picture shows, and today it is the *only* one doing so
while DeepSeek is dead. It must be selectable independently of the planner: someone may want a cheap
planner and a strong describer, or the reverse.

Route it through the same `BaseLLMProvider` seam rather than calling Gemini's endpoint directly.
Keep `gemini-2.5-flash` as the default so nothing changes for anyone who does not touch it.

**Note:** `gemini-2.5-pro` returns **404 Not Found** on this account. Do not offer a model in the
dropdown without confirming the account can call it — list the models the key actually supports, or
validate on selection and say so.

## Job 3 — a dead provider must be visible

This is the part that cost the owner a week.

- A permanent provider error — **401, 402, 403, 404** — must reach the **UI**, not stderr. Name the
  provider, the code, and what it means in plain words: `DeepSeek refused the request: 402 Payment
  Required. Your account is out of credit. Planning fell back to keyword matching.`
- The fallback may still happen. It must never happen **quietly**.
- Add a **Test** button per provider in Settings that makes one cheap call and reports the real
  result — working, bad key, or out of credit.

The existing retry logic already classifies these as permanent and skips retrying
(`pipeline/text_parser.py`, the `permanent = any(code in str(e) ...)` block). Reuse that
classification; do not invent a second one.

---

## Traps

1. **Do not weaken a test to make it pass.** The vignette limit was once raised from 0.40 to 0.45
   and reported as "passes cleanly". Every `tests/` diff is read. If an existing test must change,
   quote it before and after and justify it in one sentence.
2. **Do not work in a git worktree** — no gitignored assets there, so render tests always fail.
3. **A stale `cache/` causes phantom failures.** Delete it and re-run before reporting a regression.
4. **Setting `.value` in JS fires no `change` event.** Restore a select, repopulate its dependants,
   then set the dependent value — see `applyUiDefaults()` in `frontend/app.js`.
5. **Inline `style="` attributes in `index.html` are capped at 19** and all nineteen are dynamic
   state. Layout belongs in `style.css`. A previous pass pushed this to 26 and had to be undone.
6. **The description cache key is at `v5`** and already carries the model
   (`_scene_hash` in `pipeline/shot_description.py`). If a provider change alters what the pass
   produces, bump it — or the previous provider's answers are served back and the change looks
   like a no-op. This exact bug made flash and pro return byte-identical output.

---

## Tests

- Each provider is constructed by the factory from its own settings key, and an unknown name raises.
- The OpenAI provider returns the same shape as DeepSeek and Gemini for one mocked structured reply.
- The description pass honours the configured description model, independently of the planner.
- A 402 from the planner produces a user-visible message naming the provider and the code — assert
  on the payload the UI receives, not on stderr.
- Defaults unchanged: no settings edited, planner is DeepSeek, describer is `gemini-2.5-flash`.
- No key value ever appears in any returned payload or log line.

## What to report

1. The literal UI message shown when a provider returns 402, pasted.
2. One structured completion from the new OpenAI provider, pasted, beside the DeepSeek one for the
   same input.
3. Confirmation that a switched description model actually changes the generated text — two
   descriptions for the same scene under two models, pasted. This is the check the `v5` key exists
   to make possible.
4. The full suite count. Baseline to match or beat: **462 passed, 1 xfailed, 0 failures**.
5. Whether `library/index.npz` shows as modified, and confirmation you did not restore it.
