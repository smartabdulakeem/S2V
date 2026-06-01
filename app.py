"""
S2V — Script-to-Video Pipeline
Entry point: creates the PyWebView window and exposes the Python API to the frontend.
"""

import os
import sys
import json
import threading
import subprocess
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(BASE_DIR, "config", "settings.json")

# Add vendor ffmpeg to PATH so moviepy/ffmpeg can find it
_vendor_ffmpeg = os.path.join(BASE_DIR, "vendor", "ffmpeg", "bin")
if os.path.exists(_vendor_ffmpeg):
    os.environ["PATH"] = _vendor_ffmpeg + os.pathsep + os.environ.get("PATH", "")
    os.environ["IMAGEIO_FFMPEG_EXE"] = os.path.join(_vendor_ffmpeg, "ffmpeg.exe")


def _load_settings() -> dict:
    default = {
        "huggingface_api_key": "",
        "output_dir": "output",
        "cache_dir": "cache",
        "whisper_model": "base",
    }
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                stored = json.load(f)
            # Support migrating from old google_api_key settings if needed
            if "google_api_key" in stored and "huggingface_api_key" not in stored:
                stored["huggingface_api_key"] = ""
            # Clean up old/unused keys
            stored.pop("pixabay_api_key", None)
            stored.pop("google_api_key", None)
            default.update(stored)
        except Exception:
            pass
    return default


def _save_settings(settings: dict):
    Path(os.path.dirname(SETTINGS_PATH)).mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)


