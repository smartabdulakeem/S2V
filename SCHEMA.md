# S2V Script Schema v2

The contract between the planner, the library, and the compositor. Everything downstream
reads this, so it is settled before any rebuild code is written.

**Two changes from v1:**

1. A segment holds a **shot list**, not a single visual. Segments are narration-shaped
   (median 25s, max 101s in the real 52-segment film); shots are camera-shaped (5–10s).
   One visual per segment was the assumption that made generative motion impossible.
2. Visuals are **sourced**, not just generated. A shot can retrieve from the library,
   generate fresh, or pin an exact file.

**v1 scripts still load.** The loader upconverts any segment without a `shots` array into
a single-shot list. Nothing in `samples/` breaks.

---

## Full example

```json
{
  "schema_version": 2,
  "project": {
    "title": "S2E6 — The Long Retreat",
    "output_filename": "s2e6.mp4",
    "aspect_ratio": "16:9",
    "resolution": "1920x1080",
    "fps": 30,

    "voice": "google:en-GB-Neural2-D",
    "voice_rate": "+0%",
    "voice_pitch": "+0Hz",
    "voice_dialect": "",
    "narrative_tone": "grave documentary",
    "speaker_mode": "single",

    "captions": { "enabled": true, "source": "tts_timings" },

    "background_music": null,
    "music_volume_db": -20,

    "visual_style": "vintage_documentary",
    "world_anchor": "7th century Arabian Peninsula, early Islamic era, Middle Eastern",
    "character_bible": {
      "Ali": "an elderly man, white beard, plain dark robes, weathered face"
    },

    "budget": { "max_generated_clips": 0, "max_spend_usd": 0 }
  },

  "segments": [
    {
      "segment_id": 1,
      "type": "hook",
      "narration": "<speak>There is an image the history books do not linger on.<break time='400ms'/> A man of sixty years.</speak>",
      "voice": null,
      "voice_steering": "grave, unhurried, let the pauses breathe",

      "shots": [
        {
          "shot_id": "1a",
          "duration": null,
          "source": "library",
          "query": "lone rider on a ridge at dusk, empty desert behind",
          "min_score": 0.26,
          "motion": { "kind": "ken_burns", "effect": "zoom_in" },
          "treatment": { "filter": "vignette", "grade": null }
        },
        {
          "shot_id": "1b",
          "duration": 6.0,
          "source": "pin",
          "pin": "projects/s2e6/ali_portrait.jpg",
          "motion": { "kind": "ken_burns", "effect": "pan_left" },
          "treatment": { "filter": "none" }
        }
      ],

      "text_overlay": {
        "text": "MADINAH — 656 CE",
        "position": "bottom_center",
        "start": 0.5,
        "duration_seconds": 4
      },
      "transition_in": "fade",
      "transition_out": "cut",
      "sfx": [{ "name": "wind", "offset_ms": 0, "gain_db": -12 }]
    }
  ]
}
```

---

## `project`

| Field | Type | Default | Notes |
|---|---|---|---|
| `title` | string | required | Also the project slug — **Unicode-normalised before slugifying** |
| `output_filename` | string | required | `.mp4` appended if missing |
| `aspect_ratio` | enum | `16:9` | `16:9` `9:16` `1:1` `4:3` |
| `resolution` | string | derived | `WxH`. Defaults per ratio; 1080p once the compositor is FFmpeg-native |
| `fps` | int | `30` | |
| `voice` | string | required | `edge:` `google:` `local:` prefix |
| `voice_rate` / `voice_pitch` | string | `+0%` / `+0Hz` | |
| `captions.enabled` | bool | `true` | |
| `captions.source` | enum | `tts_timings` | `tts_timings` \| `whisper` \| `none` |
| `background_music` | string\|null | `null` | path |
| `music_volume_db` | number | `-20` | |
| `visual_style` | string | `""` | preset name or free text |
| `series_slug` | string | `""` | Series identifier matching `config/series/<series_slug>.json` |
| `world_anchor` | string | `""` | Prepended to every generated prompt. Absent from v1, and its absence produced 111 of 160 off-brief images |
| `character_bible` | object | `{}` | name → description |
| `budget.max_generated_clips` | int | `0` | Hard ceiling on paid motion clips. `0` disables generative motion |
| `budget.max_spend_usd` | number | `0` | Checked **before** any API call |

