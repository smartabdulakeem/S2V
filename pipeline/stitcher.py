"""
Stage 6 — Final video stitching via FFmpeg concat demuxer.
Optionally mixes background music (audio-only re-encode, video stream copied losslessly).
"""

import os
import subprocess
import tempfile
from pathlib import Path


def _find_ffmpeg() -> str:
    """Return path to ffmpeg binary. Prefers vendor copy, falls back to system PATH."""
    vendor_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "vendor", "ffmpeg", "bin", "ffmpeg.exe"
    )
    if os.path.exists(vendor_path):
        return vendor_path

    # Try system PATH
    import shutil
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    raise FileNotFoundError(
        "FFmpeg was not found. Please run setup.bat first to install it automatically."
    )


def stitch_segments(
    segment_paths: list[str],
    output_path: str,
    master_audio_path: str,
    background_music: str | None = None,
    music_volume_db: int = -20,
    on_progress=None,
) -> str:
    """
    Concatenate segment MP4s into a final video using FFmpeg concat demuxer.
    If background_music is set, mix it in with a second FFmpeg pass.
    Returns path to the final output file.
    """
    if on_progress:
        on_progress("Stitching segments into final video...")

    ffmpeg = _find_ffmpeg()
    Path(os.path.dirname(output_path)).mkdir(parents=True, exist_ok=True)

    # Write the concat list file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        concat_file = f.name
        for path in segment_paths:
            # FFmpeg requires forward slashes and escaped special chars
            safe_path = path.replace("\\", "/")
            f.write(f"file '{safe_path}'\n")

    try:
        temp_video = output_path.replace(".mp4", "_novideo.mp4")
        # Step 1: concat video only
        cmd1 = [
            ffmpeg, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-an",
            "-c:v", "copy",
            temp_video
        ]
        _run_ffmpeg(cmd1, "concat video")

        # Step 2: add master audio (and optionally background music)
        if not background_music:
            cmd2 = [
                ffmpeg, "-y",
                "-i", temp_video,
                "-i", master_audio_path,
                "-c:v", "copy",
                "-c:a", "aac",
                output_path
            ]
            _run_ffmpeg(cmd2, "add master audio")
        else:
            if on_progress:
                on_progress("Mixing background music...")

            volume_factor = 10 ** (music_volume_db / 20)
            music_filter = (
                f"[1:a][2:a]amix=inputs=2:duration=first:dropout_transition=3"
                f",volume={volume_factor:.4f}[aout]"
            )
            cmd2 = [
                ffmpeg, "-y",
                "-i", temp_video,
                "-i", master_audio_path,
                "-stream_loop", "-1",
                "-i", background_music,
                "-filter_complex", music_filter,
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "copy",
                "-c:a", "aac",
                "-shortest",
                output_path
            ]
            _run_ffmpeg(cmd2, "music mix")

        if os.path.exists(temp_video):
            os.remove(temp_video)

    finally:
        if os.path.exists(concat_file):
            os.remove(concat_file)

    if on_progress:
        on_progress(f"Success: Final video saved: {output_path}")

    return output_path


def _run_ffmpeg(cmd: list[str], stage_name: str):
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg failed during {stage_name}.\n"
            f"Error details:\n{result.stderr[-2000:]}"
        )
