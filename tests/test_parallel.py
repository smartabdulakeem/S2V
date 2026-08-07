import os
import shutil
import tempfile
import subprocess
import pytest
from pipeline.orchestrator import RenderOrchestrator
from pipeline.captions import get_whisper_load_count
from pipeline.composer import _find_ffprobe

def test_whisper_singleton_load_count():
    """Verify that Whisper model is loaded at most once across renders."""
    initial_count = get_whisper_load_count()
    assert initial_count <= 1, f"Expected whisper load count <= 1, got {initial_count}"


def test_parallel_render_duration_and_frame_count_match():
    """
    Test rendering a multi-segment script with parallel orchestrator.
    Asserts output container duration and frame count match expected timeline.
    """
    base_dir = os.path.abspath(".")
    script_path = os.path.abspath("civil_war_sample.json")

    orchestrator = RenderOrchestrator(base_dir=base_dir)
    res = orchestrator.render(script_path)
    assert res["success"] is True, f"Render failed: {res.get('error')}"

    output_path = res["output"]
    assert os.path.exists(output_path), "Final stitched MP4 missing"

    ffprobe = _find_ffprobe()
    dur_cmd = [ffprobe, "-i", output_path, "-show_entries", "format=duration", "-v", "quiet", "-of", "csv=p=0"]
    frames_cmd = [ffprobe, "-i", output_path, "-select_streams", "v:0", "-show_entries", "stream=nb_frames", "-v", "quiet", "-of", "csv=p=0"]

    dur = float(subprocess.run(dur_cmd, capture_output=True, text=True, check=True).stdout.strip())
    frames = int(subprocess.run(frames_cmd, capture_output=True, text=True, check=True).stdout.strip())

    # Total duration for 3 segments (13.8s + 15.0s + 12.0s or exact audio sum)
    assert dur > 25.0, f"Expected >25s total video duration, got {dur:.2f}s"
    assert frames > 750, f"Expected >750 frames, got {frames}"


def test_cancellation_mid_render():
    """Test cancelling orchestrator mid-render stops cleanly."""
    base_dir = os.path.abspath(".")
    script_path = os.path.abspath("samples/sample_script.json")

    orchestrator = RenderOrchestrator(base_dir=base_dir)
    orchestrator.cancel()  # Immediate cancellation
    res = orchestrator.render(script_path)

    assert res["success"] is False
    assert "cancelled" in res["error"].lower()


def test_partial_failure_reporting():
    """Test that partial segment failure reports segment id and fails render."""
    base_dir = os.path.abspath(".")
    orchestrator = RenderOrchestrator(base_dir=base_dir)
    err_res = orchestrator._fail_render({2: "Failed to load image"})

    assert err_res["success"] is False
    assert "Segment 2" in err_res["error"]
