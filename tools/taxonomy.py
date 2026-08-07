# -*- coding: utf-8 -*-
"""
Single source of truth for the image-library taxonomy.

Both the studio page and the fetchers import this, so a batch id like "I2" always
means exactly the same 25 prompts everywhere. The shuffle seed is fixed for that
reason — do not change SEED or the batch ids will silently point at different prompts.
"""

import itertools
import random

SEED = 7

# Bump when the prompt wording changes. It is part of the manifest dedupe key, so a bump
# means previously fetched images no longer satisfy the new prompt and will be re-fetched.
PROMPT_VERSION = 2

STYLE = ("cinematic documentary photography, dramatic natural lighting, historical realism, "
         "highly detailed, sharp focus, no text, no watermark, no modern objects")

# v1 had no geographic or period anchor, so FLUX defaulted to generic stock landscapes —
# East Asian huts, green European fields, wrong dress. Only 49 of the first 160 prompts
# named a place at all. The anchor is per-theme because the secondary series are elsewhere.
WORLD_DEFAULT = ("7th century Arabian Peninsula, early Islamic era, Middle Eastern, "
                 "arid desert region")
WORLD = {
    "CW": "American Civil War, 1860s United States",
    "MO": "",          # contemporary and abstract — deliberately unanchored
}


def world_for(code):
    return WORLD.get(code, WORLD_DEFAULT)

LIGHT = ["dawn light", "harsh noon sun", "golden hour", "dusk", "blue hour", "overcast haze",
         "firelight", "lamplight", "moonlight", "dust-filtered sunlight", "backlit silhouette",
         "storm light"]

SHOT = ["wide establishing shot", "extreme wide shot", "medium shot", "close detail shot",
        "low angle shot", "high angle shot", "aerial view"]

SEEDS = [42, 101, 202, 303, 404, 515, 626, 737, 848, 959]

# Themes whose subjects are people. Pollinations FLUX is weak on faces and hands at low
# step counts, so these route to Imagen 4.0 when a Google key is available.
QUALITY_THEMES = {"E", "F", "H", "I", "J", "K", "M", "X", "Y", "CW", "MO"}

