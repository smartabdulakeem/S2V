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
