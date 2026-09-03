import os
import json
import shutil
import tempfile
import subprocess
import socket
import urllib.error
import pytest

from pipeline.captions import (
    create_srt_from_tts_timings,
    generate_captions,
    parse_srt,
    get_whisper_load_count,
)
from pipeline.voiceover import _generate_with_google_tts
from pipeline.ffmpeg_locate import find_ffprobe


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

        ffprobe = find_ffprobe()
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


def test_caption_timing_correctness_and_monotonicity():
    """
    Correctness Test:
    Synthesizes audio via Google TTS, generates SRT from timepoints, probes actual audio duration,
    and asserts:
    1. The last caption's end time matches audio duration within 0.15s tolerance.
    2. Caption entries are strictly monotonic and non-overlapping (start_i >= end_{i-1}).
    """
    api_key = _get_test_google_api_key()
    if not api_key:
        pytest.skip("No Google API Key found in config/settings.json")

    narration = "The House of Wisdom in Baghdad became a global center of science and philosophy."

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_mp3 = os.path.join(tmp_dir, "segment_888_audio.mp3")
        tts_srt_path = os.path.join(tmp_dir, "segment_888_captions.srt")

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
        assert len(tts_entries) > 0, "TTS timepoint SRT empty"

        # Probe exact audio duration
        ffprobe = find_ffprobe()
        dur_cmd = [ffprobe, "-i", out_mp3, "-show_entries", "format=duration", "-v", "quiet", "-of", "csv=p=0"]
        audio_dur = float(subprocess.run(dur_cmd, capture_output=True, text=True, check=True).stdout.strip())

        last_caption_end = tts_entries[-1][1]
        duration_diff = abs(last_caption_end - audio_dur)

        print(f"\n[CAPTION TIMING CORRECTNESS REPORT]")
        print(f"Probed Audio Duration:  {audio_dur:.3f}s")
        print(f"Final Caption End Time: {last_caption_end:.3f}s")
        print(f"Final Caption Duration Difference: {duration_diff:.3f}s")

        # 1. Assert last caption ends within 0.15s of audio duration
        assert duration_diff <= 0.15, (
            f"Final caption end time {last_caption_end:.3f}s differs from audio duration {audio_dur:.3f}s "
            f"by {duration_diff:.3f}s (exceeds 0.15s tolerance)"
        )

        # 2. Assert monotonicity and non-overlapping timestamps
        for i in range(len(tts_entries)):
            start_i, end_i, text_i = tts_entries[i]
            assert start_i < end_i, f"Caption {i+1} start ({start_i:.3f}s) must be < end ({end_i:.3f}s)"
            if i > 0:
                prev_end = tts_entries[i - 1][1]
                assert start_i >= prev_end - 0.001, (
                    f"Caption {i+1} start ({start_i:.3f}s) overlaps with caption {i} end ({prev_end:.3f}s)"
                )


def test_whisper_fallback_when_timings_unavailable():
    """Verify that generate_captions falls back to Whisper when no cached SRT or TTS timings exist."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        import glob
        candidates = sorted(glob.glob("cache/*/segment_*_audio.mp3"))
        if not candidates:
            pytest.skip("no cached narration audio to transcribe")
        audio_path = os.path.abspath(candidates[0])

        srt_path = generate_captions(999, audio_path, tmp_dir)

        assert os.path.exists(srt_path)
        entries = parse_srt(srt_path)
        assert len(entries) > 0, "Whisper fallback produced no SRT entries"


def test_concurrent_caption_workers_do_not_corrupt_whisper(tmp_path):
    """
    The Whisper model is a shared singleton; concurrent transcribe() calls on one
    instance corrupt each other. Fails (with a varying torch RuntimeError) if the
    transcribe lock is removed.
    """
    import glob
    from concurrent.futures import ThreadPoolExecutor
    from pipeline import captions as cap

    audio = sorted(glob.glob("cache/*/segment_*_audio.mp3"))[:3]
    if len(audio) < 2:
        pytest.skip("needs at least two cached narration clips")

    errors = []

    def transcribe(job):
        idx, path = job
        try:
            cap.generate_captions(idx, path, str(tmp_path))
        except Exception as exc:  # noqa: BLE001 — the point is to catch anything
            errors.append(f"segment {idx}: {type(exc).__name__}: {exc}")

    with ThreadPoolExecutor(max_workers=len(audio)) as pool:
        list(pool.map(transcribe, enumerate(audio, 1)))

    assert not errors, "concurrent transcription failed: " + "; ".join(errors)


def test_captions_use_the_real_narration_not_the_transcription():
    """
    Whisper mis-hears synthesised speech, and proper nouns go first: "the Caliph
    Al-Mansur founded" came back as "the Kayla Falmon surfounded". We know the exact
    words, so its timings are kept and the true narration is laid over them.
    """
    from pipeline.captions import _redistribute_narration

    narration = ("In the year 762, the Caliph Al-Mansur founded a city that would become "
                 "the beating heart of human civilisation.")
    misheard = [
        {"text": "In the year 762, the Kayla Falmon surfounded a city"},
        {"text": "that would become the beating heart of human civilization."},
    ]

    out = _redistribute_narration(narration, misheard)

    assert len(out) == len(misheard)
    rebuilt = " ".join(out)
    assert rebuilt == " ".join(narration.split()), "no word may be dropped or invented"
    assert "Al-Mansur" in rebuilt
    assert "Kayla Falmon" not in rebuilt
    assert all(chunk.strip() for chunk in out), "no caption line may be empty"


def test_captions_fall_back_to_transcription_without_narration():
    from pipeline.captions import _redistribute_narration
    misheard = [{"text": "whatever it heard"}]
    assert _redistribute_narration("", misheard) == ["whatever it heard"]


def test_captions_strip_ssml_before_laying_text_over_timings():
    from pipeline.captions import _redistribute_narration
    out = _redistribute_narration("<speak>Hello there<break time='400ms'/> friend</speak>",
                                  [{"text": "a b"}, {"text": "c"}])
    assert "<" not in " ".join(out) and "speak" not in " ".join(out)
    assert " ".join(out) == "Hello there friend"
