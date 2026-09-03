# pipeline/ffmpeg_locate.py
"""
Central resolver for ffmpeg and ffprobe binaries.

Search order:
1. Explicit environment overrides (IMAGEIO_FFMPEG_EXE / IMAGEIO_FFPROBE_EXE)
2. System PATH (shutil.which) -- what shipped builds find on user machines
3. vendor/ffmpeg/bin/ -- development convenience only for local repository dev
4. Raise FFmpegMissing with helpful guidance and download link
"""

import os
import shutil


class FFmpegMissing(RuntimeError):
    """ffmpeg or ffprobe could not be found on this machine."""
    pass


_FFMPEG_MESSAGE = (
    "FFmpeg is not installed on this computer. Smart Studio needs it to build video and to measure "
    "narration. Install it from https://ffmpeg.org/download.html, make sure it is on your PATH, then "
    "restart Smart Studio."
)


def find_ffmpeg() -> str:
    """Absolute path to an ffmpeg binary. Raises FFmpegMissing if there is none."""
    # 1. Explicit override
    override = os.environ.get("IMAGEIO_FFMPEG_EXE", "")
    if override and os.path.exists(override):
        return os.path.abspath(override)

    # 2. System PATH
    found = shutil.which("ffmpeg")
    if found:
        return os.path.abspath(found)

    # 3. Development vendor path
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    vendor_ffmpeg = os.path.join(base_dir, "vendor", "ffmpeg", "bin", "ffmpeg.exe")
    if os.path.exists(vendor_ffmpeg):
        return os.path.abspath(vendor_ffmpeg)

    # 4. Raise FFmpegMissing
    raise FFmpegMissing(_FFMPEG_MESSAGE)


def find_ffprobe() -> str:
    """Absolute path to an ffprobe binary. Raises FFmpegMissing if there is none."""
    # 1. Explicit override
    override = os.environ.get("IMAGEIO_FFPROBE_EXE", "")
    if override and os.path.exists(override):
        return os.path.abspath(override)

    # 2. System PATH
    found = shutil.which("ffprobe")
    if found:
        return os.path.abspath(found)

    # 3. Development vendor path
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    vendor_ffprobe = os.path.join(base_dir, "vendor", "ffmpeg", "bin", "ffprobe.exe")
    if os.path.exists(vendor_ffprobe):
        return os.path.abspath(vendor_ffprobe)

    # 4. Raise FFmpegMissing
    raise FFmpegMissing(_FFMPEG_MESSAGE)
