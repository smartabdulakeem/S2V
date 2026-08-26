"""
Unit tests for pipeline/validator.py (S2V Script Schema v2).
"""

import json
import os
import pytest
from pathlib import Path
from pipeline.validator import (
    validate,
    validate_file,
    load_and_upconvert,
    resolve_shot_durations,
)

BASE_DIR = Path(__file__).parent.parent


# ── Test 1: All existing sample scripts validate ────────────────────────────

def test_samples_validate():
    samples_dir = BASE_DIR / "samples"
    sample_files = list(samples_dir.glob("*.json"))
    assert len(sample_files) > 0, "No sample files found in samples/"

    for sample in sample_files:
        script, errors = validate_file(str(sample))
        assert errors == [], f"Sample '{sample.name}' failed validation: {errors}"
        assert script is not None
        assert "segments" in script
        for seg in script["segments"]:
            assert "shots" in seg
            assert len(seg["shots"]) >= 1


def test_other_root_samples_validate():
    for name in ["civil_war_sample.json", "arabic_storytelling_e2e_output.json"]:
        path = BASE_DIR / name
        if path.exists():
            script, errors = validate_file(str(path))
            assert errors == [], f"Root sample '{name}' failed validation: {errors}"


# ── Test 2: Native v2 shot-list script validates ─────────────────────────────

def test_v2_shot_list_script_validates():
    v2_script = {
        "schema_version": 2,
        "project": {
            "title": "S2E6 — The Long Retreat",
            "output_filename": "s2e6.mp4",
            "aspect_ratio": "16:9",
            "resolution": "1920x1080",
            "fps": 30,
            "voice": "google:en-GB-Neural2-D",
            "voice_rate": "+0%",
            "voice_pitch": "+0Hz",
            "captions": {"enabled": True, "source": "tts_timings"},
            "background_music": None,
            "music_volume_db": -20,
            "visual_style": "vintage_documentary",
            "world_anchor": "7th century Arabian Peninsula",
            "character_bible": {"Ali": "an elderly man, white beard, plain dark robes"},
            "budget": {"max_generated_clips": 0, "max_spend_usd": 0}
        },
        "segments": [
            {
                "segment_id": 1,
                "type": "hook",
                "narration": "There is an image the history books do not linger on.",
                "voice_steering": "grave, unhurried",
                "shots": [
                    {
                        "shot_id": "1a",
                        "duration": None,
                        "source": "library",
                        "query": "lone rider on a ridge at dusk",
                        "min_score": 0.26,
                        "motion": {"kind": "ken_burns", "effect": "zoom_in"},
                        "treatment": {"filter": "vignette", "grade": None}
                    },
                    {
                        "shot_id": "1b",
                        "duration": 6.0,
                        "source": "library",
                        "query": "desert fortress under moonlight",
                        "motion": {"kind": "ken_burns", "effect": "pan_left"},
                        "treatment": {"filter": "none"}
                    }
                ],
                "text_overlay": {
                    "text": "MADINAH — 656 CE",
                    "position": "bottom_center",
                    "start": 0.5,
                    "duration_seconds": 4
                },
                "transition_in": "fade",
                "transition_out": "cut",
                "sfx": [{"name": "wind", "offset_ms": 0, "gain_db": -12}]
            }
        ]
    }

    errors = validate(v2_script)
    assert errors == [], f"v2 script validation errors: {errors}"
    upconverted = load_and_upconvert(v2_script)
    assert len(upconverted["segments"][0]["shots"]) == 2


# ── Test 3: The 8 Non-Type Rules failing cases ──────────────────────────────

def get_base_script():
    return {
        "project": {
            "title": "Test Base Project",
            "output_filename": "test_base.mp4",
            "voice": "en-US-GuyNeural",
            "budget": {"max_generated_clips": 0, "max_spend_usd": 0}
        },
        "segments": [
            {
                "segment_id": 1,
                "narration": "Sample narration text.",
                "shots": [
                    {
                        "shot_id": "1a",
                        "duration": None,
                        "source": "library",
                        "query": "ancient city aerial landscape",
                        "motion": {"kind": "ken_burns", "effect": "zoom_in"}
                    }
                ]
            }
        ]
    }


def test_rule_1_segment_id_unique_and_positive():
    # Duplicate segment_id
    script = get_base_script()
    script["segments"].append({
        "segment_id": 1,
        "narration": "Second segment with duplicate id.",
        "shots": [{"shot_id": "1b", "query": "city landscape"}]
    })
    errors = validate(script)
    assert any("duplicate id 1" in e for e in errors)

    # Invalid segment_id < 1
    script2 = get_base_script()
    script2["segments"][0]["segment_id"] = 0
    errors2 = validate(script2)
    assert any("must be >= 1" in e for e in errors2)


def test_rule_2_segment_at_least_one_shot_and_unique_shot_id():
    # Empty shots array
    script = get_base_script()
    script["segments"][0]["shots"] = []
    errors = validate(script)
    assert any("must contain at least 1 shot" in e for e in errors)

    # Duplicate shot_id in same segment
    script2 = get_base_script()
    script2["segments"][0]["shots"] = [
        {"shot_id": "1a", "source": "library", "query": "desert rider"},
        {"shot_id": "1a", "source": "library", "query": "oasis landscape"}
    ]
    errors2 = validate(script2)
    assert any("duplicate shot_id '1a'" in e for e in errors2)


