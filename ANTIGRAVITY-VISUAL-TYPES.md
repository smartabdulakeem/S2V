# Brief: the visual type list, and the death of Medium and Palette

Hand this whole file to Antigravity.

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget` — stay on it. **Commit** when done. **Do not push.**
**Never** run `git add -A` — it stages ~816 MB including two 310 MB ONNX models. Stage explicit
paths only.
**Never** run `git checkout -- library/index.npz`. Running the test suite rewrites that file. It
was restored twice during the layout work and cost 170 images their searchability. If it shows as
modified, leave it alone and say so in your report.

---

## The request

> "What I'm seeing here is mostly redundant. Most of them are not useful. What should be there is
> just the niche name and the visual type — like 3D realistic photo — which should be one box,
> where the user can create as many as possible for this particular niche. Everything you need
> should be there if a user wants to edit, add to it, or remove. The era is also useful, for
> consistency. And the negative box should be kept, but optional, as well as the era. The prompt
> box will do the heavy lifting."

---

## What already exists — do not rebuild it

All ten packs in `config/series/` already define `style_presets`. `biography.json` has five:

```json
"style_presets": {
  "portrait_archive": {
    "prompt": "Medium format archival portrait, warm window light, silver halide grain...",
    "treatment": "documentary"
  },
  "oil_portrait": {
    "prompt": "Classical oil portrait, visible brushwork...",
    "treatment": "illustration"
  }
}
```

`style_presets_for()` (`pipeline/library.py` ~1856) merges those over six `UNIVERSAL_STYLE_PRESETS`.
`resolve_style_preset()` turns a picked key into `{prompt, treatment}`. `build_image_prompt()`
already lets a picked visual type **replace** `medium_block` + `palette_block` entirely.

So the engine is built. **Two things are missing**, and they are the whole job:

1. No UI to create, edit, reorder or remove a visual type.
2. `style_presets` is absent from the nine `allowed_keys` in `save_series_override()`
   (`pipeline/library.py` ~245), so a custom list cannot be saved for a niche.

---

## The panel, after

| Field | State |
|---|---|
| Niche + New niche | unchanged |
| Display name | unchanged |
| **Visual types** | **new** — the list |
| Era | kept, optional |
| Negative prompt | kept, optional |
| Prompt recipe | unchanged |

**Delete from the panel:** Brief subject, Medium, Palette. Their inputs are
`#niche-brief-subject-input`, `#niche-medium-input`, `#niche-palette-input`
(`frontend/index.html` lines 514, 521, 524).

Each visual type row shows: **name**, **description**, **up/down** to reorder, **remove**. An
"Add visual type" button sits under the list. Biography opens with 11 rows — its own five, then
the six universal ones — and every one is editable and deletable.

---

## The work

### 1. Storage shape

An override's `style_presets` is the **complete** list for that niche, not a patch. JSON object
order is the list order.

```json
"style_presets": {
  "three_d_realistic_photo": {
    "label": "3D realistic photo",
    "prompt": "3D render, soft global illumination, physically based materials, shallow depth of field.",
    "treatment": "none"
  }
}
```

`label` is new and is what the user typed. Without it, a key like `three_d_realistic_photo` renders
as "Three D Realistic Photo" through the title-case fallback in `app.py`. New types written by the
user get `"treatment": "none"`.

### 2. `pipeline/library.py`

- Add `"style_presets"` to `allowed_keys` in `save_series_override()` (~245).
- Extend pack validation (~93–108): `style_presets` must be a dict; each value a dict with a
  non-empty string `prompt`, and optional string `label` and `treatment`.
- **An override's list is authoritative.** `style_presets_for()` currently always merges the
  universals underneath. When the list came from an override, the merge must be skipped — otherwise
  deleting a universal type does not stick, it reappears on the next load. Have
  `get_series_config()` set `style_presets_is_override: True` on the merged config when the
  override file supplied the key, and have `style_presets_for()` return the list as-is in that
  case. A niche with no override keeps merging exactly as it does today.
