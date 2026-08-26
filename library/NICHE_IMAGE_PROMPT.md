# Library image prompt — fill in the niche, generate, drop into `library/images/`

Built to match what `compose_gap_prompt()` already produces, so images generated
this way score against the same vocabulary CLIP retrieves with. Anything wildly
off-style still lands in the library but tends to lose to closer matches.

---

## The template

Replace the three bracketed fields. Leave everything else alone.

```
wide establishing shot of [SUBJECT], [NICHE SETTING AND PERIOD],
Shot on 35mm film, cinematic documentary photography, natural directional light,
shallow depth of field, muted [PALETTE], fine film grain, historically accurate
[NICHE SETTING AND PERIOD].

Negative prompt: no text, no watermark, no signature, no logo, no caption,
no title card, no lens flare, no plastic-looking skin, no modern objects,
no visible faces of named religious figures, no anachronistic clothing,
no duplicated limbs, no distorted hands.
```

### The three fields

| Field | What to write | Example |
|---|---|---|
| `[SUBJECT]` | One concrete thing, no abstractions | `a scribe copying a manuscript by lamplight` |
| `[NICHE SETTING AND PERIOD]` | Place and era, repeated twice on purpose | `9th century Baghdad, Abbasid era` |
| `[PALETTE]` | Three colours that define the look | `earth palette of ochre sand, dust grey and deep indigo shadow` |

### Ready-made niche lines

| Niche | `[NICHE SETTING AND PERIOD]` | `[PALETTE]` |
|---|---|---|
| Early Islamic history | `7th century Arabian Peninsula, early Islamic era` | `ochre sand, dust grey, deep indigo shadow` |
| Abbasid / House of Wisdom | `9th century Baghdad, Abbasid era` | `parchment cream, lamplight amber, ink black` |
| Ottoman | `16th century Ottoman Anatolia` | `tile blue, brass, dark crimson` |
| Andalusia | `10th century Córdoba, Al-Andalus` | `whitewash, olive green, terracotta` |
| Maritime / trade | `Indian Ocean trade routes, 12th century` | `sea grey, rope brown, sail off-white` |

---

## Shot variety — generate several per subject

A library of nothing but wide shots makes every film look the same, and retrieval
returns the same handful of images. For each subject, vary the first line:

- `wide establishing shot of …`
- `low angle shot of …`
- `overhead shot of …`
- `close detail of …` (hands, texture, an object)
- `silhouette against …`
- `over-the-shoulder view of …`

Five angles of one subject is worth more than five different subjects at one
angle, because the shot rhythm needs multiple usable images per scene.

---

## Rules that matter here

**No text in the image, ever.** A single burned-in word makes the picture
unusable as b-roll and pollutes retrieval. This is why title cards live in
`library/_thumbnails/`, out of the search pool.

**Avoid depicting the Prophet ﷺ and the Rashidun caliphs.** Use backs turned,
silhouettes, hands, crowds, or the objects and places around them.

**Generate at the largest size the tool offers.** 68% of the current library is
1024×576, which upscales 2.16× at 1080p with motion and reads soft. Anything
1920×1080 or larger is a permanent improvement.

---

## Do niches need separate folders?

**No — keep one folder.** Retrieval is semantic, not path-based: CLIP compares the
image to the shot's query, so a Baghdad image simply loses to a better match when
the script is about something else. Splitting the folder would fragment the index
and lose cross-niche shots (deserts, hands, crowds, skies) that serve everything.

What *does* separate niches is a **series pack** in `config/series/`, which carries
the world anchor, style block, negative block, and a calibrated match floor per
series. That is the right place for niche-specific behaviour.
