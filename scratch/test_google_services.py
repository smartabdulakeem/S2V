import os
import sys
import json
import base64
import urllib.request

# Setup path to include project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import _load_settings
from pipeline.visuals import _fetch_google_imagen_image
from pipeline.voiceover import _generate_with_google_tts

def test_google_imagen(api_key):
    print("\n--- Testing Google Imagen 3 (Image Generation) ---")
    prompt = "A high-quality cinematic historical shot of a library in ancient Baghdad, golden hour light, photorealistic, 16:9 aspect ratio"
    output_path = "cache/test_google_image.jpg"
    
    # Ensure cache folder exists
    os.makedirs("cache", exist_ok=True)
    if os.path.exists(output_path):
        os.remove(output_path)
        
    print(f"Sending prompt: {prompt}")
    success = _fetch_google_imagen_image(
        segment_id=999,
        prompt=prompt,
        width=1280,
        height=720,
        google_api_key=api_key,
        output_path=output_path,
        on_progress=print
    )
    
    if success and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        print(f"[SUCCESS] Image generated and saved to: {output_path} (Size: {os.path.getsize(output_path)} bytes)")
        return True
    else:
        print("[FAILED] Image was not generated.")
        return False

def test_google_tts(api_key):
    print("\n--- Testing Google Cloud Text-to-Speech (Journey Voice) ---")
    narration = "This is a premium Journey voice from Google Cloud. Pronunciation test for Ali ibn Abi Talib."
    output_path = "cache/test_google_audio.mp3"
    
    if os.path.exists(output_path):
        os.remove(output_path)
        
    print(f"Sending text: {narration}")
    try:
        _generate_with_google_tts(
            narration=narration,
            voice="google:en-US-Journey-F",
            voice_rate="+0%",
            voice_pitch="+0Hz",
            google_api_key=api_key,
            output_path=output_path,
            on_progress=print,
            segment_id=999
        )
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            print(f"[SUCCESS] Voice generated and saved to: {output_path} (Size: {os.path.getsize(output_path)} bytes)")
            return True
        else:
            print("[FAILED] Audio file was not created or empty.")
            return False
    except Exception as e:
        print(f"[FAILED] Raised exception: {e}")
        return False

def main():
    settings = _load_settings()
    api_key = settings.get("google_api_key", "").strip()
    tts_key = settings.get("google_tts_api_key", "").strip()
    if not tts_key:
        tts_key = api_key
    
    if not api_key:
        print("[ERROR] google_api_key is missing in config/settings.json.")
        print("Please save your Google API Key in the UI settings or manually edit config/settings.json.")
        sys.exit(1)
        
    print(f"Loaded Google API Key (Gemini/Imagen) ending in: ...{api_key[-6:]}")
    print(f"Loaded Google Cloud TTS API Key ending in: ...{tts_key[-6:]}")
    
    imagen_ok = test_google_imagen(api_key)
    tts_ok = test_google_tts(tts_key)
    
    print("\n--- Test Results Summary ---")
    print(f"Google Imagen 3: {'PASS' if imagen_ok else 'FAIL'}")
    print(f"Google Cloud TTS: {'PASS' if tts_ok else 'FAIL'}")
    
    if imagen_ok and tts_ok:
        print("\n[SUCCESS] All Google integration tests passed successfully!")
        sys.exit(0)
    else:
        print("\n[WARNING] Some tests failed. Please review errors above.")
        sys.exit(1)

if __name__ == "__main__":
    main()
