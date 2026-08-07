import sys
import os
import json

# Add parent directory to path to allow importing from pipeline
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.ai_agent import generate_storyboard_plan
from pipeline.voiceover import generate_voiceover
from pipeline.visuals import fetch_visual
from app import _load_settings

def main():
    settings = _load_settings()
    google_api_key = settings.get("google_api_key", "")
    
    # Simple short script for verification
    test_script_text = (
        "Every story has a room that the main narrative moves past too quickly. "
        "History told at the level of states and campaigns has no choice but to move at that speed. "
        "But in a house in Al-Madinah, connected to the mosque by a door that the Prophet had used, a man sat with his dying wife and did not move at all."
    )
    
    print("--- Testing Storyboard Generation with Custom Guideline ---")
    result = generate_storyboard_plan(
        text=test_script_text,
        title="Test Verification Project",
        voice="google:gemini-3.1-flash-tts-preview:Puck",
        output_filename="test_verification",
        visual_style="Modern 3D Render",
        google_api_key=google_api_key,
        ai_guideline="Nigerian English cadence, conversational delivery, highly dramatic visuals"
    )
    
    if not result["success"]:
        print("Failed to generate storyboard:", result.get("error_msg"))
        sys.exit(1)
        
    print("Storyboard generation SUCCESS!")
    print(f"Fallback used: {result['fallback']}")
    
    script_data = result["script"]
    print("\n--- Project Config ---")
    print(json.dumps(script_data["project"], indent=2))
    
    print("\n--- Storyboard Segments ---")
    for s in script_data["segments"]:
        print(f"\nSegment {s['segment_id']}:")
        print(f"  Narration: {s['narration']}")
        print(f"  Visual Prompt: {s['b_roll_keyword']}")
        print(f"  Voice Steering: {s.get('voice_steering')}")
        
    # Test manual visuals placeholder generation
    print("\n--- Testing Manual Visuals Placeholder Sourcing ---")
    cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache", "test_hash")
    os.makedirs(cache_dir, exist_ok=True)
    
    seg = script_data["segments"][0]
    visual_path = fetch_visual(
        segment_id=seg["segment_id"],
        keyword=seg["b_roll_keyword"],
        narration=seg["narration"],
        cache_dir=cache_dir,
        google_api_key=google_api_key,
        aspect_ratio="16:9",
        render_id="test_render_id",
        video_title="Test Verification Project",
        visual_style="Modern 3D Render"
    )
    print(f"Placeholder visual generated at: {visual_path}")
    
    # Check if image_prompts.txt is written
    project_slug = "Test_Verification_Project"
    project_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "projects", project_slug)
    prompts_file = os.path.join(project_dir, "image_prompts.txt")
    if os.path.exists(prompts_file):
        print(f"Prompts file written to: {prompts_file}")
        with open(prompts_file, "r", encoding="utf-8") as pf:
            print("Contents of image_prompts.txt:")
            print(pf.read())
            
    # Test Gemini 3.1 Flash TTS voiceover generation
    print("\n--- Testing Gemini 3.1 Flash TTS Voiceover ---")
    if google_api_key:
        try:
            audio_path = generate_voiceover(
                segment_id=seg["segment_id"],
                narration=seg["narration"],
                voice=script_data["project"]["voice"],
                voice_rate="+0%",
                voice_pitch="+0Hz",
                cache_dir=cache_dir,
                google_api_key=google_api_key,
                voice_steering=seg.get("voice_steering", "")
            )
            print(f"Voiceover generated successfully at: {audio_path}")
        except Exception as ex:
            print(f"Voiceover generation failed: {ex}")
    else:
        print("Skipping voiceover test because google_api_key is empty.")

if __name__ == "__main__":
    main()
