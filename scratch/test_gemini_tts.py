import os
import sys

# Ensure S2V directory is in python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import _load_settings
from pipeline.voiceover import _generate_with_gemini_tts

def main():
    settings = _load_settings()
    google_key = settings.get("google_api_key", "").strip()
    if not google_key:
        print("[ERROR] google_api_key is missing in settings.json")
        sys.exit(1)
        
    print(f"Loaded google_api_key ending in: ...{google_key[-6:]}")
    
    output_path = "cache/test_gemini_voice.mp3"
    if os.path.exists(output_path):
        os.remove(output_path)
        
    print("Generating voiceover using gemini-3.1-flash-tts-preview...")
    try:
        _generate_with_gemini_tts(
            narration="Hello! This is a test of the Gemini 3.1 Flash Text-to-Speech preview voice.",
            voice="google:gemini-3.1-flash-tts-preview:Puck",
            google_api_key=google_key,
            output_path=output_path,
            voice_steering="Speak with a clear conversational tone.",
            segment_id=777
        )
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            print(f"[SUCCESS] Gemini TTS audio generated successfully! Size: {os.path.getsize(output_path)} bytes")
        else:
            print("[FAILED] Audio file is empty or not created.")
    except Exception as e:
        print(f"[FAILED] Error generating Gemini TTS: {e}")

if __name__ == "__main__":
    main()
