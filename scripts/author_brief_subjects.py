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

SUBJECTS = {
    "biography": "a historical biography film",
    "business_money": "a documentary on business and finance",
    "default": "a documentary film",
    "islamic_history": "a documentary on seventh century Arabia and early Islamic history",
    "motivational": "a contemporary motivational film",
    "mythology_folklore": "a film on myth and folklore",
    "nature_wildlife": "a natural history wildlife film",
    "space_science": "a documentary on space and science",
    "true_crime": "a true crime documentary",
    "world_military_history": "a military history documentary",
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