## `segment`

| Field | Type | Default | Notes |
|---|---|---|---|
| `segment_id` | int | required | unique, ≥1 |
| `type` | enum | `body` | `hook` \| `body` \| `conclusion` |
| `narration` | string | required | plain or SSML |
| `voice` | string\|null | `null` | overrides project voice |
| `voice_steering` | string | `""` | Gemini TTS only |
| `shots` | array | required | ≥1 shot |
| `text_overlay` | object\|null | `null` | `start` is new in v2 |
| `transition_in/out` | enum | `cut` | `cut` \| `fade` \| `crossfade` |
| `sfx` | array | `[]` | `gain_db` is new in v2 |

## `shot`

| Field | Type | Default | Notes |
|---|---|---|---|
| `shot_id` | string | derived | `{segment_id}{a,b,c…}` |
| `duration` | number\|null | `null` | Seconds. **`null` = share what's left** |
| `source` | enum | `library` | `library` \| `generate` \| `pin` |
| `query` | string | required unless `pin` | Retrieval text and generation prompt |
| `pin` | string\|null | `null` | Exact file path. Required when `source: pin` |
| `min_score` | number | `0.26` | CLIP floor. Below it, `library` falls back to `generate` |
| `motion.kind` | enum | `ken_burns` | `ken_burns` \| `static` \| `generative` |
| `motion.effect` | enum | `zoom_in` | ken_burns only: `zoom_in` `zoom_out` `pan_left` `pan_right` |
| `motion.provider` | string | `auto` | generative only |
| `motion.seconds` | number | `5` | generative only, 1–10 |
| `treatment.filter` | enum | `vignette` | `none` `vignette` `vox_collage` `diptych` `collage` |
| `treatment.grade` | string\|null | `null` | optional colour grade |

### Duration resolution

Segment length comes from its narration audio — it is never authored. Within a segment:

1. Sum the explicit `duration` values.
2. Split the remainder evenly across shots with `duration: null`.
3. If explicit durations exceed the audio, scale them all down proportionally and warn.
4. A segment whose shots are all explicit and all short leaves a gap — the **last shot
   stretches** to cover it.

So the common case is every shot at `duration: null`: three shots across a 25-second
segment become 8.33s each, with no arithmetic in the script.

---

## Sourcing

```
source: pin       → use that exact file. Fail loudly if missing.
source: library   → CLIP search. Best match above min_score wins.
                    Below min_score → fall through to generate.
source: generate  → make it, save into library/images/, add to the index.
```

Two rules the retrieval layer must enforce, both learned from measurement:

- **Never return the same image twice in one video.** At 461 images only 44 distinct
  images were ever top-1, and one won 13 queries. Pure top-1 concentrates hard.
- **Penalise recently used images** across the render so variety improves as the library
  grows rather than staying pinned to a few favourites.

---

## Validation

`pipeline/validator.py` is rewritten against this document. v1 validated none of
`magick_filter`, `sfx`, `level1_overlay`, `crop`, `character_bible`, `aspect_ratio`, or
`disable_captions` — seven fields the pipeline consumed, so bad values surfaced as a
traceback mid-render.

Every error names its exact path and says how to fix it:

```
segments[3].shots[1].motion.kind: "zoom" is not valid.
  Expected one of: ken_burns, static, generative.

segments[7].shots[0]: source is "pin" but no pin path was given.

project.budget.max_spend_usd is 0 but segments[2].shots[1] requests generative motion.
  Raise the budget or change motion.kind.
```

