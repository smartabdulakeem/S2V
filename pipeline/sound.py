"""
Ambient sound beds.

The schema has carried an `sfx` field and the compositor an `_overlay_sound_effects`
mixer for a long time, but nothing ever chose a sound, so every film has been dry
narration over stills. This module is the missing half: pick a bed that suits the
scene, fit it to the segment, and duck it under the voice.

Beds are matched on the search terms they were fetched with — the sounds manifest
records a `query` per file ("desert wind strong", "crowd murmur"). That is a plain
word-overlap match, not a model: with a few dozen sounds it is enough, and it is
honest about what it does.
"""

import json
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOUNDS_DIR = os.path.join(ROOT, "library", "sounds")
INBOX_DIR = os.path.join(SOUNDS_DIR, "_inbox")
MANIFEST_PATH = os.path.join(SOUNDS_DIR, "manifest.jsonl")

#: Bed level under narration, and how hard the voice ducks it.
BED_GAIN_DB = -26.0
DUCK_RATIO = 8

_STOPWORDS = {
    "the", "a", "an", "of", "and", "in", "on", "at", "to", "for", "with",
    "his", "her", "their", "its", "was", "were", "is", "are", "that", "this",
}


def _words(text: str) -> set:
    return {w for w in re.findall(r"[a-z]+", (text or "").lower()) if w not in _STOPWORDS and len(w) > 2}


def load_beds(include_inbox: bool = True) -> list:
    """
    Every usable bed, as {path, query, duration}.

    Reads the sounds manifest and keeps entries whose file is still on disk.
    Inbox sounds are included by default: roughly half of a fetched batch is
    unusable, but excluding the inbox entirely means no beds at all until a review
    pass that has not happened yet.
    """
    beds = []
    if not os.path.exists(MANIFEST_PATH):
        return beds

    seen = set()
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("category") not in (None, "beds", "bed", "ambience"):
                continue
            rel = (rec.get("path") or "").replace("\\", "/")
            if not rel or rel in seen:
                continue
            if not include_inbox and "_inbox/" in rel:
                continue
            abs_path = os.path.join(ROOT, rel)
            if not os.path.exists(abs_path):
                continue
            seen.add(rel)
            beds.append({
                "path": rel,
                "abs_path": abs_path,
                "query": rec.get("query", ""),
                "duration": float(rec.get("duration") or 0.0),
            })
    return beds


def pick_bed(scene_text: str, beds: list, exclude: set = None) -> dict:
    """
    Best bed for a scene, or None when nothing overlaps.

    Returning None matters: an unrelated bed is worse than silence. A freight
    train under a 7th-century desert scene is not ambience, it is a mistake.
    """
    if not beds:
        return None
    exclude = exclude or set()
    scene = _words(scene_text)
    if not scene:
        return None

    best, best_score = None, 0
    for bed in beds:
        if bed["path"] in exclude:
            continue
        score = len(scene & _words(bed["query"]))
        if score > best_score:
            best, best_score = bed, score
    return best


def build_bed_track(bed_abs_path: str, duration: float, output_path: str,
                    ffmpeg: str, fade: float = 1.5) -> str:
    """Loop or trim a bed to `duration`, with fades at both ends."""
    fade = min(fade, max(0.2, duration / 4))
    cmd = [
        ffmpeg, "-y", "-stream_loop", "-1", "-i", bed_abs_path,
        "-t", f"{duration:.3f}",
        "-af", f"afade=t=in:st=0:d={fade:.2f},afade=t=out:st={max(0.0, duration - fade):.2f}:d={fade:.2f}",
        "-ar", "44100", "-ac", "2",
        output_path,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0 or not os.path.exists(output_path):
        raise RuntimeError(f"Could not build bed track: {res.stderr[-300:]}")
    return output_path


def mix_bed_under_narration(narration_path: str, bed_path: str, output_path: str,
                            ffmpeg: str, bed_gain_db: float = BED_GAIN_DB) -> str:
    """
    Mix a bed under narration, ducking it whenever the voice is present.

    sidechaincompress keyed on the narration is what makes ambience sit *under* a
    voice rather than fight it. On any failure the original narration is returned
    untouched — atmosphere is never worth losing the audio for.
    """
    filtergraph = (
        f"[1:a]volume={bed_gain_db}dB[bed];"
        f"[0:a]asplit=2[voice][key];"
        f"[bed][key]sidechaincompress=threshold=0.03:ratio={DUCK_RATIO}:attack=5:release=300[ducked];"
        f"[voice][ducked]amix=inputs=2:duration=first:dropout_transition=0[out]"
    )
    cmd = [
        ffmpeg, "-y", "-i", narration_path, "-i", bed_path,
        "-filter_complex", filtergraph, "-map", "[out]",
        "-codec:a", "libmp3lame", "-q:a", "2",
        output_path,
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            return output_path
    except Exception:
        pass
    return narration_path
