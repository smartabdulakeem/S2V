# Niche Visual Type & Structured Prompts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the visual type picked on the planning board actually steer every image prompt, and rebuild those prompts as structured image direction opening with a consistent per-project brief.

**Architecture:** Each series pack already carries a `style_presets` block that nothing reads. We expand it to a niche-specific vocabulary, resolve it at prompt-composition time in place of `style_block`, and replace the raw narration dump with eight named slots filled from regex vocabulary tables. A per-project `project_brief` is drafted once and emitted first in every prompt so a folder of images reads as one film.

**Tech Stack:** Python 3.12, pytest, pywebview 6.2.1, vanilla JS. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-26-niche-visual-type-design.md`

**Environment note:** Python is not on PATH under that name. Every command below uses the full path:
`C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe`
Set `PYTHONIOENCODING=utf-8` before any command that prints prompt text — the Windows console dies on `₦` and `—`, which looks like a failure but is not.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `config/series/*.json` (11 files) | Per-niche vocabulary and calibration data | Modify — add `style_presets`, fix `motivational` calibration |
| `pipeline/prompt_slots.py` | Slot vocabulary tables and the matcher. New module so the tables are editable without touching composition logic | **Create** |
| `pipeline/library.py` | Pack validation, preset resolution, prompt composition, project brief | Modify |
| `pipeline/composer.py` | Treatment resolution from the picked preset | Modify |
| `app.py` | `get_style_presets` API, `visual_type` + `project_brief` persistence | Modify |
| `frontend/index.html` | Visual type select, project brief field | Modify |
| `frontend/app.js` | Repopulate visual type on niche change, pass new fields | Modify |
| `tests/test_series_packs.py` | Every pack on disk validates and resolves | **Create** |
| `tests/test_prompt_slots.py` | Slot matching and composition | **Create** |
| `tests/test_project_brief.py` | Brief drafting, capping, persistence | **Create** |

`pipeline/prompt_slots.py` is a new module rather than more constants in `library.py` because `library.py` is already 1600+ lines; the vocabulary is data the owner will edit often and should not require scrolling past retrieval code.

---

## Task 1: Stop the Motivational niche crashing the planner

`config/series/motivational.json` has 0 `real_queries` and 0 `fake_queries`; `validate_series_pack` requires 10 of each. `get_series_config` re-raises (`pipeline/library.py:183`), so planning with this niche throws `ValueError`. It has 15 `seed_queries` to draw real queries from.

**Files:**
- Create: `tests/test_series_packs.py`
- Modify: `config/series/motivational.json`

- [ ] **Step 1: Write the failing test**

Create `tests/test_series_packs.py`:

```python
"""
Every series pack on disk must validate and resolve.

A pack that fails validation is not a cosmetic problem: get_series_config
re-raises, so selecting that niche crashes the planner.
"""

import glob
import json
import os
import pytest

from pipeline.library import validate_series_pack, get_series_config

PACK_PATHS = sorted(glob.glob(os.path.join("config", "series", "*.json")))
PACK_SLUGS = [os.path.basename(p)[:-5] for p in PACK_PATHS]


def test_there_are_packs_to_check():
    assert len(PACK_PATHS) >= 11, f"expected at least 11 packs, found {len(PACK_PATHS)}"


@pytest.mark.parametrize("path", PACK_PATHS, ids=PACK_SLUGS)
def test_pack_validates(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    errors = validate_series_pack(data)
    assert errors == [], f"{os.path.basename(path)} failed validation: {errors}"


@pytest.mark.parametrize("slug", PACK_SLUGS, ids=PACK_SLUGS)
def test_pack_resolves_without_raising(slug):
    cfg = get_series_config(series_slug=slug)
    assert cfg.get("series_slug"), f"{slug} resolved to a pack with no series_slug"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
"C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_series_packs.py -q
```

Expected: 2 failures, both `motivational` — `test_pack_validates[motivational]` reporting the two calibration errors, and `test_pack_resolves_without_raising[motivational]` raising `ValueError`.

- [ ] **Step 3: Add the missing calibration queries**

Open `config/series/motivational.json` and replace the `"real_queries": []` and `"fake_queries": []` arrays with these. Real queries describe images this niche *should* match; fake queries describe images it must *not*.

```json
    "real_queries": [
      "lone runner climbing a steep hill road at sunrise",
      "weathered hands gripping a barbell before a lift",
      "empty gym at dawn with light through high windows",
      "climber reaching over a rock ledge against open sky",
      "person sitting alone on locker room bench after training",
      "silhouette of a figure walking a long empty road",
      "close on worn running shoes on wet pavement",
      "swimmer pausing at the end of a lane, catching breath",
      "figure standing at a window looking out over a city at dawn",
      "hands writing in a notebook under a single desk lamp"
    ],
    "fake_queries": [
      "medieval siege catapult launching burning rock at a castle wall",
      "underwater coral reef with neon sea anemones and sharks",
      "space shuttle launching into orbit with huge flame plumes",
      "wild grizzly bear hunting salmon in river rapids",
      "futuristic cybernetic android walking through a neon rain city",
      "deep ocean trench with glowing bioluminescent jellyfish",
      "steam locomotive blowing white smoke in a mountain tunnel",
      "formula 1 race car making a sharp turn on track asphalt",
      "alien landscape with two moons over purple crystals",
      "ornate baroque cathedral ceiling fresco with gold leaf"
    ],
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
"C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_series_packs.py -q
```

Expected: all pass (23 tests — 1 count check plus 11 × 2).

- [ ] **Step 5: Verify the crash is actually gone end to end**

```bash
"C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe" -c "import sys; sys.path.insert(0,'.'); from pipeline.library import get_series_config; print(get_series_config(series_slug='motivational')['display_name'])"
```

Expected: prints the pack's display name, no traceback.

- [ ] **Step 6: Commit**

```bash
git add tests/test_series_packs.py config/series/motivational.json
git commit -m "fix(series): motivational pack crashed the planner on selection"
```

---

## Task 2: Resolve a style preset from a pack

A preset value may be a plain string (prompt only) or an object with `prompt` and optional `treatment`. One resolver handles both so no caller needs to know the difference.

**Files:**
- Create: `tests/test_prompt_slots.py`
- Modify: `pipeline/library.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_prompt_slots.py`:

```python
"""Preset resolution and slot-based prompt composition."""

import pytest

from pipeline.library import resolve_style_preset


def test_string_entry_becomes_prompt_with_no_treatment():
    cfg = {"style_presets": {"oil_portrait": "Classical oil portrait, visible brushwork."}}
    out = resolve_style_preset(cfg, "oil_portrait")
    assert out == {"prompt": "Classical oil portrait, visible brushwork.", "treatment": None}


def test_object_entry_carries_its_treatment():
    cfg = {"style_presets": {"evidence_photo": {
        "prompt": "Flash-lit evidence photograph, flat frontal light.",
        "treatment": "documentary",
    }}}
    out = resolve_style_preset(cfg, "evidence_photo")
    assert out["prompt"] == "Flash-lit evidence photograph, flat frontal light."
    assert out["treatment"] == "documentary"


def test_unknown_key_resolves_to_none():
    cfg = {"style_presets": {"oil_portrait": "x"}}
    assert resolve_style_preset(cfg, "no_such_preset") is None


def test_empty_visual_type_resolves_to_none():
    cfg = {"style_presets": {"oil_portrait": "x"}}
    assert resolve_style_preset(cfg, "") is None
    assert resolve_style_preset(cfg, None) is None


def test_malformed_object_resolves_to_none():
    cfg = {"style_presets": {"broken": {"treatment": "documentary"}}}
    assert resolve_style_preset(cfg, "broken") is None
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
"C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_prompt_slots.py -q
```

Expected: collection error — `ImportError: cannot import name 'resolve_style_preset'`.

- [ ] **Step 3: Write the resolver**

In `pipeline/library.py`, immediately above `def compose_gap_prompt(` (currently line 1254), add:

```python
def resolve_style_preset(series_cfg: dict, visual_type: str) -> dict | None:
    """
    The picked visual type, as {"prompt": str, "treatment": str | None}.

    A pack entry is either prose on its own or an object that also names the
    post-processing treatment it maps to, because a preset called
    "evidence_photo" cannot have its treatment inferred from its key.
    Returns None when nothing usable is defined, and callers fall back to
    style_block.
    """
    if not visual_type:
        return None
    presets = (series_cfg or {}).get("style_presets") or {}
    entry = presets.get(visual_type)
    if isinstance(entry, str) and entry.strip():
        return {"prompt": entry.strip(), "treatment": None}
    if isinstance(entry, dict):
        prompt = entry.get("prompt")
        if isinstance(prompt, str) and prompt.strip():
            return {"prompt": prompt.strip(), "treatment": entry.get("treatment")}
    return None
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
"C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_prompt_slots.py -q
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_prompt_slots.py pipeline/library.py
git commit -m "feat(prompts): resolve a style preset from a series pack"
```

---

## Task 3: Author the 55 presets across all 11 packs

The prose is fixed by the spec's "The vocabulary to author" section. Writing it with a script keeps all 55 entries in one reviewable place and avoids 11 hand-edits.

**Files:**
- Modify: `config/series/*.json` (all 11)
- Create: `scripts/author_style_presets.py`

- [ ] **Step 1: Write the authoring script**

Create `scripts/author_style_presets.py`:

```python
"""
Write the per-niche style_presets vocabulary into every series pack.

Idempotent: re-running replaces style_presets wholesale and leaves every other
key untouched. Run from the repo root.
"""

import json
import os
from collections import OrderedDict

PRESETS = {
    "biography": [
        ("portrait_archive", "documentary", "Medium format archival portrait, warm window light, silver halide grain, sitter turned slightly off-camera."),
        ("family_album", "vox_collage", "Aged family album page, overlapping deckle-edged snapshots on black card."),
        ("oil_portrait", "illustration", "Classical oil portrait, visible brushwork, dark umber ground, museum lighting."),
        ("study_silhouette", "silhouette", "Figure silhouetted at a tall study window, dust suspended in the light shaft."),
        ("newsprint_profile", "documentary", "Halftone newspaper profile photograph, coarse dot screen, feature-page crop."),
    ],
    "business_money": [
        ("boardroom_reportage", "documentary", "Corporate reportage photograph, glass and steel, available light, shallow depth of field."),
        ("ledger_macro", "vignette", "Macro of a ledger, banknotes or ticker tape, raking light, fine paper fibre detail."),
        ("editorial_isometric", "illustration", "Editorial isometric illustration of commerce, restrained two-colour palette, clean geometry."),
        ("trading_floor_silhouette", "silhouette", "Silhouetted figures against a bank of glowing market screens."),
        ("vintage_industry", "documentary", "Mid-century industrial archive photograph, warm monochrome, factory or trading hall."),
    ],
    "civil_war": [
        ("wet_plate", "documentary", "Wet-plate collodion field photograph, shallow tonal range, edge vignetting, period uniform detail."),
        ("battlefield_reportage", "documentary", "Restrained battlefield reportage, overcast light, mud and smoke, no heroic posing."),
        ("lithograph", "illustration", "Period lithograph or steel engraving, cross-hatched shading, muted ink wash."),
        ("campfire_silhouette", "silhouette", "Silhouetted figures around a campfire against a dusk treeline."),
        ("letters_collage", "vox_collage", "Collage of folded letters, ration tickets and tintypes on worn linen."),
    ],
    "default": [
        ("documentary_photo", "documentary", "Cinematic documentary photograph, natural directional light, muted palette, fine grain."),
        ("cinematic_still", "vignette", "Anamorphic cinematic still, shallow focus, atmospheric haze."),
        ("editorial_illustration", "illustration", "Editorial illustration, confident line, limited palette, flat colour fields."),
        ("graphic_silhouette", "silhouette", "Strong graphic silhouette against a bright gradient sky."),
        ("paper_collage", "vox_collage", "Cut-paper collage on textured board, layered edges and shadow."),
    ],
    "islamic_history": [
        ("manuscript_illumination", "illustration", "Illuminated manuscript panel, gold leaf, lapis and vermilion, geometric border."),
        ("architectural_plate", "documentary", "Architectural photograph of courtyard, arcade and muqarnas, raking desert light."),
        ("geometric_pattern", "illustration", "Tessellated girih pattern in glazed tile, deep blue and turquoise."),
        ("caravan_silhouette", "silhouette", "Caravan silhouetted on a dune ridge at dusk."),
        ("parchment_archive", "vox_collage", "Aged parchment leaves, tooled leather binding, pressed wax seals."),
    ],
    "motivational": [
        ("golden_hour_figure", "vignette", "Lone figure at golden hour, long shadow, warm rim light, wide horizon."),
        ("summit_silhouette", "silhouette", "Climber silhouetted on a ridge against a bright sky."),
        ("training_reportage", "documentary", "Gritty training-room reportage, sweat and texture, hard directional light."),
        ("cinematic_wide", "vignette", "Anamorphic cinematic wide, shallow focus, atmospheric haze, teal and amber grade."),
        ("bold_graphic", "illustration", "Bold high-contrast poster illustration, limited palette, strong diagonal composition."),
    ],
    "mythology_folklore": [
        ("oil_myth", "illustration", "Romantic-era mythological oil painting, dramatic chiaroscuro, heroic scale."),
        ("woodcut", "illustration", "Folk woodcut print, heavy black line, flat ochre and madder inks."),
        ("misted_landscape", "vignette", "Mist-wrapped ancient landscape, standing stones, low blue light."),
        ("firelit_silhouette", "silhouette", "Storyteller and listeners silhouetted around firelight."),
        ("tapestry", "vox_collage", "Woven medieval tapestry panel, faded wool, millefleurs ground."),
    ],
    "nature_wildlife": [
        ("wildlife_telephoto", "documentary", "Telephoto wildlife photograph, animal sharp against compressed bokeh, early light."),
        ("macro_detail", "vignette", "Extreme macro of feather, scale or leaf vein, dew, razor-thin focal plane."),
        ("aerial_landscape", "documentary", "High aerial of terrain, river braid or migrating herd, natural colour, midday clarity."),
        ("naturalist_plate", "illustration", "Victorian naturalist field-guide plate, watercolour and ink, specimen on cream ground."),
        ("dusk_silhouette", "silhouette", "Animal silhouetted on a ridge against a burning dusk sky."),
    ],
    "space_science": [
        ("telescope_plate", "documentary", "Deep-field telescope plate, nebula filament detail, narrowband colour."),
        ("mission_archival", "documentary", "Archival mission photograph, hard unfiltered sunlight, matte spacecraft surfaces."),
        ("technical_cutaway", "illustration", "Precise technical cutaway, thin clean linework, unannotated."),
        ("lab_reportage", "documentary", "Clean-room or laboratory reportage, cool fluorescent light, instrument detail."),
        ("horizon_silhouette", "silhouette", "Figure or antenna silhouetted against a planetary horizon."),
    ],
    "true_crime": [
        ("evidence_photo", "documentary", "Flash-lit evidence photograph, flat frontal light, scale marker, clinical framing."),
        ("surveillance_still", "vignette", "Grainy surveillance still, low resolution, high-contrast monochrome."),
        ("newspaper_archive", "vox_collage", "Clipped newspaper archive fragments layered on a case file folder."),
        ("courtroom_sketch", "illustration", "Courtroom sketch in coloured pencil and pastel, loose confident line."),
        ("night_exterior", "silhouette", "Figure silhouetted under a sodium streetlight on a wet night street."),
    ],
    "world_military_history": [
        ("combat_reportage", "documentary", "Combat reportage, pushed monochrome film, heavy grain, motion at the frame edges."),
        ("archival_colour", "documentary", "Early colour archival transparency, muted dyes, period materiel detail."),
        ("campaign_plate", "illustration", "Hand-drawn campaign plate, contour hatching, ink and wash."),
        ("trench_silhouette", "silhouette", "Soldiers silhouetted on a trench parapet against flare light."),
        ("propaganda_poster", "illustration", "Period poster illustration, bold flat colour, heavy litho texture."),
    ],
}

SERIES_DIR = os.path.join("config", "series")


def main():
    total = 0
    for slug, rows in PRESETS.items():
        path = os.path.join(SERIES_DIR, f"{slug}.json")
        if not os.path.isfile(path):
            raise SystemExit(f"missing pack: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f, object_pairs_hook=OrderedDict)
        data["style_presets"] = OrderedDict(
            (key, OrderedDict((("prompt", prose), ("treatment", treatment))))
            for key, treatment, prose in rows
        )
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        total += len(rows)
        print(f"{slug}: {len(rows)} presets")
    print(f"total: {total}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

```bash
"C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe" scripts/author_style_presets.py
```

Expected: 11 lines each reporting 5 presets, then `total: 55`.

- [ ] **Step 3: Confirm the packs still validate and still load**

```bash
"C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_series_packs.py -q
```

Expected: all pass. This proves the rewrite did not corrupt any pack.

- [ ] **Step 4: Commit**

```bash
git add scripts/author_style_presets.py config/series/
git commit -m "feat(series): author 55 niche-specific style presets across 11 packs"
```

---

## Task 4: Validate `style_presets` so a malformed pack fails loudly

`style_presets` is load-bearing now. A pack missing it must fail validation rather than silently emitting no style.

**Files:**
- Modify: `pipeline/library.py`
- Modify: `tests/test_series_packs.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_series_packs.py`:

```python
from pipeline.composer import SINGLE_IMAGE_TREATMENTS


def _minimal_pack(**overrides):
    pack = {
        "series_slug": "x", "display_name": "X",
        "world_anchor": "somewhere", "style_block": "a look",
        "negative_block": "no text",
        "voice": {"id": "en-US-RogerNeural"},
        "calibration": {"real_queries": ["q"] * 10, "fake_queries": ["q"] * 10},
        "style_presets": {"a_look": {"prompt": "a look", "treatment": "documentary"}},
    }
    pack.update(overrides)
    return pack


def test_missing_style_presets_is_an_error():
    errors = validate_series_pack(_minimal_pack(style_presets=None))
    assert any("style_presets" in e for e in errors), errors


def test_empty_style_presets_is_an_error():
    errors = validate_series_pack(_minimal_pack(style_presets={}))
    assert any("style_presets" in e for e in errors), errors


def test_entry_without_prompt_is_an_error():
    errors = validate_series_pack(_minimal_pack(style_presets={"a": {"treatment": "documentary"}}))
    assert any("style_presets.a" in e for e in errors), errors


def test_unknown_treatment_is_an_error():
    errors = validate_series_pack(
        _minimal_pack(style_presets={"a": {"prompt": "x", "treatment": "sepia_tone"}})
    )
    assert any("style_presets.a.treatment" in e for e in errors), errors


def test_plain_string_entry_is_accepted():
    assert validate_series_pack(_minimal_pack(style_presets={"a": "just prose"})) == []


@pytest.mark.parametrize("path", PACK_PATHS, ids=PACK_SLUGS)
def test_every_authored_treatment_is_real(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for key, entry in (data.get("style_presets") or {}).items():
        if isinstance(entry, dict) and entry.get("treatment"):
            assert entry["treatment"] in SINGLE_IMAGE_TREATMENTS, \
                f"{os.path.basename(path)}: {key} maps to unknown treatment {entry['treatment']}"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
"C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_series_packs.py -q -k "style_presets or treatment_is_real"
```

Expected: the four error-case tests fail (validation does not yet report `style_presets`). `test_plain_string_entry_is_accepted` and `test_every_authored_treatment_is_real` already pass.

- [ ] **Step 3: Add the validation**

In `pipeline/library.py`, inside `validate_series_pack`, immediately after the `negative_block` check (currently line 96-97), insert:

```python
    presets = pack_data.get("style_presets")
    if not isinstance(presets, dict) or not presets:
        errors.append("series_pack.style_presets: expected a non-empty dictionary")
    else:
        from pipeline.composer import SINGLE_IMAGE_TREATMENTS
        for key, entry in presets.items():
            if isinstance(entry, str):
                if not entry.strip():
                    errors.append(f"series_pack.style_presets.{key}: empty prompt string")
                continue
            if not isinstance(entry, dict):
                errors.append(f"series_pack.style_presets.{key}: expected string or object")
                continue
            prompt = entry.get("prompt")
            if not isinstance(prompt, str) or not prompt.strip():
                errors.append(f"series_pack.style_presets.{key}.prompt: required non-empty string")
            treatment = entry.get("treatment")
            if treatment is not None and treatment not in SINGLE_IMAGE_TREATMENTS:
                errors.append(
                    f"series_pack.style_presets.{key}.treatment: "
                    f"unknown treatment '{treatment}'"
                )
```

The import is function-local so pack validation does not drag the compositor and its Pillow
dependency into every process that only wants to read a pack. (Checked: `pipeline/composer.py`
imports only `pipeline.captions` and `pipeline.validator`, so this is not a circular-import
problem — it is a startup-cost one.)

- [ ] **Step 4: Run the tests to verify they pass**

```bash
"C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_series_packs.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add pipeline/library.py tests/test_series_packs.py
git commit -m "feat(series): validate style_presets, which is load-bearing now"
```

---

## Task 5: The slot vocabulary module

**Files:**
- Create: `pipeline/prompt_slots.py`
- Modify: `tests/test_prompt_slots.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_prompt_slots.py`:

```python
from pipeline.prompt_slots import (
    match_slot, PROMPT_FRAMING, PROMPT_MOTION, PROMPT_GROUND,
    PROMPT_ATMOSPHERE, PROMPT_LIGHT, DEFAULT_FRAMING,
)


def test_match_slot_returns_the_first_matching_phrase():
    assert "pre-dawn" in match_slot(PROMPT_LIGHT, "reaching the valley before dawn")


def test_match_slot_returns_default_when_nothing_matches():
    assert match_slot(PROMPT_LIGHT, "a quiet room", default="none") == "none"


def test_match_slot_returns_none_by_default():
    assert match_slot(PROMPT_LIGHT, "a quiet room") is None


def test_match_slot_is_case_insensitive():
    assert match_slot(PROMPT_LIGHT, "AT MIDNIGHT") is not None


def test_ground_matches_mire():
    assert "waterlogged" in match_slot(PROMPT_GROUND, "horses sank into churned mire")


def test_motion_matches_riding():
    assert "mid-movement" in match_slot(PROMPT_MOTION, "Khalid rode through the night")


def test_atmosphere_matches_smoke():
    assert "smoke" in match_slot(PROMPT_ATMOSPHERE, "mud and smoke over the field")


def test_framing_defaults_to_wide_establishing():
    assert match_slot(PROMPT_FRAMING, "a man on a horse", default=DEFAULT_FRAMING) == DEFAULT_FRAMING


def test_framing_honours_an_explicit_close_shot():
    assert "detail" in match_slot(PROMPT_FRAMING, "close detail of a bridle")


def test_every_table_is_pairs_of_pattern_and_phrase():
    for table in (PROMPT_FRAMING, PROMPT_MOTION, PROMPT_GROUND, PROMPT_ATMOSPHERE, PROMPT_LIGHT):
        for pattern, phrase in table:
            assert isinstance(pattern, str) and pattern
            assert isinstance(phrase, str) and phrase
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
"C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_prompt_slots.py -q
```

Expected: collection error — `ModuleNotFoundError: No module named 'pipeline.prompt_slots'`.

- [ ] **Step 3: Write the module**

Create `pipeline/prompt_slots.py`:

```python
"""
Vocabulary tables for structured image prompts.

Each table is an ordered list of (regex, phrase) pairs. The first pattern that
matches the shot's text contributes its phrase to that slot; a slot that
matches nothing is left out of the prompt entirely rather than emitting filler.

These live in their own module because they are data the owner edits often,
and because pipeline/library.py is already long enough.
"""

import re

#: Camera distance and how the subject sits in the frame.
PROMPT_FRAMING = [
    (r"\b(close|detail|macro|tight)\b", "tight detail shot, shallow plane of focus"),
    (r"\b(aerial|overhead|bird's eye)\b", "high aerial shot looking down"),
    (r"\b(wide|establishing|vista|panorama)\b", "wide establishing shot, subject small in the frame"),
]

#: Used when the shot names no framing of its own.
DEFAULT_FRAMING = "wide establishing shot, subject small in the frame"

#: Whether the scene is moving or held.
PROMPT_MOTION = [
    (r"\b(rode|riding|rides|charge|charging|gallop|advance|advancing|march|marching|fled|fleeing|running)\b",
     "bodies and animals mid-movement, motion blur at the frame edges"),
    (r"\b(stood|standing|waiting|held|holding|watched|watching|silent|still)\b",
     "held still, weight settled, tension in the stance"),
]

#: What the ground underfoot looks like.
PROMPT_GROUND = [
    (r"\b(mire|mud|muddy|churned|flooded|marsh|swamp|bog)\b",
     "churned waterlogged ground, standing water breaking the surface"),
    (r"\b(dune|dunes|sand|desert|arid)\b",
     "wind-scoured sand, drifting grain across the foreground"),
    (r"\b(snow|ice|frozen|frost)\b",
     "snow and frozen ground, breath visible in the cold"),
    (r"\b(rubble|ruins|debris|wreckage)\b",
     "broken rubble underfoot, dust settling between stones"),
]

#: What hangs in the air.
PROMPT_ATMOSPHERE = [
    (r"\b(dust|smoke|smouldering|burning|fire|flame)\b",
     "hanging dust and smoke catching the light"),
    (r"\b(rain|storm|downpour|torrent)\b",
     "rain streaking the air, wet reflective surfaces"),
    (r"\b(mist|fog|haze)\b", "low mist clinging to the ground"),
]

#: Time of day expressed as light a camera would see.
PROMPT_LIGHT = [
    (r"\b(dawn|daybreak|first light|sunrise|before dawn)\b",
     "cold blue pre-dawn light, sun still below the ridge, long low shadows"),
    (r"\b(dusk|sunset|nightfall|evening|twilight)\b",
     "low golden dusk light, long raking shadows, warm highlights against cool shade"),
    (r"\b(night|midnight|moonlit|after dark|nocturnal)\b",
     "deep night, moonlight and torch flame the only sources, deep unlit shadow"),
    (r"\b(noon|midday|blazing sun|high sun)\b",
     "hard overhead midday sun, short black shadows, bleached highlights"),
]


def match_slot(table, text: str, default: str = None) -> str | None:
    """The phrase for the first pattern in `table` that `text` matches."""
    if not text:
        return default
    for pattern, phrase in table:
        if re.search(pattern, text, re.IGNORECASE):
            return phrase
    return default
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
"C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_prompt_slots.py -q
```

Expected: 15 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/prompt_slots.py tests/test_prompt_slots.py
git commit -m "feat(prompts): slot vocabulary tables for structured image direction"
```

---

## Task 6: Draft the per-project brief

Every prompt in a script opens with the same block, so images generated across sessions read as one film. Capped at 30 words because generators weight early tokens heavily.

**Files:**
- Create: `tests/test_project_brief.py`
- Modify: `pipeline/library.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_project_brief.py`:

```python
"""The consistent opening block shared by every prompt in one script."""

from pipeline.library import draft_project_brief, BRIEF_MAX_WORDS


CFG = {"world_anchor": "7th century Arabian Peninsula, early Islamic era"}
SCRIPT = ("Khalid ibn al-Walid rode through the night. Abu Ubaidah held the centre. "
          "Khalid reached the Jordan valley before dawn and Abu Ubaidah followed.")


def test_documentary_treatment_opens_with_documentary_still():
    brief = draft_project_brief("The Battle of the Mud", CFG, SCRIPT, "documentary")
    assert brief.startswith("Documentary still from")


def test_illustration_treatment_opens_with_illustration_plate():
    brief = draft_project_brief("The Battle of the Mud", CFG, SCRIPT, "illustration")
    assert brief.startswith("Illustration plate from")


def test_silhouette_treatment_opens_with_silhouette_study():
    brief = draft_project_brief("X", CFG, SCRIPT, "silhouette")
    assert brief.startswith("Silhouette study from")


def test_unknown_treatment_falls_back_to_documentary_still():
    brief = draft_project_brief("X", CFG, SCRIPT, None)
    assert brief.startswith("Documentary still from")


def test_brief_carries_the_world_anchor():
    brief = draft_project_brief("X", CFG, SCRIPT, "documentary")
    assert "7th century Arabian Peninsula" in brief


def test_brief_names_recurring_figures():
    brief = draft_project_brief("X", CFG, SCRIPT, "documentary")
    assert "Khalid" in brief


def test_a_name_used_once_is_not_treated_as_recurring():
    script = "Khalid rode north. Zayd appeared once. Khalid turned back. Khalid rested."
    brief = draft_project_brief("X", CFG, script, "documentary")
    assert "Zayd" not in brief


def test_the_title_never_appears_verbatim():
    brief = draft_project_brief("The Battle of the Mud", CFG, SCRIPT, "documentary")
    assert "The Battle of the Mud" not in brief


def test_brief_is_capped():
    long_cfg = {"world_anchor": " ".join(["anchor"] * 60)}
    brief = draft_project_brief("X", long_cfg, SCRIPT, "documentary")
    assert len(brief.split()) <= BRIEF_MAX_WORDS


def test_brief_is_stable_for_the_same_inputs():
    a = draft_project_brief("X", CFG, SCRIPT, "documentary")
    b = draft_project_brief("X", CFG, SCRIPT, "documentary")
    assert a == b
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
"C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_project_brief.py -q
```

Expected: collection error — `ImportError: cannot import name 'draft_project_brief'`.

- [ ] **Step 3: Write the drafter**

In `pipeline/library.py`, immediately above `def resolve_style_preset(` from Task 2, add:

```python
#: Generators weight early tokens heavily; an unbounded brief would out-argue
#: the shot's own subject.
BRIEF_MAX_WORDS = 30

#: How each treatment names the kind of picture the film is made of.
BRIEF_OPENERS = {
    "documentary": "Documentary still from",
    "illustration": "Illustration plate from",
    "silhouette": "Silhouette study from",
    "vox_collage": "Collage panel from",
    "vignette": "Cinematic still from",
}

#: Words that start a sentence and are capitalised for that reason alone.
_BRIEF_STOPWORDS = {
    "The", "A", "An", "He", "She", "They", "It", "This", "That", "There",
    "But", "And", "When", "After", "Before", "By", "In", "On", "At", "For",
    "His", "Her", "Their", "Its", "We", "You", "I", "As", "If", "So",
}


def draft_project_brief(title: str, series_cfg: dict, script_text: str,
                        treatment: str = None) -> str:
    """
    The opening block shared by every prompt in one script.

    The title is never emitted: it is metadata, not a picture. What carries
    across shots is the kind of picture, the era and region, and the figures
    who recur often enough to need to look the same in every frame.
    """
    opener = BRIEF_OPENERS.get(treatment or "", BRIEF_OPENERS["documentary"])

    anchor = (series_cfg or {}).get("world_anchor") or ""
    parts = [f"{opener} a film set in {anchor}" if anchor else f"{opener} a documentary film"]

    counts = {}
    for name in re.findall(r"\b[A-Z][a-z]{2,}(?:\s+(?:ibn|bin|al-|el-)[a-zA-Z-]+)*", script_text or ""):
        head = name.split()[0]
        if head in _BRIEF_STOPWORDS:
            continue
        counts[name] = counts.get(name, 0) + 1

    recurring = sorted([n for n, c in counts.items() if c >= 2],
                       key=lambda n: (-counts[n], n))[:3]
    if recurring:
        parts.append("consistent depiction of " + ", ".join(recurring))

    brief = ", ".join(parts)
    words = brief.split()
    if len(words) > BRIEF_MAX_WORDS:
        brief = " ".join(words[:BRIEF_MAX_WORDS])
    return brief.rstrip(" ,")
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
"C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_project_brief.py -q
```

Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add pipeline/library.py tests/test_project_brief.py
git commit -m "feat(prompts): draft a per-project brief that opens every prompt"
```

---

## Task 7: Compose the prompt from slots

Replaces the narration dump. This is where the duplication and mid-phrase truncation die.

**Files:**
- Modify: `pipeline/library.py`
- Modify: `tests/test_prompt_slots.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_prompt_slots.py`:

```python
from pipeline.library import compose_gap_prompt

CTX = ("Khalid ibn al-Walid rode through the night with the advance guard, reaching the "
       "Jordan valley before dawn. The ground at Fahl had been flooded deliberately, and "
       "the horses sank to the knee in churned mire.")


def _prompt(**kw):
    base = dict(shot_query="Khalid ibn al-Walid leading cavalry",
                script_context=CTX, series_slug="islamic_history")
    base.update(kw)
    return compose_gap_prompt(**base)


def test_the_world_anchor_appears_exactly_once():
    out = _prompt(visual_type="architectural_plate")
    assert out.lower().count("7th century arabian peninsula") == 1


def test_the_prompt_does_not_end_mid_phrase():
    out = _prompt(visual_type="architectural_plate")
    assert not out.rstrip().endswith("churned,")
    assert not out.rstrip().endswith(",")


def test_narration_is_not_quoted_verbatim():
    out = _prompt(visual_type="architectural_plate")
    assert "reaching the Jordan valley" not in out


def test_the_picked_preset_supplies_the_medium():
    out = _prompt(visual_type="architectural_plate")
    assert "muqarnas" in out


def test_no_visual_type_falls_back_to_style_block():
    out = _prompt(visual_type=None)
    assert "35mm film" in out


def test_light_and_ground_slots_are_present():
    out = _prompt(visual_type="architectural_plate")
    assert "pre-dawn" in out
    assert "waterlogged" in out


def test_a_bare_shot_with_no_context_still_composes():
    out = compose_gap_prompt(shot_query="a walled city", script_context="",
                             series_slug="islamic_history",
                             visual_type="architectural_plate")
    assert out.endswith(".")
    assert "wide establishing shot" in out
    assert "a walled city" in out


def test_the_brief_opens_the_prompt():
    out = _prompt(visual_type="architectural_plate", project_brief="Documentary still from a film")
    assert out.startswith("Documentary still from a film")


def test_no_negative_block_is_emitted_by_default():
    out = _prompt(visual_type="architectural_plate")
    assert "Negative prompt" not in out
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
"C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_prompt_slots.py -q -k "anchor or mid_phrase or verbatim or medium or fallback or slots_are_present or bare_shot or brief_opens"
```

Expected: several failures — `compose_gap_prompt() got an unexpected keyword argument 'visual_type'`.

- [ ] **Step 3: Rewrite the composer**

In `pipeline/library.py`, replace the whole body of `compose_gap_prompt` (currently lines 1254 to the `return ", ".join(parts)`) with:

```python
def compose_gap_prompt(
    shot_query: str,
    world_anchor: str = None,
    character_bible: dict = None,
    script_context: str = "",
    series_slug: str = None,
    project_title: str = None,
    include_negative: bool = None,
    visual_type: str = None,
    project_brief: str = None,
) -> str:
    """
    A ready-to-use image prompt for one shot, built from named slots.

    Slots, in order: project brief, framing, subject, motion, ground,
    atmosphere, setting, character bible, medium. A slot that matches nothing
    is omitted rather than emitting filler. Narration is never quoted
    verbatim, which is what stops the old 34-word cut chopping prompts
    mid-phrase, and the setting is suppressed when the medium text already
    carries it, which is what stops the world anchor appearing twice.
    """
    from pipeline.prompt_slots import (
        match_slot, PROMPT_FRAMING, PROMPT_MOTION, PROMPT_GROUND,
        PROMPT_ATMOSPHERE, PROMPT_LIGHT, DEFAULT_FRAMING,
    )

    series_cfg = get_series_config(series_slug=series_slug, project_title=project_title)
    blob = f"{shot_query or ''} {script_context or ''}"

    preset = resolve_style_preset(series_cfg, visual_type)
    medium = preset["prompt"] if preset else (series_cfg.get("style_block") or "")

    parts = []

    if project_brief:
        parts.append(project_brief.rstrip(" ,."))

    parts.append(match_slot(PROMPT_FRAMING, shot_query or "", default=DEFAULT_FRAMING))
    parts.append((shot_query or "").strip())

    for table in (PROMPT_MOTION, PROMPT_GROUND, PROMPT_ATMOSPHERE):
        phrase = match_slot(table, blob)
        if phrase:
            parts.append(phrase)

    anchor = world_anchor or series_cfg.get("world_anchor") or ""
    if anchor and anchor.lower() not in medium.lower():
        parts.append(anchor)

    light = match_slot(PROMPT_LIGHT, blob)
    if light:
        parts.append(light)

    if character_bible:
        for char_name, char_desc in character_bible.items():
            pattern = r'\b' + re.escape(char_name) + r'\b'
            if re.search(pattern, shot_query or "", re.IGNORECASE) or \
               (script_context and re.search(pattern, script_context, re.IGNORECASE)):
                parts.append(f"featuring: {char_desc}")

    if medium:
        parts.append(medium.rstrip(" ."))

    if include_negative is None:
        include_negative = bool(_setting("include_negative_prompt", False))
    if include_negative:
        negative_block = series_cfg.get("negative_block")
        if negative_block:
            parts.append(f"Negative prompt: {negative_block}")

    return ", ".join(p for p in parts if p).rstrip(" ,") + "."
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
"C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_prompt_slots.py -q
```

Expected: all pass.

- [ ] **Step 5: Look at a real prompt with your own eyes**

```bash
set PYTHONIOENCODING=utf-8 && "C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe" -c "import sys; sys.path.insert(0,'.'); from pipeline.library import compose_gap_prompt; print(compose_gap_prompt(shot_query='Khalid ibn al-Walid leading cavalry', script_context='Khalid rode through the night, reaching the Jordan valley before dawn. The horses sank to the knee in churned mire.', series_slug='islamic_history', visual_type='architectural_plate'))"
```

Expected: one sentence, roughly 45-60 words, ending in a full stop, with the era stated once and no narration quoted.

- [ ] **Step 6: Run the whole suite — this function has many callers**

```bash
"C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe" -m pytest -q
```

Expected: no failures. If `tests/test_prompt_name_match.py` or `tests/test_description_matching.py` fail, they are asserting on the old prompt shape; read the assertion and update it to the slot shape rather than reverting the composer.

- [ ] **Step 7: Commit**

```bash
git add pipeline/library.py tests/test_prompt_slots.py
git commit -m "feat(prompts): compose from slots, killing duplication and mid-phrase cuts"
```

---

## Task 8: Pass the visual type through, and resolve its treatment

**Files:**
- Modify: `pipeline/library.py` (call sites at 1531, 1563, 1609)
- Modify: `pipeline/composer.py`
- Modify: `tests/test_prompt_slots.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_prompt_slots.py`:

```python
from pipeline.composer import treatment_for_style


def test_preset_object_treatment_wins():
    preset = {"prompt": "x", "treatment": "documentary"}
    assert treatment_for_style("anything", preset=preset) == "documentary"


def test_preset_key_that_is_itself_a_treatment_is_used():
    assert treatment_for_style("", preset=None, visual_type="illustration") == "illustration"


def test_prose_substring_match_still_works():
    assert treatment_for_style("Vox paper-collage") == "vox_collage"


def test_nothing_to_go_on_returns_none():
    assert treatment_for_style("") is None
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
"C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_prompt_slots.py -q -k treatment
```

Expected: `TypeError: treatment_for_style() got an unexpected keyword argument 'preset'`.

- [ ] **Step 3: Extend `treatment_for_style`**

In `pipeline/composer.py`, replace the `treatment_for_style` function (currently at line 190) with:

```python
def treatment_for_style(visual_style: str, preset: dict = None,
                        visual_type: str = None) -> str | None:
    """
    Map the project's look onto a post-processing treatment.

    Order matters: a preset that names its own treatment is authoritative, then
    a preset key that is itself a treatment name, and only then the loose prose
    match that was here before. This is what finally makes the prompt and the
    picture agree — picking courtroom_sketch now yields an illustration prompt
    *and* the illustration treatment.
    """
    if preset and preset.get("treatment") in SINGLE_IMAGE_TREATMENTS:
        return preset["treatment"]

    if visual_type and visual_type in SINGLE_IMAGE_TREATMENTS:
        return visual_type

    if not visual_style:
        return None
    s = visual_style.lower()
    for key, name in (
        ("vox", "vox_collage"), ("collage", "vox_collage"), ("paper", "vox_collage"),
        ("silhouette", "silhouette"),
        ("illustrat", "illustration"), ("drawn", "illustration"), ("painted", "illustration"),
        ("documentary", "documentary"), ("archival", "documentary"), ("vintage", "documentary"),
    ):
        if key in s:
            return name
    return None
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
"C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_prompt_slots.py -q -k treatment
```

Expected: 4 passed.

- [ ] **Step 5: Thread `visual_type` and `project_brief` through the three call sites**

In `pipeline/library.py`, `plan_shots` currently reads project fields near line 1334. Add, directly after the existing `world_anchor` line:

```python
    visual_type = project_info.get("visual_type") or ""
    project_brief = project_info.get("project_brief") or ""
```

Then at each of the three `compose_gap_prompt(` calls (near lines 1531, 1563 and 1609), add these two arguments to the existing argument list:

```python
                    visual_type=visual_type,
                    project_brief=project_brief,
```

- [ ] **Step 6: Verify the whole suite still passes**

```bash
"C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe" -m pytest -q
```

Expected: no failures.

- [ ] **Step 7: Commit**

```bash
git add pipeline/library.py pipeline/composer.py tests/test_prompt_slots.py
git commit -m "feat(prompts): the picked visual type now drives prompt and treatment alike"
```

---

## Task 9: The planning board UI

**Files:**
- Modify: `app.py`
- Modify: `frontend/index.html`
- Modify: `frontend/app.js`

- [ ] **Step 1: Add the presets API**

In `app.py`, immediately after `get_series_packs` (ends line 122), add:

```python
    def get_style_presets(self, series_slug: str = None) -> list:
        """The visual types one niche offers, for the planning board dropdown."""
        try:
            from pipeline.library import get_series_config
            cfg = get_series_config(series_slug=series_slug)
        except Exception:
            return []
        out = []
        for key, entry in (cfg.get("style_presets") or {}).items():
            prompt = entry if isinstance(entry, str) else (entry or {}).get("prompt", "")
            out.append({
                "key": key,
                "label": key.replace("_", " ").title(),
                "prompt": prompt,
            })
        return out
```

- [ ] **Step 2: Verify it returns real data**

```bash
set PYTHONIOENCODING=utf-8 && "C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe" -c "import sys; sys.path.insert(0,'.'); import app; a=app.Api(); [print(p['key'], '|', p['label']) for p in a.get_style_presets('true_crime')]"
```

Expected: five rows, `evidence_photo | Evidence Photo` first.

- [ ] **Step 3: Persist the two new fields**

In `app.py`, change `UI_DEFAULT_KEYS` (line 286) from:

```python
    UI_DEFAULT_KEYS = ("voice", "series_slug", "tone", "visual_style",
                       "captions_enabled", "shot_rhythm_seconds", "formats")
```

to:

```python
    UI_DEFAULT_KEYS = ("voice", "series_slug", "tone", "visual_style", "visual_type",
                       "captions_enabled", "shot_rhythm_seconds", "formats")
```

- [ ] **Step 4: Replace the hardcoded style select**

In `frontend/index.html`, replace lines 119-125 (the `Visual style` label and its three hardcoded options) with:

```html
          <label class="f">Visual type
            <select id="pt-style">
              <!-- Populated from the picked niche's style_presets -->
            </select>
          </label>
```

- [ ] **Step 5: Add the project brief field**

In `frontend/index.html`, directly after the `Script` textarea label (the block containing `id="pt-text"`), add:

```html
      <label class="f" style="flex:1 1 100%">Prompt opening (shared by every image in this film)
        <input type="text" id="pt-brief" placeholder="Drafted automatically when you plan — edit to lock the look across every shot.">
      </label>
```

- [ ] **Step 6: Populate the visual type list when the niche changes**

In `frontend/app.js`, at the end of `loadSeriesPacks()` (after the `seriesPacks.forEach` block, before the closing brace), add:

```javascript
  select.addEventListener("change", loadStylePresets);
  await loadStylePresets();
}

// ── Visual Types ─────────────────────────────────────────────────────────────
async function loadStylePresets() {
  const sel = document.getElementById("pt-style");
  const slug = document.getElementById("pt-series-slug").value;
  if (!sel) return;

  let presets = [];
  if (!isWebMode && window.pywebview.api.get_style_presets) {
    try {
      presets = await window.pywebview.api.get_style_presets(slug);
    } catch (e) {
      console.error("Failed to load style presets:", e);
    }
  }

  sel.innerHTML = "";
  if (!presets.length) {
    sel.appendChild(new Option("Pack default", ""));
    return;
  }
  presets.forEach(p => {
    const opt = new Option(p.label, p.key);
    opt.title = p.prompt;
    sel.appendChild(opt);
  });
```

Note the added `}` closes `loadSeriesPacks`; the new function follows it.

- [ ] **Step 7: Stamp the new fields onto the planned script**

The desktop path does not build a payload object — `planStoryboard` calls
`parse_plain_text(text, title, voice, filename, style, format, "", "", tone)` with positional
arguments, and the project dict is assembled inside `pipeline/text_parser.py`. Threading two more
arguments through two parser signatures is not worth it; stamp the fields on the result instead,
where `plan_shots` will read them.

In `frontend/app.js`, in `window.onParseComplete` (line 647), directly after
`currentScriptData = result.script_data;` (line 653), insert:

```javascript
    // The planner does not know about these two, so attach them here, before the
    // draft is saved and before coverage is planned — plan_shots reads them off
    // project and every prompt in this script then opens the same way.
    currentScriptData.project = currentScriptData.project || {};
    currentScriptData.project.visual_type = document.getElementById("pt-style").value || "";
    const briefEl = document.getElementById("pt-brief");
    if (briefEl && briefEl.value.trim()) {
      currentScriptData.project.project_brief = briefEl.value.trim();
    }
```

Order matters: this must sit above the existing `await saveDraftScript(true);` so the fields are
persisted, and above `await refreshStoryboardCoverage();` so the first coverage pass already has them.

- [ ] **Step 7b: Show the drafted brief back to the user**

`ensure_project_brief` (Task 10) writes its draft onto `project`. Reflect it into the field so it
can be edited. In `frontend/app.js`, inside `refreshStoryboardCoverage()`, after the coverage
result is assigned, add:

```javascript
  const briefBox = document.getElementById("pt-brief");
  if (briefBox && !briefBox.value.trim() && currentScriptData?.project?.project_brief) {
    briefBox.value = currentScriptData.project.project_brief;
  }
```

- [ ] **Step 8: Add `visual_type` to the remembered fields**

In `frontend/app.js`, change `UI_FIELDS` (line 104) from:

```javascript
const UI_FIELDS = {
  voice: "pt-voice", series_slug: "pt-series-slug",
  tone: "pt-tone", visual_style: "pt-style",
};
```

to:

```javascript
const UI_FIELDS = {
  voice: "pt-voice", series_slug: "pt-series-slug",
  tone: "pt-tone", visual_type: "pt-style",
};
```

- [ ] **Step 9: Check the JavaScript parses**

```bash
node --check frontend/app.js
```

Expected: no output, exit 0.

- [ ] **Step 10: Run the app and confirm the dropdown reacts**

```bash
run.bat
```

On the Script screen: switch the Series Pack between **True Crime** and **Nature & Wildlife**. The Visual type list must change from `Evidence Photo / Surveillance Still / Newspaper Archive / Courtroom Sketch / Night Exterior` to `Wildlife Telephoto / Macro Detail / Aerial Landscape / Naturalist Plate / Dusk Silhouette`. Select **Motivational** and plan a short script — it must not raise.

- [ ] **Step 11: Commit**

```bash
git add app.py frontend/index.html frontend/app.js
git commit -m "feat(ui): pick a visual type per niche and a shared prompt opening"
```

---

## Task 10: Draft the brief automatically during planning

**Files:**
- Modify: `pipeline/library.py`
- Modify: `tests/test_project_brief.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_project_brief.py`:

```python
from pipeline.library import ensure_project_brief


def test_a_missing_brief_is_drafted():
    info = {"title": "The Battle of the Mud", "series_slug": "islamic_history",
            "visual_type": "architectural_plate"}
    out = ensure_project_brief(info, SCRIPT)
    assert out.startswith("Documentary still from")


def test_an_existing_brief_is_left_alone():
    info = {"title": "X", "series_slug": "islamic_history",
            "visual_type": "architectural_plate",
            "project_brief": "My own wording, untouched"}
    assert ensure_project_brief(info, SCRIPT) == "My own wording, untouched"


def test_a_blank_brief_is_treated_as_missing():
    info = {"title": "X", "series_slug": "islamic_history",
            "visual_type": "architectural_plate", "project_brief": "   "}
    assert ensure_project_brief(info, SCRIPT).startswith("Documentary still from")
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
"C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_project_brief.py -q
```

Expected: `ImportError: cannot import name 'ensure_project_brief'`.

- [ ] **Step 3: Write it**

In `pipeline/library.py`, directly below `draft_project_brief`, add:

```python
def ensure_project_brief(project_info: dict, script_text: str = "") -> str:
    """
    The project's brief, drafted on first use and never overwritten after.

    A hand-edited brief has to survive re-planning, or the owner would lose
    their wording every time they adjusted the shot rhythm.
    """
    existing = (project_info or {}).get("project_brief") or ""
    if existing.strip():
        return existing.strip()

    slug = (project_info or {}).get("series_slug")
    try:
        cfg = get_series_config(series_slug=slug)
    except Exception:
        cfg = {}

    visual_type = (project_info or {}).get("visual_type") or ""
    preset = resolve_style_preset(cfg, visual_type)
    treatment = preset.get("treatment") if preset else None
    if not treatment and visual_type:
        from pipeline.composer import SINGLE_IMAGE_TREATMENTS
        if visual_type in SINGLE_IMAGE_TREATMENTS:
            treatment = visual_type

    return draft_project_brief(
        (project_info or {}).get("title", ""), cfg, script_text, treatment
    )
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
"C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe" -m pytest tests/test_project_brief.py -q
```

Expected: 13 passed.

- [ ] **Step 5: Call it from `plan_shots`**

In `pipeline/library.py`, replace the `project_brief` line added in Task 8 Step 5 with:

```python
    project_brief = ensure_project_brief(
        project_info,
        " ".join(seg.get("narration", "") for seg in script_data.get("segments", [])),
    )
    project_info["project_brief"] = project_brief
```

- [ ] **Step 6: Confirm every prompt in one script opens identically**

```bash
set PYTHONIOENCODING=utf-8 && "C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe" -c "import sys,glob,json; sys.path.insert(0,'.'); from pipeline.library import plan_shots; d=json.load(open(sorted(glob.glob('samples/*.json'))[0],encoding='utf-8')); d.setdefault('project',{})['visual_type']='architectural_plate'; d['project']['series_slug']='islamic_history'; r=plan_shots(d); ps=[x['composed_prompt'] for x in r['shot_reports'] if x.get('composed_prompt')]; op=set(p.split(',')[0] for p in ps); print('shots:',len(ps)); print('distinct openings:',len(op)); print(list(op)[0][:80])"
```

Expected: `distinct openings: 1`.

- [ ] **Step 7: Run the whole suite**

```bash
"C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe" -m pytest -q
```

Expected: no failures.

- [ ] **Step 8: Commit**

```bash
git add pipeline/library.py tests/test_project_brief.py
git commit -m "feat(prompts): draft the project brief during planning, keep edits"
```

---

## Task 11: End-to-end check on a real film

No code. This is the step that catches what tests cannot, and ROADMAP B1 exists because it was skipped before.

- [ ] **Step 1: Export a prompt sheet**

Launch `run.bat`, load a real script, pick a niche and a visual type, plan the storyboard, then press **Copy all prompts**.

- [ ] **Step 2: Read the first three prompts and confirm all six**

1. every prompt opens with the same brief
2. the era appears once per prompt, not twice
3. no prompt ends mid-phrase or on a comma
4. the medium text matches the visual type you picked
5. no `Negative prompt:` text anywhere
6. the numbering is intact — `<tag>1.`, `<tag>2.`, …

- [ ] **Step 3: Generate three images and drop them in a folder**

Name them `<tag>1_…`, `<tag>2_…`, `<tag>3_…`, point the app at the folder, and confirm each lands on its own shot.

- [ ] **Step 4: Update the roadmap**

In `ROADMAP.md`, add a row recording that the niche→visual-type link is closed, with the measured prompt length before and after.

- [ ] **Step 5: Commit**

```bash
git add ROADMAP.md
git commit -m "docs: record the visual type link as verified end to end"
```

---

## Out of scope

- The image-count floor (ROADMAP C1) — unrelated, tracked separately.
- Per-shot visual type override.
- Any change to `match_shots_by_number` or the numbered-folder round-trip.
- An LLM pass over prompts — rejected in the spec in favour of offline slots.
