"""
Smart Studio — Script to Video
Entry point: creates the PyWebView window and exposes the Python API to the frontend.
"""

import os
import sys
import json
import threading
import subprocess
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Child processes must not flash a console window over the UI (pythonw launch).
from pipeline.noconsole import install as _install_noconsole
_install_noconsole()

SETTINGS_PATH = os.path.join(BASE_DIR, "config", "settings.json")

# Put vendor ffmpeg on PATH for child processes if present, without overriding system PATH
_vendor_ffmpeg = os.path.join(BASE_DIR, "vendor", "ffmpeg", "bin")
if os.path.exists(_vendor_ffmpeg):
    import shutil
    if not shutil.which("ffmpeg"):
        os.environ["PATH"] = _vendor_ffmpeg + os.pathsep + os.environ.get("PATH", "")
    elif _vendor_ffmpeg not in os.environ.get("PATH", ""):
        os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + _vendor_ffmpeg


def _load_settings() -> dict:
    default = {
        "google_api_key": "",
        "google_tts_api_key": "",
        "deepseek_api_key": "",
        "output_dir": "output",
        "cache_dir": "cache",
        "whisper_model": "base",
        "ai_shot_descriptions": False,
    }
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                stored = json.load(f)
            # Clean up old/unused keys
            stored.pop("pixabay_api_key", None)
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

    def check_ffmpeg(self) -> dict:
        """Report whether ffmpeg and ffprobe are available, with paths or plain-English guidance."""
        from pipeline.ffmpeg_locate import find_ffmpeg, find_ffprobe, FFmpegMissing, _FFMPEG_MESSAGE

        ffmpeg_path = None
        ffprobe_path = None
        ffmpeg_error = None
        ffprobe_error = None

        try:
            ffmpeg_path = find_ffmpeg()
        except FFmpegMissing as e:
            ffmpeg_error = str(e)
        except Exception as e:
            ffmpeg_error = str(e)

        try:
            ffprobe_path = find_ffprobe()
        except FFmpegMissing as e:
            ffprobe_error = str(e)
        except Exception as e:
            ffprobe_error = str(e)

        available = bool(ffmpeg_path and ffprobe_path)
        message = None
        if not available:
            message = ffmpeg_error or ffprobe_error or _FFMPEG_MESSAGE

        return {
            "available": available,
            "ffmpeg_path": ffmpeg_path,
            "ffprobe_path": ffprobe_path,
            "message": message,
            "download_url": "https://ffmpeg.org/download.html",
        }

    # ── Settings ──────────────────────────────────────────────────────────────

    #: Never leaves the backend. The page is local today, but a key handed to the
    #: front end is a key in the DOM, in any devtools session, and in any future
    #: web build. The UI only ever needs to know whether a key is present.
    SECRET_SETTING_KEYS = (
        "google_api_key", "google_tts_api_key", "deepseek_api_key",
        "anthropic_api_key", "openai_api_key", "elevenlabs_api_key",
    )

    def get_settings(self) -> dict:
        """Settings for the UI, with secrets reduced to a set/not-set flag."""
        safe = {k: v for k, v in self._settings.items() if k not in self.SECRET_SETTING_KEYS}
        for key in self.SECRET_SETTING_KEYS:
            key_val = str(self._settings.get(key, "")).strip()
            safe[f"{key}_set"] = bool(key_val)
            safe[f"{key}_len"] = len(key_val) if key_val else 0

        safe.setdefault("prompt_writer_mode", self._settings.get("prompt_writer_mode", "auto"))
        safe.setdefault("prompt_writer_providers", self._settings.get("prompt_writer_providers", {
            "anthropic": {"enabled": bool(self._settings.get("anthropic_api_key")), "model": "claude-sonnet-5"},
            "openai": {"enabled": bool(self._settings.get("openai_api_key")), "model": "gpt-4o"},
            "gemini": {"enabled": True, "model": "gemini-2.5-flash"},
            "deepseek": {"enabled": False, "model": "deepseek-chat"},
        }))
        safe.setdefault("llm_planning_enabled", self._settings.get("llm_planning_enabled", False))
        return safe

    def save_ai_shot_descriptions(self, enabled: bool) -> dict:
        self._settings["ai_shot_descriptions"] = bool(enabled)
        _save_settings(self._settings)
        return {"success": True}

    def save_llm_planning_enabled(self, enabled: bool) -> dict:
        self._settings["llm_planning_enabled"] = bool(enabled)
        _save_settings(self._settings)
        return {"success": True}

    def save_prompt_writer_settings(self, settings_data: dict) -> dict:
        if isinstance(settings_data, dict):
            if "prompt_writer_mode" in settings_data:
                self._settings["prompt_writer_mode"] = str(settings_data["prompt_writer_mode"]).strip().lower()
            if "prompt_writer_providers" in settings_data and isinstance(settings_data["prompt_writer_providers"], dict):
                self._settings["prompt_writer_providers"] = settings_data["prompt_writer_providers"]
            _save_settings(self._settings)
        return {"success": True}

    def save_google_key(self, key: str) -> dict:
        self._settings["google_api_key"] = key.strip()
        _save_settings(self._settings)
        return {"success": True}

    def save_google_tts_key(self, key: str) -> dict:
        self._settings["google_tts_api_key"] = key.strip()
        _save_settings(self._settings)
        return {"success": True}

    def save_deepseek_key(self, key: str) -> dict:
        self._settings["deepseek_api_key"] = key.strip()
        _save_settings(self._settings)
        return {"success": True}

    def save_anthropic_key(self, key: str) -> dict:
        self._settings["anthropic_api_key"] = key.strip()
        _save_settings(self._settings)
        return {"success": True}

    def save_openai_key(self, key: str) -> dict:
        self._settings["openai_api_key"] = key.strip()
        _save_settings(self._settings)
        return {"success": True}

    #: Which settings key each provider name in the UI writes to.
    PROVIDER_KEY_NAMES = {
        "gemini": "google_api_key",
        "google": "google_api_key",
        "google_tts": "google_tts_api_key",
        "anthropic": "anthropic_api_key",
        "openai": "openai_api_key",
        "deepseek": "deepseek_api_key",
        "elevenlabs": "elevenlabs_api_key",
    }

    def remove_api_key(self, provider: str) -> dict:
        """
        Delete a stored key, deliberately and by name.

        Clearing the field and pressing Test did nothing: the save is guarded by
        `if (keyVal)`, so an emptied box was read as "no change". That guard is
        correct and must stay — `get_settings` never sends real keys to the
        browser, so every field is blank on load and an always-save would wipe a
        working key on the first Test of any other provider. Removing a key is a
        different intention from saving one and needs to be said out loud.
        """
        name = self.PROVIDER_KEY_NAMES.get((provider or "").strip().lower())
        if not name:
            return {"success": False, "error": f"There is no key called {provider!r}."}
        had = bool((self._settings.get(name) or "").strip())
        self._settings[name] = ""
        _save_settings(self._settings)
        return {"success": True, "removed": had, "provider": provider}

    def test_llm_provider(self, provider: str, model: str = "", key: str = "") -> dict:
        from pipeline.llm.factory import test_provider
        prov = (provider or "").strip().lower()
        key_to_use = key.strip() if key and key.strip() else (
            self._settings.get(f"{prov}_api_key") or
            (self._settings.get("google_api_key") if prov in ("gemini", "google") else "")
        )
        return test_provider(provider_name=prov, model=model if model else None, api_key=key_to_use)

    def get_provider_status(self) -> dict:
        from pipeline.llm.factory import get_last_provider_status
        return get_last_provider_status()

    def save_elevenlabs_key(self, key: str) -> dict:
        """Optional — only set by users who choose to pay for ElevenLabs."""
        self._settings["elevenlabs_api_key"] = key.strip()
        _save_settings(self._settings)
        return {"success": True}

    def get_series_packs(self) -> list:
        """Return all available series packs in config/series/ and user-created niches in config/series_overrides/."""
        packs = []
        seen_slugs = set()
        series_dir = os.path.join(BASE_DIR, "config", "series")
        if os.path.exists(series_dir):
            for f in sorted(os.listdir(series_dir)):
                if f.endswith(".json"):
                    fp = os.path.join(series_dir, f)
                    try:
                        with open(fp, "r", encoding="utf-8") as file:
                            data = json.load(file)
                            slug = data.get("series_slug") or f[:-5]
                            name = data.get("display_name") or slug.replace("_", " ").title()
                            packs.append({"series_slug": slug, "display_name": name, "file": f, "is_user_created": False})
                            seen_slugs.add(slug)
                    except Exception:
                        pass

        override_dir = os.path.join(BASE_DIR, "config", "series_overrides")
        if os.path.exists(override_dir):
            for f in sorted(os.listdir(override_dir)):
                if f.endswith(".json"):
                    slug_name = f[:-5]
                    if slug_name not in seen_slugs:
                        fp = os.path.join(override_dir, f)
                        try:
                            with open(fp, "r", encoding="utf-8") as file:
                                data = json.load(file)
                                slug = data.get("series_slug") or slug_name
                                name = data.get("display_name") or slug.replace("_", " ").title()
                                packs.append({"series_slug": slug, "display_name": name, "file": f, "is_user_created": True})
                                seen_slugs.add(slug)
                        except Exception:
                            pass
        return packs

    def get_niche_style(self, series_slug: str = None) -> dict:
        """Return merged niche configuration and override status for the Settings editor."""
        try:
            from pipeline.library import get_series_config, get_series_override, style_presets_for, SERIES_CONFIG_DIR
            cfg = get_series_config(series_slug=series_slug)
            overrides = get_series_override(series_slug=series_slug)
            slug = cfg.get("series_slug", series_slug or "default")
            is_user_created = not os.path.exists(os.path.join(SERIES_CONFIG_DIR, f"{slug}.json"))
            presets_list = []
            for key, entry in style_presets_for(cfg).items():
                if isinstance(entry, str):
                    prompt = entry
                    treatment = "none"
                    label = self.STYLE_LABEL_OVERRIDES.get(key, key.replace("_", " ").title())
                elif isinstance(entry, dict):
                    prompt = entry.get("prompt", "")
                    treatment = entry.get("treatment") or "none"
                    label = entry.get("label") or self.STYLE_LABEL_OVERRIDES.get(key, key.replace("_", " ").title())
                else:
                    continue
                presets_list.append({
                    "key": key,
                    "label": label,
                    "prompt": prompt,
                    "treatment": treatment,
                })

            return {
                "success": True,
                "series_slug": slug,
                "display_name": cfg.get("display_name", ""),
                "era_block": cfg.get("era_block", ""),
                "negative_block": cfg.get("negative_block", ""),
                "style_block": cfg.get("style_block", ""),
                "prompt_recipe": cfg.get("prompt_recipe", ""),
                "style_presets": presets_list,
                "is_overridden": bool(overrides) or is_user_created,
                "is_user_created": is_user_created,
                "overrides": overrides,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def create_user_niche(self, series_slug: str, display_name: str, base_slug: str = "default") -> dict:
        """Create a new user-defined niche seeded from default.json."""
        try:
            from pipeline.library import create_user_niche
            return create_user_niche(series_slug=series_slug, display_name=display_name, base_slug=base_slug)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_user_niche(self, series_slug: str) -> dict:
        """Delete a user-defined niche from config/series_overrides/."""
        try:
            from pipeline.library import delete_user_niche
            return delete_user_niche(series_slug=series_slug)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def apply_external_prompts(self, script_data: dict, pasted_text: str, folder: str = None) -> dict:
        """Apply pasted external prompts and match images from working folder by number."""
        try:
            from pipeline.library import apply_external_prompts
            return apply_external_prompts(script_data=script_data, pasted_text=pasted_text, folder=folder)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def save_niche_style(self, series_slug: str, overrides: dict) -> dict:
        """Save per-niche overrides in config/series_overrides/<slug>.json."""
        try:
            from pipeline.library import save_series_override
            return save_series_override(series_slug=series_slug, overrides=overrides)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def reset_niche_style(self, series_slug: str) -> dict:
        """Reset a niche to default by deleting its override file."""
        try:
            from pipeline.library import reset_series_override
            return reset_series_override(series_slug=series_slug)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def preview_niche_prompt(self, series_slug: str, visual_type: str = None, visual_type_prompt: str = None,
                             era_block: str = None, negative_block: str = None,
                             shot_query: str = "A citadel at dawn", apply_era: bool = True) -> dict:
        """Generate a live prompt preview using visual type prompt and era."""
        try:
            from pipeline.library import get_series_config, resolve_style_preset, style_presets_for
            cfg = get_series_config(series_slug=series_slug)

            medium = ""
            if visual_type_prompt and visual_type_prompt.strip():
                medium = visual_type_prompt.strip()
            elif visual_type:
                preset = resolve_style_preset(cfg, visual_type)
                if preset:
                    medium = preset.get("prompt", "")
            if not medium:
                all_p = style_presets_for(cfg)
                if all_p:
                    first_k = next(iter(all_p))
                    preset = resolve_style_preset(cfg, first_k)
                    if preset:
                        medium = preset.get("prompt", "")

            era = era_block if era_block is not None else cfg.get("era_block", "")
            era = era.strip() if (apply_era and era) else ""

            parts = [shot_query, "wide establishing shot"]
            if medium:
                parts.append(medium.rstrip(" ."))
            if era and era.lower() not in ", ".join(parts).lower():
                parts.append(era.rstrip(" ."))
            preview_text = ", ".join(p for p in parts if p).rstrip(" ,") + "."
            neg = negative_block if negative_block is not None else cfg.get("negative_block")
            return {"success": True, "prompt": preview_text, "negative_prompt": neg}
        except Exception as e:
            return {"success": False, "error": str(e)}

    #: Keys whose title-cased form reads badly ("Three D Render").
    STYLE_LABEL_OVERRIDES = {
        "three_d_render": "3D Render",
        "black_and_white": "Black & White",
    }

    def get_style_presets(self, series_slug: str = None) -> list:
        """The visual types one niche offers, for the planning board dropdown."""
        try:
            from pipeline.library import get_series_config
            cfg = get_series_config(series_slug=series_slug)
        except Exception:
            return []
        from pipeline.library import style_presets_for, UNIVERSAL_STYLE_PRESETS
        own = set((cfg.get("style_presets") or {}).keys())
        out = []
        for key, entry in style_presets_for(cfg).items():
            if isinstance(entry, str):
                prompt = entry
                label = self.STYLE_LABEL_OVERRIDES.get(key, key.replace("_", " ").title())
            elif isinstance(entry, dict):
                prompt = entry.get("prompt", "")
                label = entry.get("label") or self.STYLE_LABEL_OVERRIDES.get(key, key.replace("_", " ").title())
            else:
                prompt = ""
                label = self.STYLE_LABEL_OVERRIDES.get(key, key.replace("_", " ").title())
            out.append({
                "key": key,
                "label": label,
                "prompt": prompt,
                "universal": key in UNIVERSAL_STYLE_PRESETS and key not in own,
            })
        return out

    def get_voice_catalogue(self) -> list:
        """Return the voice catalogue from config/voices.json."""
        v_path = os.path.join(BASE_DIR, "config", "voices.json")
        if os.path.exists(v_path):
            try:
                with open(v_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def save_voice_catalogue(self, catalogue: list) -> dict:
        """Save updated voice catalogue to config/voices.json."""
        v_path = os.path.join(BASE_DIR, "config", "voices.json")
        try:
            with open(v_path, "w", encoding="utf-8") as f:
                json.dump(catalogue, f, indent=2, ensure_ascii=False)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    _THUMB_CACHE: dict = {}

    @classmethod
    def _thumb(cls, repo_relative_path: str, width: int = 320) -> str:
        """
        A small JPEG encoded straight into the page as a data URI.

        file:// URLs are refused as subresources by the WebView2 control that hosts
        this page, so every thumbnail rendered as a broken-image icon. Embedding the
        bytes sidesteps the protocol entirely. Downscaled to `width`, so a board of
        fifty shots costs a few hundred KB rather than fifty full-size images.
        """
        if not repo_relative_path:
            return ""
        key = (repo_relative_path, width)
        if key in cls._THUMB_CACHE:
            return cls._THUMB_CACHE[key]

        abs_path = os.path.join(BASE_DIR, str(repo_relative_path).replace("/", os.sep))
        if not os.path.exists(abs_path):
            return ""
        try:
            import base64
            import io as _io
            from PIL import Image

            with Image.open(abs_path) as im:
                im = im.convert("RGB")
                ratio = width / float(im.width) if im.width else 1.0
                im = im.resize((width, max(1, int(im.height * ratio))), Image.LANCZOS)
                buf = _io.BytesIO()
                im.save(buf, "JPEG", quality=72)
            uri = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception:
            return ""

        if len(cls._THUMB_CACHE) > 400:
            cls._THUMB_CACHE.clear()
        cls._THUMB_CACHE[key] = uri
        return uri

    @staticmethod
    def _media_url(repo_relative_path: str) -> str:
        """
        Absolute file:// URL for an image.

        The page is loaded from frontend/index.html, so a repo-relative src like
        "library/images/x.jpg" resolves to frontend/library/images/x.jpg and 404s —
        which is why every storyboard thumbnail fell back to a grey placeholder.
        """
        if not repo_relative_path:
            return ""
        abs_path = os.path.join(BASE_DIR, str(repo_relative_path).replace("/", os.sep))
        return Path(abs_path).as_uri()

    def get_storyboard_coverage(self, script_data: dict) -> dict:
        """Calculate clip coverage per shot using pipeline.library.plan_shots()."""
        try:
            from pipeline.library import plan_shots
            report = plan_shots(script_data)

            # Attach displayable URLs so the board can actually show what it matched.
            for shot in report.get("shot_reports", []):
                shot["best_url"] = self._thumb(shot.get("best_path"))
                shot["alternative_urls"] = [
                    {"url": self._thumb(p, 160), "path": p, "score": score}
                    for p, score in (shot.get("alternatives") or [])
                ]
            return {"success": True, "report": report}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def import_shot_image(self, query: str = "", segment_id=None, shot_id=None) -> dict:
        """
        Bring an image you made outside the app into the library and pin it to a shot.

        The pin is the point. Adding the file alone only entered it into a CLIP
        popularity contest it had no reason to win: measured against the real board,
        two imported images ranked 250th and 361st of 1,243 for their own shot's
        query, and nothing in the library cleared the match floor for that query at
        all. Returning the path so the caller can pin it is what actually fills the
        shot; the manifest entry and reindex only make it findable later.
        """
        try:
            import hashlib
            import shutil
            import time as _time
            from pipeline import library

            picked = self._window.create_file_dialog(
                dialog_type=10,  # OPEN_DIALOG
                allow_multiple=False,
                file_types=("Images (*.jpg;*.jpeg;*.png;*.webp)", "All files (*.*)"),
            )
            if not picked:
                return {"success": False, "cancelled": True}

            source = picked[0]
            with open(source, "rb") as f:
                data = f.read()

            ext = os.path.splitext(source)[1].lower() or ".jpg"
            if ext not in (".jpg", ".jpeg", ".png", ".webp"):
                return {"success": False, "error": f"{ext} is not an image file"}

            name = hashlib.sha1(data).hexdigest()[:12] + ext
            os.makedirs(library.IMAGES_DIR, exist_ok=True)
            target = os.path.join(library.IMAGES_DIR, name)
            already_present = os.path.exists(target)
            if not already_present:
                shutil.copy(source, target)

            rel = f"library/images/{name}"
            if not already_present:
                with open(library.MANIFEST_PATH, "a", encoding="utf-8") as mf:
                    mf.write(json.dumps({
                        "path": rel,
                        "prompt": query,
                        "source": "imported",
                        "bytes": len(data),
                        "created_at": _time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    }, ensure_ascii=False) + "\n")
                library.reindex(force=True)

            return {
                "success": True,
                "path": rel,
                "url": self._thumb(rel),
                "filename": name,
                "segment_id": segment_id,
                "shot_id": shot_id,
                "already_in_library": already_present,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    LAST_PROJECT_PATH = os.path.join(BASE_DIR, "config", "last_project.json")

    #: Choices the Script screen should still be showing next time.
    #: `shot_rhythm` held a slider position under a mapping that has since been
    #: corrected, so it is stored as seconds now and the old key is not read.
    def get_narration_tones(self, series_slug: str = None) -> list:
        """
        Every tone, the ones suited to this niche first.

        A tone is not decoration: it sets the reading speed and the length of
        the silences between sentences and paragraphs, which is what makes a
        motivational read different from a news read on the same words.
        """
        try:
            from pipeline.delivery import tones_for_niche
            return tones_for_niche(series_slug)
        except Exception:
            return []

    def get_motion_styles(self) -> list:
        """
        Every camera-motion style the project can be rendered under.

        Like the tone, this is not decoration: it sets how far the frame travels
        per second of shot and which moves follow which, so a film stops running
        one move at one strength from the first shot to the last.
        """
        try:
            from pipeline.motion import styles_for_ui
            return styles_for_ui()
        except Exception:
            return []

    def draft_brief_preview(self, series_slug: str = None, visual_type: str = "") -> dict:
        """
        The opening line these two choices would produce, for the board to show.

        No script is involved, so the recurring-cast clause is absent: that is
        added when the storyboard is planned and the narration is known.
        """
        try:
            from pipeline.library import (get_series_config, resolve_style_preset,
                                          draft_project_brief)
            cfg = get_series_config(series_slug=series_slug)
            preset = resolve_style_preset(cfg, visual_type)
            treatment = preset.get("treatment") if preset else None
            return {"success": True,
                    "brief": draft_project_brief("", cfg, "", treatment)}
        except Exception as e:
            return {"success": False, "error": str(e), "brief": ""}

    UI_DEFAULT_KEYS = ("voice", "series_slug", "tone", "visual_style", "visual_type",
                       "captions_enabled", "shot_rhythm_seconds", "image_count", "formats")

    def save_ui_defaults(self, defaults: dict) -> dict:
        """
        Remember the Script screen's choices.

        Voice, series pack, tone and style reset to the first option on every
        launch, so the same selections had to be made before every single video.
        """
        try:
            stored = dict(self._settings.get("ui_defaults") or {})
            for key in self.UI_DEFAULT_KEYS:
                if key in (defaults or {}):
                    stored[key] = defaults[key]
            self._settings["ui_defaults"] = stored
            _save_settings(self._settings)
            return {"success": True, "ui_defaults": stored}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_ui_defaults(self) -> dict:
        return {"success": True, "ui_defaults": dict(self._settings.get("ui_defaults") or {})}

    def save_project(self, script_data: dict) -> dict:
        """
        Save the project where it belongs and remember it as the current one.

        Planned scripts were written to a temp file, and the only route back was
        a JSON file picker — so closing the app lost an afternoon of placing
        images, and Windows could clear the file on its own. Projects now live in
        projects/<title>/script.json and reopen by themselves.
        """
        try:
            import re as _re
            import unicodedata as _ud

            proj = (script_data or {}).get("project") or {}
            title = (proj.get("title") or "untitled").strip()
            slug = _ud.normalize("NFKD", title)
            slug = _re.sub(r"[^\w\-]+", "_", slug).strip("_") or "untitled"

            folder = os.path.join(BASE_DIR, "projects", slug)
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, "script.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(script_data, f, ensure_ascii=False, indent=2)

            os.makedirs(os.path.dirname(self.LAST_PROJECT_PATH), exist_ok=True)
            with open(self.LAST_PROJECT_PATH, "w", encoding="utf-8") as f:
                json.dump({"path": path, "title": title}, f, indent=2)

            return {"success": True, "path": path, "title": title}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_last_project(self) -> dict:
        """The project this app last had open, so it can pick up where it left off."""
        try:
            if not os.path.exists(self.LAST_PROJECT_PATH):
                return {"success": True, "found": False}
            with open(self.LAST_PROJECT_PATH, "r", encoding="utf-8") as f:
                pointer = json.load(f)
            path = pointer.get("path", "")
            if not path or not os.path.exists(path):
                return {"success": True, "found": False}
            with open(path, "r", encoding="utf-8") as f:
                script_data = json.load(f)
            return {
                "success": True,
                "found": True,
                "path": path,
                "title": pointer.get("title", ""),
                "script_data": script_data,
                "segments": len(script_data.get("segments", [])),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def choose_working_folder(self, script_data: dict) -> dict:
        """
        Pick any folder on this machine to work from, and index it.

        Not a library subfolder — anywhere. A working folder is the handful of
        pictures chosen for one video, kept wherever the user keeps them. Moving
        them into the library afterwards is their call, not the app's.
        """
        try:
            from pipeline import library

            picked = self._window.create_file_dialog(dialog_type=20)  # FOLDER_DIALOG
            if not picked:
                return {"success": False, "cancelled": True}

            folder = picked[0] if isinstance(picked, (list, tuple)) else str(picked)
            images = library.folder_image_files(folder)
            if not images:
                return {"success": False,
                        "error": f"No images found in {folder}.\n"
                                 "Put your .jpg/.png files there and choose it again."}

            count, elapsed = library.index_folder(folder)
            script_data.setdefault("project", {})["image_folder"] = folder

            # Existing choices pointing at the old source would survive the switch
            # and make the new folder look like it changed nothing.
            cleared = library.clear_out_of_scope_choices(script_data, folder)

            return {
                "success": True,
                "script_data": script_data,
                "folder": folder,
                "images": count,
                "seconds": round(elapsed, 1),
                "cleared_pins": cleared["pins"],
                "cleared_resolved": cleared["resolved"],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def use_whole_library(self, script_data: dict) -> dict:
        """Go back to searching the whole library."""
        try:
            script_data.setdefault("project", {})["image_folder"] = ""
            return {"success": True, "script_data": script_data}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_working_folder_status(self, script_data: dict) -> dict:
        """What the board should show about the current image source."""
        try:
            from pipeline import library
            folder = ((script_data or {}).get("project") or {}).get("image_folder") or ""
            if folder:
                return {"success": True, "folder": folder,
                        "images": len(library.folder_image_files(folder)),
                        "name": os.path.basename(os.path.normpath(folder))}
            return {"success": True, "folder": "",
                    "images": len(library.get_image_files()), "name": ""}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def refresh_library(self) -> dict:
        """
        Pick up images added to library/images by hand, without a full rebuild.

        Generating an image elsewhere and dropping it into the folder used to do
        nothing until something happened to invalidate the index, and then cost a
        full re-embed of the whole library. This indexes only what changed.
        """
        try:
            from pipeline import library
            notes = []
            count, elapsed = library.reindex(on_progress=notes.append)
            return {
                "success": True,
                "images": count,
                "seconds": round(elapsed, 1),
                "detail": notes[0] if notes else "Library already up to date",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def save_prompts_to_file(self, text: str) -> dict:
        """Fallback for when WebView2 refuses clipboard access."""
        try:
            import time as _time
            out_dir = os.path.join(BASE_DIR, "output")
            os.makedirs(out_dir, exist_ok=True)
            path = os.path.join(out_dir, f"prompts_{_time.strftime('%Y%m%d_%H%M%S')}.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            return {"success": True, "path": path}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_all_prompts(self, script_data: dict) -> dict:
        """
        Every shot's image prompt for this script, as one block of text.

        Includes shots that already matched, not only gaps: a suggested image is
        not always the one you want, and generating a better one needs the prompt.
        """
        try:
            from pipeline.library import plan_shots

            report = plan_shots(script_data)

            # One prompt per line, in shot order. Line N is shot N.
            #
            # The line used to open with a project tag and the shot number
            # ("whydid1. ..."), because that survives the ~20-character filename
            # truncation image tools apply and says which shot a picture is for.
            # But the generator reads it as part of the picture: a prompt opening
            # with a scene label comes back with a slate burnt into the frame.
            # The number is worth nothing if it costs a watermark on every image.
            #
            # So the prompt is now description only. The number goes on the file
            # at generation time instead, where no generator can read it.
            # One prompt per picture, not per shot. A shot carrying share_with
            # reuses an earlier shot's image, so its prompt asks for a picture
            # nothing will ever display: a 25-image plan across 44 segments
            # emitted 44 prompts. Generating all of them wastes the owner's
            # image budget, and dropping all 44 into the folder hands the
            # numbered matcher one image per segment, undoing the plan.
            lines = []
            for r in report.get("shot_reports", []):
                if r.get("share_with"):
                    continue
                prompt = " ".join((r.get("composed_prompt") or "").split())
                if prompt:
                    lines.append(prompt)

            return {
                "success": True,
                "text": "\n".join(lines),
                "shots": len(lines),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def set_shot_rhythm(self, script_data: dict, seconds_per_shot: float = 7.0) -> dict:
        """
        Re-cut every segment into shots of roughly seconds_per_shot.

        The slider on the Storyboard used to only rewrite its own label. This is
        what it was always meant to do: more shots per segment, each with its own
        query, so the picture changes on a rhythm instead of holding one image for
        the whole segment.
        """
        try:
            from pipeline.text_parser import apply_shot_rhythm
            stats = apply_shot_rhythm(script_data, seconds_per_shot)
            return {"success": True, "script_data": script_data, **stats}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def set_image_count(self, script_data: dict, image_count: int) -> dict:
        """
        Re-cut the whole script so it uses exactly image_count images.

        Plans across the whole script: when fewer images are asked for than there
        are segments, consecutive segments share one image.
        """
        try:
            from pipeline.text_parser import plan_image_budget
            stats = plan_image_budget(script_data, image_count)
            return {"success": True, "script_data": script_data, **stats}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def measure_narration_for_script(self, script_data: dict) -> dict:
        """
        Render every line and record how long it really takes to say.

        Planning guessed a line's length from its word count. 2.6 words a second
        is fair across a film and wrong on every individual line, so boundaries
        placed on it drift from the audio the viewer hears.

        The audio is generated for the render anyway and is cached under the same
        project key the render uses, so this moves the work earlier rather than
        adding it - a later render finds the files already there.
        """
        import base64
        import hashlib

        def _push(event: dict):
            payload = base64.b64encode(
                json.dumps(event, ensure_ascii=False).encode("utf-8")
            ).decode("ascii")
            try:
                self._window.evaluate_js(
                    f"window.onTimingProgress("
                    f"JSON.parse(window.decodeBase64UTF8('{payload}')))"
                )
            except Exception:
                pass

        try:
            from pipeline.narration_timing import measure_narration

            project = script_data.get("project") or {}
            title = project.get("title") or "Untitled Project"
            # Same key the renderer uses, so measuring warms the render's cache
            # instead of building a second copy of every mp3 beside it.
            proj_hash = hashlib.md5(title.encode("utf-8")).hexdigest()[:8]
            cache_dir = os.path.join(BASE_DIR, "cache", proj_hash)

            google_key = (self._settings.get("google_tts_api_key", "").strip()
                          or self._settings.get("google_api_key", "").strip())

            total = len(script_data.get("segments") or [])
            seen = {"n": 0}

            def on_progress(message):
                seen["n"] += 1
                _push({"done": seen["n"], "total": total, "message": message})

            stats = measure_narration(script_data, cache_dir=cache_dir,
                                      google_api_key=google_key,
                                      on_progress=on_progress)
            _push({"done": total, "total": total, "message": "", "finished": True})
            return {"success": True, "script_data": script_data, **stats}
        except Exception as e:
            _push({"done": 0, "total": 0, "message": "", "finished": True})
            return {"success": False, "error": str(e)}

    def plan_pictures_for_script(self, script_data: dict, image_count: int = None,
                                 min_hold: float = 8.0, max_hold: float = 75.0) -> dict:
        """
        Let the model decide where the pictures go.

        `image_count` None means the story decides how many and the holding
        range governs. A number means exactly that many, and the range steps
        aside — one picture across a twenty-minute film is a legitimate answer.
        """
        try:
            from pipeline.picture_plan import plan_pictures, apply_spans
            from pipeline.narration_timing import segment_seconds
            from pipeline.library import get_series_config

            segments = script_data.get("segments") or []
            lines = [(seg.get("narration") or "").strip() for seg in segments]
            seconds = segment_seconds(script_data)

            project = script_data.get("project") or {}
            series_cfg = get_series_config(series_slug=project.get("series_slug"),
                                           project_title=project.get("title"))

            spans = plan_pictures(lines, seconds, series_cfg=series_cfg,
                                  min_hold=min_hold, max_hold=max_hold,
                                  exact_count=int(image_count) if image_count else None)
            stats = apply_spans(script_data, spans)

            from pipeline.text_parser import assign_effects, style_of
            assign_effects(script_data, style_of(script_data))

            # Remember how this plan was asked for. The toggle used to reset to
            # Auto on every load while the saved plan did not, so the board could
            # read "Auto" above a film the user had pinned to an exact count.
            project["plan_mode"] = "exact" if image_count else "auto"
            project["plan_count"] = int(image_count) if image_count else None
            project["plan_min_hold"] = float(min_hold)
            project["plan_max_hold"] = float(max_hold)

            return {"success": True, "script_data": script_data,
                    "images_after": stats["pictures"], "segments": stats["segments"]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def split_picture_at(self, script_data: dict, at_line: int) -> dict:
        """
        Start a new picture at a script line, without re-planning the film.

        Re-planning to move one boundary costs two model calls, rewrites every
        other picture, and throws away descriptions that were already good.
        """
        try:
            from pipeline.picture_plan import split_picture
            from pipeline.text_parser import assign_effects, style_of

            out = split_picture(script_data, at_line)
            if out.get("success"):
                assign_effects(script_data, style_of(script_data))
            return out
        except Exception as e:
            return {"success": False, "error": str(e)}

    def merge_picture_at(self, script_data: dict, at_line: int) -> dict:
        """Fold the picture starting at a script line into the one before it."""
        try:
            from pipeline.picture_plan import merge_picture
            from pipeline.text_parser import assign_effects, style_of

            out = merge_picture(script_data, at_line)
            if out.get("success"):
                assign_effects(script_data, style_of(script_data))
            return out
        except Exception as e:
            return {"success": False, "error": str(e)}

    def fill_gaps_with_nearest(self, script_data: dict, allow_reuse: bool = True) -> dict:
        """
        Accept the closest library image for every gap, in one action.

        A 117-shot script left 38 gaps, each needing a manual decision. The
        closest image is already computed for every gap — it just scored under
        the match floor. Taking it is a judgement the user is entitled to make in
        bulk, and it is reversible: every filled shot is an ordinary pin that
        Replace can change.

        allow_reuse lets one image serve more than one shot. Diversity normally
        forbids that, which is right for a full library and wrong for a thin one.
        """
        try:
            from pipeline.library import plan_shots, search

            report = plan_shots(script_data)
            by_key = {(r["segment_id"], str(r["shot_id"])): r for r in report["shot_reports"]}

            taken = {
                r["best_path"] for r in report["shot_reports"]
                if r["best_path"] and r["state"] != "gap"
            }

            filled, still_empty = 0, 0
            for seg in script_data.get("segments", []):
                for shot in seg.get("shots") or []:
                    rep = by_key.get((seg.get("segment_id"), str(shot.get("shot_id"))))
                    if not rep or rep["state"] != "gap":
                        continue

                    candidate = rep.get("best_path")
                    if not candidate:
                        # Nothing survived the exclusion set; ask again without it.
                        loose = search(rep["query"], k=1, exclude=set() if allow_reuse else taken, min_score=0.0)
                        candidate = loose[0][0] if loose else None
                    if candidate and not allow_reuse and candidate in taken:
                        candidate = None

                    if not candidate:
                        still_empty += 1
                        continue

                    shot["source"] = "pin"
                    shot["pin"] = candidate
                    shot.pop("resolved", None)
                    shot.pop("resolved_score", None)
                    taken.add(candidate)
                    filled += 1

            return {
                "success": True,
                "filled": filled,
                "still_empty": still_empty,
                "script_data": script_data,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def reject_shot_image(self, query: str, image_path: str) -> dict:
        """
        "Never suggest this for this shot" — record the (query, image) rejection.

        pipeline.library.search() has always honoured this memory; nothing in the app
        had ever written to it, so library/rejections.jsonl did not exist on disk.
        """
        try:
            from pipeline import library
            if not query or not image_path:
                return {"success": False, "error": "query and image_path are both required"}
            library.record_rejection(query, image_path)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def retire_library_image(self, image_path: str) -> dict:
        """
        "Retire it" — move an image out of the retrieval pool into library/_retired/.

        Recoverable by design: the file is moved, never deleted. True deletion stays
        in the Library screen (DESIGN_SPEC section 9).
        """
        try:
            import shutil
            from pipeline import library

            abs_path = library.resolve_library_path(image_path)
            if not abs_path:
                return {"success": False, "error": f"not found: {image_path}"}

            retired_dir = os.path.join(BASE_DIR, "library", "_retired")
            os.makedirs(retired_dir, exist_ok=True)
            target = os.path.join(retired_dir, os.path.basename(abs_path))

            stem, ext = os.path.splitext(target)
            n = 1
            while os.path.exists(target):
                target = f"{stem}_{n}{ext}"
                n += 1

            shutil.move(abs_path, target)
            library.reindex(force=True)
            return {"success": True, "retired_to": os.path.relpath(target, BASE_DIR).replace("\\", "/")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _count_sounds(self) -> dict:
        """
        Count what is actually on disk. These were hardcoded to 87 and 12, which
        showed a library ten times the real size — the Library screen must never
        report a number nobody counted.
        """
        sounds_dir = os.path.join(BASE_DIR, "library", "sounds")
        audio = (".mp3", ".wav", ".ogg", ".flac", ".m4a")

        def count(path):
            if not os.path.isdir(path):
                return 0
            return len([f for f in os.listdir(path) if f.lower().endswith(audio)])

        return {
            "sounds_count": count(sounds_dir),
            "sounds_pending": count(os.path.join(sounds_dir, "_inbox")),
        }

    def get_library_data(self, query: str = "") -> dict:
        """Return library image count, coverage stats, and matching images."""
        images_dir = os.path.join(BASE_DIR, "library", "images")
        sounds = self._count_sounds()

        if not os.path.exists(images_dir):
            return {"total_images": 0, "images": [], **sounds}

        img_files = sorted([f for f in os.listdir(images_dir) if f.lower().endswith(('.jpg', '.png', '.jpeg'))])
        if query:
            q_lower = query.lower()
            img_files = [f for f in img_files if q_lower in f.lower()]

        images_info = [
            {
                "filename": f,
                "path": f"library/images/{f}",
                "url": self._thumb(f"library/images/{f}", 240),
            }
            for f in img_files[:60]
        ]
        return {
            "total_images": len(img_files),
            "images": images_info,
            **sounds,
        }

    def delete_library_image(self, filename: str) -> dict:
        """Permanent image deletion — Section 9: Deletion lives in Library only."""
        try:
            img_p = os.path.join(BASE_DIR, "library", "images", filename)
            if os.path.exists(img_p):
                os.remove(img_p)
                from pipeline.library import reindex
                reindex(force=True)
                return {"success": True}
            return {"success": False, "error": "File not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}

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

            google_key = self._settings.get("google_api_key", "")
            google_tts_key = self._settings.get("google_tts_api_key", "").strip()
            if not google_tts_key:
                google_tts_key = google_key
            
            # Gemini TTS requires the main Google Gemini Key (not the restricted Cloud TTS key)
            if "gemini-3.1-flash-tts" in voice_id.lower():
                active_key = google_key
            else:
                active_key = google_tts_key
            
            # Generate voiceover using the unified cloud TTS module
            generate_voiceover(
                segment_id=0,
                narration=sample_text,
                voice=voice_id,
                voice_rate="+0%",
                voice_pitch="+0Hz",
                cache_dir=os.path.dirname(tmp_path),
                google_api_key=active_key,
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

    def parse_plain_text(
        self,
        text: str,
        title: str,
        voice: str,
        output_filename: str,
        visual_style: str = "",
        aspect_ratio: str = "16:9",
        ai_guideline: str = "",
        voice_dialect: str = "",
        narrative_tone: str = "",
        speaker_mode: str = "single",
        motion_style: str = "",
        series_slug: str = ""
    ) -> dict:
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
                    f"window.onParseComplete(JSON.parse(window.decodeBase64UTF8('{payload}')))"
                )
            except Exception:
                pass

        def _run():
            try:
                import tempfile
                from pipeline.ai_agent import generate_storyboard_plan

                google_api_key = self._settings.get("google_api_key", "")

                res = generate_storyboard_plan(
                    text=text,
                    title=title,
                    voice=voice,
                    output_filename=output_filename,
                    visual_style=visual_style,
                    google_api_key=google_api_key,
                    ai_guideline=ai_guideline,
                    aspect_ratio=aspect_ratio,
                    voice_dialect=voice_dialect,
                    narrative_tone=narrative_tone,
                    speaker_mode=speaker_mode,
                    motion_style=motion_style,
                    series_slug=series_slug
                )

                if not res.get("success"):
                    _push({"success": False, "errors": [res.get("error_msg", "Failed to plan storyboard")]})
                    return

                script_dict = res["script"]

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
            
            # Sync edited visual prompts/placeholders with project folder
            try:
                from pipeline.visuals import initialize_project_sourcing
                initialize_project_sourcing(script_data)
            except Exception as sourcing_err:
                print(f"Failed to update project sourcing workspace on save: {sourcing_err}")
                
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ── Rendering ──────────────────────────────────────────────────────────────

    def start_render(self, script_path: str) -> dict:
        """Start the render pipeline in a background thread."""
        if self._render_thread and self._render_thread.is_alive():
            return {"success": False, "error": "A render is already in progress."}

        google_key = self._settings.get("google_api_key", "")
        google_tts_key = self._settings.get("google_tts_api_key", "").strip()

        from pipeline.orchestrator import RenderOrchestrator

        def on_event(event: dict):
            import base64
            payload = base64.b64encode(
                json.dumps(event, ensure_ascii=False).encode("utf-8")
            ).decode("ascii")
            try:
                self._window.evaluate_js(
                    f"window.onPipelineEvent("
                    f"JSON.parse(window.decodeBase64UTF8('{payload}')))"
                )
            except Exception:
                pass

        self._orchestrator = RenderOrchestrator(
            base_dir=BASE_DIR,
            on_event=on_event,
        )

        def run():
            # Anything escaping render() used to kill this thread in total silence:
            # the app runs under pythonw.exe, which has no stderr for the default
            # threading excepthook to print to, so the UI sat on "rendering"
            # indefinitely with no way to tell a dead render from a slow one.
            try:
                self._orchestrator.render(
                    script_path,
                    google_api_key=google_key,
                    google_tts_api_key=google_tts_key
                )
            except Exception as e:
                import traceback
                detail = traceback.format_exc()
                try:
                    if self._orchestrator.logger:
                        self._orchestrator.logger.error(detail)
                except Exception:
                    pass
                on_event({
                    "type": "error",
                    "message": f"The render stopped unexpectedly: {type(e).__name__}: {e}",
                    "detail": detail,
                })

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

    def open_project_folder(self, title: str) -> dict:
        """Open the Windows Explorer at the project folder path."""
        import re
        project_slug = re.sub(r'[^\w\-]', '_', title.strip()).strip('_')
        if not project_slug:
            project_slug = "my_project"
        folder = os.path.join(BASE_DIR, "projects", project_slug)
        if not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)
        subprocess.Popen(["explorer", os.path.normpath(folder)])
        return {"success": True}

    def _find_wolfcut_binary(self) -> str | None:
        """Finds the installed WolfCut executable on Windows."""
        import shutil
        on_path = shutil.which("WolfCut") or shutil.which("wolfcut")
        if on_path and os.path.exists(on_path):
            return on_path

        candidates = [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\WolfCut\WolfCut.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\WolfCut\WolfCut.exe"),
            os.path.expandvars(r"%PROGRAMFILES%\WolfCut\WolfCut.exe"),
            os.path.expandvars(r"%PROGRAMFILES(X86)%\WolfCut\WolfCut.exe"),
            os.path.expandvars(r"%APPDATA%\WolfCut\WolfCut.exe"),
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        return None

    def open_in_wolfcut(self, project_path_or_slug: str | None = None) -> dict:
        """
        Launches WolfCut with the .wolfcut project timeline file, or surfaces file location if not installed.
        """
        wolfcut_file = None
        output_dir = os.path.join(BASE_DIR, self._settings.get("output_dir", "output"))

        if project_path_or_slug and os.path.isfile(project_path_or_slug) and project_path_or_slug.endswith(".wolfcut"):
            wolfcut_file = os.path.abspath(project_path_or_slug)
        elif project_path_or_slug:
            cand = os.path.join(output_dir, f"{project_path_or_slug}.wolfcut")
            if os.path.exists(cand):
                wolfcut_file = cand

        if not wolfcut_file and os.path.exists(output_dir):
            cands = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.endswith(".wolfcut")]
            if cands:
                cands.sort(key=lambda p: os.path.getmtime(p), reverse=True)
                wolfcut_file = cands[0]

        if not wolfcut_file or not os.path.exists(wolfcut_file):
            return {
                "success": False,
                "installed": bool(self._find_wolfcut_binary()),
                "error": "No .wolfcut project file found. Export the timeline first.",
                "path": None,
                "releases_url": "https://github.com/jub0t/WolfCut/releases"
            }

        wolfcut_exe = self._find_wolfcut_binary()
        if wolfcut_exe:
            try:
                subprocess.Popen([wolfcut_exe, os.path.normpath(wolfcut_file)])
                return {"success": True, "installed": True, "path": wolfcut_file}
            except Exception as e:
                return {
                    "success": False,
                    "installed": True,
                    "error": f"Failed to launch WolfCut: {e}",
                    "path": wolfcut_file,
                    "releases_url": "https://github.com/jub0t/WolfCut/releases"
                }

        return {
            "success": False,
            "installed": False,
            "error": "WolfCut is not installed on this machine.",
            "path": wolfcut_file,
            "releases_url": "https://github.com/jub0t/WolfCut/releases"
        }

    def write_prompt_request(self, script_data: dict) -> dict:
        """
        Save the request an outside AI needs in order to write this film's
        prompts, and reveal it. The whole manual route with no API key.
        """
        try:
            from pipeline.visuals import write_prompt_request
            from pipeline.library import picture_owning_shots
            path = write_prompt_request(script_data)
            count = len(picture_owning_shots(script_data))
            try:
                subprocess.Popen(["explorer", f"/select,{os.path.normpath(path)}"])
            except Exception:
                pass
            return {"success": True, "path": path, "pictures": count}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def show_wolfcut_file(self, path: str | None = None) -> dict:
        """Reveals the .wolfcut file in Windows Explorer."""
        target = path
        if not target or not os.path.exists(target):
            output_dir = os.path.join(BASE_DIR, self._settings.get("output_dir", "output"))
            if os.path.exists(output_dir):
                cands = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.endswith(".wolfcut")]
                if cands:
                    cands.sort(key=lambda p: os.path.getmtime(p), reverse=True)
                    target = cands[0]

        if target and os.path.exists(target):
            subprocess.Popen(["explorer", f"/select,{os.path.normpath(target)}"])
            return {"success": True, "path": target}
        return {"success": False, "error": "File not found."}

    def _resolve_project_dir(self, script_data: dict, project_dir: str = "") -> str:
        """Resolve project directory or fall back to cache/<hash-of-title>."""
        if project_dir:
            return project_dir
        import hashlib
        project = (script_data or {}).get("project") or {}
        title = project.get("title") or "Untitled Project"
        proj_hash = hashlib.md5(title.encode("utf-8")).hexdigest()[:8]
        return os.path.join(BASE_DIR, "cache", proj_hash)

    def prepare_timeline_audio(self, script_data: dict, project_dir: str = "") -> dict:
        """Build (or reuse) the narration track and tell the page where it is."""
        try:
            import urllib.parse
            from pipeline.timeline_audio import build_timeline_audio
            from media_server import start_media_server

            project_dir = self._resolve_project_dir(script_data, project_dir)

            res = build_timeline_audio(script_data, project_dir)
            if not res.get("ok"):
                return res

            abs_path = os.path.abspath(res["path"])
            is_devserver = (
                os.environ.get("SMART_STUDIO_DEVSERVER") == "1"
                or (self._window is not None and type(self._window).__name__ == "DevWindow")
            )

            if is_devserver:
                src = f"/media?path={urllib.parse.quote(abs_path)}"
            else:
                host, port, token = start_media_server(BASE_DIR)
                src = f"http://{host}:{port}/media?token={token}&path={urllib.parse.quote(abs_path)}"

            res["src"] = src
            return res
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def export_wolfcut_timeline(self, script_data: dict, project_dir: str = "") -> dict:
        """
        Write a WolfCut timeline from the narration timing, with no video render.

        The exporter has always been able to do this - it takes an audio path and a
        duration per segment and measures neither. It was only ever called from
        inside the renderer, so a timeline cost a full encode.
        """
        try:
            from pipeline.narration_timing import timing_maps
            from pipeline.wolfcut_export import write_wolfcut_project

            project_dir = self._resolve_project_dir(script_data, project_dir)

            audio_paths, durations = timing_maps(script_data)
            if not audio_paths:
                return {
                    "success": False,
                    "error": "Narration has not been recorded yet. Measure narration on the Storyboard first.",
                    "path": None,
                    "pictures": 0,
                    "segments": 0,
                    "captions": 0,
                }

            wolfcut_path = write_wolfcut_project(script_data, audio_paths, durations, project_dir)

            pictures_count = 0
            segments_count = 0
            captions_count = 0
            if os.path.exists(wolfcut_path):
                with open(wolfcut_path, "r", encoding="utf-8") as f:
                    doc = json.load(f)
                clips = doc.get("clips") or []
                pictures_count = len([c for c in clips if c.get("trackId") == "T1"])
                segments_count = len([c for c in clips if c.get("trackId") == "T2"])
                captions_count = len([c for c in clips if c.get("trackId") == "T3"])

            return {
                "success": True,
                "path": os.path.abspath(wolfcut_path),
                "pictures": pictures_count,
                "segments": segments_count,
                "captions": captions_count,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "path": None,
                "pictures": 0,
                "segments": 0,
                "captions": 0,
            }

    def get_version(self) -> str:
        return "2.0.0"

    def clear_cache(self) -> dict:
        """Delete all files in the cache directory."""
        import shutil
        cache_dir = os.path.join(BASE_DIR, "cache")
        try:
            if os.path.exists(cache_dir):
                shutil.rmtree(cache_dir)
                os.makedirs(cache_dir, exist_ok=True)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}



    # ── Voiceover Studio ───────────────────────────────────────────────────────

    def voice_probe_engines(self) -> dict:
        """Which speech engines can actually run right now, and why not."""
        try:
            from pipeline.voice_studio import probe_engines
            return {"success": True, "engines": probe_engines()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def voice_generate(self, opts: dict) -> dict:
        """Generate one clip. `opts` mirrors the Voiceover Studio form."""
        try:
            from pipeline.voice_studio import synthesize
            opts = opts or {}
            result = synthesize(
                engine=opts.get("engine", "edge"),
                text=opts.get("text", ""),
                voice=opts.get("voice", ""),
                reference_audio=opts.get("reference_audio", ""),
                language=opts.get("language", "EN"),
                speed=opts.get("speed", 1.0),
                pitch=opts.get("pitch", 0.0),
                label=opts.get("label", "clip"),
                google_api_key=(self._settings.get("google_tts_api_key", "").strip()
                                or self._settings.get("google_api_key", "").strip()),
            )
            if not result.get("ok"):
                return {"success": False, "error": result.get("error", "Generation failed.")}
            return {"success": True, "entry": result["entry"]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def voice_read_audio(self, path: str) -> dict:
        """Return an audio file as a base64 data URL so the webview can play it."""
        import base64
        import mimetypes
        try:
            if not path or not os.path.isfile(path):
                return {"success": False, "error": "Audio file not found."}
            mime = mimetypes.guess_type(path)[0] or "audio/wav"
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            return {"success": True, "data_url": f"data:{mime};base64,{b64}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def voice_pick_reference(self) -> str | None:
        """Native picker for a reference voice clip."""
        try:
            result = self._window.create_file_dialog(
                dialog_type=10,  # OPEN_DIALOG
                allow_multiple=False,
                file_types=("Audio (*.wav;*.mp3;*.m4a;*.ogg;*.flac)", "All files (*.*)"),
            )
            return result[0] if result else None
        except Exception:
            return None

    def voice_save_recording(self, data_url: str, suffix: str = ".webm") -> dict:
        """Persist a microphone recording captured in the browser layer."""
        import base64
        import tempfile
        try:
            if not data_url or "," not in data_url:
                return {"success": False, "error": "No recording data received."}
            raw = base64.b64decode(data_url.split(",", 1)[1])
            if not raw:
                return {"success": False, "error": "Recording was empty."}
            fd, path = tempfile.mkstemp(suffix=suffix, prefix="voiceref_")
            with os.fdopen(fd, "wb") as f:
                f.write(raw)
            return {"success": True, "path": path}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def voice_download(self, src_path: str, preferred_name: str = "voiceover") -> dict:
        """Copy a generated clip to wherever the user chooses."""
        import re
        import shutil
        try:
            if not src_path or not os.path.isfile(src_path):
                return {"success": False, "error": "That clip is no longer on disk."}
            ext = os.path.splitext(src_path)[1] or ".wav"

            # SAVE_DIALOG is 30. Passing 20 here opened a FOLDER picker (see the
            # library folder import above), so every download landed on a
            # directory and copyfile died with a permission error.
            try:
                import webview
                save_dialog = int(webview.SAVE_DIALOG)
            except Exception:
                save_dialog = 30

            safe_name = re.sub(r'[<>:"/\|?*]+', "_", str(preferred_name)).strip(" .")
            if not safe_name:
                safe_name = "voiceover"

            label = ext.lstrip(".").upper() or "Audio"
            dest = self._window.create_file_dialog(
                dialog_type=save_dialog,
                save_filename=f"{safe_name}{ext}",
                file_types=(f"{label} audio (*{ext})", "All files (*.*)"),
            )
            if not dest:
                return {"success": False, "cancelled": True}
            if isinstance(dest, (list, tuple)):
                dest = dest[0]
            dest = str(dest)

            # A folder can still come back from some backends; keep the clip name.
            if os.path.isdir(dest):
                dest = os.path.join(dest, f"{safe_name}{ext}")
            if not os.path.splitext(dest)[1]:
                dest += ext

            if os.path.abspath(dest) != os.path.abspath(src_path):
                shutil.copyfile(src_path, dest)
            return {"success": True, "path": dest}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def voice_list_profiles(self) -> dict:
        try:
            from pipeline.voice_studio import list_profiles
            return {"success": True, "profiles": list_profiles()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def voice_save_profile(self, name: str, reference_audio: str, language: str = "EN") -> dict:
        try:
            from pipeline.voice_studio import save_profile
            r = save_profile(name, reference_audio, language)
            if not r.get("ok"):
                return {"success": False, "error": r.get("error")}
            return {"success": True, "profiles": r["profiles"]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def voice_delete_profile(self, profile_id: str) -> dict:
        try:
            from pipeline.voice_studio import delete_profile
            r = delete_profile(profile_id)
            if not r.get("ok"):
                return {"success": False, "error": r.get("error")}
            return {"success": True, "profiles": r["profiles"]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def voice_list_history(self) -> dict:
        try:
            from pipeline.voice_studio import list_history
            return {"success": True, "history": list_history()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def voice_clear_history(self) -> dict:
        try:
            from pipeline.voice_studio import clear_history
            clear_history()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def voice_open_output_folder(self) -> dict:
        try:
            from pipeline.voice_studio import OUTPUT_DIR
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            os.startfile(OUTPUT_DIR)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}


SmartStudioAPI = Api


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

    from media_server import start_media_server
    start_media_server(BASE_DIR)

    window = webview.create_window(
        title="Smart Studio",
        url=os.path.join(BASE_DIR, "frontend", "index.html"),
        js_api=api,
        width=1000,
        height=900,
        min_size=(900, 750),
        resizable=True,
        # pywebview defaults text_select to False and injects
        #   body { user-select: none; cursor: default }
        # which made every word in the app unselectable — narration could not be
        # copied out or read with a screen reader.
        text_select=True,
    )

    api.set_window(window)

    def _focus_window():
        # Without this the window opens behind everything and sits in the taskbar.
        try:
            window.restore()
            window.on_top = True
            window.on_top = False
        except Exception:
            pass

    webview.start(_focus_window, debug=False, gui='edgechromium')


if __name__ == "__main__":
    main()
