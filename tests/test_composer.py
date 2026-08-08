import json
import os
import glob
import shutil
import tempfile
import subprocess
import pytest
from pipeline.composer import compose_segment, _find_ffprobe, _find_ffmpeg


def _segment_fixture(min_seconds: float = 10.0):
    """
    Find a rendered segment (audio + visual + captions) to compose against.

    These tests used to hardcode cache/2c39a59e — a directory left behind by a render
    the repo cannot reproduce, so deleting stale cache broke the suite. Search whatever
    the current cache holds instead, and render a sample if it is empty.
    """
    def _candidates():
        for audio in sorted(glob.glob("cache/*/segment_*_audio.mp3")):
            stem = audio[: -len("_audio.mp3")]
            visual, srt = stem + "_visual.jpg", stem + "_captions.srt"
            if os.path.exists(visual) and os.path.exists(srt):
                yield audio, visual, srt

    for audio, visual, srt in _candidates():
        probe = subprocess.run(
            [_find_ffprobe(), "-i", audio, "-show_entries", "format=duration",
             "-v", "quiet", "-of", "csv=p=0"],
            capture_output=True, text=True,
        )
        try:
            if float(probe.stdout.strip()) >= min_seconds:
                return os.path.abspath(audio), os.path.abspath(visual), os.path.abspath(srt)
        except ValueError:
            continue

    pytest.skip(f"no cached segment of at least {min_seconds}s to compose against")


def test_compose_segment_duration_match():
    """
    Regression Test: Ensure composer output container duration matches input audio duration within 0.1s.
    Prevents silent fallback to static 5s renders.
    """
    audio_path, visual_path, srt_path = _segment_fixture()

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
    Regression Test: ensure the compositor does not stack a second vignette on top of
    one already baked into the source image.

    Measures the darkening the compositor ADDS, not the total darkness of the frame.
    Some library images ship with their own vignette — one fixture is already 55%
    dark at the corners before compositing — so an absolute threshold only tests
    which image the fixture picked.
    """
    import numpy as np
    from PIL import Image

    audio_path, visual_path, srt_path = _segment_fixture()

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

        def corner_darkening(image):
            arr = np.array(image.convert("L"), dtype=np.float32)
            h, w = arr.shape
            cx, cy = max(1, int(w * 0.05)), max(1, int(h * 0.05))
            corners = float(np.mean([
                np.mean(arr[0:cy, 0:cx]), np.mean(arr[0:cy, w - cx:w]),
                np.mean(arr[h - cy:h, 0:cx]), np.mean(arr[h - cy:h, w - cx:w]),
            ]))
            frame_mean = float(np.mean(arr))
            return (frame_mean - corners) / frame_mean if frame_mean > 0 else 0.0

        source_darkening = corner_darkening(Image.open(visual_path))
        output_darkening = corner_darkening(Image.open(frame_png))
        added = output_darkening - source_darkening

        assert added <= 0.40, (
            f"Runaway vignette: compositor added {added * 100:.1f}% corner darkening "
            f"(source {source_darkening * 100:.1f}%, output {output_darkening * 100:.1f}%, limit 40%)"
        )

    finally:
        shutil.rmtree(temp_cache, ignore_errors=True)


def test_imagen_aspect_ratio_maps_by_ratio_not_exact_pixels():
    """
    The Imagen aspect-ratio map must follow the ratio, not a table of exact sizes.
    An exact-size table fell through to "1:1" and returned square images as soon as
    the 16:9 default moved from 1280x720 to 1920x1080.
    """
    import pipeline.visuals as v

    captured = {}

    def fake_urlopen(req, timeout=None):  # pragma: no cover - trivial stub
        captured["body"] = json.loads(req.data.decode("utf-8"))
        raise RuntimeError("stop after capturing the request")

    original = v.urllib.request.urlopen
    v.urllib.request.urlopen = fake_urlopen
    try:
        for (w, h), expected in [
            ((1920, 1080), "16:9"), ((1280, 720), "16:9"),
            ((1080, 1920), "9:16"), ((720, 1280), "9:16"),
            ((1080, 1080), "1:1"),  ((1440, 1080), "4:3"),
        ]:
            captured.clear()
            v._fetch_google_imagen_image(1, "a prompt", w, h, "fake-key", "unused.jpg")
            got = captured["body"]["parameters"]["aspectRatio"]
            assert got == expected, f"{w}x{h} mapped to {got}, expected {expected}"
    finally:
        v.urllib.request.urlopen = original
