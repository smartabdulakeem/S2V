# S2V Video Renderer Skill

This skill allows an AI agent or automated developer script to programmatically convert raw narration scripts into fully edited, high-quality videos using S2V (Script-to-Video).

---

## 🏗️ Capability Overview

The S2V skill coordinates:
1. **AI Storyboard Planning:** Automatically splits long scripts into scenes, drafts visual generation prompts, schedules Ken Burns motions, and structures text overlays.
2. **Audio Synthesis:** Uses local offline Piper TTS or Microsoft Edge Neural TTS to generate narration tracks.
3. **AI Visual Sourcing:** Sources custom-aspect-ratio images from Hugging Face (FLUX.1-schnell) with Pollinations.ai fallback.
4. **Video Composition:** Composites images, ken-burns animations, captions, and text overlays into dynamic video segments.
5. **Stitching & Audio Mixing:** Combines all video segments and blends them with background music.

---

## 📋 Prerequisites

Before running the skill, ensure:
* **Python 3.10+** is installed on the host machine.
* **FFmpeg** binaries are placed in `vendor/ffmpeg/bin/` or added to the system `PATH`.
* **Hugging Face Access Token** is saved in `config/settings.json`.
* **Piper** binaries and models are available for local offline voiceovers.

---

## 🚀 How to Use the S2V Skill

### Step 1: Generate the Storyboard JSON Plan
Call the S2V planning agent in Python to split your text script into a JSON plan:

```python
import sys
import json
from pipeline.ai_agent import generate_storyboard_plan
from app import _load_settings

# Load settings & HF token
settings = _load_settings()
hf_token = settings.get("huggingface_api_key", "")

# Raw script narration text
script_text = "Your long narration script text goes here..."

# Plan the storyboard (returns standard S2V JSON)
result = generate_storyboard_plan(
    text=script_text,
    title="My Historical Documentary",
    voice="local:piper",  # Options: 'local:piper', 'edge:en-US-GuyNeural', etc.
    output_filename="my_documentary",
    visual_style="Cinematic photograph, dramatic natural lighting",
    hf_token=hf_token
)

if result["success"]:
    # Save the planned JSON script
    with open("my_script.json", "w", encoding="utf-8") as f:
        json.dump(result["script"], f, indent=2)
```

### Step 2: Render the Video via S2V CLI
Run the command-line rendering tool `cli.py` in your terminal, passing the path to the storyboard JSON script you created in Step 1:

```powershell
python cli.py my_script.json
```

This will run the entire compilation pipeline sequentially, print live progress logs, and save the final `.mp4` video inside the `output/` directory.

---

## 🛠️ JSON Schema Structure Reference

The JSON script passed to `cli.py` must match the following S2V schema:

```json
{
  "project": {
    "title": "My Documentary",
    "output_filename": "my_documentary.mp4",
    "voice": "local:piper",
    "voice_rate": "+0%",
    "voice_pitch": "+0Hz",
    "background_music": null,
    "visual_style": "Cinematic photograph, dramatic natural lighting",
    "aspect_ratio": "16:9"
  },
  "segments": [
    {
      "segment_id": 1,
      "type": "hook",
      "narration": "This is the first segment narration text.",
      "b_roll_keyword": "cinematic shot of ancient scrolls under warm sunlight",
      "visual_type": "ai_image",
      "ken_burns": "zoom_in",
      "text_overlay": {
        "text": "The Library of Baghdad",
        "position": "bottom_center",
        "duration_seconds": 3.0
      },
      "transition_in": "fade",
      "transition_out": "fade"
    }
  ]
}
```

---

## 🔌 Sub-skills

### Piper TTS Offline Synthesis
When the voiceover option is set to `local:piper`, the S2V rendering engine (`cli.py`) internally invokes the Piper binary located at `C:\Users\HomePC\Documents\GitHub\S2V\vendor\piper\piper.exe`.
If you need to test voiceover synthesis independently or debug voice assets, refer to the `piper-tts` skill and execute the wrapper script:
```powershell
C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe C:\Users\HomePC\Documents\GitHub\piper-desktop-skill\piper_skill.py "Text to render" -o "C:\Users\HomePC\Documents\GitHub\S2V\vendor\piper\voices\output.wav" -b "C:\Users\HomePC\Documents\GitHub\S2V\vendor\piper\piper.exe"
```

### AI Scenery Generation and Image Editing
When you need to manually generate concept art, scenery, or edit visual frames for S2V segments:
1. Refer to the `generate-image` skill.
2. Ensure you have `OPENROUTER_API_KEY` set in your `.env` configuration.
3. Run the generator script with the visual prompt (supports FLUX.2 and Gemini models):
```powershell
C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe scripts/generate_image.py "A beautiful cinematic landscape for scene" --model google/gemini-3-pro-image-preview
```

### Remotion Programmatic Video Rendering (Video Engine)
S2V compiles visual frames, subtitles, and audio tracks using the Remotion framework. 
Whenever you are making adjustments to the React compositions, styling sequences, handling canvas frame-rates, or interpolation curves for S2V rendering outputs:
1. Refer to the `remotion` skill.
2. Ensure you follow Remotion's frame-perfect rendering principles to avoid frame jitters and glitches in final video outputs.



