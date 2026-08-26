# Niche → Visual Type → Image Prompt

**Date:** 2026-08-26
**Status:** Approved, not yet implemented
**Area:** Planning board, series packs, prompt composition

---

## The problem

Picking a visual style for a film changes nothing about the image prompt it produces.

Every one of the 11 series packs in `config/series/` already defines a `style_presets`
block — named visual types written in that niche's own language:

```json
"style_presets": {
  "vintage_documentary": "Medium format portrait archive photo, warm window lighting…",
  "illustration": "Classical oil portrait or engraved charcoal biography portrait.",
  "silhouette": "Thoughtful silhouette of figure by tall window looking outside."
}
```

**`style_presets` is never read.** Grepping the tree for it returns hits only inside the
JSON files themselves — no Python, no JavaScript. It is dead data in all 11 packs.

What actually reaches a prompt is `world_anchor` + `style_block` + `negative_block`
(`pipeline/library.py:1299`). Those are one-per-niche and ignore whatever visual type was
chosen. Meanwhile `visual_style` is stored as free prose and loosely substring-matched by
`treatment_for_style` (`pipeline/composer.py:190`) only to pick a *post-processing filter* —
never to steer the prompt.

Two smaller defects surfaced while mapping this:

- The niche dropdown is a **hardcoded JavaScript array** (`frontend/app.js:262`) listing 10
  niches when 11 packs exist on disk. **`motivational` cannot be selected at all** — and it
  is the one pack whose preset set differs from the others.
- The prompt and the post-processing treatment are chosen by two unrelated mechanisms, so
  they can disagree.

## What is already working, and is not being changed

The manual round-trip — export prompts, generate images elsewhere, point the app at a
folder — is sound and needs no work:

- `get_all_prompts` (`app.py:462`) emits a numbered sheet, project-tagged:
  `thebat1. wide establishing shot of a muddy riverbank at dawn…`
  The tag prevents last month's `1_` from hijacking this month's shot 1 in the shared library.
- `match_shots_by_number` (`pipeline/library.py:891`) parses `^[a-z]{0,8}(\d{1,4})[ _\-.]`,
  so a filename truncated by an image tool to `thebat12_wide_establishing_sh.png` still lands
  on shot 12. It refuses the whole mapping when under half the folder is numbered, so a stray
  digit cannot hijack a library.

No one-by-one picking is required, and shot order cannot drift. This spec changes none of it;
the prompts flowing through it simply get better.

## Decisions taken

| Decision | Choice | Rejected alternative |
|---|---|---|
| Scope | Wire up the presets **and** expand each niche's set | Wire up the existing near-identical four as-is |
| Granularity | **Project-level** — one visual type per film | Per-shot override; per-shot always |
| Prompt shape | Preset **replaces** `style_block` | Append both (risks telling the generator "medium format camera" and "oil portrait" at once) |

---

## 1. Preset vocabulary

Each pack's `style_presets` is rewritten as a niche-specific set of 4–6 entries.

An entry value is **either** a plain string (prompt prose, the current shape) **or** an object:

```json
"evidence_photo": {
  "prompt": "Flash-lit evidence photograph, flat frontal light, scale marker, clinical framing.",
  "treatment": "documentary"
}
```

The object form exists for §4: a preset named `evidence_photo` must declare which
post-processing filter it maps to, because its name is not one of the five treatments.
Existing string entries keep working untouched.

`treatment` must be one of `SINGLE_IMAGE_TREATMENTS` (`pipeline/composer.py:96`):
`vignette`, `vox_collage`, `documentary`, `illustration`, `silhouette`.

Display labels are derived by title-casing the key (`evidence_photo` → "Evidence Photo"),
so no separate label field is needed.

### The vocabulary to author

Every entry below is `key → treatment` with the prompt prose to write into the pack.
No prose may request lettering, captions or signage — the packs' `negative_block` forbids text.

**biography**
- `portrait_archive` → documentary — Medium format archival portrait, warm window light, silver halide grain, sitter turned slightly off-camera.
- `family_album` → vox_collage — Aged family album page, overlapping deckle-edged snapshots on black card.
- `oil_portrait` → illustration — Classical oil portrait, visible brushwork, dark umber ground, museum lighting.
- `study_silhouette` → silhouette — Figure silhouetted at a tall study window, dust suspended in the light shaft.
- `newsprint_profile` → documentary — Halftone newspaper profile photograph, coarse dot screen, feature-page crop.

