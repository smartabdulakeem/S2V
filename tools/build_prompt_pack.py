#!/usr/bin/env python
"""
Build the standing image-prompt pack.

Why a generator and not a hand-written list
-------------------------------------------
`library/IMAGE_QUEUE.md` is 2,050 hand-written prompts for one niche. It went
stale the moment a second niche appeared, and nothing can regenerate it. This
script produces the pack from vocabulary plus the real series packs in
`config/series/`, so adding a niche re-emits every prompt instead of starting
another document.

Three rules, each of them learned the hard way
----------------------------------------------
1. **One prompt per (subject, framing) pair, never more.** An earlier version
   crossed subject x framing x lighting and produced 2,000 "unique" strings of
   which 1,218 were the same picture under different light. Five renderings of
   "a crowd seen from above" is not five library images. Lighting and detail are
   now chosen deterministically *per pair*, adding richness without adding
   near-duplicates. The count this produces is the honest ceiling of the
   vocabulary - if it is short of a target, the answer is more subjects, never
   more lighting.

2. **Subject first, camera second.** Image tools name files from the prompt and
   truncate to roughly 20 characters. When every prompt opened with "wide
   establishing shot of", a real folder of 47 generated images had 19 files whose
   names carried no subject words at all (`12_wide_establishing_sh.jpg`). Leading
   with the subject means the truncated name is still meaningful.

3. **No negative prompts.** They bloated every line for little gain. The budget
   goes into positive detail instead, which is what actually steers a model.

Naming
------
Every prompt carries a stable id and a filename slug:

    U0142_hands_open_in_prayer.jpg

The id never changes, so a prompt re-run later overwrites rather than duplicates.

Usage
-----
    python tools/build_prompt_pack.py                  # everything the vocab holds
    python tools/build_prompt_pack.py --total 1200     # cap it
    python tools/build_prompt_pack.py --style illustration
    python tools/build_prompt_pack.py --niche islamic_history
"""

import argparse
import glob
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERIES_DIR = os.path.join(ROOT, "config", "series")
OUT_MD = os.path.join(ROOT, "library", "PROMPT_PACK.md")
OUT_JSONL = os.path.join(ROOT, "library", "prompt_pack.jsonl")

FRAMINGS = [
    "extreme close-up", "close-up", "medium shot", "wide establishing shot",
    "overhead shot", "low angle shot", "over-the-shoulder shot", "distant wide shot",
]

#: Not every framing suits every subject. "Extreme close-up of a vast empty sky"
#: and "wide establishing shot of fingers turning a page" are both nonsense.
CATEGORY_FRAMINGS = {
    "hands_and_gesture": ["extreme close-up", "close-up", "medium shot",
                          "over-the-shoulder shot", "low angle shot"],
    "figures_and_silhouettes": ["medium shot", "wide establishing shot",
                                "low angle shot", "distant wide shot",
                                "over-the-shoulder shot"],
    "sky_and_weather": ["wide establishing shot", "distant wide shot",
                        "low angle shot", "overhead shot"],
    "light_and_shadow": ["extreme close-up", "close-up", "medium shot",
                         "wide establishing shot"],
    "terrain_and_horizon": ["wide establishing shot", "distant wide shot",
                            "overhead shot", "low angle shot"],
    "water": ["extreme close-up", "close-up", "medium shot",
              "wide establishing shot", "overhead shot"],
    "fire_and_smoke": ["extreme close-up", "close-up", "medium shot",
                       "low angle shot", "wide establishing shot"],
    "thresholds_and_roads": ["medium shot", "wide establishing shot",
                             "low angle shot", "distant wide shot"],
    "textures_and_surfaces": ["extreme close-up", "close-up", "overhead shot"],
    "objects_and_still_life": ["extreme close-up", "close-up", "medium shot",
                               "overhead shot"],
    "crowds_and_gathering": ["medium shot", "wide establishing shot",
                             "overhead shot", "distant wide shot"],
    "time_and_decay": ["extreme close-up", "close-up", "medium shot",
                       "wide establishing shot"],
    "work_and_craft": ["extreme close-up", "close-up", "medium shot",
                       "over-the-shoulder shot", "overhead shot"],
    "interiors_and_rooms": ["close-up", "medium shot", "wide establishing shot",
                            "low angle shot", "overhead shot"],
}

NICHE_FRAMINGS = ["close-up", "medium shot", "wide establishing shot",
                  "low angle shot", "distant wide shot", "overhead shot"]

