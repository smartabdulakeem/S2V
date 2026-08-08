# -*- coding: utf-8 -*-
"""
Single source of truth for the sound-library taxonomy.

Mirrors tools/taxonomy.py. Both studio tools and fetch_sounds.py import this,
so batch IDs like "BED1" or "SHOT2" always map to deterministic sound query sets.
"""

# Duration filters per category (Freesound filter syntax)
CATEGORIES = {
    "beds": {
        "name": "Beds (loopable ambience)",
        "code": "BED",
        "dur_filter": "[15 TO 120]",
        "min_dur": 15.0,
        "max_dur": 120.0,
        "target": 90,
    },
    "oneshots": {
        "name": "One-Shots (sound effects)",
        "code": "SHOT",
        "dur_filter": "[0.2 TO 5]",
        "min_dur": 0.2,
        "max_dur": 5.0,
        "target": 120,
    },
    "stingers": {
        "name": "Stingers (transitions & hits)",
        "code": "STING",
        "dur_filter": "[0.3 TO 4]",
        "min_dur": 0.3,
        "max_dur": 4.0,
        "target": 30,
    },
}

# Short, broad 1-2 word queries for Freesound.org API.
# If a query returns < 5 items, fallback queries will be tried automatically.
SOUND_BATCHES = [
    # BEDS — loopable ambience (15-120s)
    ("BED1", "beds", "Desert & Wilderness Ambience", [
        {"query": "desert wind", "fallbacks": ["wind light", "desert ambience"]},
        {"query": "desert wind strong", "fallbacks": ["strong wind", "wind gust"]},
        {"query": "sandstorm", "fallbacks": ["dust storm", "wind storm"]},
        {"query": "desert night", "fallbacks": ["night desert", "crickets night"]},
        {"query": "crickets", "fallbacks": ["crickets night", "night insects"]},
        {"query": "oasis water", "fallbacks": ["water trickle", "stream flowing"]},
        {"query": "palm fronds", "fallbacks": ["wind trees", "leaves rustle"]},
        {"query": "riverbank", "fallbacks": ["river flowing", "water stream"]},
    ]),
    ("BED2", "beds", "Gatherings, Crowds & Settlements", [
        {"query": "marketplace", "fallbacks": ["market crowd", "bazaar crowd"]},
        {"query": "crowd murmur", "fallbacks": ["small crowd", "people talking"]},
        {"query": "large crowd", "fallbacks": ["crowd noise", "street crowd"]},
        {"query": "angry crowd", "fallbacks": ["crowd shout", "protest crowd"]},
        {"query": "mourning crowd", "fallbacks": ["sad crowd", "crying crowd"]},
        {"query": "pilgrims", "fallbacks": ["walking crowd", "people walking"]},
        {"query": "city street", "fallbacks": ["ancient street", "town ambience"]},
    ]),
    ("BED3", "beds", "Interiors, Camps & Night", [
        {"query": "mosque", "fallbacks": ["mosque interior", "room tone"]},
        {"query": "room tone", "fallbacks": ["hall echo", "quiet room"]},
        {"query": "stone room", "fallbacks": ["cave tone", "hall tone"]},
        {"query": "camp night", "fallbacks": ["night camp", "campfire voices"]},
        {"query": "fire crackling", "fallbacks": ["campfire", "wood fire"]},
        {"query": "camp voices", "fallbacks": ["distant voices", "chatter camp"]},
    ]),
    ("BED4", "beds", "Animals, Travel & Weather", [
        {"query": "horses", "fallbacks": ["horse herd", "horses galloping"]},
        {"query": "camels", "fallbacks": ["camel herd", "camel caravan"]},
        {"query": "caravan", "fallbacks": ["camels walking", "pack animals"]},
        {"query": "battle ambience", "fallbacks": ["war noise", "distant battle"]},
        {"query": "aftermath wind", "fallbacks": ["desolate wind", "empty wind"]},
        {"query": "rain earth", "fallbacks": ["desert rain", "rain dirt"]},
        {"query": "thunder distant", "fallbacks": ["distant thunder", "rumble thunder"]},
        {"query": "plain wind", "fallbacks": ["open wind", "field wind"]},
    ]),

    # ONE-SHOTS — 0.2-5s effects
    ("SHOT1", "oneshots", "Weapons & Combat Effects", [
        {"query": "sword unsheath", "fallbacks": ["sword draw", "blade unsheath"]},
        {"query": "sword clash", "fallbacks": ["sword hit", "blade clash"]},
        {"query": "sword impact", "fallbacks": ["blade hit", "metal impact"]},
        {"query": "spear thrust", "fallbacks": ["spear hit", "weapon thrust"]},
        {"query": "shield block", "fallbacks": ["shield hit", "wood impact"]},
        {"query": "arrow release", "fallbacks": ["bow shot", "arrow bow"]},
    ]),
    ("SHOT2", "oneshots", "Animals & Movement", [
        {"query": "horse whinny", "fallbacks": ["horse snort", "horse cry"]},
        {"query": "gallop", "fallbacks": ["horse gallop", "hooves fast"]},
        {"query": "hooves", "fallbacks": ["horse hooves", "footsteps hooves"]},
        {"query": "camel groan", "fallbacks": ["camel grunt", "camel cry"]},
        {"query": "goat bleat", "fallbacks": ["sheep bleat", "goat cry"]},
        {"query": "eagle cry", "fallbacks": ["falcon cry", "hawk cry", "bird prey"]},
    ]),
    ("SHOT3", "oneshots", "Doors, Footsteps & Objects", [
        {"query": "door creak", "fallbacks": ["wood creak", "gate creak"]},
        {"query": "heavy door", "fallbacks": ["door close", "door slam"]},
        {"query": "gate open", "fallbacks": ["wooden gate", "door open"]},
        {"query": "footsteps sand", "fallbacks": ["footsteps dirt", "footsteps gravel"]},
        {"query": "footsteps stone", "fallbacks": ["footsteps rock", "footsteps floor"]},
        {"query": "running gravel", "fallbacks": ["footsteps run", "running dirt"]},
        {"query": "water pour", "fallbacks": ["pouring water", "liquid pour"]},
        {"query": "jug set down", "fallbacks": ["clay pot", "jar down"]},
        {"query": "bucket splash", "fallbacks": ["water splash", "well bucket"]},
    ]),
    ("SHOT4", "oneshots", "Scholarly, Commerce & Elements", [
        {"query": "parchment rustle", "fallbacks": ["paper rustle", "scroll rustle"]},
        {"query": "scroll unroll", "fallbacks": ["paper unroll", "parchment unroll"]},
        {"query": "quill writing", "fallbacks": ["pen writing", "pencil writing"]},
        {"query": "coin drop", "fallbacks": ["coin fall", "single coin"]},
        {"query": "coins jingling", "fallbacks": ["coins jingle", "money pouch"]},
        {"query": "scales tipping", "fallbacks": ["scale clink", "brass clink"]},
        {"query": "fire whoosh", "fallbacks": ["torch whoosh", "fire burst"]},
        {"query": "torch igniting", "fallbacks": ["fire start", "match ignite"]},
        {"query": "ember pop", "fallbacks": ["fire pop", "spark pop"]},
        {"query": "war drum", "fallbacks": ["drum hit", "bass drum"]},
        {"query": "drum roll", "fallbacks": ["snare roll", "war drums"]},
        {"query": "horn call", "fallbacks": ["war horn", "horn blow"]},
        {"query": "crowd gasp", "fallbacks": ["gasp crowd", "people gasp"]},
        {"query": "crowd murmur", "fallbacks": ["crowd swell", "people murmur"]},
        {"query": "single shout", "fallbacks": ["man shout", "war cry"]},
        {"query": "cloth rustle", "fallbacks": ["fabric rustle", "robe movement"]},
        {"query": "tent flap", "fallbacks": ["canvas flap", "wind flap"]},
        {"query": "rope creak", "fallbacks": ["rope pull", "tight rope"]},
        {"query": "thunder crack", "fallbacks": ["thunder strike", "lightning strike"]},
        {"query": "wind gust", "fallbacks": ["gust wind", "whoosh wind"]},
        {"query": "stone grinding", "fallbacks": ["millstone", "rock grinding"]},
    ]),

    # STINGERS — 0.3-4s transitions & hits
    ("STING1", "stingers", "Transitions & Dramatic Emphasis", [
        {"query": "drone hit", "fallbacks": ["low drone", "dark drone"]},
        {"query": "deep impact", "fallbacks": ["cinematic impact", "sub impact"]},
        {"query": "tension riser", "fallbacks": ["riser transition", "whoosh riser"]},
        {"query": "soft chime", "fallbacks": ["chime bell", "single chime"]},
        {"query": "reverse whoosh", "fallbacks": ["whoosh transition", "reverse swell"]},
        {"query": "sub bass", "fallbacks": ["bass drop", "sub boom"]},
        {"query": "heartbeat", "fallbacks": ["single heartbeat", "heart thud"]},
        {"query": "breath in", "fallbacks": ["gasp breath", "deep breath"]},
    ]),
]


def build_sound_batches():
    """Returns all sound batches with category metadata attached to each prompt."""
    batches = []
    for bid, cat_key, title, items in SOUND_BATCHES:
        cat_info = CATEGORIES[cat_key]
        prompts = []
        for item in items:
            prompts.append({
                "query": item["query"],
                "fallbacks": item.get("fallbacks", []),
                "category": cat_key,
                "dur_filter": cat_info["dur_filter"],
                "min_dur": cat_info["min_dur"],
                "max_dur": cat_info["max_dur"],
            })
        batches.append({
            "id": bid,
            "category": cat_key,
            "theme": title,
            "prompts": prompts,
        })
    return batches


def sound_batch_map():
    return {b["id"]: b for b in build_sound_batches()}


if __name__ == "__main__":
    bs = build_sound_batches()
    print(f"{len(bs)} batches, {sum(len(b['prompts']) for b in bs)} queries")
    for b in bs:
        print(f"  {b['id']:<6} {b['category']:<10} {len(b['prompts']):>2} queries  {b['theme']}")
