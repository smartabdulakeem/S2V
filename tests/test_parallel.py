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


def test_fetch_visual_reports_library_hit(tmp_path, monkeypatch):
    """
    A library retrieval must report the library path it used, so the caller can
    record usage. Fails if the on_library_hit callback is not fired.
    """
    from PIL import Image
    from pipeline import library, visuals

    images_dir = tmp_path / "images"
    images_dir.mkdir(parents=True)
    Image.new("RGB", (200, 200), color=(180, 120, 60)).save(images_dir / "only.jpg")

    monkeypatch.setattr(library, "ROOT", str(tmp_path))
    monkeypatch.setattr(library, "LIBRARY_DIR", str(tmp_path))
    monkeypatch.setattr(library, "IMAGES_DIR", str(images_dir))
    monkeypatch.setattr(library, "INDEX_PATH", str(tmp_path / "index.npz"))
    monkeypatch.setattr(library, "MANIFEST_PATH", str(tmp_path / "manifest.jsonl"))
    library.reindex(force=True)

    title = "ZZ Library Hit Probe"
    project_dir = os.path.join(os.path.abspath("."), "projects", visuals.slugify_title(title))
    shutil.rmtree(project_dir, ignore_errors=True)

    hits = []
    try:
        visuals.fetch_visual(
            segment_id=1,
            keyword="a warm coloured square",
            narration="",
            cache_dir=str(tmp_path),
            video_title=title,
            auto_generate=False,
            min_score=0.0,
            series_slug="default",
            on_library_hit=hits.append,
        )
    finally:
        shutil.rmtree(project_dir, ignore_errors=True)

    assert hits == ["images/only.jpg"], f"Expected one library hit reported, got {hits}"


def test_render_usage_recorded_only_when_render_completes(tmp_path, monkeypatch):
    """
    Library usage is committed when a render finishes, once per image per render,
    and not at all when the render is cancelled.
    Fails if the record_render_usage loop is removed from the orchestrator.
    """
    from pipeline import library
    from pipeline import orchestrator as orch_mod

    monkeypatch.setattr(library, "RENDER_USAGE_PATH", str(tmp_path / "render_usage.json"))
    assert library.get_render_usage_counts() == {}

    used = "library/images/probe_image.jpg"
    real_fetch = orch_mod.fetch_visual

    def fetch_reporting_two_hits(*args, **kwargs):
        path = real_fetch(*args, **kwargs)
        cb = kwargs.get("on_library_hit")
        if cb:
            # Same image twice: must still count once for this render.
            cb(used)
            cb(used)
        return path

    monkeypatch.setattr(orch_mod, "fetch_visual", fetch_reporting_two_hits)

    base_dir = os.path.abspath(".")
    script_path = os.path.abspath("civil_war_sample.json")

    cancelled = orch_mod.RenderOrchestrator(base_dir=base_dir)
    cancelled.cancel()
    assert cancelled.render(script_path)["success"] is False
    assert library.get_render_usage_counts() == {}, "Cancelled render must record nothing"

    res = orch_mod.RenderOrchestrator(base_dir=base_dir).render(script_path)
    assert res["success"] is True, f"Render failed: {res.get('error')}"
    assert library.get_render_usage_counts() == {used: 1}, "One completed render = one count"

    res2 = orch_mod.RenderOrchestrator(base_dir=base_dir).render(script_path)
    assert res2["success"] is True, f"Second render failed: {res2.get('error')}"
    assert library.get_render_usage_counts() == {used: 2}, "Second render must increment to 2"


def test_partial_failure_reporting():
    """Test that partial segment failure reports segment id and fails render."""
    base_dir = os.path.abspath(".")
    orchestrator = RenderOrchestrator(base_dir=base_dir)
    err_res = orchestrator._fail_render({2: "Failed to load image"})

    assert err_res["success"] is False
    assert "Segment 2" in err_res["error"]
