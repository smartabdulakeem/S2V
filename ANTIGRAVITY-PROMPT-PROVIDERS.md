# Brief: choose the AI that writes the prompts, or write them yourself

Hand this whole file to Antigravity. **This replaces `ANTIGRAVITY-PROVIDERS.md`** — that one was
written when the planner still mattered. Delete it.

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget` — stay on it. **Commit** when done. **Do not push.**
**Never** run `git add -A` — it stages ~816 MB including two 310 MB ONNX models. Stage explicit
paths only.
**Never** run `git checkout -- library/index.npz`. The suite rewrites it; restoring it once cost
170 images their searchability. If it shows as modified, leave it and say so.

---

## What the owner wants

> "When I bring a script, the app should be able to give me text-to-image prompts that I can paste
> in a folder, and the app will pick them in the right order. Two ways: one manual from external
> work, and the second, remove DeepSeek for planning. All the AI models I want to add now are for
> writing the image prompts."

Two routes to the same picture, and he wants both:

1. **A chosen AI writes the prompts** — his own OpenAI or Anthropic key, with a switch per provider
   and an **Automatic** option at the top.
2. **He writes them himself** — paste finished prompts on the **Script screen**, pick a folder, and
   the app binds them in order.

The board already does route 2. The Script screen does not. That is the gap.

---

## Job 1 — the manual route, on the Script screen

**This is the one he cares about most. Do it first.**

The Storyboard already has *Paste External Prompts & Match Folder Images*, backed by
`apply_external_prompts()` in `pipeline/library.py` (~1272): prompts separated by blank lines,
prompt *i* binds to shot *i*, images in the working folder match by leading number
(`3_x.jpg` → shot 3), and a mapping table is shown before rendering. A bound prompt is stored as
`prompt_override` and used **verbatim** — `composed = override_prompt` in `library.py` (~2313)
bypasses the composer entirely, so no framing, era or visual type is appended.

Add the same thing to the **Script screen**, beside the script box:

- a **text-to-image prompts** textarea, blank-line separated, same format as the board's
- the working-folder picker already there (`#btn-working-folder`, `index.html:48`) selects the folder
- on plan, bind the pasted prompts to the shots in order and show the same mapping table

Reuse `apply_external_prompts()`. Do not write a second implementation. If binding on the Script
screen turns out to fight the planning flow, say so plainly in the report and leave the board's
version as the only one rather than shipping a half-working second copy.

**Shot count must be honest.** If he pastes 40 prompts and the script cuts to 22 shots, the extra
prompts have nowhere to go. Say so on screen, before rendering, with both numbers.

## Job 2 — `image_prompts.txt` is the manual deliverable, and it is currently broken

`initialize_project_sourcing()` in `pipeline/visuals.py` (~939) already writes one
`image_prompts.txt` per project "to support offline manual visuals generation". This is exactly the
file he wants to take away and generate images from. Today it reads:

```
Segment 1: Adam ever walked, cinematic medium shot, subject filling much of the frame, ...
Segment 2: Adam ever walked, cinematic medium shot, subject filling much of the frame, ...
Segment 3: according reports corruption, cinematic medium shot, subject filling much of the frame, ...
```

Three faults:

1. **Every line carries the same framing.** `compose_gap_prompt` is called at `visuals.py` ~902
   **without `shot_position`**, so `default_framing_for(None)` returns cycle entry 0 every time. Pass
   the shot's index across the whole film so the four-entry cycle actually varies.
2. **The subject is `extract_keyword` output**, not the shot's `visual_description`. Prefer the
   description whenever there is one — the composer already does this; the export must too.
3. **Consecutive segments repeat the same line** because they share a keyword. Once (2) is fixed
   this mostly resolves; verify it does.

The file must be numbered so the number matches the shot the image comes back to
(`1.jpg` → shot 1), consistent with how `apply_external_prompts` matches folder images.

## Job 3 — his own key, per-provider switch, Automatic at the top

Settings → **Keys & services**. The model being chosen here is the one that **writes the image
prompt text** (`pipeline/shot_description.py`), not an image generator.

Layout, top to bottom:

```
Prompt writer
  ( ) Automatic          use the first working provider in this list
  [x] Anthropic  Claude          key: ●●●●  [Test]
  [ ] OpenAI     gpt-4o          key: ●●●●  [Test]
  [x] Google     gemini-2.5-flash key: ●●●●  [Test]
```

