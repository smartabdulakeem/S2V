"""
A render that dies must say so.

A real 14-segment render died in silence: every segment carried an explicit
"voice": null, seg.get("voice", proj["voice"]) returned that stored None rather
than the project default, and .lower() raised outside the worker's try/except.
as_completed() never called result(), so all fourteen failures were discarded in
five milliseconds; two stages later a KeyError killed the render thread, and
because the app runs under pythonw.exe there was no stderr to print it to. The
window sat on "rendering" indefinitely.
"""

from concurrent.futures import ThreadPoolExecutor

import pytest

from pipeline.orchestrator import RenderOrchestrator


@pytest.fixture
def orch(tmp_path):
    return RenderOrchestrator(base_dir=str(tmp_path), on_event=lambda e: None)


def test_explicit_null_voice_falls_back_to_the_project_voice():
    """dict.get(key, default) does not help when the key exists holding None."""
    proj = {"voice": "google:en-US-Studio-Q"}
    seg = {"segment_id": 1, "voice": None}

    # The old expression, kept here so the trap stays documented.
    assert seg.get("voice", proj["voice"]) is None

    resolved = seg.get("voice") or proj.get("voice") or ""
    assert resolved == "google:en-US-Studio-Q"
    assert "gemini-3.1-flash-tts" not in resolved.lower()  # would have raised before


def test_drain_surfaces_a_worker_exception(orch):
    """A raise inside a worker must land in errors_map, not vanish."""
    errors = {}

    def boom():
        raise ValueError("worker exploded")

    with ThreadPoolExecutor(max_workers=2) as ex:
        futures = [ex.submit(boom) for _ in range(3)]
        cancelled = orch._drain(futures, ex, "Voiceovers", errors)

    assert cancelled is False
    assert len(errors) == 3, "worker exceptions were discarded"
    assert all("ValueError: worker exploded" in v for v in errors.values())


def test_drain_is_quiet_when_workers_succeed(orch):
    errors = {}
    with ThreadPoolExecutor(max_workers=2) as ex:
        futures = [ex.submit(lambda: 42) for _ in range(3)]
        assert orch._drain(futures, ex, "Visuals", errors) is False
    assert errors == {}


def test_drain_reports_cancellation(orch):
    errors = {}
    orch.cancel()
    with ThreadPoolExecutor(max_workers=1) as ex:
        futures = [ex.submit(lambda: 1)]
        assert orch._drain(futures, ex, "Composing", errors) is True


def test_fail_render_handles_mixed_key_types(orch):
    """
    errors_map holds int segment ids and str stage labels. sorted() over mixed
    types raises TypeError, which would have replaced the real error with a
    crash inside the error reporter itself.
    """
    events = []
    orch.on_event = events.append

    result = orch._fail_render({3: "Voiceover error: boom", "Voiceovers worker 1": "TypeError: x"})

    assert result["success"] is False
    assert "Segment 3" in result["error"]
    assert "Voiceovers worker 1" in result["error"]
    assert events and events[0]["type"] == "error"