LIGHTS = [
    "first light before sunrise", "hard noon sun and short shadows",
    "low golden hour light", "blue hour after sunset", "flat overcast light",
    "a single lamp in surrounding darkness", "strong backlight from a window",
    "moonlight and deep shadow", "firelight from below", "heavy storm light",
    "thin winter daylight", "dust-filled shafts of afternoon sun",
]

#: A subject carrying its own hour or its own light source conflicts with an
#: appended lighting clause, and the model resolves the conflict at random.
_LIGHT_FIXED = ("dusk", "dawn", "sunrise", "sunset", "night", "nightfall", "noon",
                "midday", "morning", "evening", "twilight", "moonlit", "firelight",
                "candlelit", "lamplight", "starlight", "fire", "hearth", "torch",
                "lamp", "candle", "ember", "flame", "sunlit", "backlit", "dark")

# ── Tier 1: universal subjects ───────────────────────────────────────────────
# Concrete nouns only. An abstraction ("hope", "betrayal") gives a diffusion
# model nothing to draw and gives CLIP nothing to match against.
UNIVERSAL = {
    "hands_and_gesture": [
        "a pair of open weathered hands", "one hand gripping a knotted rope",
        "hands cupping water", "an old hand resting on a young shoulder",
        "hands breaking bread", "a hand pressed flat against a stone wall",
        "fingers turning the page of a worn book", "a clenched fist held at a side",
        "two hands clasped in agreement", "a hand shielding eyes from the sun",
        "hands wrapping cloth around a wound", "a hand releasing a small bird",
        "hands holding an empty bowl", "a finger tracing a line across a map",
        "a hand reaching down to lift another", "hands counting out coins",
        "a hand resting on a closed book", "fingers testing the edge of a blade",
        "hands tying a knot in cord", "a hand pushing open a heavy door",
        "hands sorting grain from chaff", "a palm holding a single seed",
    ],
    "figures_and_silhouettes": [
        "a lone figure seen from behind on a ridge", "a silhouetted figure in a doorway",
        "a hooded figure walking away down a road", "two figures talking at a distance",
        "a seated figure with head bowed", "a figure standing at the edge of water",
        "a crowd of silhouettes against a bright sky",
        "a figure kneeling alone in an empty hall",
        "a long shadow of a person cast across ground",
        "a figure climbing a stone stair seen from below",
        "a child's outline in a window frame", "a rider silhouetted on the horizon",
        "a figure carrying a heavy load uphill", "a person pausing at a fork in a road",
        "a figure wrapped against wind and dust", "two figures parting in opposite directions",
        "a watchman standing still on a high wall", "a figure asleep against a wall",
        "a person running through open ground", "a figure framed in a narrow arch",
    ],
    "sky_and_weather": [
        "a vast empty sky with one bank of cloud", "storm clouds gathering over open land",
        "rain falling into standing water", "dust carried on a hard wind",
        "a clear night sky thick with stars", "the first crack of dawn on the horizon",
        "fog lying low across a valley", "sunlight breaking through a gap in cloud",
        "snow beginning to settle on bare ground", "heat shimmer over a flat plain",
        "a wall of rain advancing across a plain", "birds scattering before a storm",
        "a rainbow thinning over wet hills", "high cirrus streaking a pale sky",
        "lightning over a distant ridge", "a sky clearing after long rain",
    ],
    "light_and_shadow": [
        "a shaft of light falling through a high window",
        "dust motes turning in a beam of light", "a flame guttering in a draught",
        "shadows of railings striping a floor", "a candle burned down to its base",
        "light spilling under a closed door", "the last light on a wall as the sun drops",
        "a lantern carried through the dark", "a grille throwing patterned shadow",
        "one lit window in a dark building", "light catching the edge of a curtain",
        "a corridor lit only at its far end", "a doorway blazing against a dim room",
        "reflected light rippling on a ceiling",
    ],
    "terrain_and_horizon": [
        "an empty road running to the horizon", "bare hills folding into the distance",
        "a mountain pass under heavy cloud", "cracked dry ground stretching away",
        "a treeline at the edge of open ground", "a cliff edge dropping to nothing",
        "a wide river valley seen from above", "footprints crossing untouched ground",
        "a single tree standing in open country", "terraced fields rising up a slope",
        "a ridge line cut sharp against the sky", "a dry riverbed winding through rock",
        "sand dunes running to the skyline", "a plain scattered with standing stones",
        "a gorge narrowing between cliff walls", "marshland broken by channels of water",
        "a plateau ending in sudden empty air", "scrubland stretching without landmark",
    ],
    "water": [
        "still water holding a reflection", "waves breaking against dark rock",
        "a well shaft dropping into darkness", "water poured from a clay vessel",
        "a narrow stream running over stones", "rain rings spreading on a flooded field",
        "a boat drawn up on an empty shore", "mist rising off a cold lake",
        "a waterfall dropping into shadow", "a frozen surface beginning to crack",
        "an irrigation channel cut through soil", "a harbour at slack tide",
        "water sheeting off a stone lip", "a ford crossing shallow water",
    ],
    "fire_and_smoke": [
        "a low fire burning down to embers", "smoke rising in a straight column",
        "sparks lifting into the night", "a burnt-out frame still smoking",
        "a torch held high in the dark", "ash settling over ground",
        "a hearth fire in an empty room", "a brazier throwing light on a wall",
        "smoke pushed flat by wind", "a lamp wick catching light",
        "charred timbers cooling", "a forge fire at working heat",
    ],
    "thresholds_and_roads": [
        "a heavy door standing half open", "a gate closed against the light",
        "worn steps leading up out of frame", "a bridge crossing to the far side",
        "a crossroads with no one at it", "a long corridor receding into shadow",
        "an archway framing distant ground", "a window looking out on open country",
        "a narrow alley opening onto light", "a track worn into grass by long use",
        "a boundary wall with a gap in it", "a tunnel mouth in a hillside",
        "a stile crossing a field boundary", "a ladder leaning against a high wall",
        "a rope bridge over a gorge", "a doorway bricked up long ago",
    ],
    "textures_and_surfaces": [
        "cracked plaster on an old wall", "the grain of weathered timber",
        "rust spreading across worn metal", "coarse woven cloth in raking light",
        "sand ridged by wind", "worn stone smoothed by generations of hands",
        "ink dried into rough paper", "rope frayed at its end",
        "lichen spreading over a boulder", "hammered metal showing every blow",
        "dried mud curling away from itself", "leather worn pale at the fold",
        "wax cooled in uneven runs", "wheat heads packed tight in a field",
        "sacking stitched and restitched", "ice crusting a stone lip",
    ],
    "objects_and_still_life": [
        "an empty chair in an empty room", "a plain bowl and cup on a bare table",
        "a key left lying on wood", "a folded letter beside a burnt-down candle",
        "worn shoes set by a doorway", "a broken vessel on the ground",
        "a lamp a book and a pair of spectacles", "a bundle tied and ready to carry",
        "scales resting in balance", "a coin turned on its edge",
        "a walking staff propped in a corner", "a water skin hung on a peg",
        "a sealed letter waiting on a table", "a knife and whetstone side by side",
        "an unrolled map weighted at its corners", "a set of tools laid out in order",
        "a child's toy left on a floor", "a ring of keys on an iron hook",
    ],
    "crowds_and_gathering": [
        "a crowd seen from above with faces indistinct",
        "a line of people waiting seen from behind",
        "many raised hands in a packed space", "an emptying square after a gathering",
        "figures scattering across open ground", "a dense crowd pressed toward one point",
        "a circle of people around something unseen",
        "a queue stretching around a corner", "a procession moving down a narrow street",
        "a market crowd thinning at the end of day",
        "a gathering seated on the ground listening",
        "people leaning from windows to watch below",
    ],
    "time_and_decay": [
        "dust thick on an untouched surface", "a building slowly taken back by growth",
        "a road half buried by drifting sand", "an abandoned room with light coming in",
        "the same stretch of ground under different seasons",
        "an old photograph curling at its edges",
        "a wall bearing the marks of many repairs", "a shutter hanging from one hinge",
        "a garden gone wild past its wall", "paint flaking from a painted sign",
        "a cart left to rot in a field", "a stair worn into a hollow at its centre",
        "an inscription weathered past reading", "roots splitting a paved surface",
    ],
    "work_and_craft": [
        "a scribe bent over a half-copied page", "a potter's hands closing on wet clay",
        "a smith turning metal in the fire", "a weaver working a loom by daylight",
        "a mason dressing a block of stone", "a farmer breaking hard soil",
        "a fisherman mending a torn net", "a baker drawing loaves from an oven",
        "a carpenter planing a long board", "a tanner working a hide",
        "a shepherd counting a flock through a gate", "a miller at a turning stone",
        "a cook grinding spice by hand", "a builder raising a course of brick",
        "a woodcutter resting on an axe", "a dyer lifting cloth from a vat",
    ],
    "interiors_and_rooms": [
        "a low room lit by one small window", "a hall with rows of empty benches",
        "a storeroom stacked to the ceiling", "a study with books to the rafters",
        "a bare cell with a single sleeping mat", "a kitchen at the end of the day",
        "a stable with light between the boards", "a courtyard seen from inside a doorway",
        "a workshop with tools hung in rows", "a chamber emptied of everything but dust",
        "a vaulted undercroft in dim light", "a long refectory table set for many",
        "a watchroom with a view over a wall", "an attic crowded with stored things",
    ],
}

