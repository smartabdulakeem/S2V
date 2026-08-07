import os
import shutil
import tempfile
import pytest
from pipeline.captions import (
    create_srt_from_tts_timings,
    generate_captions,
    parse_srt,
    get_whisper_load_count,
)

def test_google_tts_timings_captions_zero_whisper_calls():
    """
    Test creating captions directly from Google TTS SSML word timepoints.
    Asserts ZERO Whisper calls are made (whisper load count does not increase).
    """
    initial_whisper_loads = get_whisper_load_count()

    words = ["In", "762", "AD,", "Caliph", "Al-Mansur", "founded", "Baghdad."]
    timepoints = [
        {"markName": "w0", "timeSeconds": 0.0},
        {"markName": "w1", "timeSeconds": 0.25},
        {"markName": "w2", "timeSeconds": 0.60},
        {"markName": "w3", "timeSeconds": 1.10},
        {"markName": "w4", "timeSeconds": 1.50},
        {"markName": "w5", "timeSeconds": 2.10},
        {"markName": "w6", "timeSeconds": 2.60},
    ]

    with tempfile.TemporaryDirectory() as tmp_dir:
        srt_path = os.path.join(tmp_dir, "segment_101_captions.srt")
        out_path = create_srt_from_tts_timings(words, timepoints, srt_path)

        assert os.path.exists(out_path), "SRT file was not created"
        entries = parse_srt(out_path)
        assert len(entries) >= 1, "Expected at least 1 caption entry"

        # Now pass to generate_captions to simulate Stage C
        res_srt = generate_captions(101, "fake_audio.mp3", tmp_dir)
        assert res_srt == out_path

        # Assert zero Whisper loads occurred
        final_whisper_loads = get_whisper_load_count()
        assert final_whisper_loads == initial_whisper_loads, (
            f"Expected 0 new Whisper loads, but load count changed from "
            f"{initial_whisper_loads} to {final_whisper_loads}"
        )


def test_caption_timing_drift_comparison():
    """
    Compare SRT generated from TTS timepoints vs Whisper SRT on the same segment.
    Calculates drift between caption start/end times and asserts drift <= 0.5s.
    """
    words = ["The", "American", "Civil", "War", "began", "in", "1861."]
    timepoints = [
        {"markName": "w0", "timeSeconds": 0.0},
        {"markName": "w1", "timeSeconds": 0.20},
        {"markName": "w2", "timeSeconds": 0.70},
        {"markName": "w3", "timeSeconds": 1.10},
        {"markName": "w4", "timeSeconds": 1.45},
        {"markName": "w5", "timeSeconds": 1.85},
        {"markName": "w6", "timeSeconds": 2.00},
    ]

    with tempfile.TemporaryDirectory() as tmp_dir:
        tts_srt_path = os.path.join(tmp_dir, "tts_captions.srt")
        create_srt_from_tts_timings(words, timepoints, tts_srt_path)
        tts_entries = parse_srt(tts_srt_path)

        # Simulated Whisper transcription output for same sentence
        whisper_srt_path = os.path.join(tmp_dir, "whisper_captions.srt")
        with open(whisper_srt_path, "w", encoding="utf-8") as f:
            f.write("1\n00:00:00,050 --> 00:00:02,650\nThe American Civil War began in 1861.\n\n")

        whisper_entries = parse_srt(whisper_srt_path)

        assert len(tts_entries) > 0 and len(whisper_entries) > 0

        # Measure drift between TTS start time and Whisper start time
        start_drift = abs(tts_entries[0][0] - whisper_entries[0][0])
        end_drift = abs(tts_entries[0][1] - whisper_entries[0][1])

        print(f"\nCaption Start Drift: {start_drift:.3f}s, End Drift: {end_drift:.3f}s")

        assert start_drift <= 0.5, f"Start drift {start_drift:.3f}s exceeded 0.5s tolerance"
        assert end_drift <= 0.5, f"End drift {end_drift:.3f}s exceeded 0.5s tolerance"


def test_whisper_fallback_when_timings_unavailable():
    """Verify that generate_captions falls back to Whisper when no cached SRT or TTS timings exist."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        audio_path = os.path.abspath("cache/2c39a59e/segment_1_audio.mp3")
        assert os.path.exists(audio_path), "Test fixture audio missing"

        srt_path = generate_captions(999, audio_path, tmp_dir)

        assert os.path.exists(srt_path)
        entries = parse_srt(srt_path)
        assert len(entries) > 0, "Whisper fallback produced no SRT entries"
