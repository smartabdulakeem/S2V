import os
import shutil
import tempfile
import subprocess
import pytest
from pipeline.composer import compose_segment, _find_ffprobe, _find_ffmpeg

def test_compose_segment_duration_match():
    """
    Regression Test: Ensure composer output container duration matches input audio duration within 0.1s.
    Prevents silent fallback to static 5s renders.
    """
    audio_path = os.path.abspath("cache/2c39a59e/segment_1_audio.mp3")
    visual_path = os.path.abspath("cache/2c39a59e/segment_1_visual.jpg")
    srt_path = os.path.abspath("cache/2c39a59e/segment_1_captions.srt")

    assert os.path.exists(audio_path), "Test fixture audio file missing"
    assert os.path.exists(visual_path), "Test fixture visual file missing"

    ffprobe = _find_ffprobe()
    dur_cmd = [ffprobe, "-i", audio_path, "-show_entries", "format=duration", "-v", "quiet", "-of", "csv=p=0"]
    input_dur = float(subprocess.run(dur_cmd, capture_output=True, text=True, check=True).stdout.strip())
    assert input_dur > 10.0, f"Expected >10s audio duration, got {input_dur}"

    temp_cache = tempfile.mkdtemp()
    try:
        output_mp4 = compose_segment(
            segment_id=1,
            visual_path=visual_path,
            audio_path=audio_path,
            srt_path=srt_path,
            ken_burns="zoom_in",
            text_overlay=None,
            transition_in="cut",
            transition_out="cut",
            cache_dir=temp_cache,
            width=1280,
            height=720,
        )

        assert os.path.exists(output_mp4), "Composed MP4 file was not created"

        # Probe container duration
        out_dur_cmd = [ffprobe, "-i", output_mp4, "-show_entries", "format=duration", "-v", "quiet", "-of", "csv=p=0"]
        output_dur = float(subprocess.run(out_dur_cmd, capture_output=True, text=True, check=True).stdout.strip())

        # Probe video frame count
        out_frames_cmd = [ffprobe, "-i", output_mp4, "-select_streams", "v:0", "-show_entries", "stream=nb_frames", "-v", "quiet", "-of", "csv=p=0"]
        nb_frames = int(subprocess.run(out_frames_cmd, capture_output=True, text=True, check=True).stdout.strip())

        expected_frames = int(round(input_dur * 30))

        # Assert output duration matches audio duration within 0.1s
        assert abs(output_dur - input_dur) <= 0.1, f"Output duration {output_dur:.3f}s does not match input audio duration {input_dur:.3f}s within 0.1s"
        # Assert video frame count matches expected frames within 2 frames
        assert abs(nb_frames - expected_frames) <= 2, f"Output frame count {nb_frames} deviates from expected {expected_frames}"

    finally:
        shutil.rmtree(temp_cache, ignore_errors=True)
