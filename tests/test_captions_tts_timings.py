import os
import json
import shutil
import tempfile
import subprocess
import pytest
from pipeline.captions import (
    create_srt_from_tts_timings,
    generate_captions,
    parse_srt,
    get_whisper_load_count,
)
from pipeline.voiceover import _generate_with_google_tts
from pipeline.composer import _find_ffprobe


import socket
import urllib.error


def _get_test_google_api_key() -> str:
    """Load Google TTS API key from config/settings.json if available."""
    settings_path = os.path.abspath("config/settings.json")
    if os.path.exists(settings_path):
        try:
            with open(settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("google_tts_api_key") or data.get("google_api_key") or ""
        except Exception:
            pass
    return ""


def _is_network_error(exc: Exception) -> bool:
    """Return True if exception is caused by network/DNS/connectivity failure."""
    if isinstance(exc, (urllib.error.URLError, socket.gaierror, TimeoutError, ConnectionError)):
        return True
    err_str = str(exc).lower()
    network_keywords = [
        "getaddrinfo failed",
        "name or service not known",
        "connection refused",
        "timed out",
        "network is unreachable",
        "socket.gaierror",
        "errno 11002"
    ]
    return any(kw in err_str for kw in network_keywords)


def test_google_tts_v1beta1_timepoints_and_zero_whisper_calls():
    """
    Live API Integration Test:
    Synthesizes a real segment using Google TTS v1beta1 (voice: google:en-US-Neural2-F),
    verifies non-empty timepoints are returned, prints them, and asserts that generating captions
    requires ZERO Whisper model loads.
    Skips cleanly if network/DNS is unreachable.
    """
    api_key = _get_test_google_api_key()
    if not api_key:
        pytest.skip("No Google API Key found in config/settings.json")

    initial_whisper_loads = get_whisper_load_count()
    narration = "In 762 AD, Caliph Al-Mansur founded Baghdad as the capital of the Abbasid Caliphate."

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_mp3 = os.path.join(tmp_dir, "segment_777_audio.mp3")
        srt_path = os.path.join(tmp_dir, "segment_777_captions.srt")

        # 1. Synthesize audio + generate SRT directly from Google TTS timepoints via v1beta1
        try:
            _generate_with_google_tts(
                narration=narration,
                voice="google:en-US-Neural2-F",
                voice_rate="+0%",
                voice_pitch="+0Hz",
                google_api_key=api_key,
                output_path=out_mp3,
                segment_id=777,
                cache_dir=tmp_dir,
            )
        except Exception as e:
            if _is_network_error(e):
                pytest.skip(f"Google TTS API unreachable (network/DNS failure): {e}")
            raise

        # 2. Verify Audio Output is sane
        assert os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 1000, "Generated MP3 audio is invalid"

        ffprobe = _find_ffprobe()
        dur_cmd = [ffprobe, "-i", out_mp3, "-show_entries", "format=duration", "-v", "quiet", "-of", "csv=p=0"]
        dur = float(subprocess.run(dur_cmd, capture_output=True, text=True, check=True).stdout.strip())
        assert dur > 2.0, f"Expected audio duration > 2.0s, got {dur:.2f}s"

        # 3. Verify SRT generated from TTS timepoints exists and print timepoints
        assert os.path.exists(srt_path), "SRT captions file was not generated from timepoints"
        tts_srt_entries = parse_srt(srt_path)
        assert len(tts_srt_entries) > 0, "TTS timepoint SRT contains no entries"

        print(f"\n[LIVE GOOGLE TTS TIMEPOINTS TEST]")
        print(f"Generated MP3 Duration: {dur:.3f}s")
        print(f"Generated SRT Path: {srt_path}")
        print(f"Parsed TTS Timepoint SRT Entries:")
        for idx, (st, et, txt) in enumerate(tts_srt_entries, 1):
            print(f"  [{idx}] {st:.3f}s --> {et:.3f}s : '{txt}'")

        # 4. Simulate Stage C Captions and prove ZERO Whisper calls
        res_srt = generate_captions(777, out_mp3, tmp_dir)
        assert res_srt == srt_path
        final_whisper_loads = get_whisper_load_count()
        assert final_whisper_loads == initial_whisper_loads, (
            f"Expected ZERO Whisper loads, but load count changed from {initial_whisper_loads} to {final_whisper_loads}"
        )


def test_real_measured_caption_timing_drift_vs_whisper():
    """
    Real Measurement Test:
    Synthesizes audio via Google TTS, generates SRT from timepoints, transcribes the SAME audio
    using Whisper, and measures actual timing drift between the two caption paths.
    """
    api_key = _get_test_google_api_key()
    if not api_key:
        pytest.skip("No Google API Key found in config/settings.json")

    narration = "The House of Wisdom in Baghdad became a global center of science and philosophy."

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_mp3 = os.path.join(tmp_dir, "segment_888_audio.mp3")
        tts_srt_path = os.path.join(tmp_dir, "segment_888_captions.srt")

        # 1. Synthesize audio with TTS timepoints SRT
        try:
            _generate_with_google_tts(
                narration=narration,
                voice="google:en-US-Neural2-F",
                voice_rate="+0%",
                voice_pitch="+0Hz",
                google_api_key=api_key,
                output_path=out_mp3,
                segment_id=888,
                cache_dir=tmp_dir,
            )
        except Exception as e:
            if _is_network_error(e):
                pytest.skip(f"Google TTS API unreachable (network/DNS failure): {e}")
            raise

        assert os.path.exists(tts_srt_path), "TTS SRT file missing"
        tts_entries = parse_srt(tts_srt_path)

        # 2. Force Whisper transcription on the SAME synthesized MP3 audio
        whisper_dir = os.path.join(tmp_dir, "whisper_cache")
        whisper_srt_path = generate_captions(888, out_mp3, whisper_dir)
        whisper_entries = parse_srt(whisper_srt_path)

        assert len(tts_entries) > 0, "TTS timepoint SRT empty"
        assert len(whisper_entries) > 0, "Whisper SRT empty"

        # 3. Calculate REAL measured start and end drift between timepoints and Whisper
        start_drift = abs(tts_entries[0][0] - whisper_entries[0][0])
        end_drift = abs(tts_entries[-1][1] - whisper_entries[-1][1])

        print(f"\n[REAL MEASURED CAPTION DRIFT REPORT]")
        print(f"TTS Timepoint Start: {tts_entries[0][0]:.3f}s, End: {tts_entries[-1][1]:.3f}s")
        print(f"Whisper Start:       {whisper_entries[0][0]:.3f}s, End: {whisper_entries[-1][1]:.3f}s")
        print(f"Measured Start Drift: {start_drift:.3f}s")
        print(f"Measured End Drift:   {end_drift:.3f}s")

        assert start_drift <= 1.0, f"Start drift {start_drift:.3f}s exceeded 1.0s tolerance"
        assert end_drift <= 1.0, f"End drift {end_drift:.3f}s exceeded 1.0s tolerance"


def test_whisper_fallback_when_timings_unavailable():
    """Verify that generate_captions falls back to Whisper when no cached SRT or TTS timings exist."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        audio_path = os.path.abspath("cache/2c39a59e/segment_1_audio.mp3")
        assert os.path.exists(audio_path), "Test fixture audio missing"

        srt_path = generate_captions(999, audio_path, tmp_dir)

        assert os.path.exists(srt_path)
        entries = parse_srt(srt_path)
        assert len(entries) > 0, "Whisper fallback produced no SRT entries"