#: A concrete detail per category, rotated across that category's prompts. This
#: is where the extra description goes now that negative prompts are gone.
DETAILS = {
    "hands_and_gesture": [
        "dirt worked deep into every crease", "skin cracked across the knuckles",
        "a frayed cuff at the wrist", "an old scar across the back of the hand",
        "veins standing under thin skin", "nails broken short from work",
        "a plain band worn smooth on one finger", "callus thick across the palm",
    ],
    "figures_and_silhouettes": [
        "the face turned away and unreadable", "clothing pulled tight by wind",
        "the body weighted to one side", "shoulders set against the cold",
        "the head lowered and still", "a cloak edge lifting behind",
        "the stance loose and unguarded", "the outline broken by carried load",
    ],
    "sky_and_weather": [
        "the horizon a thin hard line", "cloud stacked in distinct layers",
        "the air thick and particulate", "birds small and scattered high up",
        "colour draining toward the edges", "weather visibly moving across frame",
        "a distant curtain of falling rain", "the light uneven across the ground",
    ],
    "light_and_shadow": [
        "the beam sharply edged", "shadow falling in hard geometry",
        "the source itself just out of frame", "brightness blowing out at the centre",
        "warm light against cold shade", "the far side of the room in near dark",
        "reflected light lifting the shadows", "a haze softening the beam",
    ],
    "terrain_and_horizon": [
        "no sign of any building", "the ground broken and uneven underfoot",
        "scrub clinging in the hollows", "a track just visible crossing it",
        "distance flattening every feature", "stone showing through thin soil",
        "the scale set by one small figure", "wind visible in the low growth",
    ],
    "water": [
        "the surface barely moving", "sediment clouding the shallows",
        "light fracturing on the ripples", "the far bank lost to haze",
        "foam gathering at the edge", "the depth unreadable and dark",
        "weed streaming with the current", "spray hanging in the air",
    ],
    "fire_and_smoke": [
        "embers pulsing under grey ash", "smoke curling then flattening",
        "heat distorting the air above", "sparks carried sideways",
        "the surroundings lit only by this", "charred edges still glowing",
        "soot blackening everything near", "the flame low and steady",
    ],
    "thresholds_and_roads": [
        "the far side bright and indistinct", "hinges rusted and sagging",
        "the threshold worn into a dip", "nothing visible beyond the opening",
        "the way ahead narrowing", "the surface rutted by long use",
        "a wall running out of frame either side", "the entrance framed in deep shadow",
    ],
    "textures_and_surfaces": [
        "every flaw held in sharp focus", "raking light picking out the relief",
        "colour muted and uneven", "layers of wear showing through",
        "the pattern irregular and hand-made", "grain running hard across frame",
        "salt and dust caught in the hollows", "the edge crumbling away",
    ],
    "objects_and_still_life": [
        "arranged as though just set down", "one object catching the light",
        "the background plain and unlit", "surfaces scuffed from long handling",
        "shadow anchoring each piece", "nothing decorative in frame",
        "dust visible on the upper surfaces", "the composition left off-centre",
    ],
    "crowds_and_gathering": [
        "individual faces not readable", "movement blurring at the edges",
        "the density uneven across frame", "clothing muted and similar",
        "attention turned in one direction", "gaps opening in the press",
        "the scale of it running past frame", "stillness in the middle of movement",
    ],
    "time_and_decay": [
        "untouched for a long time", "growth pushing through every gap",
        "colour bleached out by exposure", "the damage gradual not violent",
        "one detail still intact", "layers of dust undisturbed",
        "the structure still legible beneath", "repairs older than the damage",
    ],
    "work_and_craft": [
        "hands central and in focus", "the workspace cluttered and functional",
        "material caught mid-transformation", "tools worn to the shape of a grip",
        "the face angled down in concentration", "dust or smoke in the working air",
        "finished pieces stacked to one side", "the light coming from one side only",
    ],
    "interiors_and_rooms": [
        "the corners falling into dark", "furniture sparse and functional",
        "light entering from one side only", "the floor bare and swept",
        "the ceiling lost in shadow", "nothing on the walls",
        "objects left where they were used", "the air visibly still",
    ],
}

