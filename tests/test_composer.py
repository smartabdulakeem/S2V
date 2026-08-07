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


def test_composer_corner_brightness_vignette_check():
    """
    Regression Test: Ensure corners are not crushed by double vignette application.
    Samples corner pixel brightness from rendered video frame and fails if corners
    are more than 40% darker than frame mean brightness.
    """
    import numpy as np
    from PIL import Image

    audio_path = os.path.abspath("cache/2c39a59e/segment_1_audio.mp3")
    visual_path = os.path.abspath("cache/2c39a59e/segment_1_visual.jpg")
    srt_path = os.path.abspath("cache/2c39a59e/segment_1_captions.srt")

    ffmpeg = _find_ffmpeg()
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

        # Extract frame at t=7.0s
        frame_png = os.path.join(temp_cache, "frame_7s.png")
        cmd = [ffmpeg, "-ss", "7.0", "-i", output_mp4, "-vframes", "1", "-y", frame_png]
        subprocess.run(cmd, capture_output=True, check=True)

        img = Image.open(frame_png).convert("L")
        arr = np.array(img, dtype=np.float32)
        h, w = arr.shape
        frame_mean = float(np.mean(arr))

        cx, cy = int(w * 0.05), int(h * 0.05)
        tl = np.mean(arr[0:cy, 0:cx])
        tr = np.mean(arr[0:cy, w-cx:w])
        bl = np.mean(arr[h-cy:h, 0:cx])
        br = np.mean(arr[h-cy:h, w-cx:w])
        mean_corners = float((tl + tr + bl + br) / 4.0)

        darkening_ratio = (frame_mean - mean_corners) / frame_mean if frame_mean > 0 else 0
        assert darkening_ratio <= 0.40, f"Runaway vignette detected: corners are {darkening_ratio*100:.1f}% darker than frame mean (limit 40%)"

    finally:
        shutil.rmtree(temp_cache, ignore_errors=True)
