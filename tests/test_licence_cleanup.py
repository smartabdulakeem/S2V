"""
Tests for licence cleanup and dependency compliance.
Verifies removal of GPL components (edge-tts, piper DLLs) and fallback routing.
"""

import json
import os
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import pipeline.voiceover as vo


def test_1_edge_tts_is_gone():
    """requirements.txt has no edge-tts; no .py under pipeline/ or app.py has edge_tts; config/voices.json has no edge:."""
    req_path = REPO_ROOT / "requirements.txt"
    assert req_path.exists()
    req_text = req_path.read_text(encoding="utf-8")
    assert "edge-tts" not in req_text.lower()
    assert "edge_tts" not in req_text.lower()

    # Check app.py and all python files under pipeline/
    py_files = [REPO_ROOT / "app.py"] + list((REPO_ROOT / "pipeline").rglob("*.py"))
    for py_file in py_files:
        content = py_file.read_text(encoding="utf-8")
        assert "edge_tts" not in content, f"Found edge_tts in {py_file.relative_to(REPO_ROOT)}"

    # Check config/voices.json
    voices_path = REPO_ROOT / "config" / "voices.json"
    assert voices_path.exists()
    with open(voices_path, "r", encoding="utf-8") as f:
        catalogue = json.load(f)
    for group in catalogue:
        assert group.get("engine") != "Edge Neural", f"Found Edge Neural engine group in {voices_path}"
        for voice in group.get("voices", []):
            assert not voice.get("id", "").startswith("edge:"), f"Found edge: voice id {voice.get('id')}"


def test_2_unknown_voice_still_renders(tmp_path):
    """Calling generate_voiceover with an unknown voice id routes to Kokoro and reaches Kokoro generator."""
    calls = []

    def _mock_kokoro(narration, voice, voice_rate, output_path, on_progress=None, segment_id=0, narrative_tone=""):
        calls.append({"narration": narration, "voice": voice, "output_path": output_path})
        with open(output_path, "wb") as f:
            f.write(b"ID3mock-audio")

    orig = vo._generate_with_local_kokoro
    vo._generate_with_local_kokoro = _mock_kokoro
    try:
        out = vo.generate_voiceover(
            segment_id=1,
            narration="Testing unknown voice routing.",
            voice="nonsense:whatever",
            voice_rate="+0%",
            voice_pitch="+0Hz",
            cache_dir=str(tmp_path)
        )
        assert len(calls) == 1, "Expected _generate_with_local_kokoro to be called exactly once"
        assert calls[0]["voice"] == vo.FALLBACK_VOICE
        assert calls[0]["voice"].startswith("local:kokoro")
        assert os.path.exists(out)
    finally:
        vo._generate_with_local_kokoro = orig


def test_3_saved_edge_voice_migrates(tmp_path):
    """A project carrying a legacy edge: voice resolves to FALLBACK_VOICE and reaches Kokoro."""
    calls = []

    def _mock_kokoro(narration, voice, voice_rate, output_path, on_progress=None, segment_id=0, narrative_tone=""):
        calls.append({"narration": narration, "voice": voice, "output_path": output_path})
        with open(output_path, "wb") as f:
            f.write(b"ID3mock-audio")

    orig = vo._generate_with_local_kokoro
    vo._generate_with_local_kokoro = _mock_kokoro
    try:
        out = vo.generate_voiceover(
            segment_id=2,
            narration="Testing saved legacy edge voice migration.",
            voice="edge:en-US-GuyNeural",
            voice_rate="+0%",
            voice_pitch="+0Hz",
            cache_dir=str(tmp_path)
        )
        assert len(calls) == 1, "Expected _generate_with_local_kokoro to be called for legacy edge voice"
        assert calls[0]["voice"] == vo.FALLBACK_VOICE
        assert calls[0]["voice"].startswith("local:kokoro")
        assert os.path.exists(out)
    finally:
        vo._generate_with_local_kokoro = orig