#: Rotated across niche prompts, which take their subject from the series pack.
NICHE_DETAILS = [
    "period-accurate in every detail", "the setting worn and lived-in",
    "materials and clothing true to the era", "the background richly detailed but unlit",
    "one figure anchoring the composition", "the scale of the setting made clear",
    "surfaces showing age and use", "the moment caught mid-action",
]

VISUAL_STYLES = {
    "realistic": ("Photorealistic, shot on 35mm film, natural directional light, "
                  "shallow depth of field, fine film grain, muted natural colour."),
    "cinematic": ("Cinematic film still, anamorphic lens, dramatic directional light, "
                  "deep contrast, muted colour grade, fine grain."),
    "illustration": ("Painted editorial illustration, visible brushwork, limited "
                     "palette, strong shapes, flat depth."),
    "cartoon": ("Clean flat vector illustration, bold outlines, simplified shapes, "
                "flat colour fills, even lighting."),
    "silhouette": ("High contrast silhouette against a bright ground, subject fully "
                   "dark, no facial detail, strong graphic shape."),
    "archival": ("Aged archival photograph, desaturated, soft focus, visible "
                 "scratches and emulsion damage, period-accurate."),
}

_STOP = {"a", "an", "the", "of", "in", "on", "at", "to", "and", "with", "into",
         "from", "for", "by", "its", "one", "two", "his", "her", "their"}


