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
    parser = argparse.ArgumentParser(description="S2V Command Line Interface for rendering videos.")
    parser.add_argument("script_path", help="Path to the JSON script file to render.")
    args = parser.parse_args()
    
    script_path = args.script_path
    if not os.path.exists(script_path):
        print(f"Error: Script file not found at {script_path}")
        sys.exit(1)
        
    settings = _load_settings()
    hf_key = settings.get("huggingface_api_key", "")
    
    print(f"Starting S2V CLI Render for: {script_path}")
    if hf_key:
        print("Hugging Face Access Token loaded.")
    else:
        print("Warning: Hugging Face Token is missing. Visuals will fall back to Pollinations.")
        
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
    result = orchestrator.render(script_path, hf_key)
    
    if result.get("success"):
        print("\nS2V Render finished successfully!")
        sys.exit(0)
    else:
        print(f"\nS2V Render failed: {result.get('error')}")
        sys.exit(1)

if __name__ == "__main__":
    main()
