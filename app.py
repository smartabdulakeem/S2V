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
    # Tell moviepy explicitly where ffmpeg is
    os.environ["IMAGEIO_FFMPEG_EXE"] = os.path.join(_vendor_ffmpeg, "ffmpeg.exe")


def _load_settings() -> dict:
    default = {
        "pixabay_api_key": "",
        "output_dir": "output",
        "cache_dir": "cache",
        "whisper_model": "base",
    }
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                stored = json.load(f)
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
        return self._settings

    def save_pixabay_key(self, key: str) -> dict:
        self._settings["pixabay_api_key"] = key.strip()
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
            "path": json_path,
        }

    def preview_voice(self, voice_id: str) -> dict:
        """Generate a short audio sample for the chosen voice and return it as base64."""
        import base64
        import tempfile
        import asyncio
        import edge_tts

        sample_text = (
            "Welcome. This is a preview of the selected voice. "
            "You are listening to the voice that will narrate your video."
        )

        async def _gen(path):
            communicate = edge_tts.Communicate(sample_text, voice_id)
            await communicate.save(path)

        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                tmp_path = f.name

            loop = asyncio.new_event_loop()
            loop.run_until_complete(_gen(tmp_path))
            loop.close()

            with open(tmp_path, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode("utf-8")

            os.unlink(tmp_path)
            return {"success": True, "audio_b64": audio_b64}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def parse_plain_text(self, text: str, title: str, voice: str, output_filename: str) -> dict:
        """
        Start plain-text parsing in a background thread.
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
                from pipeline.text_parser import build_script
                from pipeline.validator import validate_script, estimate_duration

                try:
                    script = build_script(text, title, voice, output_filename)
                except ValueError as e:
                    _push({"success": False, "errors": [str(e)]})
                    return

                errors = validate_script(script)
                if errors:
                    _push({"success": False, "errors": errors})
                    return

                tmp = tempfile.NamedTemporaryFile(
                    mode="w", suffix=".json", delete=False, encoding="utf-8"
                )
                json.dump(script, tmp, ensure_ascii=False, indent=2)
                tmp.close()

                est = estimate_duration(script)
                segs = script["segments"]

                _push({
                    "success": True,
                    "path": tmp.name,
                    "title": script["project"]["title"],
                    "segment_count": len(segs),
                    "estimated_duration": round(est),
                    "voice": script["project"]["voice"],
                    "output_filename": script["project"]["output_filename"],
                    "keywords": [s["b_roll_keyword"] for s in segs],
                })
            except Exception as e:
                _push({"success": False, "errors": [f"Internal error: {type(e).__name__}: {e}"]})

        threading.Thread(target=_run, daemon=True).start()
        return {"started": True}

    # ── Rendering ──────────────────────────────────────────────────────────────

    def start_render(self, script_path: str) -> dict:
        """Start the render pipeline in a background thread."""
        if self._render_thread and self._render_thread.is_alive():
            return {"success": False, "error": "A render is already in progress."}

        pexels_key = self._settings.get("pixabay_api_key", "")

        from pipeline.orchestrator import RenderOrchestrator

        def on_event(event: dict):
            # Push event to the JavaScript frontend.
            # Use JSON.parse with a base64-encoded payload to avoid any
            # backslash / quote escaping issues with Windows paths.
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
                pass  # never crash the render thread on a UI update failure

        self._orchestrator = RenderOrchestrator(
            base_dir=BASE_DIR,
            on_event=on_event,
        )

        def run():
            self._orchestrator.render(script_path, pexels_key)

        self._render_thread = threading.Thread(target=run, daemon=True)
        self._render_thread.start()

        # Send an immediate confirmation so the UI knows the render started
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
        return "1.0.0"


# ── Window bootstrap ───────────────────────────────────────────────────────────

def main():
    import webview

    # Check FFmpeg is available before starting
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
        title="S2V — Script-to-Video Pipeline",
        url=os.path.join(BASE_DIR, "frontend", "index.html"),
        js_api=api,
        width=960,
        height=860,
        min_size=(820, 700),
        resizable=True,
    )

    api.set_window(window)

    webview.start(debug=False)


if __name__ == "__main__":
    main()
