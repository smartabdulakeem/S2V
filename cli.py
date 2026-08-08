import os
import sys
import argparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

# Add vendor ffmpeg to PATH so moviepy/ffmpeg can find it
_vendor_ffmpeg = os.path.join(BASE_DIR, "vendor", "ffmpeg", "bin")
if os.path.exists(_vendor_ffmpeg):
    os.environ["PATH"] = _vendor_ffmpeg + os.pathsep + os.environ.get("PATH", "")
    os.environ["IMAGEIO_FFMPEG_EXE"] = os.path.join(_vendor_ffmpeg, "ffmpeg.exe")

from pipeline.orchestrator import RenderOrchestrator
from app import _load_settings

def main():
    parser = argparse.ArgumentParser(description="Smart Studio command line renderer.")
    parser.add_argument("script_path", help="Path to the JSON script file to render.")
    args = parser.parse_args()
    
    script_path = args.script_path
    if not os.path.exists(script_path):
        print(f"Error: Script file not found at {script_path}")
        sys.exit(1)
        
    settings = _load_settings()
    google_key = settings.get("google_api_key", "").strip()
    google_tts_key = settings.get("google_tts_api_key", "").strip()
    
    print(f"Starting Smart Studio render for: {script_path}")
    if google_key:
        print("Google API Key loaded.")
    else:
        print("Warning: Google API Key is missing.")
    if google_tts_key:
        print("Google Cloud TTS Key loaded.")
        
    def on_event(event):
        if event.get("type") == "log":
            print(f"[LOG] {event.get('message')}")
        elif event.get("type") == "progress":
            print(f"[PROGRESS] {event.get('message')}")
        elif event.get("type") == "stage":
            print(f"\n[STAGE {event.get('stage_num')}/{event.get('total_stages')}] {event.get('name')}")
        elif event.get("type") == "error":
            print(f"\n[ERROR] {event.get('message')}")
        elif event.get("type") == "complete":
            print(f"\n[COMPLETE] Video rendered successfully at: {event.get('output_path')}")
            
    orchestrator = RenderOrchestrator(base_dir=BASE_DIR, on_event=on_event)
    result = orchestrator.render(script_path, google_api_key=google_key, google_tts_api_key=google_tts_key)
    
    if result.get("success"):
        print("\nSmart Studio render finished successfully!")
        sys.exit(0)
    else:
        print(f"\nSmart Studio render failed: {result.get('error')}")
        sys.exit(1)

if __name__ == "__main__":
    main()
