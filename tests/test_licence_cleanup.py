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
        "moviepy",
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