**business_money**
- `boardroom_reportage` → documentary — Corporate reportage photograph, glass and steel, available light, shallow depth of field.
- `ledger_macro` → vignette — Macro of a ledger, banknotes or ticker tape, raking light, fine paper fibre detail.
- `editorial_isometric` → illustration — Editorial isometric illustration of commerce, restrained two-colour palette, clean geometry.
- `trading_floor_silhouette` → silhouette — Silhouetted figures against a bank of glowing market screens.
- `vintage_industry` → documentary — Mid-century industrial archive photograph, warm monochrome, factory or trading hall.

**civil_war**
- `wet_plate` → documentary — Wet-plate collodion field photograph, shallow tonal range, edge vignetting, period uniform detail.
- `battlefield_reportage` → documentary — Restrained battlefield reportage, overcast light, mud and smoke, no heroic posing.
- `lithograph` → illustration — Period lithograph or steel engraving, cross-hatched shading, muted ink wash.
- `campfire_silhouette` → silhouette — Silhouetted figures around a campfire against a dusk treeline.
- `letters_collage` → vox_collage — Collage of folded letters, ration tickets and tintypes on worn linen.

**default**
- `documentary_photo` → documentary — Cinematic documentary photograph, natural directional light, muted palette, fine grain.
- `cinematic_still` → vignette — Anamorphic cinematic still, shallow focus, atmospheric haze.
- `editorial_illustration` → illustration — Editorial illustration, confident line, limited palette, flat colour fields.
- `graphic_silhouette` → silhouette — Strong graphic silhouette against a bright gradient sky.
- `paper_collage` → vox_collage — Cut-paper collage on textured board, layered edges and shadow.

**islamic_history**
- `manuscript_illumination` → illustration — Illuminated manuscript panel, gold leaf, lapis and vermilion, geometric border.
- `architectural_plate` → documentary — Architectural photograph of courtyard, arcade and muqarnas, raking desert light.
- `geometric_pattern` → illustration — Tessellated girih pattern in glazed tile, deep blue and turquoise.
- `caravan_silhouette` → silhouette — Caravan silhouetted on a dune ridge at dusk.
- `parchment_archive` → vox_collage — Aged parchment leaves, tooled leather binding, pressed wax seals.

**motivational**
- `golden_hour_figure` → vignette — Lone figure at golden hour, long shadow, warm rim light, wide horizon.
- `summit_silhouette` → silhouette — Climber silhouetted on a ridge against a bright sky.
- `training_reportage` → documentary — Gritty training-room reportage, sweat and texture, hard directional light.
- `cinematic_wide` → vignette — Anamorphic cinematic wide, shallow focus, atmospheric haze, teal and amber grade.
- `bold_graphic` → illustration — Bold high-contrast poster illustration, limited palette, strong diagonal composition.

**mythology_folklore**
- `oil_myth` → illustration — Romantic-era mythological oil painting, dramatic chiaroscuro, heroic scale.
- `woodcut` → illustration — Folk woodcut print, heavy black line, flat ochre and madder inks.
- `misted_landscape` → vignette — Mist-wrapped ancient landscape, standing stones, low blue light.
- `firelit_silhouette` → silhouette — Storyteller and listeners silhouetted around firelight.
- `tapestry` → vox_collage — Woven medieval tapestry panel, faded wool, millefleurs ground.

**nature_wildlife**
- `wildlife_telephoto` → documentary — Telephoto wildlife photograph, animal sharp against compressed bokeh, early light.
- `macro_detail` → vignette — Extreme macro of feather, scale or leaf vein, dew, razor-thin focal plane.
- `aerial_landscape` → documentary — High aerial of terrain, river braid or migrating herd, natural colour, midday clarity.
- `naturalist_plate` → illustration — Victorian naturalist field-guide plate, watercolour and ink, specimen on cream ground.
- `dusk_silhouette` → silhouette — Animal silhouetted on a ridge against a burning dusk sky.

**space_science**
- `telescope_plate` → documentary — Deep-field telescope plate, nebula filament detail, narrowband colour.
- `mission_archival` → documentary — Archival mission photograph, hard unfiltered sunlight, matte spacecraft surfaces.
- `technical_cutaway` → illustration — Precise technical cutaway, thin clean linework, unannotated.
- `lab_reportage` → documentary — Clean-room or laboratory reportage, cool fluorescent light, instrument detail.
- `horizon_silhouette` → silhouette — Figure or antenna silhouetted against a planetary horizon.

**true_crime**
- `evidence_photo` → documentary — Flash-lit evidence photograph, flat frontal light, scale marker, clinical framing.
- `surveillance_still` → vignette — Grainy surveillance still, low resolution, high-contrast monochrome.
- `newspaper_archive` → vox_collage — Clipped newspaper archive fragments layered on a case file folder.
- `courtroom_sketch` → illustration — Courtroom sketch in coloured pencil and pastel, loose confident line.
- `night_exterior` → silhouette — Figure silhouetted under a sodium streetlight on a wet night street.