def test_rule_3_source_pin_requires_pin():
    script = get_base_script()
    script["segments"][0]["shots"][0] = {
        "shot_id": "1a",
        "source": "pin",
        "pin": None
    }
    errors = validate(script)
    assert any('source is "pin" but no pin path was given' in e for e in errors)


def test_rule_4_source_library_or_generate_requires_non_empty_query():
    script = get_base_script()
    script["segments"][0]["shots"][0] = {
        "shot_id": "1a",
        "source": "library",
        "query": "   "
    }
    errors = validate(script)
    assert any('source is "library" but no non-empty query was given' in e for e in errors)

    script2 = get_base_script()
    script2["segments"][0]["shots"][0] = {
        "shot_id": "1a",
        "source": "generate",
        "query": ""
    }
    errors2 = validate(script2)
    assert any('source is "generate" but no non-empty query was given' in e for e in errors2)


def test_rule_5_explicit_duration_must_be_positive():
    script = get_base_script()
    script["segments"][0]["shots"][0]["duration"] = 0
    errors = validate(script)
    assert any("explicit duration must be > 0" in e for e in errors)

    script2 = get_base_script()
    script2["segments"][0]["shots"][0]["duration"] = -4.5
    errors2 = validate(script2)
    assert any("explicit duration must be > 0" in e for e in errors2)


def test_rule_6_motion_seconds_between_1_and_10_for_generative():
    script = get_base_script()
    script["project"]["budget"] = {"max_generated_clips": 5, "max_spend_usd": 10}
    script["segments"][0]["shots"][0] = {
        "shot_id": "1a",
        "source": "generate",
        "query": "storm banner advancing",
        "motion": {"kind": "generative", "seconds": 15}
    }
    errors = validate(script)
    assert any("motion.seconds: must be between 1 and 10" in e for e in errors)


def test_rule_7_generative_motion_requires_budget():
    script = get_base_script()
    script["project"]["budget"] = {"max_generated_clips": 0, "max_spend_usd": 0}
    script["segments"][0]["shots"][0] = {
        "shot_id": "1a",
        "source": "generate",
        "query": "storm banner advancing",
        "motion": {"kind": "generative", "seconds": 5}
    }
    errors = validate(script)
    assert any("requests generative motion" in e for e in errors)
    assert any("Raise the budget or change motion.kind" in e for e in errors)


def test_rule_8_pin_path_traversal_is_refused():
    script = get_base_script()
    script["segments"][0]["shots"][0] = {
        "shot_id": "1a",
        "source": "pin",
        "pin": "projects/../../secret.json"
    }
    assert any("traversal" in e for e in validate(script))


def test_rule_8_absolute_pin_is_refused_without_a_working_folder():
    """
    Absolute pins used to be refused outright. A project can now work from a
    folder anywhere on the machine, so they are allowed — but only inside that
    declared folder. Otherwise a shared script could render any file on the
    recipient's disk.
    """
    script = get_base_script()
    script["segments"][0]["shots"][0] = {
        "shot_id": "1a",
        "source": "pin",
        "pin": "C:\\Windows\\System32\\drivers\\etc\\hosts",
    }
    errors = validate(script)
    assert any("only allowed when" in e for e in errors)


def test_rule_8_absolute_pin_outside_the_working_folder_is_refused(tmp_path):
    work = tmp_path / "my images"
    work.mkdir()
    script = get_base_script()
    script["project"]["image_folder"] = str(work)
    script["segments"][0]["shots"][0] = {
        "shot_id": "1a",
        "source": "pin",
        "pin": "C:\\Windows\\System32\\drivers\\etc\\hosts",
    }
    errors = validate(script)
    assert any("outside this project's working folder" in e for e in errors)


def test_rule_8_absolute_pin_inside_the_working_folder_is_allowed(tmp_path):
    work = tmp_path / "my images"
    work.mkdir()
    chosen = work / "chosen.jpg"
    chosen.write_bytes(b"not really an image, but a real file")

    script = get_base_script()
    script["project"]["image_folder"] = str(work)
    script["segments"][0]["shots"][0] = {
        "shot_id": "1a",
        "source": "pin",
        "pin": str(chosen),
    }
    assert not [e for e in validate(script) if ".pin" in e]


def test_rule_8_project_relative_pin_is_allowed():
    script = get_base_script()
    script["segments"][0]["shots"][0] = {
        "shot_id": "1a",
        "source": "pin",
        "pin": "library/_polotno_downloads/89bd0337c32c.jpg",
    }
    assert not [e for e in validate(script) if ".pin" in e]


# ── Test 4: Duration resolution logic tests ──────────────────────────────────

def test_duration_resolution_null_split():
    shots = [
        {"duration": None},
        {"duration": 5.0},
        {"duration": None}
    ]
    resolved = resolve_shot_durations(shots, total_segment_duration=25.0)
    assert len(resolved) == 3
    assert resolved[1] == 5.0
    assert resolved[0] == 10.0
    assert resolved[2] == 10.0


def test_duration_resolution_proportional_scaling():
    shots = [
        {"duration": 15.0},
        {"duration": 15.0}
    ]
    resolved = resolve_shot_durations(shots, total_segment_duration=20.0)
    assert resolved[0] == 10.0
    assert resolved[1] == 10.0


def test_duration_resolution_gap_stretching():
    shots = [
        {"duration": 4.0},
        {"duration": 4.0}
    ]
    resolved = resolve_shot_durations(shots, total_segment_duration=12.0)
    assert resolved[0] == 4.0
    assert resolved[1] == 8.0
