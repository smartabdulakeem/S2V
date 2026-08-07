import sys
import os
import json

# Add parent directory to path to allow importing from pipeline
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.ai_agent import generate_storyboard_plan
from app import _load_settings

def main():
    settings = _load_settings()
    google_api_key = settings.get("google_api_key", "")
    
    # Generate a dummy long script (>800 words)
    paragraphs = []
    for i in range(25):
        paragraphs.append(
            f"This is paragraph {i+1} of our historical documentary. We are talking about the events "
            f"that unfolded in Al-Madinah and across the Arabian desert. The caliph Abu Bakr organized "
            f"eleven banners to secure the state. Many tribes rose up in rebellion, creating a vast "
            f"coalition of apostate forces that threatened the city of Madinat al-Salam. But with "
            f"resolute faith, Abu Bakr led his horsemen into battle at Dhu Khushub. They fought under "
            f"the scorching sun, charging the enemy lines again and again until victory was won. "
            f"This battle secured the capital and proved that the new caliphate was strong enough."
        )
    test_long_script = "\n\n".join(paragraphs)
    word_count = len(test_long_script.split())
    print(f"Generated a long test script with {word_count} words.")
    
    print("\n--- Testing Chunk-Based Storyboard Generation ---")
    result = generate_storyboard_plan(
        text=test_long_script,
        title="Long Test Video",
        voice="google:gemini-3.1-flash-tts-preview:Puck",
        output_filename="long_test",
        visual_style="cinematic, ancient realism",
        google_api_key=google_api_key,
        ai_guideline="Conversational delivery, highly dramatic"
    )
    
    if not result["success"]:
        print("Failed to generate long storyboard:", result.get("error_msg"))
        sys.exit(1)
        
    print("Storyboard generation SUCCESS!")
    print(f"Fallback used: {result['fallback']}")
    
    script_data = result["script"]
    print("\n--- Project Config ---")
    print(json.dumps(script_data["project"], indent=2))
    
    print(f"\nTotal generated scenes: {len(script_data['segments'])}")
    print("First segment:")
    print(json.dumps(script_data['segments'][0], indent=2))
    print("Last segment:")
    print(json.dumps(script_data['segments'][-1], indent=2))

if __name__ == "__main__":
    main()