THEMES = [
 ("A", "Desert terrain & landscape", [
  "endless rolling sand dunes with wind-carved ridges", "cracked dry riverbed cutting through desert plain",
  "black volcanic rock field on desert flats", "lone acacia tree on an empty plain",
  "desert plateau dropping into a deep wadi", "sandstorm approaching across open desert",
  "footprints and camel tracks crossing fresh sand", "salt flat shimmering with heat haze",
  "rocky escarpment above a dry valley", "scrub brush and thorn bushes on stony ground",
  "narrow canyon pass between sandstone cliffs", "desert horizon under an enormous empty sky"]),
 ("B", "Water, wells & oases", [
  "stone-rimmed desert well with a rope and leather bucket", "palm oasis with a still reflecting pool",
  "women drawing water from a village well", "irrigation channel running between date palms",
  "clay water jars stacked beside a well", "spring bubbling from rock at the base of a cliff",
  "camels drinking at a watering hole", "flooded wadi after rain, water running over stones",
  "goatskin waterbag hanging from a tent pole", "a boy leading a donkey to water"]),
 ("C", "City walls & settlements", [
  "mud-brick city wall with a fortified gate", "dense low rooftops of an ancient Arabian town",
  "narrow alley between high mud-brick walls", "watchtower on a city wall at the desert edge",
  "city gate crowded with travellers and pack animals", "ancient town seen from a ridge at distance",
  "courtyard house with a shaded arcade", "stone steps climbing between packed houses",
  "clay-plastered wall with a heavy wooden door", "caravanserai courtyard with tethered camels"]),
 ("D", "Mosque exteriors", [
  "simple early mosque of mud brick and palm trunks", "mosque courtyard with a single minaret",
  "worshippers gathering outside a mosque doorway", "mosque wall casting long shadows at dusk",
  "early mosque with a low flat roof of palm fronds", "small desert mosque standing alone on open ground"]),
 ("E", "Mosque interiors & prayer", [
  "rows of worshippers in prayer in a dim hall", "empty prayer hall with light falling through a high window",
  "a lone figure praying in an empty mosque", "hands raised in supplication",
  "prayer mats laid in ordered rows on a stone floor", "an imam addressing a seated congregation",
  "shafts of dusty light across a columned hall", "a man prostrating alone at night"]),
 ("F", "Markets & commerce", [
  "crowded desert marketplace with cloth awnings", "merchant weighing silver coins on a balance scale",
  "spice sacks and grain baskets in a market stall", "textile merchant unrolling dyed cloth",
  "date sellers behind piled baskets of fruit", "blacksmith working at an open forge",
  "pottery stacked outside a workshop", "money changer table with scattered silver dirhams",
  "livestock pen at the edge of a market", "a haggling crowd around a market stall"]),
 ("G", "Tents & encampments", [
  "black goat-hair tents pitched on open ground", "interior of a large tent lit by an oil lamp",
  "encampment at dusk with cooking fires burning", "tent ropes and pegs in close detail",
  "a war camp of many tents seen from a ridge", "carpets and cushions inside a chieftain tent",
  "camels couched beside a tent at dawn", "smoke rising from an encampment at first light"]),
 ("H", "Councils & assemblies", [
  "elders seated in a circle in serious discussion", "a leader addressing seated tribal chiefs",
  "men arguing across a low table of documents", "a tense negotiation between two delegations",
  "an oath being sworn with clasped hands", "messenger delivering news to a seated council",
  "a council falling silent as one man rises", "scribes recording a meeting from the side"]),
 ("I", "Elders, leaders & portraits", [
  "weathered elderly man with a white beard in plain robes", "dignified leader in simple undyed cloth",
  "lined old hands resting on a wooden staff", "a leader looking out over a city at dawn",
  "grieving elder with lowered head", "a stern chieftain in a dark cloak",
  "an ageing scholar surrounded by manuscripts", "a man weeping quietly, face partly turned away",
  "a leader standing alone in an empty courtyard", "close portrait of tired resolute eyes"]),
 ("J", "Warriors & riders", [
  "young warrior in chain mail holding a spear", "rider in a dark cloak on a rearing horse",
  "warrior sharpening a blade by firelight", "armoured horseman silhouetted on a ridge",
  "a fighter adjusting his sword belt", "two warriors clasping forearms in farewell",
  "dusty rider arriving at a city gate", "warrior shield and helmet resting on sand"]),
 ("K", "Crowds & gatherings", [
  "a large crowd listening in absolute silence", "people pressing forward to hear a speaker",
  "a divided crowd, some standing, some seated", "townspeople gathering in a square at dawn",
  "a crowd parting to let a rider through", "anxious faces in a packed courtyard",
  "mourners gathered outside a doorway", "a mass of pilgrims moving along a road"]),
 ("L", "Cavalry & caravans", [
  "long camel caravan crossing dunes in single file", "cavalry column raising dust on a plain",
  "horsemen at full gallop across open ground", "loaded pack camels roped together",
  "a caravan halting at sunset", "riders fording a shallow stream",
  "horses tethered in a line outside a camp", "camel train silhouetted against a red sky"]),
 ("M", "Before battle", [
  "two armies facing each other across a plain", "war banners raised before an advance",
  "a commander surveying the field from horseback", "soldiers forming ranks in dust",
  "drums and standards at the head of a column", "tense stillness before a charge",
  "a line of spears against the horizon", "scouts watching from a rocky outcrop"]),
 ("N", "Battle aftermath", [
  "abandoned shields and broken spears on churned ground", "smoke drifting over an empty battlefield",
  "a lone figure walking among the fallen", "scorched earth and burnt tent frames",
  "torn banner half buried in sand", "survivors carrying the wounded at dusk",
  "vultures circling above a distant plain", "a bloodied sword lying in the dust"]),
 ("O", "Banners & standards", [
  "black war banner snapping in high wind", "row of tribal standards planted in sand",
  "a standard bearer alone on a ridge", "banner poles casting long shadows at dawn",
  "hands unfurling a large cloth banner", "torn banner against a stormy sky"]),
 ("P", "Manuscripts & scribes", [
  "open illuminated manuscript on a wooden stand", "scribe writing with a reed pen by lamplight",
  "stacked parchment scrolls tied with cord", "close detail of Arabic calligraphy on aged paper",
  "an ink pot, reed pens and a knife on a desk", "a scholar reading in a library of wooden shelves",
  "sealed letter being handed to a messenger", "a translator comparing two open books"]),
 ("Q", "Objects & still life", [
  "silver dirham coins and a brass balance scale", "clay oil lamp burning on a stone ledge",
  "dates and flatbread on a woven mat", "leather saddle and reins on a wooden rack",
  "a curved sword resting on folded cloth", "brass astrolabe on a dark table",
  "bundle of iron keys on a ring", "woven basket of grain beside a millstone",
  "a wooden chest bound with iron bands", "folded prayer rug and a set of prayer beads"]),
 ("R", "Night & firelight", [
  "campfire circle with faces lit from below", "a single lamp in a dark stone room",
  "torchlit gateway at night", "star-filled desert sky above black dunes",
  "night watch standing beside a fire", "moonlight over silent rooftops",
  "figures moving through a dark alley with a lantern", "a fire burning low, embers glowing"]),
 ("S", "Journeys, roads & passes", [
  "a road winding between rocky hills", "travellers cresting a ridge at sunrise",
  "a lone rider on an empty desert track", "narrow mountain pass with steep walls",
  "stone marker beside a caravan route", "a fork in the road under an open sky",
  "long shadows of walkers on a dusty road", "the gates of a distant city seen from the road"]),
 ("T", "Architecture details", [
  "carved wooden door with iron studs", "horseshoe arch in a plastered wall",
  "geometric lattice window screen", "weathered mud-brick surface texture",
  "stone column base worn smooth", "stepped rooftop parapet against the sky",
  "shadow of an arcade across a courtyard floor", "inscription carved into a stone lintel"]),
 ("U", "Maps & cartography", [
  "aged parchment map of the Arabian Peninsula", "hand-drawn map with routes marked in ink",
  "map weighted at the corners on a wooden table", "a finger tracing a route across a map",
  "regional map showing rivers and settlements", "old map with a compass rose and worn edges"]),
 ("V", "Metaphor & emotional beats", [
  "a massive ancient tree with deep exposed roots", "a single set of footprints crossing empty sand",
  "scales balanced with light on one side", "a cracked clay vessel on stone",
  "a door standing half open in a bare wall", "a candle guttering in a dark room",
  "a bird lifting from a bare branch", "a chain lying broken on the ground",
  "two paths diverging on an open plain", "a stone dropped into still water, rings spreading"]),
 ("W", "Weather & sky", [
  "towering dust storm wall advancing", "heavy rain falling on dry cracked earth",
  "dramatic clouds breaking over a desert horizon", "heat shimmer distorting a distant ridge",
  "red sunset burning across a wide sky", "cold grey dawn over a stony plain"]),
 ("X", "Domestic & daily life", [
  "woman grinding grain with a hand mill", "children playing in a dusty courtyard",
  "family eating together on a floor mat", "bread baking in a clay oven",
  "wool being spun by hand", "a mother comforting a small child",
  "washing hung to dry between mud walls", "an old woman sorting dates into baskets"]),
 ("Y", "Messengers, arrivals & departures", [
  "exhausted messenger dismounting at a gate", "a rider departing as onlookers watch",
  "a letter being read aloud to a waiting group", "farewell at the edge of an encampment",
  "dust cloud of an approaching rider", "a returning column entering a city gate"]),
 ("Z", "Aerial & establishing", [
  "aerial view of a walled desert town", "high view of a caravan crossing dunes",
  "high view of an army encamped on a plain", "aerial of a river winding through dry land",
  "overhead view of a crowded market square", "wide aerial of an oasis in empty desert"]),
 ("CW", "American Civil War (secondary series)", [
  "Union soldier in blue wool uniform and kepi cap", "Confederate soldier in grey uniform",
  "Civil War battlefield with cannon and smoke", "Abraham Lincoln portrait in a presidential office",
  "Union regiment marching along a dirt road", "field hospital tent with wounded soldiers",
  "cannon battery firing across an open field", "Civil War era map with troop positions",
  "soldiers around a campfire at night", "torn Union and Confederate flags"]),
 ("MO", "Motivation & abstract (secondary series)", [
  "a person climbing a steep rock face at sunrise", "hands gripping a rope, straining upward",
  "a lone runner on an empty road at dawn", "a seedling pushing through cracked earth",
  "a long staircase climbing into light", "silhouette standing at the summit of a hill",
  "an open hand releasing sand into wind", "a door opening onto bright light"]),
]


