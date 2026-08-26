"""
Write the `brief_subject` field into every series pack.

`world_anchor` was used for this and is wrong for it: in 10 of the 11 packs it
carries medium language as well as subject ("1860s American Civil War, Matthew
Brady tintype archival photograph"). Opening every prompt with that fought the
picked visual type - ask for a lithograph and the prompt also demanded a
tintype photograph.

`brief_subject` names what the film is about and nothing else. Idempotent:
re-running replaces the field and leaves every other key untouched. Run from
the repo root.
"""

import json
import os
from collections import OrderedDict

#: Subject matter only - never the word for a film, documentary or picture.
#:
#: These follow an opener from BRIEF_OPENERS, so the brief reads "An
#: illustrated scene of seventh century Arabia". Naming the artefact twice
#: ("Illustration plate from a documentary on...") is what put a lettered
#: caption under every generated image.
SUBJECTS = {
    "biography": "a figure from history",
    "business_money": "business and finance",
    "default": "real people and places",
    "islamic_history": "seventh century Arabia and early Islamic history",
    "motivational": "contemporary everyday life",
    "mythology_folklore": "myth and folklore",
    "nature_wildlife": "wildlife and the natural world",
    "space_science": "space and science",
    "true_crime": "a criminal investigation",
    "world_military_history": "military history",
}

SERIES_DIR = os.path.join("config", "series")


def main():
    for slug, subject in SUBJECTS.items():
        path = os.path.join(SERIES_DIR, f"{slug}.json")
        if not os.path.isfile(path):
            raise SystemExit(f"missing pack: {path}")
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f, object_pairs_hook=OrderedDict)
        data["brief_subject"] = subject
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"{slug}: {subject}")
    print(f"total: {len(SUBJECTS)}")


if __name__ == "__main__":
    main()