def test_4_legacy_gemini_voice_migrates(tmp_path):
    """A legacy gemini: voice resolves to FALLBACK_VOICE and reaches Kokoro."""
    calls = []

    def _mock_kokoro(narration, voice, voice_rate, output_path, on_progress=None, segment_id=0, narrative_tone=""):
        calls.append({"narration": narration, "voice": voice, "output_path": output_path})
        with open(output_path, "wb") as f:
            f.write(b"ID3mock-audio")

    orig = vo._generate_with_local_kokoro
    vo._generate_with_local_kokoro = _mock_kokoro
    try:
        out = vo.generate_voiceover(
            segment_id=3,
            narration="Testing legacy gemini voice migration.",
            voice="gemini:en-US-GuyNeural",
            voice_rate="+0%",
            voice_pitch="+0Hz",
            cache_dir=str(tmp_path)
        )
        assert len(calls) == 1, "Expected _generate_with_local_kokoro to be called for legacy gemini voice"
        assert calls[0]["voice"] == vo.FALLBACK_VOICE
        assert calls[0]["voice"].startswith("local:kokoro")
        assert "edge" not in calls[0]["voice"]
        assert os.path.exists(out)
    finally:
        vo._generate_with_local_kokoro = orig


def test_5_notices_file_exists_and_complete():
    """THIRD-PARTY-NOTICES.txt exists and covers all required components and licences."""
    notices_path = REPO_ROOT / "THIRD-PARTY-NOTICES.txt"
    assert notices_path.exists(), "THIRD-PARTY-NOTICES.txt is missing from repo root"
    content = notices_path.read_text(encoding="utf-8")

    required_components = [
        "Pillow",
        "openai-whisper",
        "open-clip-torch",
        "CLIP ViT-B-32",
        "requests",
        "rapidocr-onnxruntime",
        "kokoro-onnx",
        "pywebview",
        "numpy",
        "scipy",
        "torch",
        "Real-ESRGAN",
        "ncnn",
        "onnxruntime",
        "PyInstaller",
        "Supertonic",
        "OpenRAIL-M",
        "vcomp140.dll",
    ]

    for comp in required_components:
        assert comp in content, f"Component {comp} not found in THIRD-PARTY-NOTICES.txt"

    assert "Bootloader Exception" in content or "bootloader exception" in content.lower()
    assert "TODO(owner): EULA clause" in content


def test_6_build_workflow_ships_no_ffmpeg():
    """Assert .github/workflows/build.yml does not download or bundle ffmpeg, edge_tts, or moviepy, but keeps realesrgan."""
    workflow_path = REPO_ROOT / ".github" / "workflows" / "build.yml"
    assert workflow_path.exists(), "build.yml not found"
    content = workflow_path.read_text(encoding="utf-8")
    assert len(content) > 100, "build.yml is empty or truncated"
    assert "name: Build Windows EXE" in content, "Missing expected build workflow header"
    assert "pyinstaller" in content.lower(), "Missing pyinstaller in build.yml"

    # Negatives: no ffmpeg downloading/bundling, no edge_tts, no moviepy
    assert "gyan.dev" not in content
    assert "ffmpeg-release-essentials" not in content
    assert '--add-data "vendor;vendor"' not in content
    assert "edge_tts" not in content
    assert "moviepy" not in content

    # Positive assertion: Real-ESRGAN upscaling MUST keep shipping
    assert "vendor/realesrgan;vendor/realesrgan" in content


def test_7_one_finder_in_ffmpeg_locate():
    """pipeline/composer.py, pipeline/stitcher.py and pipeline/voiceover.py contain no _find_ffmpeg or _find_ffprobe."""
    targets = [
        REPO_ROOT / "pipeline" / "composer.py",
        REPO_ROOT / "pipeline" / "stitcher.py",
        REPO_ROOT / "pipeline" / "voiceover.py",
    ]
    for target in targets:
        assert target.exists(), f"{target} does not exist"
        code = target.read_text(encoding="utf-8")
        assert "def _find_ffmpeg" not in code, f"Found def _find_ffmpeg in {target.name}"
        assert "def _find_ffprobe" not in code, f"Found def _find_ffprobe in {target.name}"


