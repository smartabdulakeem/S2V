"""
tests/test_timeline_audio.py

Verification for timeline concatenated narration audio, duration drift check,
and caching logic.
"""

import os
import subprocess
import time
from unittest.mock import patch

import pytest

from pipeline.composer import _find_ffmpeg
from pipeline.narration_timing import probe_seconds
from pipeline.timeline_audio import build_timeline_audio


def _create_sine_mp3(path: str, duration: float) -> str:
    """Generate a valid, playable mp3 file of an exact duration using ffmpeg."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ffmpeg = _find_ffmpeg()
    cmd = [
        ffmpeg, "-y",
        "-f", "lavfi",
        "-i", f"sine=frequency=440:duration={duration}",
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        path
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return path


@pytest.fixture
def sample_segments(tmp_path):
    """Creates 6 distinct measured segments with real mp3 files."""
    durations = [2.0, 3.0, 1.5, 4.0, 2.5, 3.5]  # sum = 16.5s
    audio_dir = tmp_path / "audio_source"
    audio_dir.mkdir(exist_ok=True)
    segments = []
    for i, dur in enumerate(durations, 1):
        mp3_path = str(audio_dir / f"segment_{i}_audio.mp3")
        _create_sine_mp3(mp3_path, dur)
        segments.append({
            "segment_id": i,
            "narration": f"Narration line {i}",
            "narration_audio": mp3_path,
            "narration_seconds": dur
        })
    return segments


def test_concatenation_covers_every_measured_segment_and_offsets(sample_segments, tmp_path):
    """
    Test 1: Six segments in, one output, and the offsets map is the running sum
    of the measured seconds.
    """
    proj_dir = str(tmp_path / "proj_1")
    script = {"project": {"title": "Test Film 1"}, "segments": sample_segments}

    res = build_timeline_audio(script, proj_dir)

    assert res["ok"] is True
    assert res["rebuilt"] is True
    assert res["segments"] == 6
    assert res["skipped"] == 0
    assert os.path.isfile(res["path"])

    expected_offsets = {
        1: 0.0,
        2: 2.0,
        3: 5.0,
        4: 6.5,
        5: 10.5,
        6: 13.0
    }
    for seg_id, expected_off in expected_offsets.items():
        assert res["offsets"][seg_id] == expected_off, f"Offset mismatch for segment {seg_id}"
        assert res["offsets"][str(seg_id)] == expected_off


def test_duration_agrees_with_sum_within_100_ms(sample_segments, tmp_path):
    """
    Test 2: Assert probed duration agrees with sum of measured seconds within 100 ms.
    Asserts the real duration of what was written, not merely file existence.
    """
    proj_dir = str(tmp_path / "proj_2")
    script = {"project": {"title": "Test Film 2"}, "segments": sample_segments}

    res = build_timeline_audio(script, proj_dir)

    assert res["ok"] is True
    probed = probe_seconds(res["path"])
    assert probed is not None
    assert probed >= 16.0, f"Expected > 16.0s duration, got {probed}"

    # Sum of [2.0, 3.0, 1.5, 4.0, 2.5, 3.5] = 16.5
    measured_sum = 16.5
    last_seg = sample_segments[-1]
    computed_sum = res["offsets"][last_seg["segment_id"]] + last_seg["narration_seconds"]
    assert abs(computed_sum - measured_sum) <= 0.001, (
        f"Offsets sum {computed_sum} disagrees with measured sum {measured_sum}!"
    )
    assert abs(res["seconds"] - measured_sum) <= 0.100, (
        f"Drift {abs(res['seconds'] - measured_sum):.4f}s exceeded 100 ms threshold!"
    )
    assert res["diff_ms"] <= 100.0


def test_cache_is_honoured_without_calling_ffmpeg(sample_segments, tmp_path):
    """
    Test 3: Two calls in a row: the second returns rebuilt=False and does not invoke ffmpeg.
    """
    proj_dir = str(tmp_path / "proj_3")
    script = {"project": {"title": "Test Film 3"}, "segments": sample_segments}

    res1 = build_timeline_audio(script, proj_dir)
    assert res1["rebuilt"] is True
    assert os.path.isfile(res1["path"])

    real_run = subprocess.run
    call_counts = {"ffmpeg": 0}

    def patched_run(cmd, *args, **kwargs):
        if isinstance(cmd, (list, tuple)) and any("ffmpeg" in str(x).lower() for x in cmd):
            call_counts["ffmpeg"] += 1
        return real_run(cmd, *args, **kwargs)

    with patch("subprocess.run", side_effect=patched_run):
        res2 = build_timeline_audio(script, proj_dir)

    assert res2["rebuilt"] is False
    assert res2["path"] == res1["path"]
    assert res2["seconds"] == res1["seconds"]
    assert call_counts["ffmpeg"] == 0, "ffmpeg was invoked despite valid cache!"


def test_changed_narration_rebuilds(sample_segments, tmp_path):
    """
    Test 4: Touch one segment's mp3 so its mtime moves; the next call returns rebuilt=True.
    """
    proj_dir = str(tmp_path / "proj_4")
    script = {"project": {"title": "Test Film 4"}, "segments": sample_segments}

    res1 = build_timeline_audio(script, proj_dir)
    assert res1["rebuilt"] is True

    # Touch segment 1 mp3
    seg1_path = sample_segments[0]["narration_audio"]
    new_mtime = os.path.getmtime(seg1_path) + 5.0
    os.utime(seg1_path, (new_mtime, new_mtime))

    res2 = build_timeline_audio(script, proj_dir)
    assert res2["rebuilt"] is True


def test_half_measured_film_still_builds_and_reports_skipped(sample_segments, tmp_path):
    """
    Test 5: Three of six segments have audio; build succeeds and reports three skipped.
    """
    proj_dir = str(tmp_path / "proj_5")
    half_segments = []
    for i, s in enumerate(sample_segments):
        if i < 3:
            half_segments.append(dict(s))
        else:
            half_segments.append({
                "segment_id": s["segment_id"],
                "narration": s["narration"],
                "narration_audio": None,
                "narration_seconds": None
            })

    script = {"project": {"title": "Half Film"}, "segments": half_segments}
    res = build_timeline_audio(script, proj_dir)

    assert res["ok"] is True
    assert res["segments"] == 3
    assert res["skipped"] == 3
    assert res["offsets"][1] == 0.0
    assert res["offsets"][2] == 2.0
    assert res["offsets"][3] == 5.0
    probed = probe_seconds(res["path"])
    assert probed is not None
    # 2.0 + 3.0 + 1.5 = 6.5s
    assert abs(probed - 6.5) <= 0.100


def test_film_with_no_audio_returns_clear_failure_without_raising(tmp_path):
    """
    Test 6: A film with no audio at all returns a clear failure the UI can show,
    and does not raise.
    """
    proj_dir = str(tmp_path / "proj_6")
    script = {
        "project": {"title": "Empty Audio Film"},
        "segments": [
            {"segment_id": 1, "narration": "Hello world", "narration_audio": None},
            {"segment_id": 2, "narration": "Second line", "narration_audio": ""}
        ]
    }

    res = build_timeline_audio(script, proj_dir)

    assert isinstance(res, dict)
    assert res["ok"] is False
    assert "error" in res
    assert res["segments"] == 0
    assert res["skipped"] == 2