- **Pack default.** In `build_image_prompt()` (~1972), an empty `visual_type` falls back to
  `medium_block` + `palette_block`, then `style_block`. It must instead resolve to the **first
  entry** of `style_presets_for(series_cfg)`. Keep the old fallback only for the case where the
  list is empty.
- `create_user_niche()` (~360) must seed `style_presets` from the base slug so a new niche does not
  start with nothing.

**Do not touch `style_block`.** It still feeds the planner system prompt in
`pipeline/text_parser.py` (~988) whenever a niche has no recipe. `medium_block` and `palette_block`
stay in the pack files; they simply stop being read by the default path.

### 3. `app.py`

- `get_niche_style()` (~149) must also return the resolved `style_presets` list, in order, each
  entry carrying `key`, `label`, `prompt`, `treatment`, so the panel can render it.
- `get_style_presets()` (~257) must prefer a stored `label` over `STYLE_LABEL_OVERRIDES` and over
  the title-case fallback.
- `preview_niche_prompt()` (~215) takes `medium_block` and `palette_block` parameters that are
  about to have no UI. Replace them with the selected visual type.

### 4. `frontend/`

- `index.html`: remove the three fields, add the list and its Add button.
- `app.js`: render the rows, wire add / edit / delete / reorder, and include `style_presets` in the
  `overrides` object in `saveNicheStyle()` (~901). Update `updateNichePreview()` — it currently
  builds its preview from medium + palette.

### 5. `pipeline/composer.py`

Bump the shot cache key from **`v7` to `v8`** in `_get_shot_cache_key()` (~334). The literal lives
at line ~355:

```python
raw = (f"v7|{query_or_pin}|{dur_str}|{motion}|{treatment}|{res_str}|{fps}|"
       f"{default_treatment or ''}|{style_key}")
```

Add a `# v8:` line to the comment block above it, in the style of v2–v7.

This is not optional. The prompt text itself is **not** in the key — only `query_or_pin` and
`default_treatment` are. Pack default now resolves to different prompt text while the query and
often the treatment stay identical, so without the bump every cached clip from the old behaviour is
served straight back and the whole change looks like it did nothing.

---

## Traps

1. **`visual_style` is prose, `visual_type` is a key.** The board must send the key and never the
   label. A leaked label ends up inside the image prompt.
2. **Setting `.value` in JS fires no `change` event.** Restore the niche, `await
   loadStylePresets()`, then any dependent dropdown.
3. **Key generation must be stable and must not collide.** "3D realistic photo" and
   "3D Realistic Photo" cannot both claim the same key and silently overwrite one another. Renaming
   a type must not orphan a project that already stored the old key.
4. **A stale `cache/` causes phantom test failures.** If a render test fails for no reason a diff
   explains, delete `cache/` and re-run before reporting it as a regression.
5. **Do not weaken a test to make it pass.** The vignette limit was raised from 0.40 to 0.45 in an
   earlier pass and reported as "passes cleanly". Every `tests/` diff is read.
6. **Do not work in a git worktree.** It has no gitignored assets (`vendor/ffmpeg`,
   `library/images`), so render tests always fail there.

---

## Tests to add

New file `tests/test_visual_types.py`:

- An override's list **replaces** rather than merges — delete a universal type, reload, it stays
  gone.
- A niche with **no** override still merges the six universals (regression guard).
- Empty `visual_type` resolves to the **first** entry, and reordering changes which one wins.
- Save then load round trip through `save_series_override()` preserves order, label and treatment.
- Key generation is stable and collision-safe.
- A user-created niche is seeded with its base's list.

---

## What to report

Numbers, not adjectives.

1. The literal JSON written to `config/series_overrides/biography.json` after adding one type,
   renaming another and deleting a universal one. Paste the file.
2. The image prompt generated for one shot with `visual_type` empty, **before and after**, for the
   same niche and script. Paste both strings.
3. The full suite count. Baseline to match or beat: **430 passed, 1 xfailed, 0 failures**
   (~9 minutes).
4. Whether `library/index.npz` shows as modified, and confirmation you did not restore it.
