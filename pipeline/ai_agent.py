import json
import re
from pipeline.text_parser import build_script

# Coefficients for rendering time estimation (seconds)
COEFFS = {
    "voice_edge": 0.5,       # 0.5s per segment
    "voice_premium": 1.5,    # 1.5s per segment for Google TTS
    "image_google": 3.0,     # 3.0s per Google Imagen image
    "composition": 0.75,     # 0.75s per second of video
    "stitch_offset": 5.0     # 5s constant for stitching
}

def estimate_speech_duration(text: str) -> float:
    """Estimate speech duration: average of 15 characters per second."""
    chars = len(text.strip())
    if chars == 0:
        return 0.0
    return round(chars / 15.0, 1)

def calculate_estimated_render_time(num_segments: int, voice_type: str, estimated_speech_duration: float) -> int:
    """Calculate estimated rendering time in seconds."""
    is_premium_voice = voice_type.startswith("google:")
    voice_coeff = COEFFS["voice_premium"] if is_premium_voice else COEFFS["voice_edge"]
    
    voice_time = num_segments * voice_coeff
    image_time = num_segments * COEFFS["image_google"]
    comp_time = estimated_speech_duration * COEFFS["composition"]
    
    total = voice_time + image_time + comp_time + COEFFS["stitch_offset"]
    return int(round(total))


