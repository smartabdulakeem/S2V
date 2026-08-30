# tests/test_wolfcut_export.py

import os
import json
import pytest
import tempfile
from pipeline.wolfcut_export import write_wolfcut_project, _clean_slug
from pipeline.text_parser import plan_image_budget
from pipeline.visuals import initialize_project_sourcing
from pipeline.library import picture_owning_shots
from app import Api


def _create_synthetic_script(num_segments: int = 60, total_duration: float = 300.0) -> tuple[dict, dict, dict]:
    """Builds a synthetic multi-segment script with shots, audio paths, and durations."""
    segments = []
    durations_map = {}
    audio_paths_map = {}
    seg_dur = round(total_duration / num_segments, 3)

    for i in range(1, num_segments + 1):
        seg_id = i
        durations_map[seg_id] = seg_dur
        segments.append({
            "segment_id": seg_id,
            "text": f"Narration sentence {i} describing historical events in detail.",
            "shots": [
                {
                    "shot_id": f"{i}a",
                    "scene": f"Visual scene description for segment {i}",
                    "visual_description": f"A cinematic vista plate depicting historical scene {i}",
                    "duration": None,
                    "share_with": None,
                }
            ]
        })

    script_data = {
        "title": "Historical Odyssey",
        "slug": "historical_odyssey",
        "format": "16:9",
        "width": 1920,
        "height": 1080,
        "segments": segments,
    }
    return script_data, audio_paths_map, durations_map


def test_1_sixty_segment_reduced_to_12_images_produces_12_picture_clips(tmp_path):
    script_data, audio_paths_map, durations_map = _create_synthetic_script(num_segments=60, total_duration=300.0)

    # Reduce image budget to 12 images
    plan_image_budget(script_data, image_count=12)

    # Create dummy audio files
    for seg_id in durations_map:
        aud = tmp_path / f"seg_{seg_id}.mp3"
        aud.write_bytes(b"RIFF dummy audio")
        audio_paths_map[seg_id] = str(aud)

    wolfcut_file = write_wolfcut_project(script_data, audio_paths_map, durations_map, str(tmp_path))
    assert os.path.exists(wolfcut_file)

    with open(wolfcut_file, "r", encoding="utf-8") as f:
        doc = json.load(f)

    # Verify track T1 clips
    picture_clips = [c for c in doc["clips"] if c["trackId"] == "T1"]
    assert len(picture_clips) == 12, f"Expected 12 picture clips for 12 budgeted images, got {len(picture_clips)}"


def test_2_picture_clip_n_matches_prompt_line_n_and_file_n_jpg(tmp_path):
    script_data, audio_paths_map, durations_map = _create_synthetic_script(num_segments=60, total_duration=300.0)
    script_data["project"] = {
        "title": "Historical Odyssey",
        "slug": "historical_odyssey",
        "aspect_ratio": "16:9"
    }
    plan_image_budget(script_data, image_count=12)

    # Generate image_prompts.txt via initialize_project_sourcing
    project_dir = initialize_project_sourcing(script_data)
    prompt_file = os.path.join(project_dir, "image_prompts.txt")
    assert os.path.exists(prompt_file)

    with open(prompt_file, "r", encoding="utf-8") as f:
        prompt_lines = [l.strip() for l in f if l.strip()]

    assert len(prompt_lines) == 12

    # Create audio paths
    for seg_id in durations_map:
        aud = tmp_path / f"seg_{seg_id}.mp3"
        aud.write_bytes(b"dummy")
        audio_paths_map[seg_id] = str(aud)

    # Write wolfcut project
    wolfcut_file = write_wolfcut_project(script_data, audio_paths_map, durations_map, str(tmp_path))
    with open(wolfcut_file, "r", encoding="utf-8") as f:
        doc = json.load(f)

    picture_clips = [c for c in doc["clips"] if c["trackId"] == "T1"]
    owning_shots = picture_owning_shots(script_data)

    assert len(picture_clips) == len(prompt_lines) == len(owning_shots) == 12

    for idx in range(12):
        clip = picture_clips[idx]
        p_line = prompt_lines[idx]
        seg, shot = owning_shots[idx]

        # Check prompt line numbering
        assert p_line.startswith(f"{idx + 1}. ")

        # Check media item name or slot path
        media_id = clip["mediaId"]
        media_item = next(m for m in doc["media"] if m["id"] == media_id)
        assert media_item["path"].endswith(f"{idx + 1}.jpg") or shot["shot_id"] in media_item["path"]


def test_3_picture_clip_start_times_contiguous(tmp_path):
    script_data, audio_paths_map, durations_map = _create_synthetic_script(num_segments=30, total_duration=150.0)
    plan_image_budget(script_data, image_count=6)

    for seg_id in durations_map:
        aud = tmp_path / f"seg_{seg_id}.mp3"
        aud.write_bytes(b"dummy")
        audio_paths_map[seg_id] = str(aud)

    wolfcut_file = write_wolfcut_project(script_data, audio_paths_map, durations_map, str(tmp_path))
    with open(wolfcut_file, "r", encoding="utf-8") as f:
        doc = json.load(f)

    picture_clips = [c for c in doc["clips"] if c["trackId"] == "T1"]
    total_audio = sum(durations_map.values())

    expected_start = 0.0
    for clip in picture_clips:
        assert abs(clip["start"] - expected_start) < 0.002, f"Clip {clip['id']} start mismatch"
        expected_start += clip["duration"]

    assert abs(expected_start - total_audio) < 0.005, "Last clip did not end at total duration"