Rules beyond types:

1. `segment_id` unique and ≥1
2. every segment has ≥1 shot; `shot_id` unique within a segment
3. `source: pin` requires `pin`; the file must exist
4. `source: library` or `generate` requires a non-empty `query`
5. explicit durations must be > 0
6. `motion.seconds` between 1 and 10 when `kind: generative`
7. generative motion requires `budget.max_generated_clips` > 0
8. `pin` paths must stay inside the project — no absolute paths, no `..`

---

## v1 → v2 upconversion

Applied on load, in memory. No file is rewritten.

| v1 segment field | Becomes |
|---|---|
| `b_roll_keyword` | `shots[0].query` |
| `visual_type: "ai_image"` | `shots[0].source: "library"` |
| `visual_type: "stock_photo"` | `shots[0].source: "library"` |
| `ken_burns` | `shots[0].motion` |
| `magick_filter` | `shots[0].treatment.filter` |
| `use_base_image` | `shots[0].source: "pin"` + `pin` |
| `crop`, `level1_overlay` | carried onto `shots[0]` unchanged |
| `disable_captions: true` | `project.captions.enabled: false` |

A v1 script therefore renders as a one-shot-per-segment video — exactly what it does today.

---

## Cache key

Content-hash each shot so nothing is recomputed without cause:

```
sha1(query|pin + resolved_duration + motion + treatment + resolution + fps)
```

Changing narration in segment 4 re-renders segment 4 only. This is what makes iteration
affordable — and mandatory before generative motion, where a full re-render of the real
52-segment film would cost $156–$655.

---

## Series Pack Schema (v2)

Series packs live in `config/series/<series_slug>.json`. A series pack supplies **defaults only** — any property explicitly defined in a script object overrides the corresponding pack default.

### Fields

| Field | Type | Default | Notes |
|---|---|---|---|
| `series_slug` | string | required | Identifier matching filename (`config/series/<series_slug>.json`) |
| `display_name` | string | required | Human-readable title for the series pack |
| `voice.id` | string | required | Default voice ID (e.g. `edge:en-US-GuyNeural`, `google:en-US-Neural2-D`) |
| `voice.steering` | string | `""` | Default voice steering prompt for Gemini TTS |
| `voice.tone` | string | `""` | Default narrative tone descriptor |
| `grade` | string | `"vignette"` | Default treatment filter (`none`, `vignette`, `vox_collage`, `documentary`, `illustration`, `silhouette`) |
| `caption_style` | string\|object | `"bottom_center"` | Default caption positioning or formatting |
| `shot_rhythm_seconds` | number | `4.0` | Target duration per shot during automatic planning |
| `world_anchor` | string | required | Historical, geographic, or visual anchor prepended to prompts |
| `style_block` | string | required | Photographic, lighting, and medium style instructions |
| `negative_block` | string | required | Era and quality negative prompt constraints |
| `style_presets` | object | `{}` | Named visual style mapping (e.g. `vintage_documentary`, `documentary`) |
| `calibration.min_score` | number\|null | `null` | Per-pack CLIP floor written back by `calibrate(series_slug)` |
| `calibration.weak_band` | number\|null | `null` | Per-pack CLIP ambiguity band written back by `calibrate(series_slug)` |
| `calibration.real_queries` | array | required | Array of 10 known-good niche queries |
| `calibration.fake_queries` | array | required | Array of 10 known-impossible niche queries |
| `seed_queries` | array | `[]` | Curated prompts for populating a new library |

### Pack Validation Rules
1. `series_slug` must match file basename.
2. `display_name`, `world_anchor`, `style_block`, and `negative_block` must be non-empty strings.
3. `voice` must be an object containing non-empty `id`.
4. `calibration.real_queries` and `calibration.fake_queries` must each contain at least 10 non-empty query strings.