LIVING_SUBJECT_TERMS = {
    "woman", "women", "man", "men", "boy", "girl", "child", "children", "people", "crowd", "crowds",
    "figure", "figures", "rider", "riders", "horseman", "horsemen", "warrior", "warriors", "soldier",
    "soldiers", "elder", "scribe", "merchant", "imam", "worshipper", "worshippers", "pilgrims",
    "mourners", "townspeople", "scouts", "survivors", "messenger", "commander", "chieftain",
    "family", "mother", "horse", "horses", "camel", "camels", "cavalry", "donkey", "goat", "herd",
    "bird", "vultures", "livestock", "fallen",
}


def is_living_subject(subject_text: str) -> bool:
    import re
    words = set(re.findall(r'\b[a-zA-Z]+\b', subject_text.lower()))
    return bool(words & LIVING_SUBJECT_TERMS)


def pollinations_url(prompt_with_style, seed, width=1280, height=720):
    from urllib.parse import quote
    return (f"https://image.pollinations.ai/prompt/{quote(prompt_with_style)}"
            f"?width={width}&height={height}&nologo=true&seed={seed}&model=flux")


def build_batches():
    """Deterministic batch list. Batch ids are stable as long as SEED is unchanged."""
    rng = random.Random(SEED)
    batches = []
    for code, title, subjects in THEMES:
        combos = list(itertools.product(subjects, SHOT, LIGHT))
        rng.shuffle(combos)
        combos = combos[:50 if code in ("CW", "MO") else 75]
        theme_tier = "q" if code in QUALITY_THEMES else "b"
        for i in range(0, len(combos), 25):
            chunk = combos[i:i + 25]
            if len(chunk) < 10:
                continue
            world = world_for(code)
            prompts = []
            for n, (subject, shot, light) in enumerate(chunk):
                prompt_tier = "q" if (theme_tier == "q" or is_living_subject(subject)) else "b"

                if prompt_tier == "b" and is_living_subject(subject):
                    effective_shot = "wide establishing shot" if shot in ("medium shot", "close detail shot") else shot
                    suffix = ", distant figures, silhouetted, no facial detail"
                else:
                    effective_shot = shot
                    suffix = ""

                text = f"{effective_shot} of {subject}, {light}"
                # World anchor goes early — diffusion models weight leading tokens heavily.
                full = f"{text}{suffix}, {world}, {STYLE}" if world else f"{text}{suffix}, {STYLE}"
                seed = SEEDS[(n + 1) % len(SEEDS)]
                prompts.append({
                    "text": text,
                    "prompt": full,
                    "subject": subject, "shot": effective_shot, "light": light,
                    "seed": seed,
                    "url": pollinations_url(full, seed),
                    "tier": prompt_tier,
                })
            batches.append({"id": f"{code}{i//25+1}", "code": code, "theme": title,
                            "tier": theme_tier, "prompts": prompts})
    return batches


def batch_map():
    return {b["id"]: b for b in build_batches()}


if __name__ == "__main__":
    bs = build_batches()
    print(f"{len(bs)} batches, {sum(len(b['prompts']) for b in bs)} prompts")
    for b in bs:
        print(f"  {b['id']:<5} {b['tier']}  {len(b['prompts']):>3}  {b['theme']}")
