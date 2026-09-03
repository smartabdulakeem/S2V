"""
Stage 6 — Final video stitching via FFmpeg concat demuxer.
Optionally mixes background music (audio-only re-encode, video stream copied losslessly).
"""

import os
import subprocess
import tempfile
from pathlib import Path


from pipeline.ffmpeg_locate import find_ffmpeg


def build_music_filter(
    music_volume_db: float = -20,
    music_fade_in: float = 0.0,
    music_fade_out: float = 0.0,
    film_duration: float = 0.0,
) -> str:
    """Build the FFmpeg filter_complex string for background music mixing."""
    volume_factor = 10 ** (music_volume_db / 20)
    parts = [f"[2:a]volume={volume_factor:.4f}"]
    if music_fade_in and music_fade_in > 0:
        parts.append(f"afade=t=in:st=0:d={music_fade_in:.3f}")
    if music_fade_out and music_fade_out > 0 and film_duration > 0:
        fade_out_start = max(0.0, film_duration - music_fade_out)
        parts.append(f"afade=t=out:st={fade_out_start:.3f}:d={music_fade_out:.3f}")
    music_chain = ",".join(parts)
    return f"{music_chain}[music];[1:a][music]amix=inputs=2:duration=first:dropout_transition=3:normalize=0[aout]"


def stitch_segments(
    segment_paths: list[str],
    output_path: str,
    master_audio_path: str,
    background_music: str | None = None,
    music_volume_db: int = -20,
    music_fade_in: float = 0.0,
    music_fade_out: float = 0.0,
    on_progress=None,
) -> str:
    """
    Concatenate segment MP4s into a final video using FFmpeg concat demuxer.
    If background_music is set, mix it in with a second FFmpeg pass.
    Returns path to the final output file.
    """
    if on_progress:
        on_progress("Stitching segments into final video...")

    ffmpeg = find_ffmpeg()
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
                "-map", "0:v",
                "-map", "1:a",
                "-c:v", "copy",
                "-c:a", "aac",
                "-b:a", "192k",
                output_path
            ]
            _run_ffmpeg(cmd2, "add master audio")
        else:
            if on_progress:
                on_progress("Mixing background music...")

            film_duration = 0.0
            if music_fade_out and music_fade_out > 0:
                from pipeline.narration_timing import probe_seconds
                film_duration = probe_seconds(master_audio_path) or 0.0

            music_filter = build_music_filter(
                music_volume_db=music_volume_db,
                music_fade_in=music_fade_in,
                music_fade_out=music_fade_out,
                film_duration=film_duration,
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
                "-b:a", "192k",
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