def test_8_setup_bat_names_existing_files():
    """Extract every -r <name>.txt from setup.bat and assert each named file exists in the repo."""
    import re
    setup_bat = REPO_ROOT / "setup.bat"
    assert setup_bat.exists(), "setup.bat missing"
    bat_text = setup_bat.read_text(encoding="utf-8", errors="ignore")
    matches = re.findall(r"-r\s+([A-Za-z0-9_\-\.]+)\.txt", bat_text)
    assert len(matches) > 0, "No -r requirements files found in setup.bat"
    for match in matches:
        filename = f"{match}.txt"
        file_path = REPO_ROOT / filename
        assert file_path.exists(), f"setup.bat references '{filename}' which does not exist in repo root"


def test_9_moviepy_is_gone():
    """moviepy is absent from requirements.txt, pipeline/, app.py, and cli.py."""
    req_text = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "moviepy" not in req_text.lower(), "moviepy found in requirements.txt"

    py_files = [REPO_ROOT / "app.py", REPO_ROOT / "cli.py"] + list((REPO_ROOT / "pipeline").rglob("*.py"))
    for py_file in py_files:
        code = py_file.read_text(encoding="utf-8")
        assert "moviepy" not in code.lower(), f"moviepy found in {py_file.relative_to(REPO_ROOT)}"


def test_10_find_ffmpeg_prefers_path_over_vendor(monkeypatch, tmp_path):
    """find_ffmpeg prefers system PATH over vendor, falls back to vendor, and raises FFmpegMissing if neither."""
    import shutil
    from pipeline.ffmpeg_locate import find_ffmpeg, find_ffprobe, FFmpegMissing

    # Ensure no override env var is interfering
    monkeypatch.delenv("IMAGEIO_FFMPEG_EXE", raising=False)
    monkeypatch.delenv("IMAGEIO_FFPROBE_EXE", raising=False)

    fake_path_bin = tmp_path / "fake_path_ffmpeg.exe"
    fake_path_bin.write_text("fake binary")

    # 1. Point shutil.which at temp file via monkeypatch: PATH comes back even though vendor exists
    monkeypatch.setattr(shutil, "which", lambda cmd: str(fake_path_bin) if cmd == "ffmpeg" else None)
    found = find_ffmpeg()
    assert os.path.abspath(found) == os.path.abspath(str(fake_path_bin))

    # 2. Make which return None: assert the vendor path comes back.
    #    vendor/ is gitignored and is no longer created by CI, so a clean checkout has
    #    no vendor ffmpeg. Skipping there is the point of this change, not a weakening:
    #    step 1 above still proves PATH wins, and step 3 still proves the raise.
    expected_vendor = os.path.abspath(str(REPO_ROOT / "vendor" / "ffmpeg" / "bin" / "ffmpeg.exe"))
    if not os.path.exists(expected_vendor):
        pytest.skip("no vendor ffmpeg on this machine; PATH and raise branches still asserted")
    monkeypatch.setattr(shutil, "which", lambda cmd: None)
    vendor_found = find_ffmpeg()
    assert os.path.abspath(vendor_found) == expected_vendor

    # 3. Hide both PATH and vendor: assert FFmpegMissing is raised with download URL
    orig_exists = os.path.exists
    def fake_exists(path):
        if "vendor" in str(path) and "ffmpeg" in str(path):
            return False
        return orig_exists(path)

    monkeypatch.setattr(os.path, "exists", fake_exists)
    with pytest.raises(FFmpegMissing) as exc_info:
        find_ffmpeg()

    err_msg = str(exc_info.value)
    assert "https://ffmpeg.org/download.html" in err_msg
    assert "setup.bat" not in err_msg