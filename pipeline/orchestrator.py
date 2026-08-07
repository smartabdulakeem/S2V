"""
Orchestrator — coordinates all pipeline stages for a full render.
Emits structured progress events consumed by the GUI.
"""

import os
import json
import logging
import traceback
import uuid
from datetime import datetime
from pathlib import Path

from pipeline.validator import validate_file
from pipeline.voiceover import generate_voiceover, stitch_master_audio
from pipeline.captions import generate_captions
from pipeline.visuals import fetch_visual, _get_dimensions
from pipeline.composer import compose_segment
from pipeline.stitcher import stitch_segments


def _setup_logger(logs_dir: str) -> logging.Logger:
    Path(logs_dir).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(logs_dir, f"render_{timestamp}.log")
    logger = logging.getLogger(f"s2v_{timestamp}")
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(fh)
    return logger


class RenderOrchestrator:
    def __init__(self, base_dir: str, on_event=None):
        """
        base_dir: root of the S2V project folder
        on_event: callable(event_dict) — receives structured progress events
        """
        self.base_dir = base_dir
        self.on_event = on_event or (lambda e: None)
        self.cache_dir = os.path.join(base_dir, "cache")
        self.output_dir = os.path.join(base_dir, "output")
        self.logs_dir = os.path.join(base_dir, "logs")
        self.logger = None
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def _emit(self, event_type: str, **kwargs):
        event = {"type": event_type, **kwargs}
        if self.logger:
            self.logger.info(json.dumps(event))
        self.on_event(event)

    def _progress(self, stage: str, segment_idx: int, total: int, message: str):
        self._emit(
            "progress",
            stage=stage,
            segment=segment_idx,
            total_segments=total,
            message=message,
        )

    def _log(self, message: str):
        self._emit("log", message=message)
        if self.logger:
            self.logger.info(message)

    def render(self, script_path: str, google_api_key: str = "", google_tts_api_key: str = "") -> dict:
        """
        Run the full render pipeline.
        Returns {"success": True, "output": path} or {"success": False, "error": message}
        """
        self._cancelled = False
        self.logger = _setup_logger(self.logs_dir)

        # Unique ID for this render — ensures fresh AI images every run
        render_id = uuid.uuid4().hex

        # ── Stage 1: Validate ──────────────────────────────────────────────────
        self._emit("stage", name="Validating script", stage_num=1, total_stages=7)
        script, errors = validate_file(script_path)
        if errors:
            error_text = "Script validation failed:\n" + "\n".join(errors)
            self._emit("error", message=error_text)
            return {"success": False, "error": error_text}

        proj = script["project"]
        segments = script["segments"]
        total = len(segments)
        video_title  = proj.get("title", "")
        visual_style = proj.get("visual_style", "")
        disable_captions = proj.get("disable_captions", False)
        aspect_ratio = proj.get("aspect_ratio", "16:9")
        if aspect_ratio not in ("16:9", "9:16", "1:1", "4:3"):
            aspect_ratio = "16:9"

        width, height = _get_dimensions(aspect_ratio)

        # Shift cache to a project-specific directory to prevent cache collisions
        import hashlib
        proj_hash = hashlib.md5(video_title.encode("utf-8")).hexdigest()[:8]
        self.cache_dir = os.path.join(self.base_dir, "cache", proj_hash)


        self._log(f"Loaded script: {proj['title']} — {total} segments")
        self._log(f"Aspect Ratio: {aspect_ratio} ({width}x{height})")
        if visual_style:
            self._log(f"Visual style: {visual_style}")
        google_tts_key = google_tts_api_key if google_tts_api_key else google_api_key
        if google_api_key:
            self._log("Google API integrations enabled for scripts and visuals (Google Imagen)")
        if google_tts_key:
            self._log("Google Cloud TTS integration enabled for voiceovers")

        Path(self.cache_dir).mkdir(parents=True, exist_ok=True)
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

        # ── Stages 2–5: Per-segment processing ────────────────────────────────
        segment_paths = []

        for idx, seg in enumerate(segments, 1):
            if self._cancelled:
                return {"success": False, "error": "Render cancelled by user."}

            seg_id = seg["segment_id"]

            def progress(msg, _idx=idx, _total=total):
                self._progress("processing", _idx, _total, msg)
                self._log(msg)

            try:
                # Fast path: check if segment final video is already cached
                seg_video = os.path.join(self.cache_dir, f"segment_{seg_id}_final.mp4")
                if os.path.exists(seg_video) and os.path.getsize(seg_video) > 0:
                    self._progress("processing", idx, total, f"Segment {seg_id} already cached, skipping all stages")
                    self._log(f"Segment {seg_id} complete (loaded from cache): {seg_video}")
                    segment_paths.append(seg_video)
                    continue

                # Stage 2 — Voiceover
                self._emit("stage", name=f"Voiceover — segment {idx}/{total}", stage_num=2, total_stages=7)
                seg_voice = seg.get("voice", proj["voice"])
                if "gemini-3.1-flash-tts" in seg_voice.lower():
                    voice_key = google_api_key
                else:
                    voice_key = google_tts_key

                audio_path = generate_voiceover(
                    segment_id=seg_id,
                    narration=seg["narration"],
                    voice=seg_voice,
                    voice_rate=seg.get("voice_rate", proj.get("voice_rate", "+0%")),
                    voice_pitch=seg.get("voice_pitch", proj.get("voice_pitch", "+0Hz")),
                    cache_dir=self.cache_dir,
                    google_api_key=voice_key,
                    on_progress=progress,
                    voice_steering=seg.get("voice_steering", "")
                )

                if self._cancelled:
                    return {"success": False, "error": "Render cancelled by user."}

                # Stage 3 — Captions
                if disable_captions:
                    self._progress("processing", idx, total, f"Segment {seg_id} — Captions disabled, skipping Whisper")
                    srt_path = None
                else:
                    self._emit("stage", name=f"Captions — segment {idx}/{total}", stage_num=3, total_stages=7)
                    srt_path = generate_captions(
                        segment_id=seg_id,
                        audio_path=audio_path,
                        cache_dir=self.cache_dir,
                        on_progress=progress,
                    )

                if self._cancelled:
                    return {"success": False, "error": "Render cancelled by user."}

                # Stage 4 — Visual
                self._emit("stage", name=f"Visuals — segment {idx}/{total}", stage_num=4, total_stages=7)
                visual_path = fetch_visual(
                    segment_id=seg_id,
                    keyword=seg["b_roll_keyword"],
                    narration=seg.get("narration", ""),
                    cache_dir=self.cache_dir,
                    google_api_key=google_api_key,
                    aspect_ratio=aspect_ratio,
                    render_id=render_id,
                    video_title=video_title,
                    visual_style=visual_style,
                    on_progress=progress,
                    visual_type=seg.get("visual_type", "ai_image"),
                    magick_filter=seg.get("magick_filter", "vignette"),
                    use_base_image=seg.get("use_base_image"),
                    use_base_image_a=seg.get("use_base_image_a"),
                    use_base_image_b=seg.get("use_base_image_b"),
                    character_bible=proj.get("character_bible"),
                    level1_overlay=seg.get("level1_overlay"),
                    crop=seg.get("crop"),
                )

                if self._cancelled:
                    return {"success": False, "error": "Render cancelled by user."}

                # Stage 5 — Compose
                self._emit("stage", name=f"Composing — segment {idx}/{total}", stage_num=5, total_stages=7)
                seg_video = compose_segment(
                    segment_id=seg_id,
                    visual_path=visual_path,
                    audio_path=audio_path,
                    srt_path=srt_path,
                    ken_burns=seg.get("ken_burns", "none"),
                    text_overlay=seg.get("text_overlay"),
                    transition_in=seg.get("transition_in", "cut"),
                    transition_out=seg.get("transition_out", "cut"),
                    cache_dir=self.cache_dir,
                    width=width,
                    height=height,
                    on_progress=progress,
                    sfx=seg.get("sfx"),
                    level1_overlay=seg.get("level1_overlay"),
                    segment_dict=seg,
                )
                segment_paths.append(seg_video)
                self._log(f"Segment {seg_id} complete: {seg_video}")

            except Exception as e:
                tb = traceback.format_exc()
                self.logger.error(tb)
                error_msg = (
                    f"Render failed at segment {seg_id}.\n\n"
                    f"Error: {e}\n\n"
                    f"Check the log file in the logs/ folder for full details."
                )
                self._emit("error", message=error_msg)
                return {"success": False, "error": error_msg}

        # ── Stage 6: Stitch ────────────────────────────────────────────────────
        self._emit("stage", name="Stitching final video", stage_num=6, total_stages=7)
        output_filename = proj.get("output_filename", "output.mp4")
        output_path = os.path.join(self.output_dir, output_filename)

        try:
            segment_audio_paths = [os.path.join(self.cache_dir, f"segment_{seg['segment_id']}_audio.mp3") for seg in segments]
            master_audio_path = os.path.join(self.cache_dir, "master_narration.mp3")
            stitch_master_audio(segment_audio_paths, master_audio_path)

            stitch_segments(
                segment_paths=segment_paths,
                output_path=output_path,
                master_audio_path=master_audio_path,
                background_music=proj.get("background_music"),
                music_volume_db=proj.get("music_volume_db", -20),
                on_progress=lambda msg: self._log(msg),
            )
        except Exception as e:
            tb = traceback.format_exc()
            self.logger.error(tb)
            error_msg = f"Failed to stitch final video.\n\nError: {e}"
            self._emit("error", message=error_msg)
            return {"success": False, "error": error_msg}

        # ── Stage 7: Done ──────────────────────────────────────────────────────
        self._emit("stage", name="Complete", stage_num=7, total_stages=7)
        self._emit("complete", output_path=output_path)
        return {"success": True, "output": output_path}
