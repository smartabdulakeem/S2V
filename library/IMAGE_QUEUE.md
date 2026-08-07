# S2V Image Library — Generation Queue

A shared work queue. **You** and **Antigravity** both draw from it, generate a portion, and
drop the results into the same folder. Batches are claimable, so work never collides or repeats.

---

## PROTOCOL — read before generating anything

### 1. Check for duplicates FIRST

Before starting any batch, verify it has not already been produced.

```bash
# Has this batch already been done?  (replace A1 with your batch id)
grep -c '"batch": "A1"' library/manifest.jsonl

# How many images exist right now?
ls library/images | wc -l
```

**Rules:**

- Never generate a batch whose Status below is `CLAIMED` or `DONE`.
- Set Status to `CLAIMED - antigravity` or `CLAIMED - manual` **before** you start.
- Set it to `DONE` when finished, and save this file so both sides see the same state.
- Filenames are content hashes, so byte-identical images collapse on their own. But the
  same prompt at a *different* seed still burns quota — always check the table first.

### 2. Where everything goes

| What | Where |
|---|---|
| Images | `C:\Users\HomePC\Documents\GitHub\S2V\library\images\` |
| Metadata | `library\manifest.jsonl` (one JSON object per line, append-only) |
| This queue | `library\IMAGE_QUEUE.md` |

One flat folder. No subfolders — categories live in the manifest, not the directory tree.

### 3. Style suffix — append to EVERY prompt

```
cinematic documentary photography, dramatic natural lighting, historical realism, highly detailed, sharp focus, no text, no watermark, no modern objects
```

### 4. Manual generation URL

```
https://image.pollinations.ai/prompt/{URL_ENCODED_PROMPT_PLUS_STYLE}?width=1280&height=720&nologo=true&seed={SEED}&model=flux
```

Free, no API key. Save the result into `library\images\` and append a manifest line.

### 5. Manifest record format

```json
{"path": "library/images/ab12cd34ef56.jpg", "prompt": "...", "batch": "A1",
 "subject": "lone acacia tree on an empty plain", "light": "dawn light",
 "shot": "wide establishing shot", "seed": 42, "bytes": 184203,
 "created_at": "2026-08-07T10:00:00Z"}
