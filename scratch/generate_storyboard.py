import sys
import os
import json

# Add parent directory to path to allow importing from pipeline
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.ai_agent import generate_storyboard_plan
from app import _load_settings

def main():
    raw_script_path = os.path.join(os.path.dirname(__file__), "ali_silence_raw.txt")
    with open(raw_script_path, "r", encoding="utf-8") as f:
        script_text = f.read()

    settings = _load_settings()
    hf_token = settings.get("huggingface_api_key", "")
    
    print("Generating storyboard plan using S2V AI Agent...")
    result = generate_storyboard_plan(
        text=script_text,
        title="S2E4 -- Ali's Silence",
        voice="edge:en-GB-RyanNeural",
        output_filename="alis_silence",
        visual_style="Cinematic historical drama style, deep warm colors, oil painting texture, soft natural lighting, dramatic shadow detail",
        hf_token=hf_token
    )
    
    if result["success"]:
        print("Storyboard plan generated successfully!")
        if result.get("fallback"):
            print("WARNING: Fell back to rule-based storyboard generation due to:", result.get("error_msg"))
        else:
            print("Hugging Face AI planner completed successfully.")
        
        script_json_path = os.path.join(os.path.dirname(__file__), "alis_silence.json")
        with open(script_json_path, "w", encoding="utf-8") as f:
            json.dump(result["script"], f, indent=2)
        print(f"Saved storyboard plan to: {script_json_path}")
        print(f"Estimated duration: {result.get('estimated_duration')} seconds")
        print(f"Estimated render time: {result.get('estimated_render_time')} seconds")
    else:
        print("Failed to generate storyboard plan:", result.get("error_msg"))

if __name__ == "__main__":
    main()
