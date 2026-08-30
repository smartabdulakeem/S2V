# pipeline/wolfcut_export.py
#
# Authoritative schema definitions read from jub0t/WolfCut at commit:
# cad030dabc18f4013855c9fe89ca3688e8a5298d
#
# Schemas:
#   engine/crates/wolfcut-project/src/lib.rs (DOCUMENT_VERSION = 1)
#   engine/crates/wolfcut-project/src/doc.rs
#   desktop/src/lib/generated/Project.ts
#   desktop/src/lib/generated/Timeline.ts
#   desktop/src/lib/generated/Track.ts
#   desktop/src/lib/generated/Clip.ts
#   desktop/src/lib/generated/MediaItem.ts
#   desktop/src/lib/generated/TextStyle.ts
#

import os
import re
import json
from typing import Dict, Any, List, Optional, Tuple
from pipeline.validator import resolve_shot_durations
from pipeline.captions import parse_srt


def _clean_slug(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_\-]", "_", (name or "project").strip())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug.lower() if slug else "project"


def write_wolfcut_project(
    script_data: dict,
    audio_paths_map: dict,
    durations_map: dict,
    project_dir: str
) -> str:
    """
    Exports a rendered film into a WolfCut timeline project file (.wolfcut).

    Disassembles the finished film into 3 lanes:
      Track T1: Pictures (distinct picture clips at exact spoken durations,
                consecutive shots sharing an image collapsed into one clip)
      Track T2: Narration (per-segment audio clips laid end-to-end)
      Track T3: Captions (text clips synchronized to SRT subtitle cues)

    Matches jub0t/WolfCut DOCUMENT_VERSION = 1 format.
    """
    os.makedirs(project_dir, exist_ok=True)
    slug = _clean_slug(
        script_data.get("slug")
        or script_data.get("project_name")
        or script_data.get("title")
        or "project"
    )
    output_path = os.path.join(project_dir, f"{slug}.wolfcut")

    # Dimensions
    width = int(script_data.get("width") or 1920)
    height = int(script_data.get("height") or 1080)
    format_str = str(script_data.get("format") or "").strip()
    if format_str == "9:16":
        width, height = 1080, 1920
    elif format_str == "1:1":
        width, height = 1080, 1080
    elif format_str == "4:5":
        width, height = 1080, 1350

    segments = script_data.get("segments") or []

    media_list: List[Dict[str, Any]] = []
    clips_list: List[Dict[str, Any]] = []
    seen_media_paths: Dict[str, str] = {}  # abs_path -> media_id

    media_counter = 1
    clip_counter = 1

    def get_or_create_media(path: str, kind: str, duration: Optional[float] = None) -> str:
        nonlocal media_counter
        abs_p = os.path.abspath(path)
        if abs_p in seen_media_paths:
            return seen_media_paths[abs_p]

        m_id = f"m{media_counter}"
        media_counter += 1
        seen_media_paths[abs_p] = m_id

        has_audio = (kind == "audio" or kind == "video")
        item = {
            "id": m_id,
            "path": abs_p,
            "name": os.path.basename(abs_p),
            "duration": round(duration, 3) if duration is not None else None,
            "kind": kind,
            "width": width if kind in ("image", "video") else None,
            "height": height if kind in ("image", "video") else None,
            "frameRate": None,
            "frameRateFraction": None,
            "videoCodec": None,
            "audioCodec": "mp3" if kind == "audio" else None,
            "hasAudio": has_audio,
            "placeholder": False,
        }
        media_list.append(item)
        return m_id

    # 1. Build Track T1: PICTURES
    all_flat_shots = []
    picture_owner_map = {}

    for seg in segments:
        for shot in (seg.get("shots") or []):
            sid = shot.get("shot_id")
            if not shot.get("share_with"):
                picture_owner_map[sid] = shot

    for seg in segments:
        seg_id = seg.get("segment_id")
        seg_dur = float(durations_map.get(seg_id, 0.0))
        shots = seg.get("shots") or []
        resolved_durs = resolve_shot_durations(shots, seg_dur)

        for idx, shot in enumerate(shots):
            shot_dur = resolved_durs[idx] if idx < len(resolved_durs) else 0.0
            all_flat_shots.append({
                "segment": seg,
                "shot": shot,
                "duration": shot_dur,
            })

    picture_runs: List[Dict[str, Any]] = []
    current_run: Optional[Dict[str, Any]] = None

    slot_counter = 1
    for item in all_flat_shots:
        shot = item["shot"]
        dur = item["duration"]
        share_target = shot.get("share_with")

        if not share_target:
            owner_shot = shot
            owner_id = shot.get("shot_id")

            img_path = (
                owner_shot.get("resolved_image_path")
                or owner_shot.get("image_path")
                or owner_shot.get("library_image")
                or owner_shot.get("image_file")
            )
            if not img_path or not str(img_path).strip():
                cand_jpg = os.path.join(project_dir, f"{slot_counter}.jpg")
                cand_png = os.path.join(project_dir, f"{slot_counter}.png")
                cand_shot = os.path.join(project_dir, f"{owner_id}.jpg")
                if os.path.exists(cand_jpg):
                    img_path = cand_jpg
                elif os.path.exists(cand_png):
                    img_path = cand_png
                elif os.path.exists(cand_shot):
                    img_path = cand_shot
                else:
                    img_path = cand_jpg

            if current_run is not None:
                picture_runs.append(current_run)

            current_run = {
                "owner_id": owner_id,
                "slot_number": slot_counter,
                "image_path": img_path,
                "duration": dur,
                "shots": [shot],
            }
            slot_counter += 1
        else:
            if current_run is not None and (current_run["owner_id"] == share_target):
                current_run["duration"] += dur
                current_run["shots"].append(shot)
            else:
                owner_shot = picture_owner_map.get(share_target, shot)
                img_path = (
                    owner_shot.get("resolved_image_path")
                    or owner_shot.get("image_path")
                    or owner_shot.get("library_image")
                    or owner_shot.get("image_file")
                    or os.path.join(project_dir, f"{share_target}.jpg")
                )
                if current_run is not None:
                    picture_runs.append(current_run)

                current_run = {
                    "owner_id": share_target,
                    "slot_number": slot_counter - 1,
                    "image_path": img_path,
                    "duration": dur,
                    "shots": [shot],
                }

    if current_run is not None:
        picture_runs.append(current_run)

    running_pic_start = 0.0
    for run in picture_runs:
        img_p = os.path.abspath(run["image_path"])
        if not os.path.exists(img_p):
            try:
                os.makedirs(os.path.dirname(img_p), exist_ok=True)
                with open(img_p, "wb") as f:
                    f.write(b"")
            except Exception:
                pass

        m_id = get_or_create_media(img_p, kind="image", duration=None)
        run_dur = round(run["duration"], 3)

        clip_item = {
            "id": f"c{clip_counter}",
            "trackId": "T1",
            "mediaId": m_id,
            "name": os.path.basename(img_p),
            "kind": "image",
            "start": round(running_pic_start, 3),
            "duration": run_dur,
            "sourceStart": 0.0,
            "volume": 1.0,
            "fadeIn": 0.0,
            "fadeOut": 0.0,
            "scale": 1.0,
            "offsetX": 0.0,
            "offsetY": 0.0,
            "rotation": 0.0,
            "opacity": 1.0,
            "speed": 1.0,
            "preservePitch": True,
            "filters": [],
            "videoEffects": [],
        }
        clips_list.append(clip_item)
        clip_counter += 1
        running_pic_start += run["duration"]

    # 2. Build Track T2: NARRATION AUDIO
    running_audio_start = 0.0
    for seg in segments:
        seg_id = seg.get("segment_id")
        audio_p = audio_paths_map.get(seg_id)
        seg_dur = float(durations_map.get(seg_id, 0.0))

        if audio_p and os.path.exists(audio_p):
            abs_audio_p = os.path.abspath(audio_p)
            m_id = get_or_create_media(abs_audio_p, kind="audio", duration=seg_dur)

            clip_item = {
                "id": f"c{clip_counter}",
                "trackId": "T2",
                "mediaId": m_id,
                "name": os.path.basename(abs_audio_p),
                "kind": "audio",
                "start": round(running_audio_start, 3),
                "duration": round(seg_dur, 3),
                "sourceStart": 0.0,
                "volume": 1.0,
                "fadeIn": 0.0,
                "fadeOut": 0.0,
                "scale": 1.0,
                "offsetX": 0.0,
                "offsetY": 0.0,
                "rotation": 0.0,
                "opacity": 1.0,
                "speed": 1.0,
                "preservePitch": True,
                "filters": [],
                "videoEffects": [],
            }
            clips_list.append(clip_item)
            clip_counter += 1

        running_audio_start += seg_dur

    # 3. Build Track T3: CAPTIONS
    master_srt_candidates = [
        os.path.join(project_dir, f"{slug}.srt"),
        os.path.join(project_dir, "captions.srt"),
        os.path.join(project_dir, "master.srt"),
    ]
    master_srt_path = next((p for p in master_srt_candidates if os.path.exists(p)), None)

    caption_cues: List[Tuple[float, float, str]] = []

    if master_srt_path:
        caption_cues = parse_srt(master_srt_path)
    else:
        seg_time_cursor = 0.0
        for seg in segments:
            seg_id = seg.get("segment_id")
            seg_dur = float(durations_map.get(seg_id, 0.0))
            srt_path = seg.get("srt_path") or os.path.join(project_dir, f"segment_{seg_id}.srt")
            if os.path.exists(srt_path):
                cues = parse_srt(srt_path)
                for start_s, end_s, text in cues:
                    caption_cues.append((start_s + seg_time_cursor, end_s + seg_time_cursor, text))
            seg_time_cursor += seg_dur

    for start_s, end_s, text in caption_cues:
        cue_dur = max(0.05, end_s - start_s)
        display_text = str(text or "").strip()
        first_line = display_text.splitlines()[0] if display_text else "Caption"

        clip_item = {
            "id": f"c{clip_counter}",
            "trackId": "T3",
            "mediaId": "",
            "name": first_line[:30],
            "kind": "text",
            "start": round(start_s, 3),
            "duration": round(cue_dur, 3),
            "sourceStart": 0.0,
            "volume": 1.0,
            "fadeIn": 0.0,
            "fadeOut": 0.0,
            "scale": 1.0,
            "offsetX": 0.0,
            "offsetY": 0.35,
            "rotation": 0.0,
            "opacity": 1.0,
            "speed": 1.0,
            "preservePitch": True,
            "filters": [],
            "videoEffects": [],
            "text": {
                "content": display_text,
                "fontFamily": "Inter",
                "fontSize": 0.05,
                "fontWeight": 700,
                "italic": False,
                "color": "#ffffff",
                "align": "center",
                "opacity": 1.0,
                "strokeWidth": 2.0,
                "strokeColor": "#000000",
                "shadow": True,
                "background": "transparent",
                "lineHeight": 1.2,
                "tracking": 0.0,
            },
        }
        clips_list.append(clip_item)
        clip_counter += 1

    tracks_list = [
        {"id": "T1", "name": "Pictures", "visible": True, "muted": False},
        {"id": "T2", "name": "Narration", "visible": True, "muted": False},
        {"id": "T3", "name": "Captions", "visible": True, "muted": False},
    ]

    project_name = (
        script_data.get("title")
        or script_data.get("project_name")
        or slug.replace("_", " ").title()
    )

    timeline_item = {
        "id": "TL1",
        "name": "Timeline 1",
        "tracks": tracks_list,
        "clips": clips_list,
    }

    doc = {
        "wolfcut": "0.1.0",
        "version": 1,
        "name": project_name,
        "video": {
            "width": width,
            "height": height,
            "rateNum": 30,
            "rateDen": 1,
        },
        "media": media_list,
        "tracks": tracks_list,
        "clips": clips_list,
        "fonts": [],
        "timelines": [timeline_item],
        "activeTimelineId": "TL1",
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)

    return os.path.abspath(output_path)