def generate_storyboard_plan(
    text: str,
    title: str,
    voice: str,
    output_filename: str,
    visual_style: str = "",
    google_api_key: str = "",
    ai_guideline: str = "",
    aspect_ratio: str = "16:9",
    voice_dialect: str = "",
    narrative_tone: str = "",
    speaker_mode: str = "single",
    motion_style: str = "",
    series_slug: str = "",
    motion_amount: int = 60,
) -> dict:
    """
    Parse a plain script using AI (DeepSeek + Gemini Oversight, falling back to Gemini-only) into a storyboard.
    Falls back to rules if keys are missing or planning fails.
    """
    text = text.strip()
    if not text:
        raise ValueError("Script text is empty.")

    # Load DeepSeek API key and model from settings if not passed directly
    deepseek_api_key = ""
    deepseek_model = "deepseek-chat"
    try:
        import os
        import json
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        settings_path = os.path.join(base_dir, "config", "settings.json")
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
                deepseek_api_key = settings.get("deepseek_api_key", "").strip()
                deepseek_model = settings.get("deepseek_model", "deepseek-chat").strip()
    except Exception:
        pass

    from pipeline.motion import assign_effects, resolve_motion_style
    from pipeline.visuals import initialize_project_sourcing

    if deepseek_api_key or google_api_key:
        if deepseek_api_key:
            print(f"DeepSeek API Key found. Routing storyboard planning through {deepseek_model} + Gemini Oversight.")
        else:
            print("Google API Key found. Routing storyboard planning through Gemini AI.")
            
        try:
            from pipeline.text_parser import build_script_with_deepseek_and_gemini
            script_dict = build_script_with_deepseek_and_gemini(
                text=text,
                title=title,
                voice=voice,
                output_filename=output_filename,
                visual_style=visual_style,
                google_api_key=google_api_key,
                deepseek_api_key=deepseek_api_key,
                ai_guideline=ai_guideline,
                deepseek_model=deepseek_model,
                voice_dialect=voice_dialect,
                narrative_tone=narrative_tone,
                speaker_mode=speaker_mode,
                **({"series_slug": series_slug} if series_slug else {})
            )
            script_dict["project"]["aspect_ratio"] = aspect_ratio
            script_dict["project"]["voice_dialect"] = voice_dialect
            script_dict["project"]["narrative_tone"] = narrative_tone
            script_dict["project"]["speaker_mode"] = speaker_mode
            # The camera moves are the motion style's to deal out, not the
            # planner's: a cached plan carries the moves it was first given.
            script_dict["project"]["motion_style"] = resolve_motion_style(motion_style)
            script_dict["project"]["motion_amount"] = int(motion_amount) if motion_amount is not None else 60
            if series_slug:
                script_dict["project"]["series_slug"] = series_slug
            assign_effects(script_dict, motion_style)
            
            # Initialize project sourcing workspace (folders, placeholders, image_prompts.txt)
            try:
                initialize_project_sourcing(script_dict)
            except Exception as sourcing_err:
                print(f"Failed to initialize project sourcing during planning: {sourcing_err}")

            # Estimate duration and render time
            duration = sum(estimate_speech_duration(s["narration"]) for s in script_dict["segments"])
            render_time = calculate_estimated_render_time(len(script_dict["segments"]), voice, duration)
            return {
                "success": True,
                "fallback": False,
                "script": script_dict,
                "estimated_duration": duration,
                "estimated_render_time": render_time
            }
        except Exception as e:
            print(f"AI storyboard planning failed: {e}. Falling back to rule-based parser.")
            script_dict = build_script(text, title, voice, output_filename, visual_style)
            script_dict["project"]["voice_tone_guideline"] = ai_guideline
            script_dict["project"]["aspect_ratio"] = aspect_ratio
            script_dict["project"]["voice_dialect"] = voice_dialect
            script_dict["project"]["narrative_tone"] = narrative_tone
            script_dict["project"]["speaker_mode"] = speaker_mode
            # The camera moves are the motion style's to deal out, not the
            # planner's: a cached plan carries the moves it was first given.
            script_dict["project"]["motion_style"] = resolve_motion_style(motion_style)
            script_dict["project"]["motion_amount"] = int(motion_amount) if motion_amount is not None else 60
            if series_slug:
                script_dict["project"]["series_slug"] = series_slug
            assign_effects(script_dict, motion_style)
            for s in script_dict["segments"]:
                s["voice_steering"] = ai_guideline
            
            # Initialize project sourcing workspace for fallback
            try:
                initialize_project_sourcing(script_dict)
            except Exception as sourcing_err:
                print(f"Failed to initialize project sourcing during fallback planning: {sourcing_err}")

            duration = sum(estimate_speech_duration(s["narration"]) for s in script_dict["segments"])
            render_time = calculate_estimated_render_time(len(script_dict["segments"]), voice, duration)
            
            return {
                "success": True,
                "fallback": True,
                "error_msg": str(e),
                "script": script_dict,
                "estimated_duration": duration,
                "estimated_render_time": render_time
            }
    else:
        print("All API Keys missing. Falling back to rule-based parser.")
        script_dict = build_script(text, title, voice, output_filename, visual_style)
        script_dict["project"]["voice_tone_guideline"] = ai_guideline
        script_dict["project"]["aspect_ratio"] = aspect_ratio
        script_dict["project"]["voice_dialect"] = voice_dialect
        script_dict["project"]["narrative_tone"] = narrative_tone
        script_dict["project"]["speaker_mode"] = speaker_mode
        # The camera moves are the motion style's to deal out, not the
        # planner's: a cached plan carries the moves it was first given.
        script_dict["project"]["motion_style"] = resolve_motion_style(motion_style)
        script_dict["project"]["motion_amount"] = int(motion_amount) if motion_amount is not None else 60
        assign_effects(script_dict, motion_style)
        for s in script_dict["segments"]:
            s["voice_steering"] = ai_guideline
        
        # Initialize project sourcing workspace for fallback
        try:
            initialize_project_sourcing(script_dict)
        except Exception as sourcing_err:
            print(f"Failed to initialize project sourcing during fallback planning: {sourcing_err}")

        duration = sum(estimate_speech_duration(s["narration"]) for s in script_dict["segments"])
        render_time = calculate_estimated_render_time(len(script_dict["segments"]), voice, duration)
        
        return {
            "success": True,
            "fallback": True,
            "error_msg": "Google and DeepSeek API keys are missing in settings",
            "script": script_dict,
            "estimated_duration": duration,
            "estimated_render_time": render_time
        }
