"""Stage 2 — Voiceover generation using edge-tts (free, no API key, neural voices)."""

import asyncio
import os
from pathlib import Path


async def _generate_async(text: str, voice: str, rate: str, pitch: str, output_path: str):
    import edge_tts
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
    await communicate.save(output_path)


def generate_voiceover(
    segment_id: int,
    narration: str,
    voice: str,
    voice_rate: str,
    voice_pitch: str,
    cache_dir: str,
    on_progress=None,
) -> str:
    """
    Generate MP3 voiceover for a segment. Returns path to the MP3 file.
    Skips generation if file already exists (resume capability).
    """
    output_path = os.path.join(cache_dir, f"segment_{segment_id}_audio.mp3")

    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        if on_progress:
            on_progress(f"Segment {segment_id} — voiceover already cached, skipping")
        return output_path

    if on_progress:
        on_progress(f"Segment {segment_id} — generating voiceover ({voice})")

    Path(cache_dir).mkdir(parents=True, exist_ok=True)

    try:
        asyncio.run(_generate_async(narration, voice, voice_rate, voice_pitch, output_path))
    except RuntimeError:
        # asyncio.run() fails if there's already a running event loop (e.g. in Jupyter)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                _generate_async(narration, voice, voice_rate, voice_pitch, output_path)
            )
        finally:
            loop.close()

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError(f"Segment {segment_id}: voiceover file was not created. "
                           "Check your internet connection and try again.")

    return output_path


def get_audio_duration(mp3_path: str) -> float:
    """Return duration in seconds using moviepy (avoids needing mutagen/tinytag)."""
    from moviepy.editor import AudioFileClip
    with AudioFileClip(mp3_path) as clip:
        return clip.duration