def test_4_narration_clips_laid_end_to_end_sum_to_total(tmp_path):
    script_data, audio_paths_map, durations_map = _create_synthetic_script(num_segments=10, total_duration=50.0)

    for seg_id in durations_map:
        aud = tmp_path / f"seg_{seg_id}.mp3"
        aud.write_bytes(b"dummy")
        audio_paths_map[seg_id] = str(aud)

    wolfcut_file = write_wolfcut_project(script_data, audio_paths_map, durations_map, str(tmp_path))
    with open(wolfcut_file, "r", encoding="utf-8") as f:
        doc = json.load(f)

    audio_clips = [c for c in doc["clips"] if c["trackId"] == "T2"]
    assert len(audio_clips) == 10

    running_start = 0.0
    for idx, seg_id in enumerate(durations_map.keys()):
        clip = audio_clips[idx]
        assert abs(clip["start"] - running_start) < 0.002
        assert abs(clip["duration"] - durations_map[seg_id]) < 0.002
        running_start += clip["duration"]

    assert abs(running_start - sum(durations_map.values())) < 0.005


def test_5_media_and_track_ids_referential_integrity(tmp_path):
    script_data, audio_paths_map, durations_map = _create_synthetic_script(num_segments=5, total_duration=25.0)

    for seg_id in durations_map:
        aud = tmp_path / f"seg_{seg_id}.mp3"
        aud.write_bytes(b"dummy")
        audio_paths_map[seg_id] = str(aud)

    # Add a mock SRT
    srt_file = tmp_path / "historical_odyssey.srt"
    srt_file.write_text("1\n00:00:01,000 --> 00:00:03,500\nIn ancient times\n\n2\n00:00:04,000 --> 00:00:07,000\nThe desert spanned far\n\n", encoding="utf-8")

    wolfcut_file = write_wolfcut_project(script_data, audio_paths_map, durations_map, str(tmp_path))
    with open(wolfcut_file, "r", encoding="utf-8") as f:
        doc = json.load(f)

    valid_media_ids = {m["id"] for m in doc["media"]}
    valid_track_ids = {t["id"] for t in doc["tracks"]}

    for clip in doc["clips"]:
        assert clip["trackId"] in valid_track_ids
        if clip["kind"] != "text":
            assert clip["mediaId"] in valid_media_ids
        else:
            assert clip["mediaId"] == ""
            assert "text" in clip and "content" in clip["text"]


def test_6_media_paths_absolute_and_exist(tmp_path):
    script_data, audio_paths_map, durations_map = _create_synthetic_script(num_segments=4, total_duration=20.0)

    for seg_id in durations_map:
        aud = tmp_path / f"seg_{seg_id}.mp3"
        aud.write_bytes(b"dummy")
        audio_paths_map[seg_id] = str(aud)

    wolfcut_file = write_wolfcut_project(script_data, audio_paths_map, durations_map, str(tmp_path))
    with open(wolfcut_file, "r", encoding="utf-8") as f:
        doc = json.load(f)

    for m in doc["media"]:
        p = m["path"]
        assert os.path.isabs(p), f"Path {p} is not absolute"
        assert os.path.exists(p), f"Path {p} does not exist on disk"


def test_7_document_round_trips_json_cleanly(tmp_path):
    script_data, audio_paths_map, durations_map = _create_synthetic_script(num_segments=3, total_duration=15.0)

    for seg_id in durations_map:
        aud = tmp_path / f"seg_{seg_id}.mp3"
        aud.write_bytes(b"dummy")
        audio_paths_map[seg_id] = str(aud)

    wolfcut_file = write_wolfcut_project(script_data, audio_paths_map, durations_map, str(tmp_path))
    with open(wolfcut_file, "r", encoding="utf-8") as f:
        raw_text = f.read()

    doc = json.loads(raw_text)
    re_serialized = json.dumps(doc, indent=2)
    re_parsed = json.loads(re_serialized)
    assert doc == re_parsed


def test_8_film_without_captions_produces_valid_document(tmp_path):
    script_data, audio_paths_map, durations_map = _create_synthetic_script(num_segments=3, total_duration=15.0)

    for seg_id in durations_map:
        aud = tmp_path / f"seg_{seg_id}.mp3"
        aud.write_bytes(b"dummy")
        audio_paths_map[seg_id] = str(aud)

    wolfcut_file = write_wolfcut_project(script_data, audio_paths_map, durations_map, str(tmp_path))
    with open(wolfcut_file, "r", encoding="utf-8") as f:
        doc = json.load(f)

    # Document schema valid
    assert doc["wolfcut"] == "0.1.0"
    assert doc["version"] == 1
    assert len(doc["tracks"]) == 3
    # No captions track clips
    caption_clips = [c for c in doc["clips"] if c["trackId"] == "T3"]
    assert len(caption_clips) == 0


def test_9_app_wolfcut_endpoints(tmp_path):
    app = Api()
    app._settings["output_dir"] = str(tmp_path)

    # Test when no file exists
    res_none = app.open_in_wolfcut("non_existent_project")
    assert res_none["success"] is False
    assert "releases_url" in res_none

    # Create dummy wolfcut file
    wf = tmp_path / "test_ep.wolfcut"
    wf.write_text('{"wolfcut": "0.1.0", "version": 1}', encoding="utf-8")

    res_exist = app.open_in_wolfcut(str(wf))
    assert "installed" in res_exist
    assert res_exist["path"] == str(wf)

    res_show = app.show_wolfcut_file(str(wf))
    assert res_show["success"] is True
    assert res_show["path"] == str(wf)