class Api:
    """All methods on this class are callable from JavaScript via window.pywebview.api.*"""

    def __init__(self):
        self._window = None  # Set via set_window() after webview.create_window()
        self._settings = _load_settings()
        self._orchestrator = None
        self._render_thread = None

    def set_window(self, window):
        self._window = window

    # ── Settings ──────────────────────────────────────────────────────────────

    def get_settings(self) -> dict:
        return dict(self._settings)

    def save_huggingface_key(self, key: str) -> dict:
        self._settings["huggingface_api_key"] = key.strip()
        _save_settings(self._settings)
        return {"success": True}

    # ── Script loading ─────────────────────────────────────────────────────────

    def open_file_dialog(self) -> str | None:
        """Open a native file picker and return the chosen path (or None)."""
        result = self._window.create_file_dialog(
            dialog_type=10,  # OPEN_DIALOG
            allow_multiple=False,
            file_types=("JSON Script (*.json)", "All files (*.*)")
        )
        if result and len(result) > 0:
            return result[0]
        return None

    def load_script(self, json_path: str) -> dict:
        """Validate and return summary info for the loaded script."""
        from pipeline.validator import validate_file, estimate_duration
        script, errors = validate_file(json_path)
        if errors:
            return {"success": False, "errors": errors}

        proj = script["project"]
        segments = script["segments"]
        est = estimate_duration(script)

        return {
            "success": True,
            "title": proj.get("title", "Untitled"),
            "segment_count": len(segments),
            "estimated_duration": est,
            "voice": proj.get("voice", ""),
            "output_filename": proj.get("output_filename", ""),
            "aspect_ratio": proj.get("aspect_ratio", "16:9"),
            "path": json_path,
            "script_data": script
        }

    def preview_voice(self, voice_id: str) -> dict:
        """Generate a short audio sample for the chosen voice and return it as base64."""
        import base64
        import tempfile
        from pipeline.voiceover import generate_voiceover

        sample_text = (
            "Welcome. This is a preview of the selected voice. "
            "You are listening to the narration quality."
        )

        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                tmp_path = f.name

            hf_key = self._settings.get("huggingface_api_key", "")
            
            # Generate voiceover using the unified cloud TTS module
            generate_voiceover(
                segment_id=0,
                narration=sample_text,
                voice=voice_id,
                voice_rate="+0%",
                voice_pitch="+0Hz",
                cache_dir=os.path.dirname(tmp_path),
                huggingface_api_key=hf_key,
            )

            # Look for the generated output segment
            generated_file = os.path.join(os.path.dirname(tmp_path), "segment_0_audio.mp3")
            
            with open(generated_file, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode("utf-8")

            # Clean up
            try:
                os.unlink(generated_file)
                os.unlink(tmp_path)
            except OSError:
                pass

            return {"success": True, "audio_b64": audio_b64}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def parse_plain_text(self, text: str, title: str, voice: str, output_filename: str, visual_style: str = "", aspect_ratio: str = "16:9") -> dict:
        """
        Start plain-text parsing using the AI storyboard planner in a background thread.
        Returns immediately with {"started": True}.
        Result is delivered to JS via window.onParseComplete(result).
        """
        import base64

        def _push(result: dict):
            payload = base64.b64encode(
                json.dumps(result, ensure_ascii=False).encode("utf-8")
            ).decode("ascii")
            try:
                self._window.evaluate_js(
                    f"window.onParseComplete(JSON.parse(atob('{payload}')))"
                )
            except Exception:
                pass

        def _run():
            try:
                import tempfile
                from pipeline.ai_agent import generate_storyboard_plan

                hf_token = self._settings.get("huggingface_api_key", "")

                res = generate_storyboard_plan(
                    text=text,
                    title=title,
                    voice=voice,
                    output_filename=output_filename,
                    visual_style=visual_style,
                    hf_token=hf_token
                )

                if not res.get("success"):
                    _push({"success": False, "errors": [res.get("error_msg", "Failed to plan storyboard")]})
                    return

                script_dict = res["script"]
                script_dict["project"]["aspect_ratio"] = aspect_ratio

                # Save the planned script to a temporary file
                tmp = tempfile.NamedTemporaryFile(
                    mode="w", suffix=".json", delete=False, encoding="utf-8"
                )
                json.dump(script_dict, tmp, ensure_ascii=False, indent=2)
                tmp.close()

                segs = script_dict["segments"]

                _push({
                    "success": True,
                    "path": tmp.name,
                    "title": script_dict["project"]["title"],
                    "segment_count": len(segs),
                    "estimated_duration": round(res["estimated_duration"]),
                    "estimated_render_time": res["estimated_render_time"],
                    "voice": script_dict["project"]["voice"],
                    "output_filename": script_dict["project"]["output_filename"],
                    "aspect_ratio": aspect_ratio,
                    "fallback": res.get("fallback", False),
                    "script_data": script_dict
                })
            except Exception as e:
                _push({"success": False, "errors": [f"Internal planning error: {type(e).__name__}: {e}"]})

        threading.Thread(target=_run, daemon=True).start()
        return {"started": True}

    def save_edited_script(self, path: str, script_data: dict) -> dict:
        """Save edited storyboard script from frontend back to JSON file."""
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(script_data, f, ensure_ascii=False, indent=2)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Rendering ──────────────────────────────────────────────────────────────

    def start_render(self, script_path: str) -> dict:
        """Start the render pipeline in a background thread."""
        if self._render_thread and self._render_thread.is_alive():
            return {"success": False, "error": "A render is already in progress."}

        hf_key = self._settings.get("huggingface_api_key", "")

        from pipeline.orchestrator import RenderOrchestrator

        def on_event(event: dict):
            import base64
            payload = base64.b64encode(
                json.dumps(event, ensure_ascii=False).encode("utf-8")
            ).decode("ascii")
            try:
                self._window.evaluate_js(
                    f"window.onPipelineEvent("
                    f"JSON.parse(atob('{payload}')))"
                )
            except Exception:
                pass

        self._orchestrator = RenderOrchestrator(
            base_dir=BASE_DIR,
            on_event=on_event,
        )

        def run():
            self._orchestrator.render(script_path, hf_key)

        self._render_thread = threading.Thread(target=run, daemon=True)
        self._render_thread.start()

        on_event({"type": "log", "message": "Render started — loading pipeline modules…"})

        return {"success": True}

    def cancel_render(self) -> dict:
        if self._orchestrator:
            self._orchestrator.cancel()
        return {"success": True}

    # ── Utilities ──────────────────────────────────────────────────────────────

    def open_output_folder(self, output_path: str | None = None) -> dict:
        folder = os.path.dirname(output_path) if output_path else os.path.join(BASE_DIR, "output")
        if os.path.exists(folder):
            subprocess.Popen(["explorer", os.path.normpath(folder)])
        return {"success": True}

    def get_version(self) -> str:
        return "2.0.0"


# ── Window bootstrap ───────────────────────────────────────────────────────────

def main():
    import webview

    vendor_ffmpeg = os.path.join(BASE_DIR, "vendor", "ffmpeg", "bin", "ffmpeg.exe")
    if not os.path.exists(vendor_ffmpeg):
        import shutil
        if not shutil.which("ffmpeg"):
            print(
                "\n⚠️  FFmpeg was not found.\n"
                "Please run setup.bat first to install all required components.\n"
            )
            input("Press Enter to close...")
            sys.exit(1)

    api = Api()

    window = webview.create_window(
        title="S2V — Script-to-Video Pipeline v2.0",
        url=os.path.join(BASE_DIR, "frontend", "index.html"),
        js_api=api,
        width=1000,
        height=900,
        min_size=(900, 750),
        resizable=True,
    )

    api.set_window(window)

    webview.start(debug=False, gui='edgechromium')


if __name__ == "__main__":
    main()
