"""
Orchestrator — coordinates all pipeline stages for a full render.
Uses parallel ThreadPoolExecutors across stages A-E with thread-safe limits,
Whisper singleton loading, cancellation checks, completed-count progress, and partial failure tracking.
"""

import os
import glob
import json
import logging
import traceback
import uuid
import threading
from datetime import datetime
from pathlib import Path
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

from pipeline.validator import validate_file
from pipeline.voiceover import generate_voiceover, stitch_master_audio
from pipeline.captions import generate_captions
from pipeline.library import project_world_anchor
from pipeline.visuals import fetch_visual, _get_dimensions, segment_keyword, segment_pin
from pipeline.composer import compose_segment, _find_ffprobe
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


def _load_concurrency_settings(base_dir: str) -> dict:
    defaults = {
        "max_tts_workers": 4,
        "max_visual_workers": 4,
        "max_caption_workers": 2,
        "max_compose_workers": 3,
    }
    settings_file = os.path.join(base_dir, "config", "settings.json")
    if os.path.exists(settings_file):
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for k in defaults:
                    if k in data and isinstance(data[k], int) and data[k] > 0:
                        defaults[k] = data[k]
        except Exception:
            pass
    return defaults


def _load_auto_generate(base_dir: str) -> bool:
    """
    When true, a library gap is filled by generating the image instead of failing
    the render. Google Imagen is used when a key is present; otherwise it falls
    back to Pollinations, which needs no key and costs nothing.

    Defaults to False so a render stops and hands you the composed prompt — the
    right behaviour when you would rather make the image yourself and grow the
    library than accept whatever a generator returns.
    """
    settings_file = os.path.join(base_dir, "config", "settings.json")
    if os.path.exists(settings_file):
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                return bool(json.load(f).get("auto_generate_missing_images", False))
        except Exception:
            pass
    return False


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
        self._lock = threading.Lock()

    def cancel(self):
        self._cancelled = True

    def _emit(self, event_type: str, **kwargs):
        event = {"type": event_type, **kwargs}
        if self.logger:
            self.logger.info(json.dumps(event))
        self.on_event(event)

    def _progress(self, stage: str, completed: int, total: int, message: str):
        self._emit(
            "progress",
            stage=stage,
            completed=completed,
            total=total,
            message=message,
        )

    def _log(self, message: str):
        self._emit("log", message=message)
        if self.logger:
            self.logger.info(message)

    #: Intermediate artefacts, safe to delete once the final film exists.
    INTERMEDIATE_PATTERNS = (
        "shot_*.mp4", "shot_*_*.jpg",
        "segment_*_final.mp4", "segment_*_visual_concat.mp4", "segment_*_shots.txt",
        "segment_*_mixed_audio.wav", "static_ov_*.png",
    )

    def _cleanup_intermediates(self) -> int:
        """
        Delete this render's intermediates, keeping narration and captions.

        Narration MP3s and SRTs stay: they are the expensive part to recreate and
        are what makes a re-render seconds rather than minutes. Video
        intermediates are cheap to rebuild and are what actually fills the disk.
        Controlled by config/settings.json → clean_cache_after_render.
        """
        settings_file = os.path.join(self.base_dir, "config", "settings.json")
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                if not json.load(f).get("clean_cache_after_render", True):
                    return 0
        except Exception:
            pass

        removed, freed = 0, 0
        for pattern in self.INTERMEDIATE_PATTERNS:
            for path in glob.glob(os.path.join(self.cache_dir, pattern)):
                try:
                    freed += os.path.getsize(path)
                    os.remove(path)
                    removed += 1
                except OSError:
                    pass
        if removed:
            self._log(f"Cleaned {removed} intermediate files ({freed / (1024*1024):.0f} MB); "
                      f"narration and captions kept for fast re-renders")
        return removed

    def _drain(self, futures, executor, stage_name: str, errors_map: dict) -> bool:
        """
        Wait for a stage's workers, surfacing anything they raised.

        as_completed() on its own silently discards worker exceptions: a raise
        outside a worker's own try/except is stored on the Future and lost unless
        result() is called. That is how fourteen failed voiceovers produced a
        five-millisecond stage with no log lines, and a KeyError two stages later
        that killed the render thread without a word.

        Returns True if the render was cancelled.
        """
        for f in as_completed(futures):
            if self._cancelled:
                executor.shutdown(wait=False, cancel_futures=True)
                return True
            try:
                f.result()
            except Exception as e:
                key = f"{stage_name} worker {len(errors_map) + 1}"
                errors_map[key] = f"{type(e).__name__}: {e}"
                self._log(f"{stage_name} worker raised {type(e).__name__}: {e}")
        return False

    def render(self, script_path: str, google_api_key: str = "", google_tts_api_key: str = "") -> dict:
        """
        Run the full render pipeline with parallel stages A through F.
        Returns {"success": True, "output": path} or {"success": False, "error": message}
        """
        if self._cancelled:
            return {"success": False, "error": "Render cancelled by user."}

        self.logger = _setup_logger(self.logs_dir)
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

        # Library images used by this render. Committed to the usage counter only
        # when the render completes — a cancelled or failed render records nothing.
        used_library_paths = set()
        video_title = proj.get("title", "")
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

        # Load concurrency settings
        concurrency = _load_concurrency_settings(self.base_dir)
        auto_generate = _load_auto_generate(self.base_dir)

        self._log(f"Loaded script: {proj['title']} — {total} segments")
        self._log(f"Aspect Ratio: {aspect_ratio} ({width}x{height})")
        self._log(f"Parallel limits: TTS={concurrency['max_tts_workers']}, Visuals={concurrency['max_visual_workers']}, Captions={concurrency['max_caption_workers']}, Compose={concurrency['max_compose_workers']}")

        google_tts_key = google_tts_api_key if google_tts_api_key else google_api_key
        if google_api_key:
            self._log("Google API integrations enabled for scripts and visuals (Google Imagen)")
        if google_tts_key:
            self._log("Google Cloud TTS integration enabled for voiceovers")

        Path(self.cache_dir).mkdir(parents=True, exist_ok=True)
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

        audio_paths_map = {}
        durations_map = {}
        srt_paths_map = {}
        visual_paths_map = {}
        segment_videos_map = {}
        errors_map = {}

        # ── STAGE A: Voiceovers (Stage 2/7) ──────────────────────────────────
        self._emit("stage", name="Voiceovers (Parallel)", stage_num=2, total_stages=7)
        completed_tts = 0

        def run_tts(idx, seg):
            nonlocal completed_tts
            if self._cancelled:
                return
            seg_id = seg["segment_id"]
            # The planner writes an explicit "voice": null on every segment, and
            # dict.get(key, default) returns that stored None rather than the
            # default — the key exists. `or` is what actually falls back here.
            seg_voice = seg.get("voice") or proj.get("voice") or ""
            voice_key = google_api_key if "gemini-3.1-flash-tts" in seg_voice.lower() else google_tts_key

            def progress_cb(msg):
                self._log(f"[Segment {seg_id} TTS] {msg}")

            try:
                path = generate_voiceover(
                    segment_id=seg_id,
                    narration=seg["narration"],
                    voice=seg_voice,
                    voice_rate=seg.get("voice_rate") or proj.get("voice_rate") or "+0%",
                    voice_pitch=seg.get("voice_pitch") or proj.get("voice_pitch") or "+0Hz",
                    cache_dir=self.cache_dir,
                    google_api_key=voice_key,
                    on_progress=progress_cb,
                    voice_steering=seg.get("voice_steering", ""),
                    narrative_tone=proj.get("narrative_tone", "")
                )
                with self._lock:
                    audio_paths_map[seg_id] = path
                    completed_tts += 1
                    self._progress("Voiceovers", completed_tts, total, f"Completed voiceover {completed_tts}/{total}")
            except Exception as e:
                with self._lock:
                    errors_map[seg_id] = f"Voiceover error: {e}"

        with ThreadPoolExecutor(max_workers=concurrency["max_tts_workers"]) as executor:
            futures = [executor.submit(run_tts, idx, seg) for idx, seg in enumerate(segments, 1)]
            if self._drain(futures, executor, "Voiceovers", errors_map):
                return {"success": False, "error": "Render cancelled by user."}

        if self._cancelled:
            return {"success": False, "error": "Render cancelled by user."}

        # Check errors before STAGE B
        if errors_map:
            return self._fail_render(errors_map)

        # ── STAGE B: Build Timeline in One Pass (Stage 3/7) ───────────────────
        self._emit("stage", name="Building Timeline", stage_num=3, total_stages=7)
        ffprobe_bin = _find_ffprobe()
        total_audio_duration = 0.0

        for seg in segments:
            seg_id = seg["segment_id"]
            audio_path = audio_paths_map[seg_id]
            cmd = [ffprobe_bin, "-i", audio_path, "-show_entries", "format=duration", "-v", "quiet", "-of", "csv=p=0"]
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0 or not res.stdout.strip():
                errors_map[seg_id] = f"ffprobe audio duration probe failed for {audio_path}: {res.stderr}"
                continue
            try:
                dur = float(res.stdout.strip())
                durations_map[seg_id] = dur
                total_audio_duration += dur
            except ValueError:
                errors_map[seg_id] = f"ffprobe returned invalid duration for {audio_path}: {res.stdout.strip()}"

        if errors_map:
            return self._fail_render(errors_map)

        self._log(f"Timeline constructed: total narration duration = {total_audio_duration:.2f}s across {total} segments")

        # ── STAGE C: Captions for ALL Segments (Stage 4/7) ────────────────────
        self._emit("stage", name="Captions (Parallel)", stage_num=4, total_stages=7)
        completed_cap = 0

        captions_cfg = proj.get("captions", {})
        disable_captions = proj.get("disable_captions", False) or not captions_cfg.get("enabled", True)
        captions_source = captions_cfg.get("source", "tts_timings")

        if disable_captions or captions_source == "none":
            for seg in segments:
                srt_paths_map[seg["segment_id"]] = None
            self._log("Captions disabled in project settings (or source='none'), skipping captions")
        else:
            def run_cap(idx, seg):
                nonlocal completed_cap
                if self._cancelled:
                    return
                seg_id = seg["segment_id"]
                audio_path = audio_paths_map[seg_id]

                def progress_cb(msg):
                    self._log(f"[Segment {seg_id} Captions] {msg}")

                try:
                    srt_path = generate_captions(
                        segment_id=seg_id,
                        audio_path=audio_path,
                        cache_dir=self.cache_dir,
                        narration=seg.get("narration", ""),
                        on_progress=progress_cb,
                    )
                    with self._lock:
                        srt_paths_map[seg_id] = srt_path
                        completed_cap += 1
                        self._progress("Captions", completed_cap, total, f"Completed captions {completed_cap}/{total}")
                except Exception as e:
                    with self._lock:
                        errors_map[seg_id] = f"Captions error: {e}"

            with ThreadPoolExecutor(max_workers=concurrency["max_caption_workers"]) as executor:
                futures = [executor.submit(run_cap, idx, seg) for idx, seg in enumerate(segments, 1)]
                if self._drain(futures, executor, "Captions", errors_map):
                    return {"success": False, "error": "Render cancelled by user."}

        if self._cancelled:
            return {"success": False, "error": "Render cancelled by user."}

        if errors_map:
            return self._fail_render(errors_map)

        # ── STAGE D: Fetch/Resolve ALL Visuals (Stage 5/7) ───────────────────
        self._emit("stage", name="Visuals (Parallel)", stage_num=5, total_stages=7)
        completed_vis = 0

        def run_vis(idx, seg):
            nonlocal completed_vis
            if self._cancelled:
                return
            seg_id = seg["segment_id"]

            def progress_cb(msg):
                self._log(f"[Segment {seg_id} Visuals] {msg}")

            def library_hit_cb(lib_path):
                with self._lock:
                    used_library_paths.add(lib_path)

            try:
                vis_path = fetch_visual(
                    segment_id=seg_id,
                    keyword=segment_keyword(seg),
                    narration=seg.get("narration", ""),
                    cache_dir=self.cache_dir,
                    google_api_key=google_api_key,
                    aspect_ratio=aspect_ratio,
                    render_id=render_id,
                    video_title=video_title,
                    visual_style=visual_style,
                    on_progress=progress_cb,
                    visual_type=seg.get("visual_type", "ai_image"),
                    magick_filter=seg.get("magick_filter", "none"),
                    use_base_image=segment_pin(seg),
                    use_base_image_a=seg.get("use_base_image_a"),
                    use_base_image_b=seg.get("use_base_image_b"),
                    character_bible=proj.get("character_bible"),
                    level1_overlay=seg.get("level1_overlay"),
                    crop=seg.get("crop"),
                    series_slug=proj.get("series_slug"),
                    auto_generate=auto_generate,
                    on_library_hit=library_hit_cb,
                    # The project's chosen look. Named style_preset here because
                    # visual_type above already means the image SOURCE.
                    style_preset=proj.get("visual_type", ""),
                    project_brief=proj.get("project_brief", ""),
                    world_anchor=project_world_anchor(proj),
                    work_folder=(proj.get("image_folder") or "").strip() or None,
                    visual_description=(seg.get("shots") and seg["shots"][0].get("visual_description")) or seg.get("visual_description"),
                    prompt_override=(seg.get("shots") and seg["shots"][0].get("prompt_override")) or seg.get("prompt_override"),
                    apply_era=proj.get("apply_era", True),
                )
                with self._lock:
                    visual_paths_map[seg_id] = vis_path
                    completed_vis += 1
                    self._progress("Visuals", completed_vis, total, f"Completed visuals {completed_vis}/{total}")
            except Exception as e:
                with self._lock:
                    errors_map[seg_id] = f"Visuals error: {e}"

        with ThreadPoolExecutor(max_workers=concurrency["max_visual_workers"]) as executor:
            futures = [executor.submit(run_vis, idx, seg) for idx, seg in enumerate(segments, 1)]
            if self._drain(futures, executor, "Visuals", errors_map):
                return {"success": False, "error": "Render cancelled by user."}

        if self._cancelled:
            return {"success": False, "error": "Render cancelled by user."}

        if errors_map:
            return self._fail_render(errors_map)

        # ── STAGE E: Compose ALL Segments (Stage 6/7) ─────────────────────────
        self._emit("stage", name="Composing (Parallel)", stage_num=6, total_stages=7)
        completed_comp = 0

        def run_comp(idx, seg):
            nonlocal completed_comp
            if self._cancelled:
                return
            seg_id = seg["segment_id"]

            def progress_cb(msg):
                self._log(f"[Segment {seg_id} Compose] {msg}")

            try:
                seg_video = compose_segment(
                    segment_id=seg_id,
                    visual_path=visual_paths_map[seg_id],
                    audio_path=audio_paths_map[seg_id],
                    srt_path=srt_paths_map[seg_id],
                    ken_burns=seg.get("ken_burns", "none"),
                    text_overlay=seg.get("text_overlay"),
                    transition_in=seg.get("transition_in", "cut"),
                    transition_out=seg.get("transition_out", "cut"),
                    cache_dir=self.cache_dir,
                    width=width,
                    height=height,
                    on_progress=progress_cb,
                    sfx=seg.get("sfx"),
                    level1_overlay=seg.get("level1_overlay"),
                    segment_dict=seg,
                    visual_style=visual_style,
                    visual_type=proj.get("visual_type", ""),
                    series_slug=proj.get("series_slug"),
                    motion_style=proj.get("motion_style"),
                )
                with self._lock:
                    segment_videos_map[seg_id] = seg_video
                    completed_comp += 1
                    self._progress("Composing", completed_comp, total, f"Completed composing {completed_comp}/{total}")
            except Exception as e:
                with self._lock:
                    errors_map[seg_id] = f"Compose error: {e}"

        with ThreadPoolExecutor(max_workers=concurrency["max_compose_workers"]) as executor:
            futures = [executor.submit(run_comp, idx, seg) for idx, seg in enumerate(segments, 1)]
            if self._drain(futures, executor, "Composing", errors_map):
                return {"success": False, "error": "Render cancelled by user."}

        if self._cancelled:
            return {"success": False, "error": "Render cancelled by user."}

        if errors_map:
            return self._fail_render(errors_map)

        # ── STAGE F: Stitch Final Video (Stage 7/7) ───────────────────────────
        self._emit("stage", name="Stitching final video", stage_num=7, total_stages=7)
        output_filename = proj.get("output_filename", "output.mp4")
        output_path = os.path.join(self.output_dir, output_filename)

        # Ensure strict segment ordering matching script
        segment_paths = [segment_videos_map[seg["segment_id"]] for seg in segments]

        try:
            segment_audio_paths = [audio_paths_map[seg["segment_id"]] for seg in segments]
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

        # Render completed — now, and only now, commit library usage.
        # Once per image per render: used_library_paths is a set.
        if used_library_paths:
            from pipeline import library
            for lib_path in sorted(used_library_paths):
                try:
                    library.record_render_usage(lib_path)
                except Exception as e:
                    self._log(f"Could not record library usage for {lib_path}: {e}")

        # Intermediates are worth keeping only while a render might resume. Once
        # the film exists they are dead weight — 1,970 MB had accumulated across
        # 1,811 files by the second real episode.
        self._cleanup_intermediates()

        # Write WolfCut timeline project (.wolfcut)
        wolfcut_path = None
        try:
            from pipeline.wolfcut_export import write_wolfcut_project
            wolfcut_path = write_wolfcut_project(
                script_data=self.script_data,
                audio_paths_map=audio_paths_map,
                durations_map=durations_map,
                project_dir=self.output_dir
            )
            self._log(f"Exported WolfCut project timeline: {wolfcut_path}")
        except Exception as e:
            self._log(f"Warning: WolfCut project export failed: {e}")

        # Done
        self._emit("complete", output_path=output_path, wolfcut_path=wolfcut_path)
        return {"success": True, "output": output_path, "wolfcut_path": wolfcut_path}

    def _fail_render(self, errors_map: dict) -> dict:
        # Keys are segment ids (int) for handled failures and stage labels (str)
        # for worker crashes, so sort on the text form rather than the raw key.
        details = "\n".join(
            f" - Segment {sid}: {err}"
            for sid, err in sorted(errors_map.items(), key=lambda kv: str(kv[0]))
        )
        error_msg = f"Render failed due to errors in {len(errors_map)} segment(s):\n{details}"
        self._emit("error", message=error_msg)
        return {"success": False, "error": error_msg}
