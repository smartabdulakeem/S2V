import json
import re
import urllib.request
import urllib.error
from pipeline.text_parser import build_script

HF_LLM_URL = "https://router.huggingface.co/v1/chat/completions"

_LLM_PLANNER_PROMPT = """\
You are an AI video editor and storyboard planning agent. Your task is to split a narration script into logical, scene-by-scene storyboard steps for a short video.

Rules:
1. You MUST split the input script into scene segments. Each segment should contain between 15 and 45 words of narration representing a cohesive visual beat.
2. Every word of the original script MUST be included in the segment narration fields, in order, without summaries, paraphrasing, additions, or omissions.
3. For each segment, define:
   - "b_roll_keyword": a descriptive 3-5 word noun phrase detailing a concrete, historical or physical visual to generate (e.g. "ancient roman library with scrolls, warm light" instead of "reading a book").
   - "text_overlay": an optional text string to display on screen (or null if not needed).
   - "ken_burns": a motion effect. Choose one from: "zoom_in", "zoom_out", "pan_left", "pan_right", "none".
4. You must output ONLY a valid raw JSON object. Do not include markdown formatting, backticks, or explanation.

The JSON output MUST follow this exact structure:
{{
  "visual_style": "<suggested descriptive visual style matching the topic>",
  "segments": [
    {{
      "narration": "<verbatim segment of text>",
      "b_roll_keyword": "<concrete image prompt keywords>",
      "text_overlay": "<overlay text or null>",
      "ken_burns": "<zoom_in/zoom_out/pan_left/pan_right/none>"
    }},
    ...
  ]
}}

Script title: {title}
User visual style: {visual_style}
Script content:
{script}"""

# Coefficients for rendering time estimation (seconds)
COEFFS = {
    "voice_edge": 0.5,       # 0.5s per segment
    "voice_hf": 6.0,         # 6s per segment (Bark, Coqui XTTS)
    "image_hf": 2.5,         # 2.5s per image
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
    # Detect voice type
    is_hf_voice = voice_type.startswith("hf:") or "bark" in voice_type.lower() or "xtts" in voice_type.lower()
    voice_coeff = COEFFS["voice_hf"] if is_hf_voice else COEFFS["voice_edge"]
    
    voice_time = num_segments * voice_coeff
    image_time = num_segments * COEFFS["image_hf"]
    comp_time = estimated_speech_duration * COEFFS["composition"]
    
    total = voice_time + image_time + comp_time + COEFFS["stitch_offset"]
    return int(round(total))

def generate_storyboard_plan(
    text: str,
    title: str,
    voice: str,
    output_filename: str,
    visual_style: str = "",
    hf_token: str = ""
) -> dict:
    """
    Parse a plain script using Hugging Face LLM into a storyboard.
    Falls back to text_parser.build_script if HF token is missing or if the API fails.
    """
    text = text.strip()
    if not text:
        raise ValueError("Script text is empty.")

    # Fallback if no HF token
    if not hf_token:
        print("HF Token missing. Falling back to rule-based parser.")
        script_dict = build_script(text, title, voice, output_filename, visual_style)
        duration = sum(estimate_speech_duration(s["narration"]) for s in script_dict["segments"])
        render_time = calculate_estimated_render_time(len(script_dict["segments"]), voice, duration)
        
        return {
            "success": True,
            "fallback": True,
            "error_msg": "Hugging Face API key is missing in settings",
            "script": script_dict,
            "estimated_duration": duration,
            "estimated_render_time": render_time
        }

    # Format the prompt
    prompt = _LLM_PLANNER_PROMPT.format(
        title=title or "Untitled Video",
        visual_style=visual_style or "cinematic, high detail",
        script=text
    )

    headers = {
        "Authorization": f"Bearer {hf_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "Qwen/Qwen2.5-72B-Instruct",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 4096
    }
    body = json.dumps(payload).encode("utf-8")

    try:
        req = urllib.request.Request(
            HF_LLM_URL, data=body, headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=90) as resp:
            raw_response = resp.read()
            response_json = json.loads(raw_response.decode("utf-8"))
            
            # Extract content from OpenAI chat completions format
            if isinstance(response_json, dict) and "choices" in response_json:
                generated_text = response_json["choices"][0]["message"]["content"].strip()
            else:
                generated_text = str(response_json).strip()

        # Clean JSON from backticks or extra text
        if "```" in generated_text:
            generated_text = re.sub(r"^```[a-z]*\n?", "", generated_text, flags=re.IGNORECASE)
            generated_text = re.sub(r"\n?```$", "", generated_text)
        generated_text = generated_text.strip()

        parsed = json.loads(generated_text)
        ai_segments = parsed.get("segments", [])
        ai_style = parsed.get("visual_style", visual_style or "cinematic, photorealistic").strip()

        if not ai_segments:
            raise ValueError("LLM returned empty segments list")

        # Re-build into standard S2V schema
        segments = []
        total_duration = 0.0
        
        # Ensure transitions and effects are cycled cleanly
        ken_burns_cycle = ["zoom_in", "pan_right", "zoom_out", "pan_left", "zoom_in", "zoom_out"]
        transition_cycle = ["fade", "crossfade", "fade", "crossfade"]

        for i, seg in enumerate(ai_segments):
            narration = seg.get("narration", "").strip()
            if not narration:
                continue
            
            seg_duration = estimate_speech_duration(narration)
            total_duration += seg_duration

            if i == 0:
                seg_type = "hook"
            elif i == len(ai_segments) - 1:
                seg_type = "conclusion"
            else:
                seg_type = "body"

            segments.append({
                "segment_id": i + 1,
                "type": seg_type,
                "narration": narration,
                "b_roll_keyword": seg.get("b_roll_keyword", "scene scene").strip(),
                "visual_type": "ai_image",
                "ken_burns": seg.get("ken_burns") if seg.get("ken_burns") in ["zoom_in", "zoom_out", "pan_left", "pan_right", "none"] else ken_burns_cycle[i % len(ken_burns_cycle)],
                "text_overlay": {
                    "text": seg.get("text_overlay"),
                    "position": "bottom_center",
                    "duration_seconds": max(2.0, round(seg_duration * 0.7, 1))
                } if seg.get("text_overlay") else None,
                "transition_in": transition_cycle[i % len(transition_cycle)],
                "transition_out": transition_cycle[i % len(transition_cycle)]
            })

        # Sanitize filename
        safe_name = re.sub(r'[^\w\-]', '_', output_filename.strip())
        safe_name = re.sub(r'_+', '_', safe_name).strip('_')
        if not safe_name:
            safe_name = "my_video"
        if not safe_name.lower().endswith('.mp4'):
            safe_name += '.mp4'

        script_dict = {
            "project": {
                "title": title.strip() or "My Video",
                "output_filename": safe_name,
                "voice": voice,
                "voice_rate": "+0%",
                "voice_pitch": "+0Hz",
                "background_music": None,
                "visual_style": ai_style,
            },
            "segments": segments,
        }

        render_time = calculate_estimated_render_time(len(segments), voice, total_duration)

        return {
            "success": True,
            "fallback": False,
            "script": script_dict,
            "estimated_duration": total_duration,
            "estimated_render_time": render_time
        }

    except Exception as e:
        print(f"AI planner request failed: {e}. Falling back to rules.")
        script_dict = build_script(text, title, voice, output_filename, visual_style)
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