- One **on/off switch per provider**, and a **model name** per provider.
- **Automatic** sits at the very top. It means: try the enabled providers in listed order, and on a
  permanent failure (**401, 402, 403, 404**) move to the next one and record which was used. It does
  not mean "guess".
- A **Test** button per provider makes one cheap call and reports the true result: working, bad key,
  or out of credit.
- Keys live in `config/settings.json`, which is gitignored and stays that way. **Never** print a key
  to a log, an error, or the UI — show "set" / "not set" and a length only.

`pipeline/llm/factory.py` already has the seam: a `BaseLLMProvider` interface, one class per
provider, and `get_llm_provider()` reading `llm_provider` from settings. `AnthropicProvider` exists;
verify it works or say plainly it is untested. **OpenAI is missing — add `pipeline/llm/openai.py`**
following `deepseek.py` and `gemini.py` exactly.

Then route `shot_description.py` through that seam instead of calling Gemini's endpoint directly.
Keep `gemini-2.5-flash` as the default so nothing changes for anyone who does not touch it.

**Anthropic does not generate images.** It writes prompt text only. Do not offer it as an image
generator anywhere in this UI. **`gemini-2.5-pro` returns 404 on this account** — do not list a
model without confirming the key can call it.

## Job 4 — planning without an LLM must be a supported choice, not an accident

DeepSeek has been dead on `402 Payment Required` for weeks and the app kept producing videos, so
LLM planning is already optional in practice. Make it explicit: a setting to turn LLM planning
**off**, defaulting to its current behaviour.

What is genuinely lost when it is off, so the UI can say so honestly:

- **`voice_steering` per segment** — narration tone steering. This is the only real loss.
- **shot `query`** falls back to `extract_keyword`, two or three words. Retrieval prefers
  `visual_description` when present (`visuals.py` ~753), so the impact is small but not zero.
- **shots per segment** falls back to the rhythm slider, which the owner sets himself anyway.

Segmentation is **not** affected: narration is split in Python with zero LLM calls
(`text_parser.py` ~987) and copied verbatim. Say this on screen — the owner should not have to guess
what he is giving up.

---

## Traps

1. **Do not weaken a test to make it pass.** The vignette limit was once raised from 0.40 to 0.45
   and reported as "passes cleanly". Every `tests/` diff is read. If an existing test must change,
   quote it before and after and justify it in one sentence.
2. **Do not work in a git worktree** — no gitignored assets there, so render tests always fail.
3. **A stale `cache/` causes phantom failures.** Delete it and re-run before reporting a regression.
4. **Setting `.value` in JS fires no `change` event.** Restore a select, repopulate its dependants,
   then set the dependent value — see `applyUiDefaults()` in `frontend/app.js`.
5. **Inline `style="` attributes in `index.html` are capped at 19**, all of them dynamic state.
   Layout belongs in `style.css`. A previous pass pushed it to 26 and had to be undone.
6. **The description cache key is at `v5`** (`_scene_hash`) and carries the niche, the recipe, the
   script and the model. If a provider change alters what the pass produces, bump it — or the
   previous provider's answers come back and the change looks like a no-op. This exact bug made two
   different models return byte-identical text.
7. **A pasted prompt must stay verbatim.** Nothing may be appended to `prompt_override`. That is the
   whole point of the manual route.

---

## Tests

- A prompt pasted on the Script screen reaches the shot as `prompt_override` and is rendered
  **unchanged** — no framing, era or visual type appended.
- More prompts than shots, and fewer prompts than shots, both report the true counts rather than
  binding silently.
- `image_prompts.txt` uses each shot's `visual_description` when present, and its framing varies
  across the film rather than repeating one phrase.
- Automatic skips a provider that returns 402 and uses the next enabled one, and reports which.
- A provider switched off is never called.
- Each provider is built by the factory from its own key; an unknown name raises.
- No key value appears in any returned payload or log line.
- Defaults unchanged when no setting is touched.

## What to report

Numbers and literal strings.

1. `image_prompts.txt` for one project, **before and after**, first eight lines of each, pasted.
2. One prompt pasted on the Script screen, and the exact string that reached the image model —
   they must be identical.
3. The Automatic path with a dead provider first in the list: which provider was used, and the
   message shown.
4. The full suite count. Baseline to match or beat: **462 passed, 1 xfailed, 0 failures**.
5. Whether `library/index.npz` shows as modified, and confirmation you did not restore it.