def slug_words(subject: str, count: int = 4) -> str:
    words = [w for w in re.findall(r"[a-z]+", subject.lower()) if w not in _STOP]
    return "_".join(words[:count]) or "shot"


def _light_for(subject: str, i: int):
    """None when the subject already fixes its own light."""
    if any(w in subject.lower() for w in _LIGHT_FIXED):
        return None
    return LIGHTS[i % len(LIGHTS)]


def _pairs(subjects: list, framings: list) -> list:
    """
    Every (subject, framing) pair exactly once, ordered framing-major so an
    even stride keeps changing both rather than walking one subject to death.
    """
    return [(s, f) for f in framings for s in subjects]


def _compose(subject: str, framing: str, detail: str, light, anchor: str,
             style: str) -> str:
    """Subject first, so a truncated filename still carries the subject."""
    parts = [subject, framing]
    if anchor:
        parts.append(anchor)
    if detail:
        parts.append(detail)
    if light:
        parts.append(light)
    return ", ".join(parts) + ". " + style


def build_universal(limit, style_key: str) -> list:
    style = VISUAL_STYLES[style_key]
    rows, n = [], 0
    for cat in sorted(UNIVERSAL):
        framings = CATEGORY_FRAMINGS.get(cat, FRAMINGS)
        details = DETAILS.get(cat, [""])
        pairs = _pairs(UNIVERSAL[cat], framings)
        if limit is not None:
            pairs = pairs[:max(1, limit // len(UNIVERSAL))]
        for i, (subject, framing) in enumerate(pairs):
            n += 1
            rows.append({
                "id": f"U{n:04d}",
                "tier": "universal",
                "category": cat,
                "style": style_key,
                "filename": f"U{n:04d}_{slug_words(subject)}.jpg",
                "prompt": _compose(subject, framing, details[i % len(details)],
                                   _light_for(subject, i), "", style),
            })
    return rows


def load_niches(only: str = None) -> list:
    packs = []
    for path in sorted(glob.glob(os.path.join(SERIES_DIR, "*.json"))):
        slug = os.path.splitext(os.path.basename(path))[0]
        if slug == "default" or (only and slug != only):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                packs.append(json.load(fh))
        except (OSError, json.JSONDecodeError):
            continue
    return packs


def build_niche(pack: dict, limit) -> list:
    """
    Subjects come from the pack's own seed and calibration queries - the phrases
    this series has actually been searched with, so generation aims at the gaps
    the series really has rather than at a guess.
    """
    slug = pack.get("series_slug", "series")
    anchor = pack.get("world_anchor", "")
    style = pack.get("style_block", "")

    seeds = list(pack.get("seed_queries") or [])
    seeds += list((pack.get("calibration") or {}).get("real_queries") or [])
    seeds = list(dict.fromkeys(s for s in seeds if s))
    if not seeds:
        return []

    prefix = "".join(w[0] for w in slug.split("_")[:2]).upper() or "N"
    pairs = _pairs(seeds, NICHE_FRAMINGS)
    if limit is not None:
        pairs = pairs[:limit]

    rows = []
    for n, (subject, framing) in enumerate(pairs, 1):
        rows.append({
            "id": f"{prefix}{n:04d}",
            "tier": "niche",
            "category": slug,
            "style": "series",
            "filename": f"{prefix}{n:04d}_{slug_words(subject)}.jpg",
            "prompt": _compose(subject, framing,
                               NICHE_DETAILS[(n - 1) % len(NICHE_DETAILS)],
                               _light_for(subject, n), anchor, style),
        })
    return rows


def audit(rows: list) -> dict:
    """The check the first version of this pack failed."""
    def key(r):
        head = r["prompt"].split(". ")[0].lower()
        return tuple(p.strip() for p in head.split(",")[:2])
    seen, dupes = set(), 0
    for r in rows:
        k = key(r)
        if k in seen:
            dupes += 1
        seen.add(k)
    return {"total": len(rows), "distinct_subject_framing": len(seen),
            "near_duplicates": dupes}


def write_markdown(rows: list, path: str, style_key: str, stats: dict) -> None:
    by_cat = {}
    for r in rows:
        by_cat.setdefault((r["tier"], r["category"]), []).append(r)

    lines = [
        "# Smart Studio - Standing Image Prompt Pack",
        "",
        "**Generated by `tools/build_prompt_pack.py`. Do not hand-edit - regenerate.**",
        "",
        f"- Prompts: **{stats['total']}**, every one a distinct subject and framing",
        f"- Near-duplicates: **{stats['near_duplicates']}**",
        f"- Visual style for the universal tier: **{style_key}**",
        "",
        "## How to use this",
        "",
        "1. Work top-down. Tick a batch off as you finish it.",
        "2. Save each image under the **exact filename given**. The id never changes,",
        "   so regenerating a prompt later overwrites instead of duplicating.",
        "3. Drop finished images into `library/images/` and run",
        "   `python -m pipeline.library reindex`.",
        "",
        "**Tier 1 (universal) is the priority.** Those images carry no period and no",
        "place, so they serve every niche and every future series.",
        "",
        "---",
        "",
    ]
    for (tier, cat), items in sorted(by_cat.items()):
        lines.append(f"## {tier.upper()} - {cat.replace('_', ' ')} ({len(items)})")
        lines.append("")
        lines.append("| # | Filename | Prompt | Done |")
        lines.append("|---|---|---|---|")
        for r in items:
            lines.append(f"| {r['id']} | `{r['filename']}` | "
                         f"{r['prompt'].replace('|', '/')} | [ ] |")
        lines.append("")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--total", type=int, default=None,
                    help="cap the pack; default is everything the vocabulary holds")
    ap.add_argument("--style", default="realistic", choices=sorted(VISUAL_STYLES))
    ap.add_argument("--niche", default=None, help="limit tier 2 to one series slug")
    ap.add_argument("--universal-share", type=float, default=0.45)
    args = ap.parse_args()

    uni_limit = int(args.total * args.universal_share) if args.total else None
    rows = build_universal(uni_limit, args.style)

    packs = load_niches(args.niche)
    if packs:
        per = ((args.total - len(rows)) // len(packs)) if args.total else None
        for pack in packs:
            rows.extend(build_niche(pack, per))

    stats = audit(rows)
    write_markdown(rows, OUT_MD, args.style, stats)
    with open(OUT_JSONL, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    uni = sum(1 for r in rows if r["tier"] == "universal")
    print(f"{stats['total']} prompts ({uni} universal, {stats['total'] - uni} niche)")
    print(f"  distinct subject+framing : {stats['distinct_subject_framing']}")
    print(f"  near-duplicates          : {stats['near_duplicates']}")
    print(f"  {OUT_MD}")
    print(f"  {OUT_JSONL}")


if __name__ == "__main__":
    main()