```

### 6. Bulk path (preferred for large runs)

`tools/build_library.py` already implements all of the above — manifest dedupe,
content-addressed filenames, retry with backoff, resume-safe. Use it for volume:

```bash
C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe tools/build_library.py --target 1200
```

Use the batches below when you want **targeted** coverage of a specific theme, when
Antigravity hits its generation cap, or when generating by hand.

### 7. Splitting work between you and Antigravity

Claim from opposite ends so you never meet in the middle:

- **Antigravity** claims from the **top** of the index (A1, A2, B1 ...)
- **You** claim from the **bottom** (MO1, CW1, Z1 ...)

---

## Batch index

| Batch | Theme | Prompts | Status |
|---|---|---|---|
| `A1` | Desert terrain & landscape | 25 | TODO |
| `A2` | Desert terrain & landscape | 25 | TODO |
| `A3` | Desert terrain & landscape | 25 | TODO |
| `B1` | Water, wells & oases | 25 | TODO |
| `B2` | Water, wells & oases | 25 | TODO |
| `B3` | Water, wells & oases | 25 | TODO |
| `C1` | City walls & settlements | 25 | TODO |
| `C2` | City walls & settlements | 25 | TODO |
| `C3` | City walls & settlements | 25 | TODO |
| `D1` | Mosque exteriors | 25 | TODO |
| `D2` | Mosque exteriors | 25 | TODO |
| `D3` | Mosque exteriors | 25 | TODO |
| `E1` | Mosque interiors & prayer | 25 | TODO |
| `E2` | Mosque interiors & prayer | 25 | TODO |
| `E3` | Mosque interiors & prayer | 25 | TODO |
| `F1` | Markets & commerce | 25 | TODO |
| `F2` | Markets & commerce | 25 | TODO |
| `F3` | Markets & commerce | 25 | TODO |
| `G1` | Tents & encampments | 25 | TODO |
| `G2` | Tents & encampments | 25 | TODO |
| `G3` | Tents & encampments | 25 | TODO |
| `H1` | Councils & assemblies | 25 | TODO |
| `H2` | Councils & assemblies | 25 | TODO |
| `H3` | Councils & assemblies | 25 | TODO |
| `I1` | Elders, leaders & portraits | 25 | TODO |
| `I2` | Elders, leaders & portraits | 25 | TODO |
| `I3` | Elders, leaders & portraits | 25 | TODO |
| `J1` | Warriors & riders | 25 | TODO |
| `J2` | Warriors & riders | 25 | TODO |
| `J3` | Warriors & riders | 25 | TODO |
| `K1` | Crowds & gatherings | 25 | TODO |
| `K2` | Crowds & gatherings | 25 | TODO |
| `K3` | Crowds & gatherings | 25 | TODO |
| `L1` | Cavalry & caravans | 25 | TODO |
| `L2` | Cavalry & caravans | 25 | TODO |
| `L3` | Cavalry & caravans | 25 | TODO |
| `M1` | Before battle | 25 | TODO |
| `M2` | Before battle | 25 | TODO |
| `M3` | Before battle | 25 | TODO |
| `N1` | Battle aftermath | 25 | TODO |
| `N2` | Battle aftermath | 25 | TODO |
| `N3` | Battle aftermath | 25 | TODO |
| `O1` | Banners & standards | 25 | TODO |
| `O2` | Banners & standards | 25 | TODO |
| `O3` | Banners & standards | 25 | TODO |
| `P1` | Manuscripts & scribes | 25 | TODO |
| `P2` | Manuscripts & scribes | 25 | TODO |
| `P3` | Manuscripts & scribes | 25 | TODO |
| `Q1` | Objects & still life | 25 | TODO |
| `Q2` | Objects & still life | 25 | TODO |
| `Q3` | Objects & still life | 25 | TODO |
| `R1` | Night & firelight | 25 | TODO |
| `R2` | Night & firelight | 25 | TODO |
| `R3` | Night & firelight | 25 | TODO |
| `S1` | Journeys, roads & passes | 25 | TODO |
| `S2` | Journeys, roads & passes | 25 | TODO |
| `S3` | Journeys, roads & passes | 25 | TODO |
| `T1` | Architecture details | 25 | TODO |
| `T2` | Architecture details | 25 | TODO |
| `T3` | Architecture details | 25 | TODO |
| `U1` | Maps & cartography | 25 | TODO |
| `U2` | Maps & cartography | 25 | TODO |
| `U3` | Maps & cartography | 25 | TODO |
| `V1` | Metaphor & emotional beats | 25 | TODO |
| `V2` | Metaphor & emotional beats | 25 | TODO |
| `V3` | Metaphor & emotional beats | 25 | TODO |
| `W1` | Weather & sky | 25 | TODO |
| `W2` | Weather & sky | 25 | TODO |
| `W3` | Weather & sky | 25 | TODO |
| `X1` | Domestic & daily life | 25 | TODO |
| `X2` | Domestic & daily life | 25 | TODO |
| `X3` | Domestic & daily life | 25 | TODO |
| `Y1` | Messengers, arrivals & departures | 25 | TODO |
| `Y2` | Messengers, arrivals & departures | 25 | TODO |
| `Y3` | Messengers, arrivals & departures | 25 | TODO |
| `Z1` | Aerial & establishing | 25 | TODO |
| `Z2` | Aerial & establishing | 25 | TODO |
| `Z3` | Aerial & establishing | 25 | TODO |
| `CW1` | American Civil War (secondary series) | 25 | TODO |
| `CW2` | American Civil War (secondary series) | 25 | TODO |
| `MO1` | Motivation & abstract (secondary series) | 25 | TODO |
| `MO2` | Motivation & abstract (secondary series) | 25 | TODO |

**82 batches - 2050 prompts total.**

---

## Batches

### `A1` - Desert terrain & landscape

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | wide establishing shot of black volcanic rock field on desert flats, storm light | 101 |
| 2 | close detail shot of sandstorm approaching across open desert, firelight | 202 |
| 3 | extreme wide shot of desert horizon under an enormous empty sky, moonlight | 303 |
| 4 | high angle shot of footprints and camel tracks crossing fresh sand, golden hour | 404 |
| 5 | aerial view of narrow canyon pass between sandstone cliffs, dust-filtered sunlight | 515 |
| 6 | high angle shot of endless rolling sand dunes with wind-carved ridges, dust-filtered sunlight | 626 |
| 7 | medium shot of sandstorm approaching across open desert, blue hour | 737 |
| 8 | medium shot of desert horizon under an enormous empty sky, overcast haze | 848 |
| 9 | aerial view of footprints and camel tracks crossing fresh sand, overcast haze | 959 |
| 10 | low angle shot of black volcanic rock field on desert flats, firelight | 42 |
| 11 | close detail shot of black volcanic rock field on desert flats, backlit silhouette | 101 |
| 12 | medium shot of sandstorm approaching across open desert, storm light | 202 |
| 13 | wide establishing shot of cracked dry riverbed cutting through desert plain, overcast haze | 303 |
| 14 | extreme wide shot of footprints and camel tracks crossing fresh sand, dawn light | 404 |
| 15 | wide establishing shot of rocky escarpment above a dry valley, dust-filtered sunlight | 515 |
| 16 | medium shot of narrow canyon pass between sandstone cliffs, dawn light | 626 |
| 17 | high angle shot of narrow canyon pass between sandstone cliffs, harsh noon sun | 737 |
| 18 | aerial view of endless rolling sand dunes with wind-carved ridges, dust-filtered sunlight | 848 |
| 19 | high angle shot of scrub brush and thorn bushes on stony ground, dusk | 959 |
| 20 | aerial view of narrow canyon pass between sandstone cliffs, firelight | 42 |
| 21 | wide establishing shot of endless rolling sand dunes with wind-carved ridges, backlit silhouette | 101 |
| 22 | aerial view of black volcanic rock field on desert flats, dawn light | 202 |
| 23 | wide establishing shot of desert horizon under an enormous empty sky, firelight | 303 |
| 24 | medium shot of cracked dry riverbed cutting through desert plain, moonlight | 404 |
| 25 | extreme wide shot of desert horizon under an enormous empty sky, backlit silhouette | 515 |

### `A2` - Desert terrain & landscape

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | aerial view of cracked dry riverbed cutting through desert plain, moonlight | 101 |
| 2 | high angle shot of rocky escarpment above a dry valley, moonlight | 202 |
| 3 | extreme wide shot of black volcanic rock field on desert flats, harsh noon sun | 303 |
| 4 | close detail shot of cracked dry riverbed cutting through desert plain, storm light | 404 |
| 5 | wide establishing shot of scrub brush and thorn bushes on stony ground, backlit silhouette | 515 |
| 6 | close detail shot of sandstorm approaching across open desert, overcast haze | 626 |
| 7 | medium shot of endless rolling sand dunes with wind-carved ridges, dawn light | 737 |
| 8 | close detail shot of desert plateau dropping into a deep wadi, moonlight | 848 |
| 9 | medium shot of black volcanic rock field on desert flats, backlit silhouette | 959 |
| 10 | aerial view of endless rolling sand dunes with wind-carved ridges, firelight | 42 |
| 11 | medium shot of black volcanic rock field on desert flats, harsh noon sun | 101 |
| 12 | low angle shot of cracked dry riverbed cutting through desert plain, storm light | 202 |
| 13 | wide establishing shot of cracked dry riverbed cutting through desert plain, firelight | 303 |
| 14 | extreme wide shot of rocky escarpment above a dry valley, firelight | 404 |
| 15 | medium shot of scrub brush and thorn bushes on stony ground, dawn light | 515 |
| 16 | close detail shot of cracked dry riverbed cutting through desert plain, harsh noon sun | 626 |
| 17 | aerial view of scrub brush and thorn bushes on stony ground, blue hour | 737 |
| 18 | medium shot of black volcanic rock field on desert flats, golden hour | 848 |
| 19 | extreme wide shot of narrow canyon pass between sandstone cliffs, blue hour | 959 |
| 20 | high angle shot of desert plateau dropping into a deep wadi, dusk | 42 |
| 21 | low angle shot of desert horizon under an enormous empty sky, dusk | 101 |
| 22 | high angle shot of salt flat shimmering with heat haze, dawn light | 202 |
| 23 | close detail shot of footprints and camel tracks crossing fresh sand, golden hour | 303 |
| 24 | extreme wide shot of sandstorm approaching across open desert, backlit silhouette | 404 |
| 25 | medium shot of sandstorm approaching across open desert, backlit silhouette | 515 |

### `A3` - Desert terrain & landscape

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | close detail shot of black volcanic rock field on desert flats, golden hour | 101 |
| 2 | extreme wide shot of cracked dry riverbed cutting through desert plain, golden hour | 202 |
| 3 | medium shot of rocky escarpment above a dry valley, moonlight | 303 |
| 4 | wide establishing shot of footprints and camel tracks crossing fresh sand, lamplight | 404 |
| 5 | extreme wide shot of rocky escarpment above a dry valley, backlit silhouette | 515 |
| 6 | wide establishing shot of desert plateau dropping into a deep wadi, overcast haze | 626 |
| 7 | low angle shot of cracked dry riverbed cutting through desert plain, lamplight | 737 |
| 8 | close detail shot of endless rolling sand dunes with wind-carved ridges, moonlight | 848 |
| 9 | close detail shot of black volcanic rock field on desert flats, harsh noon sun | 959 |
| 10 | extreme wide shot of salt flat shimmering with heat haze, harsh noon sun | 42 |
| 11 | extreme wide shot of rocky escarpment above a dry valley, storm light | 101 |
| 12 | wide establishing shot of narrow canyon pass between sandstone cliffs, golden hour | 202 |
| 13 | close detail shot of desert horizon under an enormous empty sky, golden hour | 303 |
| 14 | high angle shot of salt flat shimmering with heat haze, moonlight | 404 |
| 15 | aerial view of narrow canyon pass between sandstone cliffs, lamplight | 515 |
| 16 | wide establishing shot of salt flat shimmering with heat haze, backlit silhouette | 626 |
| 17 | extreme wide shot of footprints and camel tracks crossing fresh sand, golden hour | 737 |
| 18 | low angle shot of desert plateau dropping into a deep wadi, moonlight | 848 |
| 19 | close detail shot of black volcanic rock field on desert flats, blue hour | 959 |
| 20 | high angle shot of salt flat shimmering with heat haze, storm light | 42 |
| 21 | low angle shot of desert plateau dropping into a deep wadi, dawn light | 101 |
| 22 | medium shot of black volcanic rock field on desert flats, storm light | 202 |
| 23 | medium shot of desert horizon under an enormous empty sky, moonlight | 303 |
| 24 | high angle shot of black volcanic rock field on desert flats, storm light | 404 |
| 25 | aerial view of lone acacia tree on an empty plain, dusk | 515 |

### `B1` - Water, wells & oases

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | wide establishing shot of goatskin waterbag hanging from a tent pole, harsh noon sun | 101 |
| 2 | medium shot of stone-rimmed desert well with a rope and leather bucket, firelight | 202 |
| 3 | low angle shot of camels drinking at a watering hole, harsh noon sun | 303 |
| 4 | low angle shot of camels drinking at a watering hole, dusk | 404 |
| 5 | low angle shot of a boy leading a donkey to water, blue hour | 515 |
| 6 | wide establishing shot of goatskin waterbag hanging from a tent pole, firelight | 626 |
| 7 | medium shot of camels drinking at a watering hole, lamplight | 737 |
| 8 | wide establishing shot of a boy leading a donkey to water, firelight | 848 |
| 9 | aerial view of clay water jars stacked beside a well, harsh noon sun | 959 |
| 10 | extreme wide shot of irrigation channel running between date palms, firelight | 42 |
| 11 | medium shot of palm oasis with a still reflecting pool, golden hour | 101 |
| 12 | wide establishing shot of camels drinking at a watering hole, overcast haze | 202 |
| 13 | wide establishing shot of women drawing water from a village well, dusk | 303 |
| 14 | close detail shot of goatskin waterbag hanging from a tent pole, storm light | 404 |
| 15 | wide establishing shot of irrigation channel running between date palms, blue hour | 515 |
| 16 | medium shot of spring bubbling from rock at the base of a cliff, backlit silhouette | 626 |
| 17 | medium shot of flooded wadi after rain, water running over stones, blue hour | 737 |
| 18 | extreme wide shot of spring bubbling from rock at the base of a cliff, dawn light | 848 |
| 19 | low angle shot of spring bubbling from rock at the base of a cliff, blue hour | 959 |
| 20 | aerial view of a boy leading a donkey to water, storm light | 42 |
| 21 | close detail shot of palm oasis with a still reflecting pool, dusk | 101 |
| 22 | low angle shot of women drawing water from a village well, dusk | 202 |
| 23 | high angle shot of goatskin waterbag hanging from a tent pole, firelight | 303 |
| 24 | low angle shot of stone-rimmed desert well with a rope and leather bucket, dawn light | 404 |
| 25 | wide establishing shot of clay water jars stacked beside a well, firelight | 515 |

### `B2` - Water, wells & oases

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | low angle shot of goatskin waterbag hanging from a tent pole, backlit silhouette | 101 |
| 2 | aerial view of camels drinking at a watering hole, backlit silhouette | 202 |
| 3 | extreme wide shot of clay water jars stacked beside a well, harsh noon sun | 303 |
| 4 | low angle shot of a boy leading a donkey to water, golden hour | 404 |
| 5 | low angle shot of clay water jars stacked beside a well, lamplight | 515 |
| 6 | low angle shot of flooded wadi after rain, water running over stones, moonlight | 626 |
| 7 | extreme wide shot of irrigation channel running between date palms, storm light | 737 |
| 8 | wide establishing shot of palm oasis with a still reflecting pool, backlit silhouette | 848 |
| 9 | aerial view of flooded wadi after rain, water running over stones, storm light | 959 |
| 10 | wide establishing shot of camels drinking at a watering hole, lamplight | 42 |
| 11 | wide establishing shot of flooded wadi after rain, water running over stones, overcast haze | 101 |
| 12 | extreme wide shot of flooded wadi after rain, water running over stones, blue hour | 202 |
| 13 | medium shot of spring bubbling from rock at the base of a cliff, firelight | 303 |
| 14 | high angle shot of stone-rimmed desert well with a rope and leather bucket, backlit silhouette | 404 |
| 15 | low angle shot of palm oasis with a still reflecting pool, storm light | 515 |
| 16 | wide establishing shot of flooded wadi after rain, water running over stones, harsh noon sun | 626 |
| 17 | extreme wide shot of irrigation channel running between date palms, moonlight | 737 |
| 18 | close detail shot of a boy leading a donkey to water, harsh noon sun | 848 |
| 19 | medium shot of camels drinking at a watering hole, overcast haze | 959 |
| 20 | low angle shot of spring bubbling from rock at the base of a cliff, storm light | 42 |
| 21 | aerial view of goatskin waterbag hanging from a tent pole, lamplight | 101 |
| 22 | extreme wide shot of stone-rimmed desert well with a rope and leather bucket, golden hour | 202 |
| 23 | close detail shot of irrigation channel running between date palms, dusk | 303 |
| 24 | high angle shot of women drawing water from a village well, harsh noon sun | 404 |
| 25 | medium shot of clay water jars stacked beside a well, harsh noon sun | 515 |

### `B3` - Water, wells & oases

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | extreme wide shot of clay water jars stacked beside a well, lamplight | 101 |
| 2 | aerial view of goatskin waterbag hanging from a tent pole, golden hour | 202 |
| 3 | medium shot of palm oasis with a still reflecting pool, blue hour | 303 |
| 4 | wide establishing shot of women drawing water from a village well, backlit silhouette | 404 |
| 5 | wide establishing shot of irrigation channel running between date palms, dusk | 515 |
| 6 | aerial view of goatskin waterbag hanging from a tent pole, dawn light | 626 |
| 7 | high angle shot of flooded wadi after rain, water running over stones, firelight | 737 |
| 8 | close detail shot of camels drinking at a watering hole, harsh noon sun | 848 |
| 9 | aerial view of a boy leading a donkey to water, moonlight | 959 |
| 10 | wide establishing shot of palm oasis with a still reflecting pool, dusk | 42 |
| 11 | aerial view of women drawing water from a village well, dust-filtered sunlight | 101 |
| 12 | wide establishing shot of spring bubbling from rock at the base of a cliff, dusk | 202 |
| 13 | wide establishing shot of flooded wadi after rain, water running over stones, lamplight | 303 |
| 14 | extreme wide shot of women drawing water from a village well, dawn light | 404 |
| 15 | high angle shot of stone-rimmed desert well with a rope and leather bucket, golden hour | 515 |
| 16 | close detail shot of palm oasis with a still reflecting pool, overcast haze | 626 |
| 17 | high angle shot of stone-rimmed desert well with a rope and leather bucket, storm light | 737 |
| 18 | medium shot of a boy leading a donkey to water, dusk | 848 |
| 19 | medium shot of irrigation channel running between date palms, dawn light | 959 |
| 20 | medium shot of stone-rimmed desert well with a rope and leather bucket, harsh noon sun | 42 |
| 21 | extreme wide shot of a boy leading a donkey to water, overcast haze | 101 |
| 22 | high angle shot of irrigation channel running between date palms, moonlight | 202 |
| 23 | wide establishing shot of clay water jars stacked beside a well, golden hour | 303 |
| 24 | medium shot of spring bubbling from rock at the base of a cliff, storm light | 404 |
| 25 | close detail shot of goatskin waterbag hanging from a tent pole, golden hour | 515 |

### `C1` - City walls & settlements

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | wide establishing shot of ancient town seen from a ridge at distance, blue hour | 101 |
| 2 | close detail shot of ancient town seen from a ridge at distance, lamplight | 202 |
| 3 | high angle shot of mud-brick city wall with a fortified gate, lamplight | 303 |
| 4 | aerial view of stone steps climbing between packed houses, storm light | 404 |
| 5 | aerial view of narrow alley between high mud-brick walls, overcast haze | 515 |
| 6 | wide establishing shot of narrow alley between high mud-brick walls, moonlight | 626 |
| 7 | low angle shot of dense low rooftops of an ancient Arabian town, dusk | 737 |
| 8 | medium shot of caravanserai courtyard with tethered camels, blue hour | 848 |
| 9 | extreme wide shot of watchtower on a city wall at the desert edge, overcast haze | 959 |
| 10 | low angle shot of caravanserai courtyard with tethered camels, golden hour | 42 |
| 11 | high angle shot of mud-brick city wall with a fortified gate, dust-filtered sunlight | 101 |
| 12 | high angle shot of mud-brick city wall with a fortified gate, moonlight | 202 |
| 13 | extreme wide shot of watchtower on a city wall at the desert edge, harsh noon sun | 303 |
| 14 | medium shot of watchtower on a city wall at the desert edge, dusk | 404 |
| 15 | extreme wide shot of dense low rooftops of an ancient Arabian town, backlit silhouette | 515 |
| 16 | wide establishing shot of dense low rooftops of an ancient Arabian town, dust-filtered sunlight | 626 |
| 17 | extreme wide shot of stone steps climbing between packed houses, backlit silhouette | 737 |
| 18 | wide establishing shot of caravanserai courtyard with tethered camels, dawn light | 848 |
| 19 | medium shot of ancient town seen from a ridge at distance, firelight | 959 |
| 20 | close detail shot of watchtower on a city wall at the desert edge, overcast haze | 42 |
| 21 | low angle shot of dense low rooftops of an ancient Arabian town, harsh noon sun | 101 |
| 22 | medium shot of caravanserai courtyard with tethered camels, overcast haze | 202 |
| 23 | high angle shot of mud-brick city wall with a fortified gate, dusk | 303 |
| 24 | wide establishing shot of clay-plastered wall with a heavy wooden door, moonlight | 404 |
| 25 | medium shot of dense low rooftops of an ancient Arabian town, overcast haze | 515 |

### `C2` - City walls & settlements

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | extreme wide shot of narrow alley between high mud-brick walls, dust-filtered sunlight | 101 |
| 2 | high angle shot of ancient town seen from a ridge at distance, backlit silhouette | 202 |
| 3 | wide establishing shot of caravanserai courtyard with tethered camels, backlit silhouette | 303 |
| 4 | high angle shot of clay-plastered wall with a heavy wooden door, dusk | 404 |
| 5 | wide establishing shot of ancient town seen from a ridge at distance, firelight | 515 |
| 6 | medium shot of caravanserai courtyard with tethered camels, lamplight | 626 |
| 7 | medium shot of watchtower on a city wall at the desert edge, firelight | 737 |
| 8 | high angle shot of city gate crowded with travellers and pack animals, dust-filtered sunlight | 848 |
| 9 | aerial view of caravanserai courtyard with tethered camels, overcast haze | 959 |
| 10 | extreme wide shot of courtyard house with a shaded arcade, dawn light | 42 |
| 11 | low angle shot of mud-brick city wall with a fortified gate, dawn light | 101 |
| 12 | extreme wide shot of clay-plastered wall with a heavy wooden door, firelight | 202 |
| 13 | aerial view of narrow alley between high mud-brick walls, lamplight | 303 |
| 14 | aerial view of watchtower on a city wall at the desert edge, lamplight | 404 |
| 15 | close detail shot of mud-brick city wall with a fortified gate, golden hour | 515 |
| 16 | low angle shot of city gate crowded with travellers and pack animals, overcast haze | 626 |
| 17 | wide establishing shot of narrow alley between high mud-brick walls, storm light | 737 |
| 18 | low angle shot of courtyard house with a shaded arcade, dusk | 848 |
| 19 | high angle shot of mud-brick city wall with a fortified gate, blue hour | 959 |
| 20 | aerial view of mud-brick city wall with a fortified gate, firelight | 42 |
| 21 | high angle shot of ancient town seen from a ridge at distance, moonlight | 101 |
| 22 | high angle shot of clay-plastered wall with a heavy wooden door, dust-filtered sunlight | 202 |
| 23 | aerial view of clay-plastered wall with a heavy wooden door, dust-filtered sunlight | 303 |
| 24 | medium shot of ancient town seen from a ridge at distance, moonlight | 404 |
| 25 | low angle shot of dense low rooftops of an ancient Arabian town, blue hour | 515 |

### `C3` - City walls & settlements

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | aerial view of dense low rooftops of an ancient Arabian town, harsh noon sun | 101 |
| 2 | medium shot of stone steps climbing between packed houses, harsh noon sun | 202 |
| 3 | extreme wide shot of clay-plastered wall with a heavy wooden door, moonlight | 303 |
| 4 | low angle shot of ancient town seen from a ridge at distance, dust-filtered sunlight | 404 |
| 5 | medium shot of stone steps climbing between packed houses, lamplight | 515 |
| 6 | extreme wide shot of ancient town seen from a ridge at distance, golden hour | 626 |
| 7 | aerial view of narrow alley between high mud-brick walls, storm light | 737 |
| 8 | medium shot of stone steps climbing between packed houses, dawn light | 848 |
| 9 | aerial view of dense low rooftops of an ancient Arabian town, firelight | 959 |
| 10 | wide establishing shot of clay-plastered wall with a heavy wooden door, dust-filtered sunlight | 42 |
| 11 | low angle shot of stone steps climbing between packed houses, dusk | 101 |
| 12 | high angle shot of clay-plastered wall with a heavy wooden door, overcast haze | 202 |
| 13 | close detail shot of stone steps climbing between packed houses, dusk | 303 |
| 14 | aerial view of watchtower on a city wall at the desert edge, dusk | 404 |
| 15 | medium shot of dense low rooftops of an ancient Arabian town, golden hour | 515 |
| 16 | wide establishing shot of clay-plastered wall with a heavy wooden door, golden hour | 626 |
| 17 | high angle shot of city gate crowded with travellers and pack animals, moonlight | 737 |
| 18 | aerial view of caravanserai courtyard with tethered camels, moonlight | 848 |
| 19 | aerial view of clay-plastered wall with a heavy wooden door, backlit silhouette | 959 |
| 20 | close detail shot of watchtower on a city wall at the desert edge, lamplight | 42 |
| 21 | extreme wide shot of dense low rooftops of an ancient Arabian town, storm light | 101 |
| 22 | extreme wide shot of narrow alley between high mud-brick walls, firelight | 202 |
| 23 | wide establishing shot of narrow alley between high mud-brick walls, firelight | 303 |
| 24 | wide establishing shot of narrow alley between high mud-brick walls, blue hour | 404 |
| 25 | wide establishing shot of ancient town seen from a ridge at distance, lamplight | 515 |

### `D1` - Mosque exteriors

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | extreme wide shot of small desert mosque standing alone on open ground, harsh noon sun | 101 |
| 2 | close detail shot of simple early mosque of mud brick and palm trunks, blue hour | 202 |
| 3 | wide establishing shot of simple early mosque of mud brick and palm trunks, moonlight | 303 |
| 4 | close detail shot of mosque courtyard with a single minaret, dawn light | 404 |
| 5 | aerial view of mosque wall casting long shadows at dusk, moonlight | 515 |
| 6 | aerial view of small desert mosque standing alone on open ground, overcast haze | 626 |
| 7 | medium shot of mosque courtyard with a single minaret, dawn light | 737 |
| 8 | low angle shot of simple early mosque of mud brick and palm trunks, firelight | 848 |
| 9 | medium shot of early mosque with a low flat roof of palm fronds, dust-filtered sunlight | 959 |
| 10 | wide establishing shot of small desert mosque standing alone on open ground, overcast haze | 42 |
| 11 | aerial view of mosque wall casting long shadows at dusk, overcast haze | 101 |
| 12 | aerial view of small desert mosque standing alone on open ground, harsh noon sun | 202 |
| 13 | low angle shot of early mosque with a low flat roof of palm fronds, moonlight | 303 |
| 14 | medium shot of small desert mosque standing alone on open ground, overcast haze | 404 |
| 15 | aerial view of mosque courtyard with a single minaret, storm light | 515 |
| 16 | extreme wide shot of simple early mosque of mud brick and palm trunks, blue hour | 626 |
| 17 | wide establishing shot of mosque courtyard with a single minaret, backlit silhouette | 737 |
| 18 | wide establishing shot of small desert mosque standing alone on open ground, storm light | 848 |
| 19 | extreme wide shot of simple early mosque of mud brick and palm trunks, dust-filtered sunlight | 959 |
| 20 | close detail shot of simple early mosque of mud brick and palm trunks, backlit silhouette | 42 |
| 21 | wide establishing shot of small desert mosque standing alone on open ground, dawn light | 101 |
| 22 | close detail shot of mosque courtyard with a single minaret, dust-filtered sunlight | 202 |
| 23 | medium shot of mosque wall casting long shadows at dusk, golden hour | 303 |
| 24 | close detail shot of mosque courtyard with a single minaret, firelight | 404 |
| 25 | low angle shot of early mosque with a low flat roof of palm fronds, dusk | 515 |

### `D2` - Mosque exteriors

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | high angle shot of early mosque with a low flat roof of palm fronds, dusk | 101 |
| 2 | high angle shot of mosque wall casting long shadows at dusk, harsh noon sun | 202 |
| 3 | close detail shot of worshippers gathering outside a mosque doorway, dawn light | 303 |
| 4 | close detail shot of mosque wall casting long shadows at dusk, backlit silhouette | 404 |
| 5 | high angle shot of worshippers gathering outside a mosque doorway, firelight | 515 |
| 6 | extreme wide shot of worshippers gathering outside a mosque doorway, blue hour | 626 |
| 7 | extreme wide shot of worshippers gathering outside a mosque doorway, dusk | 737 |
| 8 | wide establishing shot of early mosque with a low flat roof of palm fronds, backlit silhouette | 848 |
| 9 | close detail shot of worshippers gathering outside a mosque doorway, moonlight | 959 |
| 10 | high angle shot of small desert mosque standing alone on open ground, dust-filtered sunlight | 42 |
| 11 | high angle shot of early mosque with a low flat roof of palm fronds, lamplight | 101 |
| 12 | extreme wide shot of early mosque with a low flat roof of palm fronds, dusk | 202 |
| 13 | high angle shot of mosque wall casting long shadows at dusk, dawn light | 303 |
| 14 | wide establishing shot of worshippers gathering outside a mosque doorway, moonlight | 404 |
| 15 | close detail shot of simple early mosque of mud brick and palm trunks, firelight | 515 |
| 16 | high angle shot of mosque wall casting long shadows at dusk, golden hour | 626 |
| 17 | high angle shot of simple early mosque of mud brick and palm trunks, dawn light | 737 |
| 18 | low angle shot of worshippers gathering outside a mosque doorway, moonlight | 848 |
| 19 | aerial view of simple early mosque of mud brick and palm trunks, firelight | 959 |
| 20 | aerial view of early mosque with a low flat roof of palm fronds, dust-filtered sunlight | 42 |
| 21 | high angle shot of early mosque with a low flat roof of palm fronds, moonlight | 101 |
| 22 | high angle shot of simple early mosque of mud brick and palm trunks, firelight | 202 |
| 23 | extreme wide shot of early mosque with a low flat roof of palm fronds, harsh noon sun | 303 |
| 24 | high angle shot of worshippers gathering outside a mosque doorway, storm light | 404 |
| 25 | wide establishing shot of mosque courtyard with a single minaret, golden hour | 515 |

### `D3` - Mosque exteriors

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | close detail shot of simple early mosque of mud brick and palm trunks, overcast haze | 101 |
| 2 | high angle shot of small desert mosque standing alone on open ground, backlit silhouette | 202 |
| 3 | aerial view of early mosque with a low flat roof of palm fronds, blue hour | 303 |
| 4 | low angle shot of small desert mosque standing alone on open ground, dusk | 404 |
| 5 | high angle shot of early mosque with a low flat roof of palm fronds, storm light | 515 |
| 6 | high angle shot of mosque courtyard with a single minaret, dust-filtered sunlight | 626 |
| 7 | extreme wide shot of mosque wall casting long shadows at dusk, moonlight | 737 |
| 8 | high angle shot of simple early mosque of mud brick and palm trunks, dust-filtered sunlight | 848 |
| 9 | wide establishing shot of early mosque with a low flat roof of palm fronds, golden hour | 959 |
| 10 | medium shot of simple early mosque of mud brick and palm trunks, dust-filtered sunlight | 42 |
| 11 | high angle shot of mosque courtyard with a single minaret, backlit silhouette | 101 |
| 12 | wide establishing shot of simple early mosque of mud brick and palm trunks, blue hour | 202 |
| 13 | wide establishing shot of small desert mosque standing alone on open ground, golden hour | 303 |
| 14 | medium shot of worshippers gathering outside a mosque doorway, dawn light | 404 |
| 15 | medium shot of small desert mosque standing alone on open ground, dust-filtered sunlight | 515 |
| 16 | extreme wide shot of mosque wall casting long shadows at dusk, blue hour | 626 |
| 17 | medium shot of mosque wall casting long shadows at dusk, dawn light | 737 |
| 18 | extreme wide shot of early mosque with a low flat roof of palm fronds, backlit silhouette | 848 |
| 19 | close detail shot of mosque wall casting long shadows at dusk, blue hour | 959 |
| 20 | wide establishing shot of worshippers gathering outside a mosque doorway, dawn light | 42 |
| 21 | wide establishing shot of small desert mosque standing alone on open ground, harsh noon sun | 101 |
| 22 | wide establishing shot of early mosque with a low flat roof of palm fronds, lamplight | 202 |
| 23 | aerial view of mosque courtyard with a single minaret, firelight | 303 |
| 24 | high angle shot of mosque wall casting long shadows at dusk, backlit silhouette | 404 |
| 25 | high angle shot of early mosque with a low flat roof of palm fronds, harsh noon sun | 515 |

### `E1` - Mosque interiors & prayer

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | close detail shot of an imam addressing a seated congregation, moonlight | 101 |
| 2 | close detail shot of an imam addressing a seated congregation, harsh noon sun | 202 |
| 3 | extreme wide shot of rows of worshippers in prayer in a dim hall, harsh noon sun | 303 |
| 4 | close detail shot of a man prostrating alone at night, dusk | 404 |
| 5 | medium shot of shafts of dusty light across a columned hall, dust-filtered sunlight | 515 |
| 6 | wide establishing shot of an imam addressing a seated congregation, moonlight | 626 |
| 7 | close detail shot of a man prostrating alone at night, harsh noon sun | 737 |
| 8 | wide establishing shot of prayer mats laid in ordered rows on a stone floor, golden hour | 848 |
| 9 | aerial view of empty prayer hall with light falling through a high window, overcast haze | 959 |
| 10 | close detail shot of prayer mats laid in ordered rows on a stone floor, backlit silhouette | 42 |
| 11 | wide establishing shot of a lone figure praying in an empty mosque, dawn light | 101 |
| 12 | aerial view of an imam addressing a seated congregation, golden hour | 202 |
| 13 | wide establishing shot of hands raised in supplication, blue hour | 303 |
| 14 | extreme wide shot of empty prayer hall with light falling through a high window, dusk | 404 |
| 15 | extreme wide shot of prayer mats laid in ordered rows on a stone floor, golden hour | 515 |
| 16 | close detail shot of prayer mats laid in ordered rows on a stone floor, dawn light | 626 |
| 17 | close detail shot of prayer mats laid in ordered rows on a stone floor, storm light | 737 |
| 18 | close detail shot of hands raised in supplication, storm light | 848 |
| 19 | close detail shot of a lone figure praying in an empty mosque, moonlight | 959 |
| 20 | extreme wide shot of empty prayer hall with light falling through a high window, golden hour | 42 |
| 21 | wide establishing shot of a lone figure praying in an empty mosque, blue hour | 101 |
| 22 | extreme wide shot of a man prostrating alone at night, moonlight | 202 |
| 23 | low angle shot of rows of worshippers in prayer in a dim hall, overcast haze | 303 |
| 24 | medium shot of prayer mats laid in ordered rows on a stone floor, moonlight | 404 |
| 25 | aerial view of a lone figure praying in an empty mosque, blue hour | 515 |

### `E2` - Mosque interiors & prayer

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | aerial view of a man prostrating alone at night, harsh noon sun | 101 |
| 2 | close detail shot of rows of worshippers in prayer in a dim hall, moonlight | 202 |
| 3 | high angle shot of prayer mats laid in ordered rows on a stone floor, backlit silhouette | 303 |
| 4 | medium shot of shafts of dusty light across a columned hall, overcast haze | 404 |
| 5 | wide establishing shot of shafts of dusty light across a columned hall, dust-filtered sunlight | 515 |
| 6 | wide establishing shot of shafts of dusty light across a columned hall, backlit silhouette | 626 |
| 7 | low angle shot of hands raised in supplication, golden hour | 737 |
| 8 | close detail shot of hands raised in supplication, firelight | 848 |
| 9 | aerial view of an imam addressing a seated congregation, backlit silhouette | 959 |
| 10 | aerial view of prayer mats laid in ordered rows on a stone floor, harsh noon sun | 42 |
| 11 | low angle shot of shafts of dusty light across a columned hall, lamplight | 101 |
| 12 | aerial view of a lone figure praying in an empty mosque, storm light | 202 |
| 13 | medium shot of a man prostrating alone at night, golden hour | 303 |
| 14 | extreme wide shot of a lone figure praying in an empty mosque, lamplight | 404 |
| 15 | medium shot of a lone figure praying in an empty mosque, lamplight | 515 |
| 16 | extreme wide shot of hands raised in supplication, blue hour | 626 |
| 17 | close detail shot of hands raised in supplication, blue hour | 737 |
| 18 | aerial view of hands raised in supplication, storm light | 848 |
| 19 | high angle shot of empty prayer hall with light falling through a high window, overcast haze | 959 |
| 20 | medium shot of empty prayer hall with light falling through a high window, backlit silhouette | 42 |
| 21 | aerial view of an imam addressing a seated congregation, moonlight | 101 |
| 22 | medium shot of empty prayer hall with light falling through a high window, lamplight | 202 |
| 23 | low angle shot of shafts of dusty light across a columned hall, harsh noon sun | 303 |
| 24 | extreme wide shot of rows of worshippers in prayer in a dim hall, overcast haze | 404 |
| 25 | medium shot of an imam addressing a seated congregation, blue hour | 515 |

### `E3` - Mosque interiors & prayer

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | high angle shot of rows of worshippers in prayer in a dim hall, dusk | 101 |
| 2 | high angle shot of rows of worshippers in prayer in a dim hall, storm light | 202 |
| 3 | aerial view of rows of worshippers in prayer in a dim hall, dust-filtered sunlight | 303 |
| 4 | low angle shot of empty prayer hall with light falling through a high window, blue hour | 404 |
| 5 | high angle shot of empty prayer hall with light falling through a high window, backlit silhouette | 515 |
| 6 | extreme wide shot of shafts of dusty light across a columned hall, dusk | 626 |
| 7 | low angle shot of shafts of dusty light across a columned hall, moonlight | 737 |
| 8 | aerial view of shafts of dusty light across a columned hall, backlit silhouette | 848 |
| 9 | close detail shot of a lone figure praying in an empty mosque, dawn light | 959 |
| 10 | close detail shot of an imam addressing a seated congregation, dusk | 42 |
| 11 | low angle shot of hands raised in supplication, storm light | 101 |
| 12 | low angle shot of hands raised in supplication, dusk | 202 |
| 13 | close detail shot of an imam addressing a seated congregation, backlit silhouette | 303 |
| 14 | aerial view of hands raised in supplication, moonlight | 404 |
| 15 | extreme wide shot of shafts of dusty light across a columned hall, backlit silhouette | 515 |
| 16 | extreme wide shot of prayer mats laid in ordered rows on a stone floor, lamplight | 626 |
| 17 | low angle shot of hands raised in supplication, overcast haze | 737 |
| 18 | medium shot of an imam addressing a seated congregation, dusk | 848 |
| 19 | medium shot of a lone figure praying in an empty mosque, blue hour | 959 |
| 20 | aerial view of empty prayer hall with light falling through a high window, dawn light | 42 |
| 21 | low angle shot of rows of worshippers in prayer in a dim hall, storm light | 101 |
| 22 | high angle shot of hands raised in supplication, blue hour | 202 |
| 23 | high angle shot of hands raised in supplication, lamplight | 303 |
| 24 | aerial view of rows of worshippers in prayer in a dim hall, overcast haze | 404 |
| 25 | high angle shot of shafts of dusty light across a columned hall, dust-filtered sunlight | 515 |

### `F1` - Markets & commerce

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | extreme wide shot of merchant weighing silver coins on a balance scale, dawn light | 101 |
| 2 | high angle shot of pottery stacked outside a workshop, harsh noon sun | 202 |
| 3 | low angle shot of money changer table with scattered silver dirhams, golden hour | 303 |
| 4 | high angle shot of textile merchant unrolling dyed cloth, golden hour | 404 |
| 5 | low angle shot of a haggling crowd around a market stall, blue hour | 515 |
| 6 | low angle shot of spice sacks and grain baskets in a market stall, firelight | 626 |
| 7 | aerial view of money changer table with scattered silver dirhams, firelight | 737 |
| 8 | wide establishing shot of crowded desert marketplace with cloth awnings, moonlight | 848 |
| 9 | aerial view of spice sacks and grain baskets in a market stall, overcast haze | 959 |
| 10 | wide establishing shot of merchant weighing silver coins on a balance scale, backlit silhouette | 42 |
| 11 | extreme wide shot of livestock pen at the edge of a market, backlit silhouette | 101 |
| 12 | extreme wide shot of blacksmith working at an open forge, golden hour | 202 |
| 13 | close detail shot of date sellers behind piled baskets of fruit, blue hour | 303 |
| 14 | extreme wide shot of crowded desert marketplace with cloth awnings, blue hour | 404 |
| 15 | extreme wide shot of blacksmith working at an open forge, dust-filtered sunlight | 515 |
| 16 | high angle shot of crowded desert marketplace with cloth awnings, blue hour | 626 |
| 17 | close detail shot of merchant weighing silver coins on a balance scale, blue hour | 737 |
| 18 | aerial view of spice sacks and grain baskets in a market stall, harsh noon sun | 848 |
| 19 | medium shot of textile merchant unrolling dyed cloth, backlit silhouette | 959 |
| 20 | medium shot of a haggling crowd around a market stall, storm light | 42 |
| 21 | wide establishing shot of a haggling crowd around a market stall, moonlight | 101 |
| 22 | medium shot of merchant weighing silver coins on a balance scale, dust-filtered sunlight | 202 |
| 23 | high angle shot of a haggling crowd around a market stall, storm light | 303 |
| 24 | low angle shot of a haggling crowd around a market stall, dust-filtered sunlight | 404 |
| 25 | medium shot of pottery stacked outside a workshop, harsh noon sun | 515 |

### `F2` - Markets & commerce

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | low angle shot of money changer table with scattered silver dirhams, storm light | 101 |
| 2 | close detail shot of a haggling crowd around a market stall, lamplight | 202 |
| 3 | close detail shot of livestock pen at the edge of a market, golden hour | 303 |
| 4 | medium shot of livestock pen at the edge of a market, lamplight | 404 |
| 5 | high angle shot of livestock pen at the edge of a market, dusk | 515 |
| 6 | extreme wide shot of date sellers behind piled baskets of fruit, moonlight | 626 |
| 7 | close detail shot of pottery stacked outside a workshop, lamplight | 737 |
| 8 | high angle shot of a haggling crowd around a market stall, backlit silhouette | 848 |
| 9 | medium shot of textile merchant unrolling dyed cloth, dawn light | 959 |
| 10 | medium shot of livestock pen at the edge of a market, moonlight | 42 |
| 11 | extreme wide shot of money changer table with scattered silver dirhams, backlit silhouette | 101 |
| 12 | low angle shot of date sellers behind piled baskets of fruit, dust-filtered sunlight | 202 |
| 13 | extreme wide shot of pottery stacked outside a workshop, dusk | 303 |
| 14 | high angle shot of blacksmith working at an open forge, golden hour | 404 |
| 15 | aerial view of merchant weighing silver coins on a balance scale, firelight | 515 |
| 16 | close detail shot of crowded desert marketplace with cloth awnings, lamplight | 626 |
| 17 | wide establishing shot of crowded desert marketplace with cloth awnings, firelight | 737 |
| 18 | high angle shot of crowded desert marketplace with cloth awnings, moonlight | 848 |
| 19 | aerial view of blacksmith working at an open forge, firelight | 959 |
| 20 | aerial view of merchant weighing silver coins on a balance scale, golden hour | 42 |
| 21 | high angle shot of a haggling crowd around a market stall, firelight | 101 |
| 22 | wide establishing shot of date sellers behind piled baskets of fruit, dawn light | 202 |
| 23 | low angle shot of a haggling crowd around a market stall, harsh noon sun | 303 |
| 24 | close detail shot of date sellers behind piled baskets of fruit, storm light | 404 |
| 25 | close detail shot of date sellers behind piled baskets of fruit, dawn light | 515 |

### `F3` - Markets & commerce

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | extreme wide shot of merchant weighing silver coins on a balance scale, blue hour | 101 |
| 2 | aerial view of a haggling crowd around a market stall, lamplight | 202 |
| 3 | medium shot of crowded desert marketplace with cloth awnings, firelight | 303 |
| 4 | extreme wide shot of livestock pen at the edge of a market, overcast haze | 404 |
| 5 | high angle shot of spice sacks and grain baskets in a market stall, storm light | 515 |
| 6 | medium shot of blacksmith working at an open forge, backlit silhouette | 626 |
| 7 | wide establishing shot of pottery stacked outside a workshop, harsh noon sun | 737 |
| 8 | low angle shot of blacksmith working at an open forge, golden hour | 848 |
| 9 | wide establishing shot of spice sacks and grain baskets in a market stall, moonlight | 959 |
| 10 | aerial view of pottery stacked outside a workshop, overcast haze | 42 |
| 11 | aerial view of pottery stacked outside a workshop, dawn light | 101 |
| 12 | high angle shot of pottery stacked outside a workshop, firelight | 202 |
| 13 | low angle shot of merchant weighing silver coins on a balance scale, dust-filtered sunlight | 303 |
| 14 | low angle shot of money changer table with scattered silver dirhams, dawn light | 404 |
| 15 | extreme wide shot of date sellers behind piled baskets of fruit, dusk | 515 |
| 16 | extreme wide shot of spice sacks and grain baskets in a market stall, moonlight | 626 |
| 17 | medium shot of date sellers behind piled baskets of fruit, dusk | 737 |
| 18 | close detail shot of pottery stacked outside a workshop, overcast haze | 848 |
| 19 | extreme wide shot of money changer table with scattered silver dirhams, overcast haze | 959 |
| 20 | medium shot of livestock pen at the edge of a market, blue hour | 42 |
| 21 | extreme wide shot of textile merchant unrolling dyed cloth, moonlight | 101 |
| 22 | high angle shot of a haggling crowd around a market stall, overcast haze | 202 |
| 23 | medium shot of blacksmith working at an open forge, firelight | 303 |
| 24 | aerial view of money changer table with scattered silver dirhams, dawn light | 404 |
| 25 | low angle shot of pottery stacked outside a workshop, dusk | 515 |

### `G1` - Tents & encampments

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | high angle shot of smoke rising from an encampment at first light, dusk | 101 |
| 2 | low angle shot of tent ropes and pegs in close detail, blue hour | 202 |
| 3 | low angle shot of carpets and cushions inside a chieftain tent, dusk | 303 |
| 4 | low angle shot of carpets and cushions inside a chieftain tent, golden hour | 404 |
| 5 | high angle shot of smoke rising from an encampment at first light, overcast haze | 515 |
| 6 | low angle shot of carpets and cushions inside a chieftain tent, lamplight | 626 |
| 7 | medium shot of camels couched beside a tent at dawn, dusk | 737 |
| 8 | high angle shot of black goat-hair tents pitched on open ground, harsh noon sun | 848 |
| 9 | extreme wide shot of interior of a large tent lit by an oil lamp, storm light | 959 |
| 10 | wide establishing shot of camels couched beside a tent at dawn, lamplight | 42 |
| 11 | medium shot of tent ropes and pegs in close detail, lamplight | 101 |
| 12 | low angle shot of camels couched beside a tent at dawn, blue hour | 202 |
| 13 | aerial view of tent ropes and pegs in close detail, lamplight | 303 |
| 14 | close detail shot of a war camp of many tents seen from a ridge, firelight | 404 |
| 15 | low angle shot of tent ropes and pegs in close detail, storm light | 515 |
| 16 | low angle shot of interior of a large tent lit by an oil lamp, dust-filtered sunlight | 626 |
| 17 | high angle shot of tent ropes and pegs in close detail, backlit silhouette | 737 |
| 18 | low angle shot of a war camp of many tents seen from a ridge, lamplight | 848 |
| 19 | medium shot of a war camp of many tents seen from a ridge, storm light | 959 |
| 20 | wide establishing shot of smoke rising from an encampment at first light, dawn light | 42 |
| 21 | medium shot of camels couched beside a tent at dawn, dust-filtered sunlight | 101 |
| 22 | aerial view of black goat-hair tents pitched on open ground, blue hour | 202 |
| 23 | aerial view of camels couched beside a tent at dawn, blue hour | 303 |
| 24 | medium shot of tent ropes and pegs in close detail, moonlight | 404 |
| 25 | extreme wide shot of interior of a large tent lit by an oil lamp, dust-filtered sunlight | 515 |

### `G2` - Tents & encampments

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | low angle shot of camels couched beside a tent at dawn, lamplight | 101 |
| 2 | wide establishing shot of a war camp of many tents seen from a ridge, firelight | 202 |
| 3 | wide establishing shot of carpets and cushions inside a chieftain tent, firelight | 303 |
| 4 | aerial view of interior of a large tent lit by an oil lamp, blue hour | 404 |
| 5 | medium shot of smoke rising from an encampment at first light, dust-filtered sunlight | 515 |
| 6 | medium shot of camels couched beside a tent at dawn, lamplight | 626 |
| 7 | extreme wide shot of smoke rising from an encampment at first light, backlit silhouette | 737 |
| 8 | wide establishing shot of camels couched beside a tent at dawn, golden hour | 848 |
| 9 | close detail shot of camels couched beside a tent at dawn, golden hour | 959 |
| 10 | medium shot of carpets and cushions inside a chieftain tent, backlit silhouette | 42 |
| 11 | high angle shot of camels couched beside a tent at dawn, golden hour | 101 |
| 12 | medium shot of black goat-hair tents pitched on open ground, harsh noon sun | 202 |
| 13 | close detail shot of tent ropes and pegs in close detail, dawn light | 303 |
| 14 | extreme wide shot of carpets and cushions inside a chieftain tent, overcast haze | 404 |
| 15 | aerial view of a war camp of many tents seen from a ridge, dawn light | 515 |
| 16 | close detail shot of smoke rising from an encampment at first light, backlit silhouette | 626 |
| 17 | aerial view of a war camp of many tents seen from a ridge, golden hour | 737 |
| 18 | close detail shot of black goat-hair tents pitched on open ground, storm light | 848 |
| 19 | medium shot of smoke rising from an encampment at first light, lamplight | 959 |
| 20 | high angle shot of a war camp of many tents seen from a ridge, golden hour | 42 |
| 21 | close detail shot of black goat-hair tents pitched on open ground, dawn light | 101 |
| 22 | wide establishing shot of carpets and cushions inside a chieftain tent, backlit silhouette | 202 |
| 23 | high angle shot of interior of a large tent lit by an oil lamp, dust-filtered sunlight | 303 |
| 24 | extreme wide shot of black goat-hair tents pitched on open ground, dawn light | 404 |
| 25 | close detail shot of smoke rising from an encampment at first light, dusk | 515 |

### `G3` - Tents & encampments

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | close detail shot of black goat-hair tents pitched on open ground, harsh noon sun | 101 |
| 2 | low angle shot of tent ropes and pegs in close detail, dust-filtered sunlight | 202 |
| 3 | aerial view of carpets and cushions inside a chieftain tent, dust-filtered sunlight | 303 |
| 4 | aerial view of encampment at dusk with cooking fires burning, firelight | 404 |
| 5 | close detail shot of encampment at dusk with cooking fires burning, moonlight | 515 |
| 6 | low angle shot of a war camp of many tents seen from a ridge, overcast haze | 626 |
| 7 | low angle shot of encampment at dusk with cooking fires burning, harsh noon sun | 737 |
| 8 | low angle shot of encampment at dusk with cooking fires burning, dust-filtered sunlight | 848 |
| 9 | low angle shot of encampment at dusk with cooking fires burning, dawn light | 959 |
| 10 | extreme wide shot of smoke rising from an encampment at first light, dawn light | 42 |
| 11 | low angle shot of camels couched beside a tent at dawn, harsh noon sun | 101 |
| 12 | low angle shot of camels couched beside a tent at dawn, moonlight | 202 |
| 13 | wide establishing shot of carpets and cushions inside a chieftain tent, blue hour | 303 |
| 14 | high angle shot of smoke rising from an encampment at first light, storm light | 404 |
| 15 | aerial view of carpets and cushions inside a chieftain tent, storm light | 515 |
| 16 | aerial view of encampment at dusk with cooking fires burning, moonlight | 626 |
| 17 | wide establishing shot of carpets and cushions inside a chieftain tent, storm light | 737 |
| 18 | extreme wide shot of smoke rising from an encampment at first light, storm light | 848 |
| 19 | extreme wide shot of camels couched beside a tent at dawn, storm light | 959 |
| 20 | low angle shot of black goat-hair tents pitched on open ground, storm light | 42 |
| 21 | close detail shot of smoke rising from an encampment at first light, golden hour | 101 |
| 22 | close detail shot of interior of a large tent lit by an oil lamp, lamplight | 202 |
| 23 | low angle shot of camels couched beside a tent at dawn, storm light | 303 |
| 24 | extreme wide shot of smoke rising from an encampment at first light, dusk | 404 |
| 25 | extreme wide shot of camels couched beside a tent at dawn, blue hour | 515 |

### `H1` - Councils & assemblies

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | high angle shot of a tense negotiation between two delegations, golden hour | 101 |
| 2 | wide establishing shot of men arguing across a low table of documents, dust-filtered sunlight | 202 |
| 3 | medium shot of a leader addressing seated tribal chiefs, dust-filtered sunlight | 303 |
| 4 | low angle shot of a tense negotiation between two delegations, harsh noon sun | 404 |
| 5 | aerial view of scribes recording a meeting from the side, harsh noon sun | 515 |
| 6 | aerial view of an oath being sworn with clasped hands, blue hour | 626 |
| 7 | close detail shot of a council falling silent as one man rises, firelight | 737 |
| 8 | low angle shot of a council falling silent as one man rises, backlit silhouette | 848 |
| 9 | wide establishing shot of scribes recording a meeting from the side, storm light | 959 |
| 10 | low angle shot of messenger delivering news to a seated council, lamplight | 42 |
| 11 | medium shot of messenger delivering news to a seated council, golden hour | 101 |
| 12 | low angle shot of messenger delivering news to a seated council, backlit silhouette | 202 |
| 13 | high angle shot of a council falling silent as one man rises, moonlight | 303 |
| 14 | high angle shot of men arguing across a low table of documents, dust-filtered sunlight | 404 |
| 15 | medium shot of men arguing across a low table of documents, dusk | 515 |
| 16 | extreme wide shot of a leader addressing seated tribal chiefs, overcast haze | 626 |
| 17 | low angle shot of scribes recording a meeting from the side, overcast haze | 737 |
| 18 | medium shot of a tense negotiation between two delegations, dawn light | 848 |
| 19 | low angle shot of an oath being sworn with clasped hands, storm light | 959 |
| 20 | aerial view of messenger delivering news to a seated council, dust-filtered sunlight | 42 |
| 21 | high angle shot of elders seated in a circle in serious discussion, dusk | 101 |
| 22 | close detail shot of an oath being sworn with clasped hands, moonlight | 202 |
| 23 | wide establishing shot of a council falling silent as one man rises, dust-filtered sunlight | 303 |
| 24 | extreme wide shot of messenger delivering news to a seated council, storm light | 404 |
| 25 | aerial view of scribes recording a meeting from the side, storm light | 515 |

### `H2` - Councils & assemblies

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | aerial view of a tense negotiation between two delegations, harsh noon sun | 101 |
| 2 | medium shot of a leader addressing seated tribal chiefs, harsh noon sun | 202 |
| 3 | high angle shot of a tense negotiation between two delegations, storm light | 303 |
| 4 | low angle shot of messenger delivering news to a seated council, firelight | 404 |
| 5 | low angle shot of messenger delivering news to a seated council, overcast haze | 515 |
| 6 | medium shot of scribes recording a meeting from the side, golden hour | 626 |
| 7 | close detail shot of elders seated in a circle in serious discussion, lamplight | 737 |
| 8 | aerial view of a leader addressing seated tribal chiefs, lamplight | 848 |
| 9 | medium shot of scribes recording a meeting from the side, moonlight | 959 |
| 10 | medium shot of a council falling silent as one man rises, golden hour | 42 |
| 11 | wide establishing shot of a council falling silent as one man rises, dawn light | 101 |
| 12 | wide establishing shot of men arguing across a low table of documents, firelight | 202 |
| 13 | high angle shot of messenger delivering news to a seated council, dusk | 303 |
| 14 | close detail shot of an oath being sworn with clasped hands, backlit silhouette | 404 |
| 15 | medium shot of an oath being sworn with clasped hands, moonlight | 515 |
| 16 | high angle shot of a leader addressing seated tribal chiefs, dust-filtered sunlight | 626 |
| 17 | low angle shot of a council falling silent as one man rises, storm light | 737 |
| 18 | aerial view of a council falling silent as one man rises, firelight | 848 |
| 19 | extreme wide shot of a tense negotiation between two delegations, moonlight | 959 |
| 20 | high angle shot of a tense negotiation between two delegations, backlit silhouette | 42 |
| 21 | low angle shot of scribes recording a meeting from the side, blue hour | 101 |
| 22 | low angle shot of men arguing across a low table of documents, backlit silhouette | 202 |
| 23 | low angle shot of a council falling silent as one man rises, dust-filtered sunlight | 303 |
| 24 | medium shot of a tense negotiation between two delegations, golden hour | 404 |
| 25 | extreme wide shot of an oath being sworn with clasped hands, backlit silhouette | 515 |

### `H3` - Councils & assemblies

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | low angle shot of scribes recording a meeting from the side, dawn light | 101 |
| 2 | wide establishing shot of messenger delivering news to a seated council, lamplight | 202 |
| 3 | wide establishing shot of a tense negotiation between two delegations, blue hour | 303 |
| 4 | extreme wide shot of scribes recording a meeting from the side, backlit silhouette | 404 |
| 5 | close detail shot of an oath being sworn with clasped hands, dust-filtered sunlight | 515 |
| 6 | close detail shot of a leader addressing seated tribal chiefs, dust-filtered sunlight | 626 |
| 7 | medium shot of a tense negotiation between two delegations, backlit silhouette | 737 |
| 8 | aerial view of a tense negotiation between two delegations, dusk | 848 |
| 9 | wide establishing shot of a tense negotiation between two delegations, overcast haze | 959 |
| 10 | high angle shot of an oath being sworn with clasped hands, golden hour | 42 |
| 11 | high angle shot of messenger delivering news to a seated council, storm light | 101 |
| 12 | wide establishing shot of elders seated in a circle in serious discussion, storm light | 202 |
| 13 | high angle shot of men arguing across a low table of documents, harsh noon sun | 303 |
| 14 | high angle shot of a council falling silent as one man rises, dusk | 404 |
| 15 | wide establishing shot of elders seated in a circle in serious discussion, backlit silhouette | 515 |
| 16 | extreme wide shot of a leader addressing seated tribal chiefs, blue hour | 626 |
| 17 | aerial view of men arguing across a low table of documents, golden hour | 737 |
| 18 | aerial view of elders seated in a circle in serious discussion, overcast haze | 848 |
| 19 | high angle shot of an oath being sworn with clasped hands, moonlight | 959 |
| 20 | aerial view of messenger delivering news to a seated council, harsh noon sun | 42 |
| 21 | low angle shot of elders seated in a circle in serious discussion, blue hour | 101 |
| 22 | medium shot of men arguing across a low table of documents, lamplight | 202 |
| 23 | close detail shot of scribes recording a meeting from the side, dawn light | 303 |
| 24 | close detail shot of men arguing across a low table of documents, dawn light | 404 |
| 25 | aerial view of scribes recording a meeting from the side, dusk | 515 |

### `I1` - Elders, leaders & portraits

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | extreme wide shot of a stern chieftain in a dark cloak, golden hour | 101 |
| 2 | medium shot of lined old hands resting on a wooden staff, golden hour | 202 |
| 3 | extreme wide shot of a leader standing alone in an empty courtyard, firelight | 303 |
| 4 | low angle shot of close portrait of tired resolute eyes, lamplight | 404 |
| 5 | high angle shot of a stern chieftain in a dark cloak, golden hour | 515 |
| 6 | extreme wide shot of an ageing scholar surrounded by manuscripts, lamplight | 626 |
| 7 | high angle shot of close portrait of tired resolute eyes, golden hour | 737 |
| 8 | medium shot of lined old hands resting on a wooden staff, dust-filtered sunlight | 848 |
| 9 | aerial view of a leader standing alone in an empty courtyard, backlit silhouette | 959 |
| 10 | low angle shot of grieving elder with lowered head, blue hour | 42 |
| 11 | extreme wide shot of close portrait of tired resolute eyes, overcast haze | 101 |
| 12 | aerial view of close portrait of tired resolute eyes, golden hour | 202 |
| 13 | high angle shot of an ageing scholar surrounded by manuscripts, dust-filtered sunlight | 303 |
| 14 | wide establishing shot of an ageing scholar surrounded by manuscripts, backlit silhouette | 404 |
| 15 | wide establishing shot of grieving elder with lowered head, golden hour | 515 |
| 16 | close detail shot of dignified leader in simple undyed cloth, dawn light | 626 |
| 17 | aerial view of close portrait of tired resolute eyes, dust-filtered sunlight | 737 |
| 18 | low angle shot of weathered elderly man with a white beard in plain robes, lamplight | 848 |
| 19 | extreme wide shot of a leader looking out over a city at dawn, overcast haze | 959 |
| 20 | close detail shot of weathered elderly man with a white beard in plain robes, dusk | 42 |
| 21 | high angle shot of a leader looking out over a city at dawn, dawn light | 101 |
| 22 | low angle shot of grieving elder with lowered head, backlit silhouette | 202 |
| 23 | medium shot of dignified leader in simple undyed cloth, dust-filtered sunlight | 303 |
| 24 | extreme wide shot of weathered elderly man with a white beard in plain robes, storm light | 404 |
| 25 | close detail shot of lined old hands resting on a wooden staff, lamplight | 515 |

### `I2` - Elders, leaders & portraits

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | wide establishing shot of a stern chieftain in a dark cloak, harsh noon sun | 101 |
| 2 | close detail shot of dignified leader in simple undyed cloth, blue hour | 202 |
| 3 | medium shot of weathered elderly man with a white beard in plain robes, harsh noon sun | 303 |
| 4 | wide establishing shot of dignified leader in simple undyed cloth, firelight | 404 |
| 5 | low angle shot of dignified leader in simple undyed cloth, overcast haze | 515 |
| 6 | low angle shot of close portrait of tired resolute eyes, harsh noon sun | 626 |
| 7 | extreme wide shot of a man weeping quietly, face partly turned away, dusk | 737 |
| 8 | extreme wide shot of an ageing scholar surrounded by manuscripts, overcast haze | 848 |
| 9 | high angle shot of close portrait of tired resolute eyes, harsh noon sun | 959 |
| 10 | high angle shot of close portrait of tired resolute eyes, dawn light | 42 |
| 11 | close detail shot of an ageing scholar surrounded by manuscripts, dusk | 101 |
| 12 | wide establishing shot of a leader looking out over a city at dawn, storm light | 202 |
| 13 | medium shot of an ageing scholar surrounded by manuscripts, backlit silhouette | 303 |
| 14 | high angle shot of close portrait of tired resolute eyes, overcast haze | 404 |
| 15 | aerial view of lined old hands resting on a wooden staff, lamplight | 515 |
| 16 | low angle shot of a stern chieftain in a dark cloak, lamplight | 626 |
| 17 | extreme wide shot of a man weeping quietly, face partly turned away, dawn light | 737 |
| 18 | wide establishing shot of a man weeping quietly, face partly turned away, overcast haze | 848 |
| 19 | high angle shot of a stern chieftain in a dark cloak, dust-filtered sunlight | 959 |
| 20 | aerial view of grieving elder with lowered head, backlit silhouette | 42 |
| 21 | extreme wide shot of weathered elderly man with a white beard in plain robes, golden hour | 101 |
| 22 | extreme wide shot of dignified leader in simple undyed cloth, dust-filtered sunlight | 202 |
| 23 | extreme wide shot of a leader standing alone in an empty courtyard, lamplight | 303 |
| 24 | extreme wide shot of a leader looking out over a city at dawn, dust-filtered sunlight | 404 |
| 25 | aerial view of grieving elder with lowered head, storm light | 515 |

### `I3` - Elders, leaders & portraits

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | wide establishing shot of a stern chieftain in a dark cloak, lamplight | 101 |
| 2 | wide establishing shot of an ageing scholar surrounded by manuscripts, storm light | 202 |
| 3 | extreme wide shot of dignified leader in simple undyed cloth, dusk | 303 |
| 4 | wide establishing shot of weathered elderly man with a white beard in plain robes, lamplight | 404 |
| 5 | high angle shot of a stern chieftain in a dark cloak, overcast haze | 515 |
| 6 | extreme wide shot of a leader standing alone in an empty courtyard, storm light | 626 |
| 7 | aerial view of dignified leader in simple undyed cloth, moonlight | 737 |
| 8 | aerial view of grieving elder with lowered head, lamplight | 848 |
| 9 | medium shot of a leader looking out over a city at dawn, storm light | 959 |
| 10 | wide establishing shot of a leader standing alone in an empty courtyard, dusk | 42 |
| 11 | high angle shot of weathered elderly man with a white beard in plain robes, firelight | 101 |
| 12 | high angle shot of an ageing scholar surrounded by manuscripts, moonlight | 202 |
| 13 | wide establishing shot of grieving elder with lowered head, dust-filtered sunlight | 303 |
| 14 | aerial view of a stern chieftain in a dark cloak, firelight | 404 |
| 15 | extreme wide shot of a man weeping quietly, face partly turned away, dust-filtered sunlight | 515 |
| 16 | high angle shot of grieving elder with lowered head, dust-filtered sunlight | 626 |
| 17 | aerial view of a leader standing alone in an empty courtyard, moonlight | 737 |
| 18 | low angle shot of a leader looking out over a city at dawn, backlit silhouette | 848 |
| 19 | wide establishing shot of grieving elder with lowered head, harsh noon sun | 959 |
| 20 | close detail shot of lined old hands resting on a wooden staff, backlit silhouette | 42 |
| 21 | medium shot of an ageing scholar surrounded by manuscripts, dust-filtered sunlight | 101 |
| 22 | aerial view of close portrait of tired resolute eyes, overcast haze | 202 |
| 23 | high angle shot of weathered elderly man with a white beard in plain robes, harsh noon sun | 303 |
| 24 | extreme wide shot of a leader standing alone in an empty courtyard, harsh noon sun | 404 |
| 25 | aerial view of grieving elder with lowered head, firelight | 515 |

### `J1` - Warriors & riders

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | close detail shot of rider in a dark cloak on a rearing horse, dusk | 101 |
| 2 | medium shot of warrior shield and helmet resting on sand, dusk | 202 |
| 3 | close detail shot of armoured horseman silhouetted on a ridge, lamplight | 303 |
| 4 | aerial view of a fighter adjusting his sword belt, dust-filtered sunlight | 404 |
| 5 | aerial view of two warriors clasping forearms in farewell, golden hour | 515 |
| 6 | aerial view of young warrior in chain mail holding a spear, harsh noon sun | 626 |
| 7 | medium shot of rider in a dark cloak on a rearing horse, lamplight | 737 |
| 8 | high angle shot of two warriors clasping forearms in farewell, dusk | 848 |
| 9 | high angle shot of a fighter adjusting his sword belt, overcast haze | 959 |
| 10 | medium shot of rider in a dark cloak on a rearing horse, golden hour | 42 |
| 11 | low angle shot of a fighter adjusting his sword belt, overcast haze | 101 |
| 12 | medium shot of warrior sharpening a blade by firelight, lamplight | 202 |
| 13 | medium shot of rider in a dark cloak on a rearing horse, moonlight | 303 |
| 14 | medium shot of warrior sharpening a blade by firelight, dust-filtered sunlight | 404 |
| 15 | close detail shot of two warriors clasping forearms in farewell, blue hour | 515 |
| 16 | extreme wide shot of warrior shield and helmet resting on sand, golden hour | 626 |
| 17 | wide establishing shot of two warriors clasping forearms in farewell, dusk | 737 |
| 18 | wide establishing shot of young warrior in chain mail holding a spear, lamplight | 848 |
| 19 | low angle shot of warrior sharpening a blade by firelight, firelight | 959 |
| 20 | extreme wide shot of warrior sharpening a blade by firelight, dawn light | 42 |
| 21 | wide establishing shot of young warrior in chain mail holding a spear, firelight | 101 |
| 22 | low angle shot of rider in a dark cloak on a rearing horse, dusk | 202 |
| 23 | medium shot of warrior sharpening a blade by firelight, harsh noon sun | 303 |
| 24 | wide establishing shot of warrior sharpening a blade by firelight, dust-filtered sunlight | 404 |
| 25 | aerial view of warrior sharpening a blade by firelight, moonlight | 515 |

### `J2` - Warriors & riders

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | aerial view of two warriors clasping forearms in farewell, firelight | 101 |
| 2 | low angle shot of young warrior in chain mail holding a spear, moonlight | 202 |
| 3 | medium shot of dusty rider arriving at a city gate, firelight | 303 |
| 4 | close detail shot of warrior sharpening a blade by firelight, moonlight | 404 |
| 5 | aerial view of warrior sharpening a blade by firelight, firelight | 515 |
| 6 | close detail shot of rider in a dark cloak on a rearing horse, harsh noon sun | 626 |
| 7 | wide establishing shot of rider in a dark cloak on a rearing horse, dust-filtered sunlight | 737 |
| 8 | extreme wide shot of young warrior in chain mail holding a spear, firelight | 848 |
| 9 | low angle shot of a fighter adjusting his sword belt, dusk | 959 |
| 10 | extreme wide shot of rider in a dark cloak on a rearing horse, dust-filtered sunlight | 42 |
| 11 | medium shot of two warriors clasping forearms in farewell, storm light | 101 |
| 12 | close detail shot of warrior sharpening a blade by firelight, dawn light | 202 |
| 13 | close detail shot of warrior sharpening a blade by firelight, golden hour | 303 |
| 14 | medium shot of armoured horseman silhouetted on a ridge, dusk | 404 |
| 15 | wide establishing shot of a fighter adjusting his sword belt, overcast haze | 515 |
| 16 | aerial view of rider in a dark cloak on a rearing horse, golden hour | 626 |
| 17 | wide establishing shot of young warrior in chain mail holding a spear, blue hour | 737 |
| 18 | high angle shot of warrior shield and helmet resting on sand, harsh noon sun | 848 |
| 19 | wide establishing shot of a fighter adjusting his sword belt, blue hour | 959 |
| 20 | medium shot of rider in a dark cloak on a rearing horse, dusk | 42 |
| 21 | medium shot of dusty rider arriving at a city gate, golden hour | 101 |
| 22 | high angle shot of a fighter adjusting his sword belt, backlit silhouette | 202 |
| 23 | low angle shot of armoured horseman silhouetted on a ridge, blue hour | 303 |
| 24 | wide establishing shot of two warriors clasping forearms in farewell, lamplight | 404 |
| 25 | high angle shot of warrior sharpening a blade by firelight, lamplight | 515 |

### `J3` - Warriors & riders

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | low angle shot of dusty rider arriving at a city gate, firelight | 101 |
| 2 | medium shot of dusty rider arriving at a city gate, moonlight | 202 |
| 3 | close detail shot of warrior sharpening a blade by firelight, lamplight | 303 |
| 4 | aerial view of young warrior in chain mail holding a spear, dust-filtered sunlight | 404 |
| 5 | low angle shot of two warriors clasping forearms in farewell, storm light | 515 |
| 6 | high angle shot of a fighter adjusting his sword belt, dusk | 626 |
| 7 | extreme wide shot of warrior sharpening a blade by firelight, backlit silhouette | 737 |
| 8 | high angle shot of young warrior in chain mail holding a spear, backlit silhouette | 848 |
| 9 | medium shot of warrior sharpening a blade by firelight, firelight | 959 |
| 10 | low angle shot of warrior shield and helmet resting on sand, backlit silhouette | 42 |
| 11 | wide establishing shot of armoured horseman silhouetted on a ridge, dusk | 101 |
| 12 | high angle shot of rider in a dark cloak on a rearing horse, dawn light | 202 |
| 13 | aerial view of rider in a dark cloak on a rearing horse, storm light | 303 |
| 14 | wide establishing shot of a fighter adjusting his sword belt, dust-filtered sunlight | 404 |
| 15 | wide establishing shot of armoured horseman silhouetted on a ridge, storm light | 515 |
| 16 | low angle shot of a fighter adjusting his sword belt, dawn light | 626 |
| 17 | medium shot of young warrior in chain mail holding a spear, dust-filtered sunlight | 737 |
| 18 | aerial view of young warrior in chain mail holding a spear, golden hour | 848 |
| 19 | aerial view of young warrior in chain mail holding a spear, blue hour | 959 |
| 20 | low angle shot of a fighter adjusting his sword belt, moonlight | 42 |
| 21 | low angle shot of two warriors clasping forearms in farewell, golden hour | 101 |
| 22 | low angle shot of armoured horseman silhouetted on a ridge, moonlight | 202 |
| 23 | high angle shot of two warriors clasping forearms in farewell, backlit silhouette | 303 |
| 24 | high angle shot of warrior shield and helmet resting on sand, firelight | 404 |
| 25 | high angle shot of armoured horseman silhouetted on a ridge, golden hour | 515 |

### `K1` - Crowds & gatherings

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | aerial view of a large crowd listening in absolute silence, dawn light | 101 |
| 2 | medium shot of a crowd parting to let a rider through, storm light | 202 |
| 3 | high angle shot of a mass of pilgrims moving along a road, moonlight | 303 |
| 4 | high angle shot of a crowd parting to let a rider through, golden hour | 404 |
| 5 | aerial view of a mass of pilgrims moving along a road, storm light | 515 |
| 6 | close detail shot of anxious faces in a packed courtyard, blue hour | 626 |
| 7 | aerial view of people pressing forward to hear a speaker, golden hour | 737 |
| 8 | medium shot of people pressing forward to hear a speaker, blue hour | 848 |
| 9 | aerial view of townspeople gathering in a square at dawn, dawn light | 959 |
| 10 | medium shot of a crowd parting to let a rider through, dusk | 42 |
| 11 | low angle shot of people pressing forward to hear a speaker, firelight | 101 |
| 12 | close detail shot of a large crowd listening in absolute silence, golden hour | 202 |
| 13 | low angle shot of anxious faces in a packed courtyard, dust-filtered sunlight | 303 |
| 14 | medium shot of a divided crowd, some standing, some seated, storm light | 404 |
| 15 | medium shot of anxious faces in a packed courtyard, lamplight | 515 |
| 16 | high angle shot of people pressing forward to hear a speaker, dusk | 626 |
| 17 | medium shot of anxious faces in a packed courtyard, moonlight | 737 |
| 18 | high angle shot of anxious faces in a packed courtyard, dust-filtered sunlight | 848 |
| 19 | high angle shot of mourners gathered outside a doorway, firelight | 959 |
| 20 | close detail shot of anxious faces in a packed courtyard, storm light | 42 |
| 21 | close detail shot of mourners gathered outside a doorway, dust-filtered sunlight | 101 |
| 22 | close detail shot of a mass of pilgrims moving along a road, overcast haze | 202 |
| 23 | high angle shot of townspeople gathering in a square at dawn, firelight | 303 |
| 24 | wide establishing shot of a crowd parting to let a rider through, dust-filtered sunlight | 404 |
| 25 | high angle shot of anxious faces in a packed courtyard, harsh noon sun | 515 |

### `K2` - Crowds & gatherings

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | extreme wide shot of a large crowd listening in absolute silence, golden hour | 101 |
| 2 | extreme wide shot of a crowd parting to let a rider through, firelight | 202 |
| 3 | low angle shot of townspeople gathering in a square at dawn, firelight | 303 |
| 4 | aerial view of mourners gathered outside a doorway, lamplight | 404 |
| 5 | extreme wide shot of anxious faces in a packed courtyard, moonlight | 515 |
| 6 | close detail shot of anxious faces in a packed courtyard, firelight | 626 |
| 7 | close detail shot of a crowd parting to let a rider through, blue hour | 737 |
| 8 | high angle shot of a crowd parting to let a rider through, backlit silhouette | 848 |
| 9 | medium shot of a large crowd listening in absolute silence, storm light | 959 |
| 10 | close detail shot of townspeople gathering in a square at dawn, dusk | 42 |
| 11 | close detail shot of townspeople gathering in a square at dawn, blue hour | 101 |
| 12 | extreme wide shot of a mass of pilgrims moving along a road, moonlight | 202 |
| 13 | extreme wide shot of a mass of pilgrims moving along a road, dawn light | 303 |
| 14 | wide establishing shot of a crowd parting to let a rider through, dusk | 404 |
| 15 | low angle shot of people pressing forward to hear a speaker, harsh noon sun | 515 |
| 16 | low angle shot of a divided crowd, some standing, some seated, moonlight | 626 |
| 17 | aerial view of a mass of pilgrims moving along a road, lamplight | 737 |
| 18 | wide establishing shot of mourners gathered outside a doorway, dusk | 848 |
| 19 | wide establishing shot of people pressing forward to hear a speaker, blue hour | 959 |
| 20 | wide establishing shot of a divided crowd, some standing, some seated, backlit silhouette | 42 |
| 21 | extreme wide shot of anxious faces in a packed courtyard, overcast haze | 101 |
| 22 | aerial view of a mass of pilgrims moving along a road, overcast haze | 202 |
| 23 | medium shot of a large crowd listening in absolute silence, dust-filtered sunlight | 303 |
| 24 | aerial view of mourners gathered outside a doorway, dawn light | 404 |
| 25 | low angle shot of mourners gathered outside a doorway, storm light | 515 |

### `K3` - Crowds & gatherings

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | close detail shot of a crowd parting to let a rider through, golden hour | 101 |
| 2 | high angle shot of a crowd parting to let a rider through, moonlight | 202 |
| 3 | high angle shot of mourners gathered outside a doorway, storm light | 303 |
| 4 | close detail shot of a mass of pilgrims moving along a road, storm light | 404 |
| 5 | low angle shot of mourners gathered outside a doorway, lamplight | 515 |
| 6 | aerial view of a mass of pilgrims moving along a road, dusk | 626 |
| 7 | aerial view of anxious faces in a packed courtyard, firelight | 737 |
| 8 | high angle shot of a divided crowd, some standing, some seated, storm light | 848 |
| 9 | high angle shot of a divided crowd, some standing, some seated, blue hour | 959 |
| 10 | aerial view of a crowd parting to let a rider through, firelight | 42 |
| 11 | low angle shot of a mass of pilgrims moving along a road, lamplight | 101 |
| 12 | extreme wide shot of mourners gathered outside a doorway, harsh noon sun | 202 |
| 13 | aerial view of a large crowd listening in absolute silence, backlit silhouette | 303 |
| 14 | aerial view of a crowd parting to let a rider through, blue hour | 404 |
| 15 | wide establishing shot of a mass of pilgrims moving along a road, backlit silhouette | 515 |
| 16 | medium shot of anxious faces in a packed courtyard, blue hour | 626 |
| 17 | medium shot of a mass of pilgrims moving along a road, firelight | 737 |
| 18 | close detail shot of people pressing forward to hear a speaker, dawn light | 848 |
| 19 | close detail shot of a large crowd listening in absolute silence, firelight | 959 |
| 20 | extreme wide shot of a crowd parting to let a rider through, storm light | 42 |
| 21 | low angle shot of a mass of pilgrims moving along a road, storm light | 101 |
| 22 | wide establishing shot of anxious faces in a packed courtyard, lamplight | 202 |
| 23 | high angle shot of a divided crowd, some standing, some seated, firelight | 303 |
| 24 | low angle shot of a crowd parting to let a rider through, blue hour | 404 |
| 25 | wide establishing shot of a crowd parting to let a rider through, overcast haze | 515 |

### `L1` - Cavalry & caravans

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | low angle shot of horses tethered in a line outside a camp, dawn light | 101 |
| 2 | extreme wide shot of long camel caravan crossing dunes in single file, firelight | 202 |
| 3 | low angle shot of camel train silhouetted against a red sky, dusk | 303 |
| 4 | low angle shot of loaded pack camels roped together, blue hour | 404 |
| 5 | high angle shot of horsemen at full gallop across open ground, harsh noon sun | 515 |
| 6 | close detail shot of loaded pack camels roped together, dusk | 626 |
| 7 | wide establishing shot of horses tethered in a line outside a camp, backlit silhouette | 737 |
| 8 | medium shot of horsemen at full gallop across open ground, firelight | 848 |
| 9 | medium shot of camel train silhouetted against a red sky, blue hour | 959 |
| 10 | close detail shot of horses tethered in a line outside a camp, overcast haze | 42 |
| 11 | extreme wide shot of loaded pack camels roped together, dust-filtered sunlight | 101 |
| 12 | high angle shot of camel train silhouetted against a red sky, backlit silhouette | 202 |
| 13 | close detail shot of camel train silhouetted against a red sky, blue hour | 303 |
| 14 | medium shot of cavalry column raising dust on a plain, blue hour | 404 |
| 15 | medium shot of riders fording a shallow stream, dawn light | 515 |
| 16 | low angle shot of horsemen at full gallop across open ground, harsh noon sun | 626 |
| 17 | wide establishing shot of a caravan halting at sunset, firelight | 737 |
| 18 | close detail shot of riders fording a shallow stream, harsh noon sun | 848 |
| 19 | aerial view of horses tethered in a line outside a camp, lamplight | 959 |
| 20 | aerial view of cavalry column raising dust on a plain, blue hour | 42 |
| 21 | low angle shot of riders fording a shallow stream, overcast haze | 101 |
| 22 | wide establishing shot of cavalry column raising dust on a plain, golden hour | 202 |
| 23 | low angle shot of cavalry column raising dust on a plain, harsh noon sun | 303 |
| 24 | wide establishing shot of riders fording a shallow stream, dawn light | 404 |
| 25 | low angle shot of long camel caravan crossing dunes in single file, dawn light | 515 |

### `L2` - Cavalry & caravans

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | low angle shot of loaded pack camels roped together, overcast haze | 101 |
| 2 | medium shot of a caravan halting at sunset, lamplight | 202 |
| 3 | low angle shot of cavalry column raising dust on a plain, dust-filtered sunlight | 303 |
| 4 | low angle shot of riders fording a shallow stream, moonlight | 404 |
| 5 | aerial view of camel train silhouetted against a red sky, storm light | 515 |
| 6 | aerial view of camel train silhouetted against a red sky, overcast haze | 626 |
| 7 | aerial view of horses tethered in a line outside a camp, harsh noon sun | 737 |
| 8 | medium shot of a caravan halting at sunset, golden hour | 848 |
| 9 | medium shot of loaded pack camels roped together, storm light | 959 |
| 10 | wide establishing shot of cavalry column raising dust on a plain, firelight | 42 |
| 11 | close detail shot of long camel caravan crossing dunes in single file, dawn light | 101 |
| 12 | high angle shot of long camel caravan crossing dunes in single file, golden hour | 202 |
| 13 | medium shot of horses tethered in a line outside a camp, firelight | 303 |
| 14 | medium shot of loaded pack camels roped together, blue hour | 404 |
| 15 | extreme wide shot of cavalry column raising dust on a plain, storm light | 515 |
| 16 | wide establishing shot of riders fording a shallow stream, harsh noon sun | 626 |
| 17 | aerial view of a caravan halting at sunset, lamplight | 737 |
| 18 | high angle shot of a caravan halting at sunset, dust-filtered sunlight | 848 |
| 19 | medium shot of a caravan halting at sunset, dust-filtered sunlight | 959 |
| 20 | medium shot of loaded pack camels roped together, golden hour | 42 |
| 21 | high angle shot of camel train silhouetted against a red sky, golden hour | 101 |
| 22 | wide establishing shot of horses tethered in a line outside a camp, blue hour | 202 |
| 23 | extreme wide shot of long camel caravan crossing dunes in single file, harsh noon sun | 303 |
| 24 | high angle shot of loaded pack camels roped together, overcast haze | 404 |
| 25 | close detail shot of a caravan halting at sunset, dusk | 515 |

### `L3` - Cavalry & caravans

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | high angle shot of long camel caravan crossing dunes in single file, backlit silhouette | 101 |
| 2 | aerial view of horses tethered in a line outside a camp, moonlight | 202 |
| 3 | extreme wide shot of horsemen at full gallop across open ground, golden hour | 303 |
| 4 | high angle shot of horsemen at full gallop across open ground, lamplight | 404 |
| 5 | low angle shot of cavalry column raising dust on a plain, dusk | 515 |
| 6 | medium shot of loaded pack camels roped together, dusk | 626 |
| 7 | extreme wide shot of a caravan halting at sunset, blue hour | 737 |
| 8 | medium shot of cavalry column raising dust on a plain, dust-filtered sunlight | 848 |
| 9 | aerial view of cavalry column raising dust on a plain, moonlight | 959 |
| 10 | extreme wide shot of camel train silhouetted against a red sky, dust-filtered sunlight | 42 |
| 11 | low angle shot of horses tethered in a line outside a camp, dust-filtered sunlight | 101 |
| 12 | low angle shot of horses tethered in a line outside a camp, golden hour | 202 |
| 13 | extreme wide shot of horses tethered in a line outside a camp, backlit silhouette | 303 |
| 14 | low angle shot of horsemen at full gallop across open ground, moonlight | 404 |
| 15 | extreme wide shot of a caravan halting at sunset, overcast haze | 515 |
| 16 | close detail shot of cavalry column raising dust on a plain, dust-filtered sunlight | 626 |
| 17 | high angle shot of horses tethered in a line outside a camp, golden hour | 737 |
| 18 | extreme wide shot of riders fording a shallow stream, storm light | 848 |
| 19 | medium shot of cavalry column raising dust on a plain, dawn light | 959 |
| 20 | close detail shot of loaded pack camels roped together, firelight | 42 |
| 21 | extreme wide shot of camel train silhouetted against a red sky, golden hour | 101 |
| 22 | high angle shot of loaded pack camels roped together, lamplight | 202 |
| 23 | extreme wide shot of horses tethered in a line outside a camp, golden hour | 303 |
| 24 | extreme wide shot of loaded pack camels roped together, lamplight | 404 |
| 25 | extreme wide shot of horsemen at full gallop across open ground, harsh noon sun | 515 |

### `M1` - Before battle

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | high angle shot of scouts watching from a rocky outcrop, dust-filtered sunlight | 101 |
| 2 | low angle shot of tense stillness before a charge, lamplight | 202 |
| 3 | close detail shot of a line of spears against the horizon, storm light | 303 |
| 4 | low angle shot of a line of spears against the horizon, dust-filtered sunlight | 404 |
| 5 | aerial view of war banners raised before an advance, lamplight | 515 |
| 6 | medium shot of a commander surveying the field from horseback, overcast haze | 626 |
| 7 | high angle shot of tense stillness before a charge, storm light | 737 |
| 8 | close detail shot of tense stillness before a charge, dust-filtered sunlight | 848 |
| 9 | high angle shot of a commander surveying the field from horseback, dust-filtered sunlight | 959 |
| 10 | wide establishing shot of two armies facing each other across a plain, firelight | 42 |
| 11 | extreme wide shot of drums and standards at the head of a column, backlit silhouette | 101 |
| 12 | low angle shot of a commander surveying the field from horseback, firelight | 202 |
| 13 | high angle shot of two armies facing each other across a plain, blue hour | 303 |
| 14 | low angle shot of a line of spears against the horizon, blue hour | 404 |
| 15 | aerial view of tense stillness before a charge, blue hour | 515 |
| 16 | low angle shot of scouts watching from a rocky outcrop, dawn light | 626 |
| 17 | high angle shot of scouts watching from a rocky outcrop, firelight | 737 |
| 18 | aerial view of soldiers forming ranks in dust, storm light | 848 |
| 19 | close detail shot of scouts watching from a rocky outcrop, backlit silhouette | 959 |
| 20 | medium shot of a commander surveying the field from horseback, lamplight | 42 |
| 21 | extreme wide shot of tense stillness before a charge, moonlight | 101 |
| 22 | close detail shot of drums and standards at the head of a column, dust-filtered sunlight | 202 |
| 23 | aerial view of tense stillness before a charge, golden hour | 303 |
| 24 | extreme wide shot of two armies facing each other across a plain, moonlight | 404 |
| 25 | medium shot of drums and standards at the head of a column, dust-filtered sunlight | 515 |

### `M2` - Before battle

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | aerial view of war banners raised before an advance, harsh noon sun | 101 |
| 2 | close detail shot of two armies facing each other across a plain, dawn light | 202 |
| 3 | aerial view of war banners raised before an advance, overcast haze | 303 |
| 4 | medium shot of a commander surveying the field from horseback, harsh noon sun | 404 |
| 5 | close detail shot of war banners raised before an advance, overcast haze | 515 |
| 6 | extreme wide shot of two armies facing each other across a plain, dawn light | 626 |
| 7 | medium shot of a line of spears against the horizon, dust-filtered sunlight | 737 |
| 8 | aerial view of a commander surveying the field from horseback, dust-filtered sunlight | 848 |
| 9 | close detail shot of scouts watching from a rocky outcrop, lamplight | 959 |
| 10 | low angle shot of a commander surveying the field from horseback, dusk | 42 |
| 11 | aerial view of two armies facing each other across a plain, dusk | 101 |
| 12 | extreme wide shot of a line of spears against the horizon, firelight | 202 |
| 13 | close detail shot of tense stillness before a charge, lamplight | 303 |
| 14 | low angle shot of a commander surveying the field from horseback, golden hour | 404 |
| 15 | extreme wide shot of war banners raised before an advance, harsh noon sun | 515 |
| 16 | high angle shot of soldiers forming ranks in dust, storm light | 626 |
| 17 | wide establishing shot of drums and standards at the head of a column, overcast haze | 737 |
| 18 | aerial view of a line of spears against the horizon, dawn light | 848 |
| 19 | high angle shot of scouts watching from a rocky outcrop, blue hour | 959 |
| 20 | low angle shot of a line of spears against the horizon, moonlight | 42 |
| 21 | wide establishing shot of tense stillness before a charge, firelight | 101 |
| 22 | close detail shot of soldiers forming ranks in dust, dust-filtered sunlight | 202 |
| 23 | low angle shot of tense stillness before a charge, dust-filtered sunlight | 303 |
| 24 | close detail shot of drums and standards at the head of a column, overcast haze | 404 |
| 25 | close detail shot of drums and standards at the head of a column, lamplight | 515 |

### `M3` - Before battle

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | wide establishing shot of a commander surveying the field from horseback, dawn light | 101 |
| 2 | low angle shot of a commander surveying the field from horseback, backlit silhouette | 202 |
| 3 | wide establishing shot of war banners raised before an advance, harsh noon sun | 303 |
| 4 | high angle shot of a commander surveying the field from horseback, dusk | 404 |
| 5 | low angle shot of two armies facing each other across a plain, overcast haze | 515 |
| 6 | close detail shot of scouts watching from a rocky outcrop, dawn light | 626 |
| 7 | low angle shot of drums and standards at the head of a column, harsh noon sun | 737 |
| 8 | medium shot of scouts watching from a rocky outcrop, dusk | 848 |
| 9 | wide establishing shot of two armies facing each other across a plain, moonlight | 959 |
| 10 | close detail shot of two armies facing each other across a plain, dust-filtered sunlight | 42 |
| 11 | high angle shot of a commander surveying the field from horseback, firelight | 101 |
| 12 | wide establishing shot of a line of spears against the horizon, dust-filtered sunlight | 202 |
| 13 | low angle shot of a line of spears against the horizon, golden hour | 303 |
| 14 | extreme wide shot of a line of spears against the horizon, dusk | 404 |
| 15 | medium shot of tense stillness before a charge, blue hour | 515 |
| 16 | aerial view of soldiers forming ranks in dust, blue hour | 626 |
| 17 | close detail shot of a line of spears against the horizon, dust-filtered sunlight | 737 |
| 18 | close detail shot of war banners raised before an advance, blue hour | 848 |
| 19 | wide establishing shot of soldiers forming ranks in dust, harsh noon sun | 959 |
| 20 | wide establishing shot of scouts watching from a rocky outcrop, golden hour | 42 |
| 21 | close detail shot of soldiers forming ranks in dust, dawn light | 101 |
| 22 | high angle shot of tense stillness before a charge, blue hour | 202 |
| 23 | close detail shot of soldiers forming ranks in dust, dusk | 303 |
| 24 | close detail shot of a line of spears against the horizon, firelight | 404 |
| 25 | medium shot of soldiers forming ranks in dust, dust-filtered sunlight | 515 |

### `N1` - Battle aftermath

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | high angle shot of abandoned shields and broken spears on churned ground, backlit silhouette | 101 |
| 2 | high angle shot of smoke drifting over an empty battlefield, moonlight | 202 |
| 3 | low angle shot of a lone figure walking among the fallen, dusk | 303 |
| 4 | wide establishing shot of survivors carrying the wounded at dusk, storm light | 404 |
| 5 | extreme wide shot of scorched earth and burnt tent frames, dusk | 515 |
| 6 | aerial view of survivors carrying the wounded at dusk, moonlight | 626 |
| 7 | medium shot of a bloodied sword lying in the dust, moonlight | 737 |
| 8 | low angle shot of torn banner half buried in sand, dusk | 848 |
| 9 | medium shot of scorched earth and burnt tent frames, storm light | 959 |
| 10 | close detail shot of torn banner half buried in sand, moonlight | 42 |
| 11 | aerial view of survivors carrying the wounded at dusk, backlit silhouette | 101 |
| 12 | aerial view of a lone figure walking among the fallen, backlit silhouette | 202 |
| 13 | medium shot of torn banner half buried in sand, dawn light | 303 |
| 14 | extreme wide shot of a bloodied sword lying in the dust, golden hour | 404 |
| 15 | extreme wide shot of a bloodied sword lying in the dust, storm light | 515 |
| 16 | extreme wide shot of smoke drifting over an empty battlefield, moonlight | 626 |
| 17 | extreme wide shot of a lone figure walking among the fallen, firelight | 737 |
| 18 | high angle shot of smoke drifting over an empty battlefield, harsh noon sun | 848 |
| 19 | close detail shot of smoke drifting over an empty battlefield, harsh noon sun | 959 |
| 20 | aerial view of survivors carrying the wounded at dusk, firelight | 42 |
| 21 | extreme wide shot of abandoned shields and broken spears on churned ground, dusk | 101 |
| 22 | low angle shot of smoke drifting over an empty battlefield, dust-filtered sunlight | 202 |
| 23 | low angle shot of vultures circling above a distant plain, storm light | 303 |
| 24 | aerial view of a bloodied sword lying in the dust, dawn light | 404 |
| 25 | close detail shot of vultures circling above a distant plain, blue hour | 515 |

### `N2` - Battle aftermath

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | low angle shot of survivors carrying the wounded at dusk, backlit silhouette | 101 |
| 2 | aerial view of vultures circling above a distant plain, golden hour | 202 |
| 3 | wide establishing shot of a lone figure walking among the fallen, dusk | 303 |
| 4 | wide establishing shot of survivors carrying the wounded at dusk, moonlight | 404 |
| 5 | close detail shot of a lone figure walking among the fallen, firelight | 515 |
| 6 | wide establishing shot of smoke drifting over an empty battlefield, dust-filtered sunlight | 626 |
| 7 | aerial view of scorched earth and burnt tent frames, storm light | 737 |
| 8 | high angle shot of smoke drifting over an empty battlefield, blue hour | 848 |
| 9 | close detail shot of smoke drifting over an empty battlefield, backlit silhouette | 959 |
| 10 | aerial view of vultures circling above a distant plain, overcast haze | 42 |
| 11 | wide establishing shot of a bloodied sword lying in the dust, moonlight | 101 |
| 12 | close detail shot of torn banner half buried in sand, overcast haze | 202 |
| 13 | medium shot of vultures circling above a distant plain, backlit silhouette | 303 |
| 14 | aerial view of a lone figure walking among the fallen, dawn light | 404 |
| 15 | close detail shot of smoke drifting over an empty battlefield, dusk | 515 |
| 16 | extreme wide shot of abandoned shields and broken spears on churned ground, golden hour | 626 |
| 17 | extreme wide shot of scorched earth and burnt tent frames, backlit silhouette | 737 |
| 18 | low angle shot of scorched earth and burnt tent frames, lamplight | 848 |
| 19 | medium shot of survivors carrying the wounded at dusk, blue hour | 959 |
| 20 | aerial view of torn banner half buried in sand, golden hour | 42 |
| 21 | medium shot of abandoned shields and broken spears on churned ground, moonlight | 101 |
| 22 | close detail shot of survivors carrying the wounded at dusk, dust-filtered sunlight | 202 |
| 23 | extreme wide shot of scorched earth and burnt tent frames, storm light | 303 |
| 24 | low angle shot of a bloodied sword lying in the dust, firelight | 404 |
| 25 | aerial view of abandoned shields and broken spears on churned ground, firelight | 515 |

### `N3` - Battle aftermath

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | close detail shot of survivors carrying the wounded at dusk, dusk | 101 |
| 2 | aerial view of a bloodied sword lying in the dust, storm light | 202 |
| 3 | low angle shot of a bloodied sword lying in the dust, storm light | 303 |
| 4 | high angle shot of scorched earth and burnt tent frames, blue hour | 404 |
| 5 | extreme wide shot of scorched earth and burnt tent frames, dust-filtered sunlight | 515 |
| 6 | medium shot of scorched earth and burnt tent frames, moonlight | 626 |
| 7 | wide establishing shot of a lone figure walking among the fallen, storm light | 737 |
| 8 | medium shot of scorched earth and burnt tent frames, dusk | 848 |
| 9 | low angle shot of smoke drifting over an empty battlefield, lamplight | 959 |
| 10 | medium shot of vultures circling above a distant plain, harsh noon sun | 42 |
| 11 | close detail shot of vultures circling above a distant plain, storm light | 101 |
| 12 | high angle shot of scorched earth and burnt tent frames, moonlight | 202 |
| 13 | medium shot of scorched earth and burnt tent frames, blue hour | 303 |
| 14 | wide establishing shot of scorched earth and burnt tent frames, dusk | 404 |
| 15 | extreme wide shot of a bloodied sword lying in the dust, dust-filtered sunlight | 515 |
| 16 | low angle shot of survivors carrying the wounded at dusk, golden hour | 626 |
| 17 | medium shot of a bloodied sword lying in the dust, storm light | 737 |
| 18 | wide establishing shot of smoke drifting over an empty battlefield, lamplight | 848 |
| 19 | medium shot of vultures circling above a distant plain, blue hour | 959 |
| 20 | low angle shot of a lone figure walking among the fallen, harsh noon sun | 42 |
| 21 | medium shot of abandoned shields and broken spears on churned ground, blue hour | 101 |
| 22 | extreme wide shot of a lone figure walking among the fallen, dawn light | 202 |
| 23 | aerial view of scorched earth and burnt tent frames, backlit silhouette | 303 |
| 24 | aerial view of survivors carrying the wounded at dusk, dawn light | 404 |
| 25 | medium shot of torn banner half buried in sand, firelight | 515 |

### `O1` - Banners & standards

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | close detail shot of hands unfurling a large cloth banner, golden hour | 101 |
| 2 | high angle shot of torn banner against a stormy sky, dust-filtered sunlight | 202 |
| 3 | medium shot of row of tribal standards planted in sand, storm light | 303 |
| 4 | aerial view of banner poles casting long shadows at dawn, blue hour | 404 |
| 5 | aerial view of hands unfurling a large cloth banner, dawn light | 515 |
| 6 | low angle shot of hands unfurling a large cloth banner, firelight | 626 |
| 7 | aerial view of banner poles casting long shadows at dawn, dust-filtered sunlight | 737 |
| 8 | high angle shot of banner poles casting long shadows at dawn, dust-filtered sunlight | 848 |
| 9 | close detail shot of torn banner against a stormy sky, dawn light | 959 |
| 10 | medium shot of a standard bearer alone on a ridge, moonlight | 42 |
| 11 | aerial view of black war banner snapping in high wind, moonlight | 101 |
| 12 | medium shot of a standard bearer alone on a ridge, golden hour | 202 |
| 13 | wide establishing shot of banner poles casting long shadows at dawn, firelight | 303 |
| 14 | high angle shot of hands unfurling a large cloth banner, backlit silhouette | 404 |
| 15 | extreme wide shot of black war banner snapping in high wind, dusk | 515 |
| 16 | medium shot of banner poles casting long shadows at dawn, firelight | 626 |
| 17 | extreme wide shot of row of tribal standards planted in sand, moonlight | 737 |
| 18 | extreme wide shot of a standard bearer alone on a ridge, dust-filtered sunlight | 848 |
| 19 | close detail shot of row of tribal standards planted in sand, lamplight | 959 |
| 20 | high angle shot of torn banner against a stormy sky, blue hour | 42 |
| 21 | wide establishing shot of row of tribal standards planted in sand, golden hour | 101 |
| 22 | close detail shot of a standard bearer alone on a ridge, blue hour | 202 |
| 23 | aerial view of a standard bearer alone on a ridge, moonlight | 303 |
| 24 | extreme wide shot of hands unfurling a large cloth banner, storm light | 404 |
| 25 | close detail shot of a standard bearer alone on a ridge, lamplight | 515 |

### `O2` - Banners & standards

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | wide establishing shot of torn banner against a stormy sky, harsh noon sun | 101 |
| 2 | medium shot of banner poles casting long shadows at dawn, overcast haze | 202 |
| 3 | high angle shot of row of tribal standards planted in sand, firelight | 303 |
| 4 | aerial view of row of tribal standards planted in sand, overcast haze | 404 |
| 5 | aerial view of black war banner snapping in high wind, harsh noon sun | 515 |
| 6 | high angle shot of black war banner snapping in high wind, lamplight | 626 |
| 7 | low angle shot of a standard bearer alone on a ridge, blue hour | 737 |
| 8 | low angle shot of a standard bearer alone on a ridge, dust-filtered sunlight | 848 |
| 9 | medium shot of row of tribal standards planted in sand, dawn light | 959 |
| 10 | wide establishing shot of hands unfurling a large cloth banner, storm light | 42 |
| 11 | high angle shot of hands unfurling a large cloth banner, harsh noon sun | 101 |
| 12 | extreme wide shot of black war banner snapping in high wind, dust-filtered sunlight | 202 |
| 13 | aerial view of a standard bearer alone on a ridge, blue hour | 303 |
| 14 | medium shot of banner poles casting long shadows at dawn, golden hour | 404 |
| 15 | high angle shot of hands unfurling a large cloth banner, lamplight | 515 |
| 16 | aerial view of hands unfurling a large cloth banner, firelight | 626 |
| 17 | extreme wide shot of a standard bearer alone on a ridge, lamplight | 737 |
| 18 | aerial view of banner poles casting long shadows at dawn, lamplight | 848 |
| 19 | aerial view of a standard bearer alone on a ridge, dust-filtered sunlight | 959 |
| 20 | close detail shot of banner poles casting long shadows at dawn, firelight | 42 |
| 21 | aerial view of torn banner against a stormy sky, storm light | 101 |
| 22 | extreme wide shot of a standard bearer alone on a ridge, overcast haze | 202 |
| 23 | wide establishing shot of hands unfurling a large cloth banner, overcast haze | 303 |
| 24 | aerial view of banner poles casting long shadows at dawn, firelight | 404 |
| 25 | extreme wide shot of row of tribal standards planted in sand, lamplight | 515 |

### `O3` - Banners & standards

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | low angle shot of row of tribal standards planted in sand, overcast haze | 101 |
| 2 | extreme wide shot of a standard bearer alone on a ridge, blue hour | 202 |
| 3 | medium shot of black war banner snapping in high wind, dusk | 303 |
| 4 | medium shot of banner poles casting long shadows at dawn, dust-filtered sunlight | 404 |
| 5 | high angle shot of hands unfurling a large cloth banner, dawn light | 515 |
| 6 | close detail shot of black war banner snapping in high wind, lamplight | 626 |
| 7 | extreme wide shot of banner poles casting long shadows at dawn, dusk | 737 |
| 8 | high angle shot of black war banner snapping in high wind, storm light | 848 |
| 9 | aerial view of a standard bearer alone on a ridge, storm light | 959 |
| 10 | high angle shot of hands unfurling a large cloth banner, dust-filtered sunlight | 42 |
| 11 | low angle shot of torn banner against a stormy sky, firelight | 101 |
| 12 | extreme wide shot of row of tribal standards planted in sand, backlit silhouette | 202 |
| 13 | extreme wide shot of row of tribal standards planted in sand, overcast haze | 303 |
| 14 | wide establishing shot of banner poles casting long shadows at dawn, blue hour | 404 |
| 15 | wide establishing shot of a standard bearer alone on a ridge, lamplight | 515 |
| 16 | medium shot of hands unfurling a large cloth banner, blue hour | 626 |
| 17 | medium shot of black war banner snapping in high wind, blue hour | 737 |
| 18 | wide establishing shot of row of tribal standards planted in sand, backlit silhouette | 848 |
| 19 | aerial view of a standard bearer alone on a ridge, firelight | 959 |
| 20 | medium shot of a standard bearer alone on a ridge, lamplight | 42 |
| 21 | wide establishing shot of hands unfurling a large cloth banner, lamplight | 101 |
| 22 | low angle shot of banner poles casting long shadows at dawn, dawn light | 202 |
| 23 | wide establishing shot of torn banner against a stormy sky, lamplight | 303 |
| 24 | wide establishing shot of a standard bearer alone on a ridge, firelight | 404 |
| 25 | aerial view of hands unfurling a large cloth banner, overcast haze | 515 |

### `P1` - Manuscripts & scribes

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | close detail shot of open illuminated manuscript on a wooden stand, dusk | 101 |
| 2 | low angle shot of scribe writing with a reed pen by lamplight, blue hour | 202 |
| 3 | aerial view of open illuminated manuscript on a wooden stand, dust-filtered sunlight | 303 |
| 4 | extreme wide shot of an ink pot, reed pens and a knife on a desk, moonlight | 404 |
| 5 | aerial view of a translator comparing two open books, backlit silhouette | 515 |
| 6 | extreme wide shot of open illuminated manuscript on a wooden stand, storm light | 626 |
| 7 | extreme wide shot of stacked parchment scrolls tied with cord, dust-filtered sunlight | 737 |
| 8 | extreme wide shot of open illuminated manuscript on a wooden stand, dusk | 848 |
| 9 | aerial view of an ink pot, reed pens and a knife on a desk, moonlight | 959 |
| 10 | medium shot of an ink pot, reed pens and a knife on a desk, moonlight | 42 |
| 11 | low angle shot of a translator comparing two open books, harsh noon sun | 101 |
| 12 | low angle shot of open illuminated manuscript on a wooden stand, dawn light | 202 |
| 13 | extreme wide shot of open illuminated manuscript on a wooden stand, dawn light | 303 |
| 14 | extreme wide shot of sealed letter being handed to a messenger, harsh noon sun | 404 |
| 15 | close detail shot of scribe writing with a reed pen by lamplight, lamplight | 515 |
| 16 | aerial view of a translator comparing two open books, moonlight | 626 |
| 17 | medium shot of open illuminated manuscript on a wooden stand, firelight | 737 |
| 18 | close detail shot of a scholar reading in a library of wooden shelves, blue hour | 848 |
| 19 | wide establishing shot of a scholar reading in a library of wooden shelves, golden hour | 959 |
| 20 | low angle shot of open illuminated manuscript on a wooden stand, blue hour | 42 |
| 21 | close detail shot of close detail of Arabic calligraphy on aged paper, blue hour | 101 |
| 22 | high angle shot of an ink pot, reed pens and a knife on a desk, dusk | 202 |
| 23 | low angle shot of an ink pot, reed pens and a knife on a desk, dawn light | 303 |
| 24 | wide establishing shot of close detail of Arabic calligraphy on aged paper, harsh noon sun | 404 |
| 25 | low angle shot of open illuminated manuscript on a wooden stand, backlit silhouette | 515 |

### `P2` - Manuscripts & scribes

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | low angle shot of sealed letter being handed to a messenger, backlit silhouette | 101 |
| 2 | low angle shot of a scholar reading in a library of wooden shelves, harsh noon sun | 202 |
| 3 | aerial view of a scholar reading in a library of wooden shelves, overcast haze | 303 |
| 4 | extreme wide shot of a translator comparing two open books, storm light | 404 |
| 5 | extreme wide shot of an ink pot, reed pens and a knife on a desk, dawn light | 515 |
| 6 | wide establishing shot of stacked parchment scrolls tied with cord, dawn light | 626 |
| 7 | low angle shot of a scholar reading in a library of wooden shelves, dawn light | 737 |
| 8 | low angle shot of an ink pot, reed pens and a knife on a desk, dusk | 848 |
| 9 | medium shot of a translator comparing two open books, backlit silhouette | 959 |
| 10 | aerial view of open illuminated manuscript on a wooden stand, overcast haze | 42 |
| 11 | close detail shot of stacked parchment scrolls tied with cord, blue hour | 101 |
| 12 | medium shot of sealed letter being handed to a messenger, harsh noon sun | 202 |
| 13 | close detail shot of close detail of Arabic calligraphy on aged paper, golden hour | 303 |
| 14 | aerial view of sealed letter being handed to a messenger, firelight | 404 |
| 15 | extreme wide shot of scribe writing with a reed pen by lamplight, overcast haze | 515 |
| 16 | wide establishing shot of open illuminated manuscript on a wooden stand, dusk | 626 |
| 17 | wide establishing shot of an ink pot, reed pens and a knife on a desk, moonlight | 737 |
| 18 | aerial view of scribe writing with a reed pen by lamplight, dusk | 848 |
| 19 | aerial view of a translator comparing two open books, harsh noon sun | 959 |
| 20 | wide establishing shot of a translator comparing two open books, overcast haze | 42 |
| 21 | aerial view of scribe writing with a reed pen by lamplight, moonlight | 101 |
| 22 | aerial view of scribe writing with a reed pen by lamplight, storm light | 202 |
| 23 | high angle shot of stacked parchment scrolls tied with cord, golden hour | 303 |
| 24 | aerial view of close detail of Arabic calligraphy on aged paper, moonlight | 404 |
| 25 | high angle shot of a translator comparing two open books, lamplight | 515 |

### `P3` - Manuscripts & scribes

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | wide establishing shot of a translator comparing two open books, firelight | 101 |
| 2 | close detail shot of open illuminated manuscript on a wooden stand, dawn light | 202 |
| 3 | wide establishing shot of an ink pot, reed pens and a knife on a desk, blue hour | 303 |
| 4 | medium shot of scribe writing with a reed pen by lamplight, dust-filtered sunlight | 404 |
| 5 | low angle shot of scribe writing with a reed pen by lamplight, backlit silhouette | 515 |
| 6 | wide establishing shot of scribe writing with a reed pen by lamplight, golden hour | 626 |
| 7 | extreme wide shot of close detail of Arabic calligraphy on aged paper, backlit silhouette | 737 |
| 8 | extreme wide shot of a translator comparing two open books, dust-filtered sunlight | 848 |
| 9 | low angle shot of scribe writing with a reed pen by lamplight, overcast haze | 959 |
| 10 | close detail shot of scribe writing with a reed pen by lamplight, overcast haze | 42 |
| 11 | wide establishing shot of open illuminated manuscript on a wooden stand, backlit silhouette | 101 |
| 12 | wide establishing shot of stacked parchment scrolls tied with cord, moonlight | 202 |
| 13 | close detail shot of close detail of Arabic calligraphy on aged paper, storm light | 303 |
| 14 | extreme wide shot of scribe writing with a reed pen by lamplight, harsh noon sun | 404 |
| 15 | high angle shot of a scholar reading in a library of wooden shelves, firelight | 515 |
| 16 | high angle shot of scribe writing with a reed pen by lamplight, blue hour | 626 |
| 17 | high angle shot of an ink pot, reed pens and a knife on a desk, lamplight | 737 |
| 18 | high angle shot of a scholar reading in a library of wooden shelves, moonlight | 848 |
| 19 | medium shot of stacked parchment scrolls tied with cord, dust-filtered sunlight | 959 |
| 20 | close detail shot of a translator comparing two open books, blue hour | 42 |
| 21 | medium shot of a scholar reading in a library of wooden shelves, dust-filtered sunlight | 101 |
| 22 | close detail shot of a scholar reading in a library of wooden shelves, firelight | 202 |
| 23 | high angle shot of open illuminated manuscript on a wooden stand, dust-filtered sunlight | 303 |
| 24 | high angle shot of sealed letter being handed to a messenger, storm light | 404 |
| 25 | high angle shot of a translator comparing two open books, backlit silhouette | 515 |

### `Q1` - Objects & still life

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | low angle shot of dates and flatbread on a woven mat, storm light | 101 |
| 2 | aerial view of a curved sword resting on folded cloth, moonlight | 202 |
| 3 | close detail shot of dates and flatbread on a woven mat, dust-filtered sunlight | 303 |
| 4 | wide establishing shot of bundle of iron keys on a ring, storm light | 404 |
| 5 | high angle shot of clay oil lamp burning on a stone ledge, harsh noon sun | 515 |
| 6 | aerial view of silver dirham coins and a brass balance scale, firelight | 626 |
| 7 | low angle shot of silver dirham coins and a brass balance scale, dusk | 737 |
| 8 | extreme wide shot of woven basket of grain beside a millstone, lamplight | 848 |
| 9 | medium shot of dates and flatbread on a woven mat, blue hour | 959 |
| 10 | wide establishing shot of folded prayer rug and a set of prayer beads, dust-filtered sunlight | 42 |
| 11 | extreme wide shot of bundle of iron keys on a ring, moonlight | 101 |
| 12 | low angle shot of a wooden chest bound with iron bands, blue hour | 202 |
| 13 | close detail shot of dates and flatbread on a woven mat, golden hour | 303 |
| 14 | high angle shot of dates and flatbread on a woven mat, blue hour | 404 |
| 15 | low angle shot of leather saddle and reins on a wooden rack, blue hour | 515 |
| 16 | high angle shot of folded prayer rug and a set of prayer beads, dusk | 626 |
| 17 | wide establishing shot of folded prayer rug and a set of prayer beads, overcast haze | 737 |
| 18 | low angle shot of woven basket of grain beside a millstone, overcast haze | 848 |
| 19 | low angle shot of woven basket of grain beside a millstone, firelight | 959 |
| 20 | high angle shot of folded prayer rug and a set of prayer beads, storm light | 42 |
| 21 | extreme wide shot of silver dirham coins and a brass balance scale, storm light | 101 |
| 22 | medium shot of dates and flatbread on a woven mat, moonlight | 202 |
| 23 | high angle shot of silver dirham coins and a brass balance scale, firelight | 303 |
| 24 | low angle shot of folded prayer rug and a set of prayer beads, blue hour | 404 |
| 25 | low angle shot of brass astrolabe on a dark table, overcast haze | 515 |

### `Q2` - Objects & still life

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | high angle shot of a wooden chest bound with iron bands, harsh noon sun | 101 |
| 2 | high angle shot of dates and flatbread on a woven mat, dusk | 202 |
| 3 | extreme wide shot of a curved sword resting on folded cloth, storm light | 303 |
| 4 | high angle shot of a curved sword resting on folded cloth, harsh noon sun | 404 |
| 5 | medium shot of brass astrolabe on a dark table, firelight | 515 |
| 6 | medium shot of a curved sword resting on folded cloth, dusk | 626 |
| 7 | close detail shot of silver dirham coins and a brass balance scale, dawn light | 737 |
| 8 | aerial view of dates and flatbread on a woven mat, dawn light | 848 |
| 9 | aerial view of clay oil lamp burning on a stone ledge, backlit silhouette | 959 |
| 10 | medium shot of woven basket of grain beside a millstone, harsh noon sun | 42 |
| 11 | aerial view of a curved sword resting on folded cloth, dawn light | 101 |
| 12 | medium shot of brass astrolabe on a dark table, golden hour | 202 |
| 13 | low angle shot of brass astrolabe on a dark table, backlit silhouette | 303 |
| 14 | extreme wide shot of brass astrolabe on a dark table, blue hour | 404 |
| 15 | low angle shot of bundle of iron keys on a ring, storm light | 515 |
| 16 | close detail shot of dates and flatbread on a woven mat, blue hour | 626 |
| 17 | high angle shot of clay oil lamp burning on a stone ledge, lamplight | 737 |
| 18 | close detail shot of woven basket of grain beside a millstone, dusk | 848 |
| 19 | aerial view of leather saddle and reins on a wooden rack, blue hour | 959 |
| 20 | extreme wide shot of bundle of iron keys on a ring, dust-filtered sunlight | 42 |
| 21 | close detail shot of folded prayer rug and a set of prayer beads, dusk | 101 |
| 22 | medium shot of brass astrolabe on a dark table, dust-filtered sunlight | 202 |
| 23 | medium shot of a wooden chest bound with iron bands, backlit silhouette | 303 |
| 24 | close detail shot of brass astrolabe on a dark table, overcast haze | 404 |
| 25 | extreme wide shot of brass astrolabe on a dark table, dust-filtered sunlight | 515 |

### `Q3` - Objects & still life

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | close detail shot of a wooden chest bound with iron bands, dawn light | 101 |
| 2 | medium shot of folded prayer rug and a set of prayer beads, overcast haze | 202 |
| 3 | high angle shot of woven basket of grain beside a millstone, moonlight | 303 |
| 4 | low angle shot of a curved sword resting on folded cloth, overcast haze | 404 |
| 5 | medium shot of leather saddle and reins on a wooden rack, blue hour | 515 |
| 6 | aerial view of woven basket of grain beside a millstone, storm light | 626 |
| 7 | medium shot of leather saddle and reins on a wooden rack, backlit silhouette | 737 |
| 8 | medium shot of a wooden chest bound with iron bands, blue hour | 848 |
| 9 | high angle shot of a wooden chest bound with iron bands, dust-filtered sunlight | 959 |
| 10 | high angle shot of silver dirham coins and a brass balance scale, harsh noon sun | 42 |
| 11 | medium shot of bundle of iron keys on a ring, storm light | 101 |
| 12 | aerial view of folded prayer rug and a set of prayer beads, golden hour | 202 |
| 13 | high angle shot of leather saddle and reins on a wooden rack, blue hour | 303 |
| 14 | wide establishing shot of woven basket of grain beside a millstone, dawn light | 404 |
| 15 | medium shot of leather saddle and reins on a wooden rack, golden hour | 515 |
| 16 | high angle shot of dates and flatbread on a woven mat, firelight | 626 |
| 17 | high angle shot of bundle of iron keys on a ring, backlit silhouette | 737 |
| 18 | aerial view of clay oil lamp burning on a stone ledge, moonlight | 848 |
| 19 | aerial view of leather saddle and reins on a wooden rack, firelight | 959 |
| 20 | close detail shot of silver dirham coins and a brass balance scale, overcast haze | 42 |
| 21 | wide establishing shot of bundle of iron keys on a ring, dusk | 101 |
| 22 | extreme wide shot of bundle of iron keys on a ring, firelight | 202 |
| 23 | medium shot of dates and flatbread on a woven mat, overcast haze | 303 |
| 24 | wide establishing shot of bundle of iron keys on a ring, golden hour | 404 |
| 25 | medium shot of bundle of iron keys on a ring, blue hour | 515 |

### `R1` - Night & firelight

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | aerial view of a fire burning low, embers glowing, overcast haze | 101 |
| 2 | wide establishing shot of moonlight over silent rooftops, dust-filtered sunlight | 202 |
| 3 | aerial view of figures moving through a dark alley with a lantern, moonlight | 303 |
| 4 | wide establishing shot of torchlit gateway at night, firelight | 404 |
| 5 | high angle shot of night watch standing beside a fire, dawn light | 515 |
| 6 | close detail shot of campfire circle with faces lit from below, storm light | 626 |
| 7 | wide establishing shot of figures moving through a dark alley with a lantern, golden hour | 737 |
| 8 | aerial view of torchlit gateway at night, harsh noon sun | 848 |
| 9 | extreme wide shot of night watch standing beside a fire, storm light | 959 |
| 10 | high angle shot of star-filled desert sky above black dunes, backlit silhouette | 42 |
| 11 | high angle shot of moonlight over silent rooftops, backlit silhouette | 101 |
| 12 | wide establishing shot of star-filled desert sky above black dunes, overcast haze | 202 |
| 13 | extreme wide shot of a single lamp in a dark stone room, golden hour | 303 |
| 14 | wide establishing shot of figures moving through a dark alley with a lantern, harsh noon sun | 404 |
| 15 | extreme wide shot of figures moving through a dark alley with a lantern, storm light | 515 |
| 16 | wide establishing shot of night watch standing beside a fire, golden hour | 626 |
| 17 | medium shot of night watch standing beside a fire, blue hour | 737 |
| 18 | close detail shot of campfire circle with faces lit from below, lamplight | 848 |
| 19 | medium shot of torchlit gateway at night, firelight | 959 |
| 20 | extreme wide shot of torchlit gateway at night, storm light | 42 |
| 21 | wide establishing shot of a single lamp in a dark stone room, lamplight | 101 |
| 22 | extreme wide shot of star-filled desert sky above black dunes, dawn light | 202 |
| 23 | extreme wide shot of torchlit gateway at night, dusk | 303 |
| 24 | high angle shot of moonlight over silent rooftops, storm light | 404 |
| 25 | extreme wide shot of a fire burning low, embers glowing, dust-filtered sunlight | 515 |

### `R2` - Night & firelight

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | aerial view of torchlit gateway at night, dawn light | 101 |
| 2 | aerial view of campfire circle with faces lit from below, golden hour | 202 |
| 3 | low angle shot of a single lamp in a dark stone room, firelight | 303 |
| 4 | aerial view of figures moving through a dark alley with a lantern, dusk | 404 |
| 5 | medium shot of night watch standing beside a fire, lamplight | 515 |
| 6 | low angle shot of campfire circle with faces lit from below, dust-filtered sunlight | 626 |
| 7 | low angle shot of a single lamp in a dark stone room, harsh noon sun | 737 |
| 8 | medium shot of torchlit gateway at night, dust-filtered sunlight | 848 |
| 9 | extreme wide shot of figures moving through a dark alley with a lantern, blue hour | 959 |
| 10 | aerial view of star-filled desert sky above black dunes, backlit silhouette | 42 |
| 11 | extreme wide shot of star-filled desert sky above black dunes, dusk | 101 |
| 12 | high angle shot of star-filled desert sky above black dunes, harsh noon sun | 202 |
| 13 | high angle shot of night watch standing beside a fire, dust-filtered sunlight | 303 |
| 14 | close detail shot of figures moving through a dark alley with a lantern, overcast haze | 404 |
| 15 | medium shot of a single lamp in a dark stone room, storm light | 515 |
| 16 | wide establishing shot of star-filled desert sky above black dunes, lamplight | 626 |
| 17 | medium shot of moonlight over silent rooftops, firelight | 737 |
| 18 | low angle shot of a single lamp in a dark stone room, blue hour | 848 |
| 19 | close detail shot of moonlight over silent rooftops, backlit silhouette | 959 |
| 20 | wide establishing shot of moonlight over silent rooftops, moonlight | 42 |
| 21 | high angle shot of figures moving through a dark alley with a lantern, harsh noon sun | 101 |
| 22 | high angle shot of figures moving through a dark alley with a lantern, storm light | 202 |
| 23 | low angle shot of a fire burning low, embers glowing, harsh noon sun | 303 |
| 24 | low angle shot of star-filled desert sky above black dunes, blue hour | 404 |
| 25 | low angle shot of torchlit gateway at night, moonlight | 515 |

### `R3` - Night & firelight

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | wide establishing shot of a fire burning low, embers glowing, firelight | 101 |
| 2 | aerial view of campfire circle with faces lit from below, dusk | 202 |
| 3 | extreme wide shot of moonlight over silent rooftops, harsh noon sun | 303 |
| 4 | medium shot of campfire circle with faces lit from below, storm light | 404 |
| 5 | wide establishing shot of star-filled desert sky above black dunes, dust-filtered sunlight | 515 |
| 6 | medium shot of moonlight over silent rooftops, backlit silhouette | 626 |
| 7 | low angle shot of a fire burning low, embers glowing, dust-filtered sunlight | 737 |
| 8 | low angle shot of campfire circle with faces lit from below, harsh noon sun | 848 |
| 9 | extreme wide shot of night watch standing beside a fire, dust-filtered sunlight | 959 |
| 10 | medium shot of torchlit gateway at night, moonlight | 42 |
| 11 | low angle shot of star-filled desert sky above black dunes, harsh noon sun | 101 |
| 12 | wide establishing shot of a fire burning low, embers glowing, golden hour | 202 |
| 13 | wide establishing shot of a fire burning low, embers glowing, dusk | 303 |
| 14 | extreme wide shot of a single lamp in a dark stone room, backlit silhouette | 404 |
| 15 | low angle shot of star-filled desert sky above black dunes, dusk | 515 |
| 16 | medium shot of a fire burning low, embers glowing, backlit silhouette | 626 |
| 17 | aerial view of torchlit gateway at night, firelight | 737 |
| 18 | low angle shot of torchlit gateway at night, lamplight | 848 |
| 19 | medium shot of night watch standing beside a fire, storm light | 959 |
| 20 | low angle shot of moonlight over silent rooftops, backlit silhouette | 42 |
| 21 | wide establishing shot of moonlight over silent rooftops, harsh noon sun | 101 |
| 22 | close detail shot of campfire circle with faces lit from below, harsh noon sun | 202 |
| 23 | close detail shot of campfire circle with faces lit from below, dawn light | 303 |
| 24 | extreme wide shot of a fire burning low, embers glowing, firelight | 404 |
| 25 | medium shot of figures moving through a dark alley with a lantern, dust-filtered sunlight | 515 |

### `S1` - Journeys, roads & passes

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | medium shot of long shadows of walkers on a dusty road, storm light | 101 |
| 2 | high angle shot of a road winding between rocky hills, storm light | 202 |
| 3 | aerial view of the gates of a distant city seen from the road, lamplight | 303 |
| 4 | high angle shot of long shadows of walkers on a dusty road, overcast haze | 404 |
| 5 | medium shot of stone marker beside a caravan route, lamplight | 515 |
| 6 | high angle shot of a lone rider on an empty desert track, harsh noon sun | 626 |
| 7 | wide establishing shot of a fork in the road under an open sky, dawn light | 737 |
| 8 | extreme wide shot of a lone rider on an empty desert track, blue hour | 848 |
| 9 | close detail shot of a road winding between rocky hills, golden hour | 959 |
| 10 | medium shot of narrow mountain pass with steep walls, dawn light | 42 |
| 11 | aerial view of a fork in the road under an open sky, dust-filtered sunlight | 101 |
| 12 | high angle shot of a road winding between rocky hills, golden hour | 202 |
| 13 | aerial view of travellers cresting a ridge at sunrise, moonlight | 303 |
| 14 | medium shot of a fork in the road under an open sky, harsh noon sun | 404 |
| 15 | low angle shot of stone marker beside a caravan route, harsh noon sun | 515 |
| 16 | close detail shot of travellers cresting a ridge at sunrise, dusk | 626 |
| 17 | high angle shot of a lone rider on an empty desert track, overcast haze | 737 |
| 18 | medium shot of travellers cresting a ridge at sunrise, dust-filtered sunlight | 848 |
| 19 | aerial view of the gates of a distant city seen from the road, overcast haze | 959 |
| 20 | low angle shot of a lone rider on an empty desert track, harsh noon sun | 42 |
| 21 | medium shot of stone marker beside a caravan route, dusk | 101 |
| 22 | extreme wide shot of narrow mountain pass with steep walls, dawn light | 202 |
| 23 | extreme wide shot of a road winding between rocky hills, overcast haze | 303 |
| 24 | high angle shot of travellers cresting a ridge at sunrise, firelight | 404 |
| 25 | high angle shot of a lone rider on an empty desert track, dawn light | 515 |

### `S2` - Journeys, roads & passes

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | aerial view of narrow mountain pass with steep walls, golden hour | 101 |
| 2 | wide establishing shot of narrow mountain pass with steep walls, storm light | 202 |
| 3 | close detail shot of the gates of a distant city seen from the road, overcast haze | 303 |
| 4 | close detail shot of stone marker beside a caravan route, moonlight | 404 |
| 5 | close detail shot of long shadows of walkers on a dusty road, lamplight | 515 |
| 6 | wide establishing shot of travellers cresting a ridge at sunrise, lamplight | 626 |
| 7 | close detail shot of stone marker beside a caravan route, dusk | 737 |
| 8 | wide establishing shot of a road winding between rocky hills, moonlight | 848 |
| 9 | high angle shot of travellers cresting a ridge at sunrise, golden hour | 959 |
| 10 | medium shot of the gates of a distant city seen from the road, dawn light | 42 |
| 11 | high angle shot of long shadows of walkers on a dusty road, dust-filtered sunlight | 101 |
| 12 | close detail shot of a road winding between rocky hills, dusk | 202 |
| 13 | low angle shot of travellers cresting a ridge at sunrise, lamplight | 303 |
| 14 | wide establishing shot of the gates of a distant city seen from the road, dawn light | 404 |
| 15 | wide establishing shot of narrow mountain pass with steep walls, harsh noon sun | 515 |
| 16 | aerial view of a fork in the road under an open sky, firelight | 626 |
| 17 | close detail shot of narrow mountain pass with steep walls, storm light | 737 |
| 18 | medium shot of the gates of a distant city seen from the road, blue hour | 848 |
| 19 | low angle shot of a road winding between rocky hills, harsh noon sun | 959 |
| 20 | low angle shot of a road winding between rocky hills, backlit silhouette | 42 |
| 21 | close detail shot of travellers cresting a ridge at sunrise, firelight | 101 |
| 22 | aerial view of a road winding between rocky hills, dawn light | 202 |
| 23 | high angle shot of a road winding between rocky hills, backlit silhouette | 303 |
| 24 | low angle shot of the gates of a distant city seen from the road, dusk | 404 |
| 25 | extreme wide shot of the gates of a distant city seen from the road, harsh noon sun | 515 |

### `S3` - Journeys, roads & passes

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | extreme wide shot of travellers cresting a ridge at sunrise, harsh noon sun | 101 |
| 2 | medium shot of the gates of a distant city seen from the road, moonlight | 202 |
| 3 | high angle shot of long shadows of walkers on a dusty road, firelight | 303 |
| 4 | close detail shot of the gates of a distant city seen from the road, moonlight | 404 |
| 5 | aerial view of long shadows of walkers on a dusty road, backlit silhouette | 515 |
| 6 | extreme wide shot of narrow mountain pass with steep walls, firelight | 626 |
| 7 | low angle shot of a lone rider on an empty desert track, lamplight | 737 |
| 8 | close detail shot of travellers cresting a ridge at sunrise, lamplight | 848 |
| 9 | aerial view of long shadows of walkers on a dusty road, blue hour | 959 |
| 10 | close detail shot of stone marker beside a caravan route, firelight | 42 |
| 11 | wide establishing shot of narrow mountain pass with steep walls, blue hour | 101 |
| 12 | medium shot of long shadows of walkers on a dusty road, firelight | 202 |
| 13 | low angle shot of narrow mountain pass with steep walls, moonlight | 303 |
| 14 | medium shot of stone marker beside a caravan route, storm light | 404 |
| 15 | medium shot of long shadows of walkers on a dusty road, blue hour | 515 |
| 16 | medium shot of narrow mountain pass with steep walls, storm light | 626 |
| 17 | wide establishing shot of a road winding between rocky hills, blue hour | 737 |
| 18 | low angle shot of narrow mountain pass with steep walls, blue hour | 848 |
| 19 | extreme wide shot of a road winding between rocky hills, golden hour | 959 |
| 20 | low angle shot of a lone rider on an empty desert track, blue hour | 42 |
| 21 | medium shot of narrow mountain pass with steep walls, blue hour | 101 |
| 22 | medium shot of long shadows of walkers on a dusty road, dawn light | 202 |
| 23 | aerial view of narrow mountain pass with steep walls, firelight | 303 |
| 24 | high angle shot of stone marker beside a caravan route, moonlight | 404 |
| 25 | wide establishing shot of the gates of a distant city seen from the road, golden hour | 515 |

### `T1` - Architecture details

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | close detail shot of stone column base worn smooth, storm light | 101 |
| 2 | extreme wide shot of stone column base worn smooth, harsh noon sun | 202 |
| 3 | high angle shot of weathered mud-brick surface texture, backlit silhouette | 303 |
| 4 | extreme wide shot of stepped rooftop parapet against the sky, dawn light | 404 |
| 5 | extreme wide shot of shadow of an arcade across a courtyard floor, moonlight | 515 |
| 6 | high angle shot of carved wooden door with iron studs, golden hour | 626 |
| 7 | wide establishing shot of shadow of an arcade across a courtyard floor, storm light | 737 |
| 8 | low angle shot of geometric lattice window screen, storm light | 848 |
| 9 | medium shot of carved wooden door with iron studs, harsh noon sun | 959 |
| 10 | wide establishing shot of geometric lattice window screen, firelight | 42 |
| 11 | low angle shot of carved wooden door with iron studs, golden hour | 101 |
| 12 | wide establishing shot of horseshoe arch in a plastered wall, harsh noon sun | 202 |
| 13 | medium shot of stepped rooftop parapet against the sky, lamplight | 303 |
| 14 | high angle shot of stepped rooftop parapet against the sky, firelight | 404 |
| 15 | medium shot of carved wooden door with iron studs, lamplight | 515 |
| 16 | aerial view of stone column base worn smooth, golden hour | 626 |
| 17 | wide establishing shot of stone column base worn smooth, lamplight | 737 |
| 18 | aerial view of horseshoe arch in a plastered wall, moonlight | 848 |
| 19 | wide establishing shot of geometric lattice window screen, dawn light | 959 |
| 20 | wide establishing shot of inscription carved into a stone lintel, overcast haze | 42 |
| 21 | high angle shot of horseshoe arch in a plastered wall, storm light | 101 |
| 22 | low angle shot of weathered mud-brick surface texture, firelight | 202 |
| 23 | aerial view of inscription carved into a stone lintel, lamplight | 303 |
| 24 | wide establishing shot of stone column base worn smooth, blue hour | 404 |
| 25 | extreme wide shot of horseshoe arch in a plastered wall, dawn light | 515 |

### `T2` - Architecture details

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | close detail shot of carved wooden door with iron studs, harsh noon sun | 101 |
| 2 | aerial view of stepped rooftop parapet against the sky, moonlight | 202 |
| 3 | wide establishing shot of shadow of an arcade across a courtyard floor, golden hour | 303 |
| 4 | close detail shot of horseshoe arch in a plastered wall, storm light | 404 |
| 5 | medium shot of stone column base worn smooth, backlit silhouette | 515 |
| 6 | wide establishing shot of shadow of an arcade across a courtyard floor, lamplight | 626 |
| 7 | close detail shot of shadow of an arcade across a courtyard floor, firelight | 737 |
| 8 | high angle shot of stepped rooftop parapet against the sky, backlit silhouette | 848 |
| 9 | medium shot of stone column base worn smooth, golden hour | 959 |
| 10 | aerial view of inscription carved into a stone lintel, firelight | 42 |
| 11 | low angle shot of carved wooden door with iron studs, backlit silhouette | 101 |
| 12 | extreme wide shot of carved wooden door with iron studs, blue hour | 202 |
| 13 | aerial view of horseshoe arch in a plastered wall, backlit silhouette | 303 |
| 14 | wide establishing shot of weathered mud-brick surface texture, overcast haze | 404 |
| 15 | low angle shot of inscription carved into a stone lintel, moonlight | 515 |
| 16 | extreme wide shot of carved wooden door with iron studs, lamplight | 626 |
| 17 | low angle shot of geometric lattice window screen, dust-filtered sunlight | 737 |
| 18 | high angle shot of carved wooden door with iron studs, overcast haze | 848 |
| 19 | low angle shot of inscription carved into a stone lintel, backlit silhouette | 959 |
| 20 | close detail shot of shadow of an arcade across a courtyard floor, blue hour | 42 |
| 21 | high angle shot of stepped rooftop parapet against the sky, dust-filtered sunlight | 101 |
| 22 | medium shot of carved wooden door with iron studs, moonlight | 202 |
| 23 | close detail shot of stone column base worn smooth, backlit silhouette | 303 |
| 24 | high angle shot of stepped rooftop parapet against the sky, harsh noon sun | 404 |
| 25 | low angle shot of stepped rooftop parapet against the sky, dust-filtered sunlight | 515 |

### `T3` - Architecture details

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | close detail shot of horseshoe arch in a plastered wall, golden hour | 101 |
| 2 | aerial view of horseshoe arch in a plastered wall, blue hour | 202 |
| 3 | aerial view of shadow of an arcade across a courtyard floor, blue hour | 303 |
| 4 | medium shot of shadow of an arcade across a courtyard floor, golden hour | 404 |
| 5 | high angle shot of horseshoe arch in a plastered wall, firelight | 515 |
| 6 | medium shot of geometric lattice window screen, firelight | 626 |
| 7 | wide establishing shot of carved wooden door with iron studs, blue hour | 737 |
| 8 | aerial view of inscription carved into a stone lintel, dusk | 848 |
| 9 | extreme wide shot of horseshoe arch in a plastered wall, dusk | 959 |
| 10 | high angle shot of geometric lattice window screen, dust-filtered sunlight | 42 |
| 11 | aerial view of inscription carved into a stone lintel, blue hour | 101 |
| 12 | aerial view of stone column base worn smooth, overcast haze | 202 |
| 13 | high angle shot of horseshoe arch in a plastered wall, dawn light | 303 |
| 14 | wide establishing shot of inscription carved into a stone lintel, moonlight | 404 |
| 15 | low angle shot of inscription carved into a stone lintel, blue hour | 515 |
| 16 | extreme wide shot of inscription carved into a stone lintel, overcast haze | 626 |
| 17 | low angle shot of carved wooden door with iron studs, dusk | 737 |
| 18 | medium shot of stone column base worn smooth, dawn light | 848 |
| 19 | low angle shot of stepped rooftop parapet against the sky, overcast haze | 959 |
| 20 | high angle shot of geometric lattice window screen, dawn light | 42 |
| 21 | aerial view of stepped rooftop parapet against the sky, backlit silhouette | 101 |
| 22 | wide establishing shot of horseshoe arch in a plastered wall, dawn light | 202 |
| 23 | low angle shot of shadow of an arcade across a courtyard floor, dusk | 303 |
| 24 | close detail shot of carved wooden door with iron studs, golden hour | 404 |
| 25 | extreme wide shot of inscription carved into a stone lintel, firelight | 515 |

### `U1` - Maps & cartography

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | close detail shot of regional map showing rivers and settlements, firelight | 101 |
| 2 | low angle shot of hand-drawn map with routes marked in ink, moonlight | 202 |
| 3 | extreme wide shot of a finger tracing a route across a map, storm light | 303 |
| 4 | wide establishing shot of aged parchment map of the Arabian Peninsula, lamplight | 404 |
| 5 | extreme wide shot of hand-drawn map with routes marked in ink, storm light | 515 |
| 6 | extreme wide shot of regional map showing rivers and settlements, harsh noon sun | 626 |
| 7 | wide establishing shot of old map with a compass rose and worn edges, harsh noon sun | 737 |
| 8 | aerial view of old map with a compass rose and worn edges, blue hour | 848 |
| 9 | close detail shot of regional map showing rivers and settlements, dawn light | 959 |
| 10 | low angle shot of map weighted at the corners on a wooden table, dawn light | 42 |
| 11 | low angle shot of regional map showing rivers and settlements, dust-filtered sunlight | 101 |
| 12 | low angle shot of regional map showing rivers and settlements, overcast haze | 202 |
| 13 | medium shot of regional map showing rivers and settlements, lamplight | 303 |
| 14 | close detail shot of a finger tracing a route across a map, moonlight | 404 |
| 15 | medium shot of map weighted at the corners on a wooden table, dusk | 515 |
| 16 | extreme wide shot of aged parchment map of the Arabian Peninsula, firelight | 626 |
| 17 | low angle shot of regional map showing rivers and settlements, dusk | 737 |
| 18 | close detail shot of a finger tracing a route across a map, dawn light | 848 |
| 19 | wide establishing shot of aged parchment map of the Arabian Peninsula, dusk | 959 |
| 20 | wide establishing shot of hand-drawn map with routes marked in ink, storm light | 42 |
| 21 | wide establishing shot of aged parchment map of the Arabian Peninsula, moonlight | 101 |
| 22 | medium shot of regional map showing rivers and settlements, dawn light | 202 |
| 23 | wide establishing shot of hand-drawn map with routes marked in ink, overcast haze | 303 |
| 24 | wide establishing shot of aged parchment map of the Arabian Peninsula, dust-filtered sunlight | 404 |
| 25 | high angle shot of a finger tracing a route across a map, harsh noon sun | 515 |

### `U2` - Maps & cartography

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | extreme wide shot of aged parchment map of the Arabian Peninsula, moonlight | 101 |
| 2 | close detail shot of map weighted at the corners on a wooden table, overcast haze | 202 |
| 3 | high angle shot of old map with a compass rose and worn edges, dusk | 303 |
| 4 | wide establishing shot of regional map showing rivers and settlements, backlit silhouette | 404 |
| 5 | medium shot of a finger tracing a route across a map, dusk | 515 |
| 6 | extreme wide shot of map weighted at the corners on a wooden table, overcast haze | 626 |
| 7 | high angle shot of map weighted at the corners on a wooden table, blue hour | 737 |
| 8 | wide establishing shot of map weighted at the corners on a wooden table, backlit silhouette | 848 |
| 9 | medium shot of a finger tracing a route across a map, overcast haze | 959 |
| 10 | close detail shot of regional map showing rivers and settlements, lamplight | 42 |
| 11 | low angle shot of regional map showing rivers and settlements, dawn light | 101 |
| 12 | aerial view of hand-drawn map with routes marked in ink, storm light | 202 |
| 13 | close detail shot of aged parchment map of the Arabian Peninsula, golden hour | 303 |
| 14 | extreme wide shot of aged parchment map of the Arabian Peninsula, dusk | 404 |
| 15 | aerial view of hand-drawn map with routes marked in ink, blue hour | 515 |
| 16 | close detail shot of map weighted at the corners on a wooden table, blue hour | 626 |
| 17 | high angle shot of map weighted at the corners on a wooden table, firelight | 737 |
| 18 | extreme wide shot of aged parchment map of the Arabian Peninsula, storm light | 848 |
| 19 | aerial view of hand-drawn map with routes marked in ink, dust-filtered sunlight | 959 |
| 20 | wide establishing shot of regional map showing rivers and settlements, dawn light | 42 |
| 21 | low angle shot of old map with a compass rose and worn edges, overcast haze | 101 |
| 22 | medium shot of a finger tracing a route across a map, golden hour | 202 |
| 23 | aerial view of aged parchment map of the Arabian Peninsula, golden hour | 303 |
| 24 | wide establishing shot of old map with a compass rose and worn edges, dusk | 404 |
| 25 | high angle shot of aged parchment map of the Arabian Peninsula, moonlight | 515 |

### `U3` - Maps & cartography

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | extreme wide shot of hand-drawn map with routes marked in ink, dust-filtered sunlight | 101 |
| 2 | close detail shot of a finger tracing a route across a map, dusk | 202 |
| 3 | close detail shot of hand-drawn map with routes marked in ink, backlit silhouette | 303 |
| 4 | low angle shot of old map with a compass rose and worn edges, storm light | 404 |
| 5 | high angle shot of aged parchment map of the Arabian Peninsula, firelight | 515 |
| 6 | medium shot of aged parchment map of the Arabian Peninsula, firelight | 626 |
| 7 | aerial view of hand-drawn map with routes marked in ink, golden hour | 737 |
| 8 | close detail shot of old map with a compass rose and worn edges, harsh noon sun | 848 |
| 9 | medium shot of old map with a compass rose and worn edges, dust-filtered sunlight | 959 |
| 10 | high angle shot of map weighted at the corners on a wooden table, harsh noon sun | 42 |
| 11 | aerial view of aged parchment map of the Arabian Peninsula, backlit silhouette | 101 |
| 12 | extreme wide shot of hand-drawn map with routes marked in ink, harsh noon sun | 202 |
| 13 | extreme wide shot of a finger tracing a route across a map, blue hour | 303 |
| 14 | extreme wide shot of regional map showing rivers and settlements, storm light | 404 |
| 15 | close detail shot of aged parchment map of the Arabian Peninsula, harsh noon sun | 515 |
| 16 | close detail shot of old map with a compass rose and worn edges, moonlight | 626 |
| 17 | medium shot of regional map showing rivers and settlements, storm light | 737 |
| 18 | high angle shot of old map with a compass rose and worn edges, harsh noon sun | 848 |
| 19 | extreme wide shot of hand-drawn map with routes marked in ink, lamplight | 959 |
| 20 | extreme wide shot of old map with a compass rose and worn edges, harsh noon sun | 42 |
| 21 | wide establishing shot of hand-drawn map with routes marked in ink, dust-filtered sunlight | 101 |
| 22 | low angle shot of a finger tracing a route across a map, moonlight | 202 |
| 23 | aerial view of a finger tracing a route across a map, golden hour | 303 |
| 24 | low angle shot of map weighted at the corners on a wooden table, moonlight | 404 |
| 25 | extreme wide shot of old map with a compass rose and worn edges, dusk | 515 |

### `V1` - Metaphor & emotional beats

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | wide establishing shot of a candle guttering in a dark room, backlit silhouette | 101 |
| 2 | medium shot of a chain lying broken on the ground, storm light | 202 |
| 3 | extreme wide shot of a bird lifting from a bare branch, lamplight | 303 |
| 4 | close detail shot of a door standing half open in a bare wall, dust-filtered sunlight | 404 |
| 5 | extreme wide shot of a massive ancient tree with deep exposed roots, harsh noon sun | 515 |
| 6 | low angle shot of a bird lifting from a bare branch, blue hour | 626 |
| 7 | close detail shot of a door standing half open in a bare wall, harsh noon sun | 737 |
| 8 | extreme wide shot of a stone dropped into still water, rings spreading, overcast haze | 848 |
| 9 | extreme wide shot of a candle guttering in a dark room, harsh noon sun | 959 |
| 10 | close detail shot of a single set of footprints crossing empty sand, backlit silhouette | 42 |
| 11 | high angle shot of a massive ancient tree with deep exposed roots, dusk | 101 |
| 12 | wide establishing shot of a cracked clay vessel on stone, blue hour | 202 |
| 13 | high angle shot of a cracked clay vessel on stone, dust-filtered sunlight | 303 |
| 14 | low angle shot of two paths diverging on an open plain, backlit silhouette | 404 |
| 15 | close detail shot of a candle guttering in a dark room, lamplight | 515 |
| 16 | wide establishing shot of a bird lifting from a bare branch, firelight | 626 |
| 17 | wide establishing shot of a bird lifting from a bare branch, harsh noon sun | 737 |
| 18 | close detail shot of scales balanced with light on one side, blue hour | 848 |
| 19 | wide establishing shot of two paths diverging on an open plain, moonlight | 959 |
| 20 | aerial view of a single set of footprints crossing empty sand, dawn light | 42 |
| 21 | low angle shot of a stone dropped into still water, rings spreading, storm light | 101 |
| 22 | wide establishing shot of a candle guttering in a dark room, firelight | 202 |
| 23 | low angle shot of a chain lying broken on the ground, golden hour | 303 |
| 24 | aerial view of two paths diverging on an open plain, backlit silhouette | 404 |
| 25 | extreme wide shot of two paths diverging on an open plain, dawn light | 515 |

### `V2` - Metaphor & emotional beats

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | low angle shot of a massive ancient tree with deep exposed roots, dawn light | 101 |
| 2 | medium shot of a chain lying broken on the ground, dusk | 202 |
| 3 | close detail shot of a bird lifting from a bare branch, dusk | 303 |
| 4 | medium shot of a single set of footprints crossing empty sand, dust-filtered sunlight | 404 |
| 5 | close detail shot of a cracked clay vessel on stone, overcast haze | 515 |
| 6 | low angle shot of scales balanced with light on one side, harsh noon sun | 626 |
| 7 | high angle shot of a massive ancient tree with deep exposed roots, dust-filtered sunlight | 737 |
| 8 | close detail shot of two paths diverging on an open plain, blue hour | 848 |
| 9 | wide establishing shot of a candle guttering in a dark room, dawn light | 959 |
| 10 | wide establishing shot of two paths diverging on an open plain, storm light | 42 |
| 11 | wide establishing shot of a door standing half open in a bare wall, firelight | 101 |
| 12 | aerial view of two paths diverging on an open plain, moonlight | 202 |
| 13 | close detail shot of a chain lying broken on the ground, blue hour | 303 |
| 14 | high angle shot of scales balanced with light on one side, overcast haze | 404 |
| 15 | low angle shot of a single set of footprints crossing empty sand, overcast haze | 515 |
| 16 | close detail shot of a single set of footprints crossing empty sand, harsh noon sun | 626 |
| 17 | aerial view of a bird lifting from a bare branch, blue hour | 737 |
| 18 | wide establishing shot of a bird lifting from a bare branch, golden hour | 848 |
| 19 | aerial view of a candle guttering in a dark room, lamplight | 959 |
| 20 | extreme wide shot of a cracked clay vessel on stone, dawn light | 42 |
| 21 | high angle shot of a door standing half open in a bare wall, backlit silhouette | 101 |
| 22 | aerial view of a bird lifting from a bare branch, dust-filtered sunlight | 202 |
| 23 | aerial view of a stone dropped into still water, rings spreading, firelight | 303 |
| 24 | high angle shot of a stone dropped into still water, rings spreading, blue hour | 404 |
| 25 | low angle shot of two paths diverging on an open plain, blue hour | 515 |

### `V3` - Metaphor & emotional beats

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | wide establishing shot of two paths diverging on an open plain, blue hour | 101 |
| 2 | high angle shot of two paths diverging on an open plain, golden hour | 202 |
| 3 | medium shot of a single set of footprints crossing empty sand, firelight | 303 |
| 4 | medium shot of a cracked clay vessel on stone, backlit silhouette | 404 |
| 5 | medium shot of a massive ancient tree with deep exposed roots, overcast haze | 515 |
| 6 | aerial view of a bird lifting from a bare branch, dusk | 626 |
| 7 | aerial view of a stone dropped into still water, rings spreading, dusk | 737 |
| 8 | high angle shot of a candle guttering in a dark room, lamplight | 848 |
| 9 | medium shot of a chain lying broken on the ground, blue hour | 959 |
| 10 | close detail shot of a bird lifting from a bare branch, dust-filtered sunlight | 42 |
| 11 | medium shot of a candle guttering in a dark room, overcast haze | 101 |
| 12 | close detail shot of two paths diverging on an open plain, dusk | 202 |
| 13 | aerial view of two paths diverging on an open plain, golden hour | 303 |
| 14 | low angle shot of a door standing half open in a bare wall, lamplight | 404 |
| 15 | extreme wide shot of a single set of footprints crossing empty sand, dust-filtered sunlight | 515 |
| 16 | low angle shot of a single set of footprints crossing empty sand, harsh noon sun | 626 |
| 17 | aerial view of a bird lifting from a bare branch, backlit silhouette | 737 |
| 18 | low angle shot of a massive ancient tree with deep exposed roots, backlit silhouette | 848 |
| 19 | medium shot of scales balanced with light on one side, lamplight | 959 |
| 20 | high angle shot of two paths diverging on an open plain, storm light | 42 |
| 21 | medium shot of a stone dropped into still water, rings spreading, golden hour | 101 |
| 22 | aerial view of a bird lifting from a bare branch, overcast haze | 202 |
| 23 | wide establishing shot of a candle guttering in a dark room, lamplight | 303 |
| 24 | aerial view of a bird lifting from a bare branch, lamplight | 404 |
| 25 | medium shot of a chain lying broken on the ground, backlit silhouette | 515 |

### `W1` - Weather & sky

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | high angle shot of heavy rain falling on dry cracked earth, dusk | 101 |
| 2 | extreme wide shot of towering dust storm wall advancing, overcast haze | 202 |
| 3 | medium shot of dramatic clouds breaking over a desert horizon, storm light | 303 |
| 4 | low angle shot of heavy rain falling on dry cracked earth, storm light | 404 |
| 5 | medium shot of dramatic clouds breaking over a desert horizon, overcast haze | 515 |
| 6 | aerial view of towering dust storm wall advancing, moonlight | 626 |
| 7 | low angle shot of red sunset burning across a wide sky, dawn light | 737 |
| 8 | medium shot of cold grey dawn over a stony plain, overcast haze | 848 |
| 9 | aerial view of cold grey dawn over a stony plain, firelight | 959 |
| 10 | wide establishing shot of cold grey dawn over a stony plain, moonlight | 42 |
| 11 | high angle shot of red sunset burning across a wide sky, harsh noon sun | 101 |
| 12 | close detail shot of heat shimmer distorting a distant ridge, dust-filtered sunlight | 202 |
| 13 | wide establishing shot of red sunset burning across a wide sky, backlit silhouette | 303 |
| 14 | extreme wide shot of dramatic clouds breaking over a desert horizon, lamplight | 404 |
| 15 | wide establishing shot of heavy rain falling on dry cracked earth, overcast haze | 515 |
| 16 | close detail shot of cold grey dawn over a stony plain, blue hour | 626 |
| 17 | medium shot of heavy rain falling on dry cracked earth, backlit silhouette | 737 |
| 18 | extreme wide shot of towering dust storm wall advancing, golden hour | 848 |
| 19 | high angle shot of red sunset burning across a wide sky, dust-filtered sunlight | 959 |
| 20 | wide establishing shot of red sunset burning across a wide sky, lamplight | 42 |
| 21 | close detail shot of dramatic clouds breaking over a desert horizon, overcast haze | 101 |
| 22 | aerial view of towering dust storm wall advancing, dust-filtered sunlight | 202 |
| 23 | extreme wide shot of red sunset burning across a wide sky, dusk | 303 |
| 24 | high angle shot of heat shimmer distorting a distant ridge, harsh noon sun | 404 |
| 25 | aerial view of heavy rain falling on dry cracked earth, lamplight | 515 |

### `W2` - Weather & sky

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | extreme wide shot of heat shimmer distorting a distant ridge, harsh noon sun | 101 |
| 2 | extreme wide shot of heat shimmer distorting a distant ridge, golden hour | 202 |
| 3 | medium shot of towering dust storm wall advancing, lamplight | 303 |
| 4 | medium shot of heavy rain falling on dry cracked earth, harsh noon sun | 404 |
| 5 | medium shot of cold grey dawn over a stony plain, lamplight | 515 |
| 6 | extreme wide shot of red sunset burning across a wide sky, storm light | 626 |
| 7 | high angle shot of red sunset burning across a wide sky, blue hour | 737 |
| 8 | low angle shot of heat shimmer distorting a distant ridge, dust-filtered sunlight | 848 |
| 9 | extreme wide shot of red sunset burning across a wide sky, harsh noon sun | 959 |
| 10 | aerial view of red sunset burning across a wide sky, dust-filtered sunlight | 42 |
| 11 | high angle shot of dramatic clouds breaking over a desert horizon, overcast haze | 101 |
| 12 | extreme wide shot of cold grey dawn over a stony plain, overcast haze | 202 |
| 13 | aerial view of cold grey dawn over a stony plain, blue hour | 303 |
| 14 | low angle shot of dramatic clouds breaking over a desert horizon, dawn light | 404 |
| 15 | aerial view of heavy rain falling on dry cracked earth, blue hour | 515 |
| 16 | low angle shot of heavy rain falling on dry cracked earth, backlit silhouette | 626 |
| 17 | close detail shot of red sunset burning across a wide sky, dust-filtered sunlight | 737 |
| 18 | high angle shot of cold grey dawn over a stony plain, overcast haze | 848 |
| 19 | high angle shot of cold grey dawn over a stony plain, storm light | 959 |
| 20 | aerial view of red sunset burning across a wide sky, lamplight | 42 |
| 21 | extreme wide shot of towering dust storm wall advancing, blue hour | 101 |
| 22 | close detail shot of towering dust storm wall advancing, dusk | 202 |
| 23 | aerial view of cold grey dawn over a stony plain, dusk | 303 |
| 24 | extreme wide shot of dramatic clouds breaking over a desert horizon, backlit silhouette | 404 |
| 25 | low angle shot of cold grey dawn over a stony plain, backlit silhouette | 515 |

### `W3` - Weather & sky

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | extreme wide shot of cold grey dawn over a stony plain, dusk | 101 |
| 2 | medium shot of cold grey dawn over a stony plain, dusk | 202 |
| 3 | low angle shot of dramatic clouds breaking over a desert horizon, dusk | 303 |
| 4 | close detail shot of cold grey dawn over a stony plain, overcast haze | 404 |
| 5 | close detail shot of cold grey dawn over a stony plain, storm light | 515 |
| 6 | wide establishing shot of dramatic clouds breaking over a desert horizon, golden hour | 626 |
| 7 | medium shot of dramatic clouds breaking over a desert horizon, dusk | 737 |
| 8 | low angle shot of dramatic clouds breaking over a desert horizon, storm light | 848 |
| 9 | low angle shot of towering dust storm wall advancing, backlit silhouette | 959 |
| 10 | extreme wide shot of cold grey dawn over a stony plain, lamplight | 42 |
| 11 | low angle shot of red sunset burning across a wide sky, moonlight | 101 |
| 12 | wide establishing shot of heat shimmer distorting a distant ridge, lamplight | 202 |
| 13 | medium shot of cold grey dawn over a stony plain, moonlight | 303 |
| 14 | extreme wide shot of cold grey dawn over a stony plain, moonlight | 404 |
| 15 | medium shot of heat shimmer distorting a distant ridge, dusk | 515 |
| 16 | wide establishing shot of red sunset burning across a wide sky, firelight | 626 |
| 17 | wide establishing shot of towering dust storm wall advancing, dusk | 737 |
| 18 | close detail shot of heat shimmer distorting a distant ridge, storm light | 848 |
| 19 | wide establishing shot of towering dust storm wall advancing, firelight | 959 |
| 20 | close detail shot of cold grey dawn over a stony plain, dusk | 42 |
| 21 | high angle shot of heavy rain falling on dry cracked earth, lamplight | 101 |
| 22 | medium shot of towering dust storm wall advancing, moonlight | 202 |
| 23 | wide establishing shot of red sunset burning across a wide sky, dusk | 303 |
| 24 | aerial view of dramatic clouds breaking over a desert horizon, harsh noon sun | 404 |
| 25 | wide establishing shot of heat shimmer distorting a distant ridge, harsh noon sun | 515 |

### `X1` - Domestic & daily life

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | wide establishing shot of children playing in a dusty courtyard, moonlight | 101 |
| 2 | extreme wide shot of washing hung to dry between mud walls, moonlight | 202 |
| 3 | close detail shot of woman grinding grain with a hand mill, lamplight | 303 |
| 4 | wide establishing shot of an old woman sorting dates into baskets, harsh noon sun | 404 |
| 5 | extreme wide shot of children playing in a dusty courtyard, blue hour | 515 |
| 6 | extreme wide shot of family eating together on a floor mat, lamplight | 626 |
| 7 | extreme wide shot of woman grinding grain with a hand mill, dusk | 737 |
| 8 | extreme wide shot of woman grinding grain with a hand mill, harsh noon sun | 848 |
| 9 | high angle shot of children playing in a dusty courtyard, lamplight | 959 |
| 10 | close detail shot of washing hung to dry between mud walls, dusk | 42 |
| 11 | low angle shot of an old woman sorting dates into baskets, dusk | 101 |
| 12 | close detail shot of a mother comforting a small child, overcast haze | 202 |
| 13 | aerial view of family eating together on a floor mat, dawn light | 303 |
| 14 | aerial view of children playing in a dusty courtyard, firelight | 404 |
| 15 | extreme wide shot of bread baking in a clay oven, backlit silhouette | 515 |
| 16 | wide establishing shot of woman grinding grain with a hand mill, dawn light | 626 |
| 17 | low angle shot of bread baking in a clay oven, dusk | 737 |
| 18 | extreme wide shot of woman grinding grain with a hand mill, blue hour | 848 |
| 19 | wide establishing shot of wool being spun by hand, harsh noon sun | 959 |
| 20 | wide establishing shot of wool being spun by hand, backlit silhouette | 42 |
| 21 | wide establishing shot of a mother comforting a small child, harsh noon sun | 101 |
| 22 | aerial view of a mother comforting a small child, backlit silhouette | 202 |
| 23 | high angle shot of family eating together on a floor mat, dusk | 303 |
| 24 | medium shot of an old woman sorting dates into baskets, overcast haze | 404 |
| 25 | medium shot of children playing in a dusty courtyard, lamplight | 515 |

### `X2` - Domestic & daily life

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | aerial view of children playing in a dusty courtyard, harsh noon sun | 101 |
| 2 | low angle shot of family eating together on a floor mat, firelight | 202 |
| 3 | low angle shot of washing hung to dry between mud walls, overcast haze | 303 |
| 4 | aerial view of children playing in a dusty courtyard, dusk | 404 |
| 5 | aerial view of children playing in a dusty courtyard, storm light | 515 |
| 6 | close detail shot of wool being spun by hand, dusk | 626 |
| 7 | high angle shot of wool being spun by hand, dusk | 737 |
| 8 | extreme wide shot of an old woman sorting dates into baskets, harsh noon sun | 848 |
| 9 | aerial view of children playing in a dusty courtyard, dawn light | 959 |
| 10 | extreme wide shot of woman grinding grain with a hand mill, backlit silhouette | 42 |
| 11 | aerial view of family eating together on a floor mat, dust-filtered sunlight | 101 |
| 12 | close detail shot of an old woman sorting dates into baskets, overcast haze | 202 |
| 13 | medium shot of wool being spun by hand, moonlight | 303 |
| 14 | medium shot of children playing in a dusty courtyard, storm light | 404 |
| 15 | medium shot of family eating together on a floor mat, dusk | 515 |
| 16 | close detail shot of an old woman sorting dates into baskets, lamplight | 626 |
| 17 | high angle shot of family eating together on a floor mat, firelight | 737 |
| 18 | extreme wide shot of family eating together on a floor mat, dawn light | 848 |
| 19 | low angle shot of family eating together on a floor mat, backlit silhouette | 959 |
| 20 | low angle shot of woman grinding grain with a hand mill, blue hour | 42 |
| 21 | low angle shot of woman grinding grain with a hand mill, golden hour | 101 |
| 22 | wide establishing shot of children playing in a dusty courtyard, dawn light | 202 |
| 23 | medium shot of family eating together on a floor mat, moonlight | 303 |
| 24 | low angle shot of washing hung to dry between mud walls, storm light | 404 |
| 25 | low angle shot of washing hung to dry between mud walls, backlit silhouette | 515 |

### `X3` - Domestic & daily life

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | medium shot of washing hung to dry between mud walls, moonlight | 101 |
| 2 | close detail shot of woman grinding grain with a hand mill, dusk | 202 |
| 3 | wide establishing shot of woman grinding grain with a hand mill, blue hour | 303 |
| 4 | close detail shot of washing hung to dry between mud walls, dust-filtered sunlight | 404 |
| 5 | aerial view of bread baking in a clay oven, backlit silhouette | 515 |
| 6 | low angle shot of wool being spun by hand, lamplight | 626 |
| 7 | low angle shot of a mother comforting a small child, blue hour | 737 |
| 8 | extreme wide shot of children playing in a dusty courtyard, overcast haze | 848 |
| 9 | high angle shot of wool being spun by hand, dust-filtered sunlight | 959 |
| 10 | high angle shot of washing hung to dry between mud walls, golden hour | 42 |
| 11 | extreme wide shot of woman grinding grain with a hand mill, dust-filtered sunlight | 101 |
| 12 | aerial view of washing hung to dry between mud walls, storm light | 202 |
| 13 | close detail shot of woman grinding grain with a hand mill, storm light | 303 |
| 14 | high angle shot of woman grinding grain with a hand mill, golden hour | 404 |
| 15 | low angle shot of an old woman sorting dates into baskets, moonlight | 515 |
| 16 | close detail shot of bread baking in a clay oven, golden hour | 626 |
| 17 | low angle shot of wool being spun by hand, blue hour | 737 |
| 18 | medium shot of bread baking in a clay oven, lamplight | 848 |
| 19 | medium shot of wool being spun by hand, storm light | 959 |
| 20 | wide establishing shot of an old woman sorting dates into baskets, dust-filtered sunlight | 42 |
| 21 | medium shot of bread baking in a clay oven, dawn light | 101 |
| 22 | high angle shot of children playing in a dusty courtyard, golden hour | 202 |
| 23 | aerial view of wool being spun by hand, blue hour | 303 |
| 24 | close detail shot of an old woman sorting dates into baskets, moonlight | 404 |
| 25 | high angle shot of bread baking in a clay oven, lamplight | 515 |

### `Y1` - Messengers, arrivals & departures

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | wide establishing shot of dust cloud of an approaching rider, harsh noon sun | 101 |
| 2 | medium shot of farewell at the edge of an encampment, lamplight | 202 |
| 3 | close detail shot of exhausted messenger dismounting at a gate, lamplight | 303 |
| 4 | extreme wide shot of exhausted messenger dismounting at a gate, dusk | 404 |
| 5 | close detail shot of farewell at the edge of an encampment, dust-filtered sunlight | 515 |
| 6 | low angle shot of exhausted messenger dismounting at a gate, dust-filtered sunlight | 626 |
| 7 | wide establishing shot of exhausted messenger dismounting at a gate, dawn light | 737 |
| 8 | wide establishing shot of a rider departing as onlookers watch, dust-filtered sunlight | 848 |
| 9 | low angle shot of farewell at the edge of an encampment, moonlight | 959 |
| 10 | close detail shot of a returning column entering a city gate, firelight | 42 |
| 11 | wide establishing shot of a returning column entering a city gate, overcast haze | 101 |
| 12 | close detail shot of a returning column entering a city gate, backlit silhouette | 202 |
| 13 | medium shot of dust cloud of an approaching rider, lamplight | 303 |
| 14 | aerial view of farewell at the edge of an encampment, blue hour | 404 |
| 15 | high angle shot of a letter being read aloud to a waiting group, lamplight | 515 |
| 16 | close detail shot of a rider departing as onlookers watch, blue hour | 626 |
| 17 | aerial view of farewell at the edge of an encampment, backlit silhouette | 737 |
| 18 | close detail shot of a returning column entering a city gate, dusk | 848 |
| 19 | high angle shot of dust cloud of an approaching rider, storm light | 959 |
| 20 | extreme wide shot of farewell at the edge of an encampment, dusk | 42 |
| 21 | high angle shot of a rider departing as onlookers watch, blue hour | 101 |
| 22 | close detail shot of a letter being read aloud to a waiting group, backlit silhouette | 202 |
| 23 | extreme wide shot of a rider departing as onlookers watch, harsh noon sun | 303 |
| 24 | low angle shot of farewell at the edge of an encampment, lamplight | 404 |
| 25 | medium shot of farewell at the edge of an encampment, dusk | 515 |

### `Y2` - Messengers, arrivals & departures

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | aerial view of dust cloud of an approaching rider, storm light | 101 |
| 2 | extreme wide shot of a returning column entering a city gate, firelight | 202 |
| 3 | high angle shot of exhausted messenger dismounting at a gate, firelight | 303 |
| 4 | medium shot of a letter being read aloud to a waiting group, dawn light | 404 |
| 5 | high angle shot of dust cloud of an approaching rider, firelight | 515 |
| 6 | aerial view of a letter being read aloud to a waiting group, golden hour | 626 |
| 7 | wide establishing shot of exhausted messenger dismounting at a gate, overcast haze | 737 |
| 8 | wide establishing shot of a returning column entering a city gate, lamplight | 848 |
| 9 | low angle shot of a rider departing as onlookers watch, lamplight | 959 |
| 10 | high angle shot of a rider departing as onlookers watch, lamplight | 42 |
| 11 | high angle shot of a rider departing as onlookers watch, overcast haze | 101 |
| 12 | high angle shot of a rider departing as onlookers watch, dawn light | 202 |
| 13 | high angle shot of a returning column entering a city gate, harsh noon sun | 303 |
| 14 | high angle shot of a rider departing as onlookers watch, storm light | 404 |
| 15 | wide establishing shot of exhausted messenger dismounting at a gate, dust-filtered sunlight | 515 |
| 16 | low angle shot of a returning column entering a city gate, blue hour | 626 |
| 17 | close detail shot of dust cloud of an approaching rider, backlit silhouette | 737 |
| 18 | medium shot of a returning column entering a city gate, backlit silhouette | 848 |
| 19 | wide establishing shot of a letter being read aloud to a waiting group, harsh noon sun | 959 |
| 20 | medium shot of exhausted messenger dismounting at a gate, storm light | 42 |
| 21 | high angle shot of a returning column entering a city gate, golden hour | 101 |
| 22 | aerial view of farewell at the edge of an encampment, lamplight | 202 |
| 23 | high angle shot of dust cloud of an approaching rider, dawn light | 303 |
| 24 | aerial view of exhausted messenger dismounting at a gate, dawn light | 404 |
| 25 | wide establishing shot of dust cloud of an approaching rider, storm light | 515 |

### `Y3` - Messengers, arrivals & departures

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | medium shot of a letter being read aloud to a waiting group, moonlight | 101 |
| 2 | high angle shot of a rider departing as onlookers watch, backlit silhouette | 202 |
| 3 | medium shot of a letter being read aloud to a waiting group, blue hour | 303 |
| 4 | close detail shot of farewell at the edge of an encampment, dusk | 404 |
| 5 | aerial view of farewell at the edge of an encampment, dusk | 515 |
| 6 | close detail shot of a letter being read aloud to a waiting group, dust-filtered sunlight | 626 |
| 7 | close detail shot of a letter being read aloud to a waiting group, blue hour | 737 |
| 8 | extreme wide shot of a returning column entering a city gate, golden hour | 848 |
| 9 | close detail shot of a letter being read aloud to a waiting group, overcast haze | 959 |
| 10 | wide establishing shot of a returning column entering a city gate, storm light | 42 |
| 11 | aerial view of a letter being read aloud to a waiting group, dusk | 101 |
| 12 | aerial view of a returning column entering a city gate, moonlight | 202 |
| 13 | close detail shot of a returning column entering a city gate, dawn light | 303 |
| 14 | extreme wide shot of dust cloud of an approaching rider, blue hour | 404 |
| 15 | medium shot of exhausted messenger dismounting at a gate, backlit silhouette | 515 |
| 16 | low angle shot of a rider departing as onlookers watch, harsh noon sun | 626 |
| 17 | close detail shot of dust cloud of an approaching rider, storm light | 737 |
| 18 | medium shot of a rider departing as onlookers watch, blue hour | 848 |
| 19 | aerial view of dust cloud of an approaching rider, golden hour | 959 |
| 20 | low angle shot of a returning column entering a city gate, lamplight | 42 |
| 21 | high angle shot of a letter being read aloud to a waiting group, golden hour | 101 |
| 22 | high angle shot of exhausted messenger dismounting at a gate, storm light | 202 |
| 23 | low angle shot of dust cloud of an approaching rider, backlit silhouette | 303 |
| 24 | extreme wide shot of exhausted messenger dismounting at a gate, golden hour | 404 |
| 25 | extreme wide shot of a returning column entering a city gate, blue hour | 515 |

### `Z1` - Aerial & establishing

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | high angle shot of high view of an army encamped on a plain, moonlight | 101 |
| 2 | low angle shot of high view of a caravan crossing dunes, backlit silhouette | 202 |
| 3 | close detail shot of high view of an army encamped on a plain, harsh noon sun | 303 |
| 4 | close detail shot of wide aerial of an oasis in empty desert, harsh noon sun | 404 |
| 5 | close detail shot of high view of an army encamped on a plain, moonlight | 515 |
| 6 | close detail shot of overhead view of a crowded market square, backlit silhouette | 626 |
| 7 | high angle shot of aerial of a river winding through dry land, dusk | 737 |
| 8 | wide establishing shot of high view of a caravan crossing dunes, backlit silhouette | 848 |
| 9 | high angle shot of high view of a caravan crossing dunes, golden hour | 959 |
| 10 | high angle shot of high view of an army encamped on a plain, dusk | 42 |
| 11 | low angle shot of high view of a caravan crossing dunes, storm light | 101 |
| 12 | extreme wide shot of aerial of a river winding through dry land, lamplight | 202 |
| 13 | low angle shot of overhead view of a crowded market square, dusk | 303 |
| 14 | aerial view of wide aerial of an oasis in empty desert, dusk | 404 |
| 15 | low angle shot of high view of a caravan crossing dunes, firelight | 515 |
| 16 | aerial view of aerial of a river winding through dry land, overcast haze | 626 |
| 17 | aerial view of aerial view of a walled desert town, dawn light | 737 |
| 18 | high angle shot of aerial of a river winding through dry land, harsh noon sun | 848 |
| 19 | high angle shot of wide aerial of an oasis in empty desert, dawn light | 959 |
| 20 | extreme wide shot of wide aerial of an oasis in empty desert, firelight | 42 |
| 21 | wide establishing shot of overhead view of a crowded market square, backlit silhouette | 101 |
| 22 | extreme wide shot of overhead view of a crowded market square, harsh noon sun | 202 |
| 23 | aerial view of high view of an army encamped on a plain, blue hour | 303 |
| 24 | aerial view of wide aerial of an oasis in empty desert, harsh noon sun | 404 |
| 25 | low angle shot of high view of an army encamped on a plain, dawn light | 515 |

### `Z2` - Aerial & establishing

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | close detail shot of high view of a caravan crossing dunes, dusk | 101 |
| 2 | close detail shot of aerial of a river winding through dry land, golden hour | 202 |
| 3 | extreme wide shot of overhead view of a crowded market square, backlit silhouette | 303 |
| 4 | close detail shot of overhead view of a crowded market square, blue hour | 404 |
| 5 | extreme wide shot of high view of an army encamped on a plain, firelight | 515 |
| 6 | aerial view of aerial view of a walled desert town, moonlight | 626 |
| 7 | wide establishing shot of high view of a caravan crossing dunes, lamplight | 737 |
| 8 | wide establishing shot of wide aerial of an oasis in empty desert, dust-filtered sunlight | 848 |
| 9 | aerial view of high view of an army encamped on a plain, dust-filtered sunlight | 959 |
| 10 | extreme wide shot of wide aerial of an oasis in empty desert, backlit silhouette | 42 |
| 11 | low angle shot of wide aerial of an oasis in empty desert, golden hour | 101 |
| 12 | extreme wide shot of overhead view of a crowded market square, moonlight | 202 |
| 13 | medium shot of wide aerial of an oasis in empty desert, moonlight | 303 |
| 14 | close detail shot of high view of a caravan crossing dunes, dust-filtered sunlight | 404 |
| 15 | extreme wide shot of overhead view of a crowded market square, dust-filtered sunlight | 515 |
| 16 | medium shot of high view of a caravan crossing dunes, dusk | 626 |
| 17 | wide establishing shot of wide aerial of an oasis in empty desert, storm light | 737 |
| 18 | extreme wide shot of wide aerial of an oasis in empty desert, dawn light | 848 |
| 19 | wide establishing shot of high view of an army encamped on a plain, moonlight | 959 |
| 20 | high angle shot of high view of an army encamped on a plain, overcast haze | 42 |
| 21 | low angle shot of wide aerial of an oasis in empty desert, firelight | 101 |
| 22 | medium shot of high view of an army encamped on a plain, moonlight | 202 |
| 23 | close detail shot of aerial view of a walled desert town, storm light | 303 |
| 24 | aerial view of overhead view of a crowded market square, dust-filtered sunlight | 404 |
| 25 | aerial view of wide aerial of an oasis in empty desert, blue hour | 515 |

### `Z3` - Aerial & establishing

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | low angle shot of wide aerial of an oasis in empty desert, blue hour | 101 |
| 2 | low angle shot of aerial of a river winding through dry land, harsh noon sun | 202 |
| 3 | extreme wide shot of aerial view of a walled desert town, blue hour | 303 |
| 4 | aerial view of wide aerial of an oasis in empty desert, golden hour | 404 |
| 5 | high angle shot of overhead view of a crowded market square, golden hour | 515 |
| 6 | extreme wide shot of high view of a caravan crossing dunes, moonlight | 626 |
| 7 | aerial view of aerial view of a walled desert town, lamplight | 737 |
| 8 | aerial view of aerial of a river winding through dry land, dusk | 848 |
| 9 | wide establishing shot of aerial of a river winding through dry land, dust-filtered sunlight | 959 |
| 10 | aerial view of high view of an army encamped on a plain, dusk | 42 |
| 11 | close detail shot of aerial view of a walled desert town, lamplight | 101 |
| 12 | high angle shot of aerial view of a walled desert town, backlit silhouette | 202 |
| 13 | extreme wide shot of aerial of a river winding through dry land, dust-filtered sunlight | 303 |
| 14 | low angle shot of high view of an army encamped on a plain, golden hour | 404 |
| 15 | high angle shot of wide aerial of an oasis in empty desert, harsh noon sun | 515 |
| 16 | wide establishing shot of high view of an army encamped on a plain, blue hour | 626 |
| 17 | extreme wide shot of high view of an army encamped on a plain, dust-filtered sunlight | 737 |
| 18 | extreme wide shot of aerial view of a walled desert town, backlit silhouette | 848 |
| 19 | extreme wide shot of high view of a caravan crossing dunes, dusk | 959 |
| 20 | low angle shot of aerial of a river winding through dry land, blue hour | 42 |
| 21 | aerial view of high view of an army encamped on a plain, overcast haze | 101 |
| 22 | aerial view of aerial of a river winding through dry land, blue hour | 202 |
| 23 | high angle shot of overhead view of a crowded market square, dust-filtered sunlight | 303 |
| 24 | low angle shot of high view of an army encamped on a plain, moonlight | 404 |
| 25 | medium shot of high view of a caravan crossing dunes, overcast haze | 515 |

### `CW1` - American Civil War (secondary series)

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | wide establishing shot of field hospital tent with wounded soldiers, storm light | 101 |
| 2 | aerial view of cannon battery firing across an open field, golden hour | 202 |
| 3 | extreme wide shot of Union soldier in blue wool uniform and kepi cap, dawn light | 303 |
| 4 | medium shot of Union soldier in blue wool uniform and kepi cap, overcast haze | 404 |
| 5 | low angle shot of cannon battery firing across an open field, golden hour | 515 |
| 6 | aerial view of Union soldier in blue wool uniform and kepi cap, dusk | 626 |
| 7 | close detail shot of Civil War battlefield with cannon and smoke, dust-filtered sunlight | 737 |
| 8 | high angle shot of Confederate soldier in grey uniform, dusk | 848 |
| 9 | close detail shot of soldiers around a campfire at night, harsh noon sun | 959 |
| 10 | aerial view of Civil War era map with troop positions, firelight | 42 |
| 11 | high angle shot of cannon battery firing across an open field, firelight | 101 |
| 12 | aerial view of field hospital tent with wounded soldiers, golden hour | 202 |
| 13 | close detail shot of Union regiment marching along a dirt road, storm light | 303 |
| 14 | low angle shot of Union soldier in blue wool uniform and kepi cap, golden hour | 404 |
| 15 | medium shot of Abraham Lincoln portrait in a presidential office, golden hour | 515 |
| 16 | close detail shot of torn Union and Confederate flags, dusk | 626 |
| 17 | aerial view of torn Union and Confederate flags, backlit silhouette | 737 |
| 18 | aerial view of Civil War battlefield with cannon and smoke, backlit silhouette | 848 |
| 19 | wide establishing shot of Confederate soldier in grey uniform, dusk | 959 |
| 20 | aerial view of Abraham Lincoln portrait in a presidential office, firelight | 42 |
| 21 | extreme wide shot of soldiers around a campfire at night, storm light | 101 |
| 22 | low angle shot of Confederate soldier in grey uniform, golden hour | 202 |
| 23 | low angle shot of cannon battery firing across an open field, lamplight | 303 |
| 24 | medium shot of Confederate soldier in grey uniform, dawn light | 404 |
| 25 | extreme wide shot of soldiers around a campfire at night, golden hour | 515 |

### `CW2` - American Civil War (secondary series)

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | high angle shot of cannon battery firing across an open field, golden hour | 101 |
| 2 | low angle shot of Union soldier in blue wool uniform and kepi cap, harsh noon sun | 202 |
| 3 | close detail shot of Civil War battlefield with cannon and smoke, backlit silhouette | 303 |
| 4 | wide establishing shot of Abraham Lincoln portrait in a presidential office, overcast haze | 404 |
| 5 | high angle shot of Union soldier in blue wool uniform and kepi cap, dust-filtered sunlight | 515 |
| 6 | close detail shot of cannon battery firing across an open field, harsh noon sun | 626 |
| 7 | aerial view of Civil War battlefield with cannon and smoke, blue hour | 737 |
| 8 | low angle shot of Civil War era map with troop positions, dusk | 848 |
| 9 | low angle shot of field hospital tent with wounded soldiers, blue hour | 959 |
| 10 | wide establishing shot of Union regiment marching along a dirt road, golden hour | 42 |
| 11 | extreme wide shot of Abraham Lincoln portrait in a presidential office, golden hour | 101 |
| 12 | high angle shot of Union soldier in blue wool uniform and kepi cap, backlit silhouette | 202 |
| 13 | wide establishing shot of torn Union and Confederate flags, golden hour | 303 |
| 14 | wide establishing shot of Abraham Lincoln portrait in a presidential office, storm light | 404 |
| 15 | aerial view of Confederate soldier in grey uniform, overcast haze | 515 |
| 16 | wide establishing shot of torn Union and Confederate flags, lamplight | 626 |
| 17 | extreme wide shot of cannon battery firing across an open field, blue hour | 737 |
| 18 | close detail shot of soldiers around a campfire at night, dawn light | 848 |
| 19 | high angle shot of soldiers around a campfire at night, dusk | 959 |
| 20 | medium shot of Civil War battlefield with cannon and smoke, harsh noon sun | 42 |
| 21 | medium shot of Confederate soldier in grey uniform, storm light | 101 |
| 22 | extreme wide shot of Abraham Lincoln portrait in a presidential office, dusk | 202 |
| 23 | wide establishing shot of cannon battery firing across an open field, overcast haze | 303 |
| 24 | medium shot of Union regiment marching along a dirt road, backlit silhouette | 404 |
| 25 | medium shot of cannon battery firing across an open field, firelight | 515 |

### `MO1` - Motivation & abstract (secondary series)

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | aerial view of a door opening onto bright light, harsh noon sun | 101 |
| 2 | high angle shot of an open hand releasing sand into wind, harsh noon sun | 202 |
| 3 | low angle shot of a lone runner on an empty road at dawn, blue hour | 303 |
| 4 | extreme wide shot of silhouette standing at the summit of a hill, lamplight | 404 |
| 5 | low angle shot of a door opening onto bright light, lamplight | 515 |
| 6 | medium shot of a door opening onto bright light, firelight | 626 |
| 7 | low angle shot of a seedling pushing through cracked earth, harsh noon sun | 737 |
| 8 | aerial view of hands gripping a rope, straining upward, blue hour | 848 |
| 9 | close detail shot of a lone runner on an empty road at dawn, blue hour | 959 |
| 10 | low angle shot of an open hand releasing sand into wind, overcast haze | 42 |
| 11 | close detail shot of an open hand releasing sand into wind, dust-filtered sunlight | 101 |
| 12 | extreme wide shot of a person climbing a steep rock face at sunrise, dust-filtered sunlight | 202 |
| 13 | extreme wide shot of a seedling pushing through cracked earth, blue hour | 303 |
| 14 | extreme wide shot of a lone runner on an empty road at dawn, moonlight | 404 |
| 15 | close detail shot of a person climbing a steep rock face at sunrise, blue hour | 515 |
| 16 | extreme wide shot of a lone runner on an empty road at dawn, firelight | 626 |
| 17 | low angle shot of an open hand releasing sand into wind, blue hour | 737 |
| 18 | medium shot of hands gripping a rope, straining upward, dusk | 848 |
| 19 | low angle shot of an open hand releasing sand into wind, dusk | 959 |
| 20 | wide establishing shot of a seedling pushing through cracked earth, moonlight | 42 |
| 21 | high angle shot of a door opening onto bright light, storm light | 101 |
| 22 | medium shot of silhouette standing at the summit of a hill, dusk | 202 |
| 23 | high angle shot of a door opening onto bright light, backlit silhouette | 303 |
| 24 | wide establishing shot of a door opening onto bright light, blue hour | 404 |
| 25 | high angle shot of silhouette standing at the summit of a hill, firelight | 515 |

### `MO2` - Motivation & abstract (secondary series)

Status: **TODO**

| # | Prompt (append the style suffix) | Seed |
|---|---|---|
| 1 | aerial view of a lone runner on an empty road at dawn, harsh noon sun | 101 |
| 2 | medium shot of a long staircase climbing into light, blue hour | 202 |
| 3 | wide establishing shot of an open hand releasing sand into wind, overcast haze | 303 |
| 4 | aerial view of a lone runner on an empty road at dawn, backlit silhouette | 404 |
| 5 | medium shot of silhouette standing at the summit of a hill, firelight | 515 |
| 6 | aerial view of an open hand releasing sand into wind, lamplight | 626 |
| 7 | aerial view of silhouette standing at the summit of a hill, golden hour | 737 |
| 8 | aerial view of an open hand releasing sand into wind, dust-filtered sunlight | 848 |
| 9 | medium shot of a person climbing a steep rock face at sunrise, harsh noon sun | 959 |
| 10 | wide establishing shot of a long staircase climbing into light, blue hour | 42 |
| 11 | medium shot of a seedling pushing through cracked earth, overcast haze | 101 |
| 12 | aerial view of a lone runner on an empty road at dawn, dusk | 202 |
| 13 | extreme wide shot of a lone runner on an empty road at dawn, storm light | 303 |
| 14 | wide establishing shot of a seedling pushing through cracked earth, overcast haze | 404 |
| 15 | high angle shot of a lone runner on an empty road at dawn, dawn light | 515 |
| 16 | low angle shot of a person climbing a steep rock face at sunrise, firelight | 626 |
| 17 | medium shot of a lone runner on an empty road at dawn, firelight | 737 |
| 18 | extreme wide shot of an open hand releasing sand into wind, blue hour | 848 |
| 19 | aerial view of a door opening onto bright light, overcast haze | 959 |
| 20 | wide establishing shot of silhouette standing at the summit of a hill, harsh noon sun | 42 |
| 21 | aerial view of a seedling pushing through cracked earth, overcast haze | 101 |
| 22 | close detail shot of an open hand releasing sand into wind, backlit silhouette | 202 |
| 23 | low angle shot of a long staircase climbing into light, harsh noon sun | 303 |
| 24 | high angle shot of silhouette standing at the summit of a hill, harsh noon sun | 404 |
| 25 | extreme wide shot of hands gripping a rope, straining upward, backlit silhouette | 515 |