**world_military_history**
- `combat_reportage` → documentary — Combat reportage, pushed monochrome film, heavy grain, motion at the frame edges.
- `archival_colour` → documentary — Early colour archival transparency, muted dyes, period materiel detail.
- `campaign_plate` → illustration — Hand-drawn campaign plate, contour hatching, ink and wash.
- `trench_silhouette` → silhouette — Soldiers silhouetted on a trench parapet against flare light.
- `propaganda_poster` → illustration — Period poster illustration, bold flat colour, heavy litho texture.

### Known tension: printed-matter presets vs. `negative_block`

`newsprint_profile`, `newspaper_archive` and `propaganda_poster` describe printed artefacts,
while every pack's `negative_block` ends with "no text, no watermark, no signature, no logo".

**Resolution:** the prose describes the artefact as *texture and composition* and never asks
for legible lettering, and `negative_block` is emitted unchanged. Generators reliably produce
illegible pseudo-text in this situation, which is the desired result — a newspaper that reads
as a newspaper without carrying a readable headline. Do not weaken `negative_block` for these
presets; if a specific preset proves unusable in practice, cut the preset rather than the
constraint.

### Validation

`validate_series_pack` (`pipeline/library.py:75`) gains a `style_presets` check, alongside the
existing `world_anchor` / `style_block` / `negative_block` checks:

- must be a dict with at least one entry
- each value is a non-empty string, **or** an object with a non-empty `prompt`
- an object's `treatment`, when present, must be a key of `SINGLE_IMAGE_TREATMENTS`

It is load-bearing now, so a malformed pack must fail loudly rather than silently emitting no style.

## 2. Selection

`visual_type` joins `series_slug` on the project.

- The niche dropdown (`#pt-series-slug`) is populated from a new `list_series_packs()` API
  that reads `config/series/*.json` from disk, returning `series_slug` and `display_name`.
  The hardcoded array at `frontend/app.js:262` is deleted. This is what makes `motivational`
  selectable again and stops the list drifting a second time.
- `#pt-style` stops being free prose. Choosing a niche repopulates it from that pack's
  `style_presets`, labels title-cased.
- Default selection is the pack's first preset in declaration order.
- `visual_type` is added to `UI_DEFAULT_KEYS` (`app.py:286`) so it persists across launches
  like voice, niche and tone already do.

`visual_style` is retained in the project schema and continues to feed the `world_anchor`
fallback at `pipeline/library.py:1334`. It is no longer the mechanism for choosing a look.

## 3. Prompt composition

`compose_gap_prompt` (`pipeline/library.py:1254`) gains a `style_preset: str = None` argument.

At the point it currently appends `style_block` (`library.py:1299`):

- a preset is resolved from the pack → emit the preset's prose in place of `style_block`
- no preset, or an unknown key → emit `style_block`, exactly as today

`world_anchor` and `negative_block` are untouched, and their positions in the prompt are unchanged.

The three call sites (`library.py:1531`, `1563`, `1609`) pass the value through, sourced from
`project_info.get("visual_type")`.

## 4. Treatment resolution

`treatment_for_style` (`pipeline/composer.py:190`) gains a preset-aware first step, in order:

1. the resolved preset declares a `treatment` → use it
2. the preset **key** is itself a key of `SINGLE_IMAGE_TREATMENTS` → use that
3. otherwise fall back to the existing substring match over prose

The prompt and the post-processing filter then describe the same thing — picking
`courtroom_sketch` produces an illustration prompt *and* applies the illustration treatment.
That has never been true before.

## 5. Round-trip

No changes. See "What is already working" above.

## 6. Testing

- Every pack on disk passes `validate_series_pack`, `style_presets` included — parameterised
  over `config/series/*.json` so a new pack is covered automatically, and the next drift is caught.
- `compose_gap_prompt` emits preset prose when `visual_type` is set, and `style_block` when it
  is not, and when the key is unknown.
- `treatment_for_style` resolves correctly from all three paths: object `treatment`, bare key,
  and prose fallback.
- The niche list served by `list_series_packs()` contains every pack on disk — this is the
  regression lock for `motivational`.
- Every authored preset's `treatment` is a key of `SINGLE_IMAGE_TREATMENTS`.

## Out of scope

- The image-count floor (ROADMAP C1) — unrelated, tracked separately.
- Per-shot visual type override.
- Any change to the numbered-folder round-trip.
- Rewriting `style_block` to be niche-neutral (considered and rejected: presets replace it,
  so it only serves as the no-preset fallback).
