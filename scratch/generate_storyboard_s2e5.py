import sys
import os
import json
import re

# Add parent directory to path to allow importing from pipeline
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.text_parser import extract_keyword
from pipeline.ai_agent import estimate_speech_duration, calculate_estimated_render_time

def split_narration(text: str, target_words: int = 35) -> list[str]:
    # Clean up whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    # Split on sentence boundaries
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    segments = []
    current_segment = []
    current_words = 0
    
    for sentence in sentences:
        words = len(sentence.split())
        if current_words + words > target_words + 10 and current_segment:
            segments.append(" ".join(current_segment))
            current_segment = [sentence]
            current_words = words
        else:
            current_segment.append(sentence)
            current_words += words
            
    if current_segment:
        segments.append(" ".join(current_segment))
        
    return segments

def main():
    raw_script_path = os.path.join(os.path.dirname(__file__), "caliph_goes_to_war_raw.txt")
    with open(raw_script_path, "r", encoding="utf-8") as f:
        script_text = f.read()

    print("Generating storyboard plan using customized rule-based sentence chunker...")
    
    # We strip title/header lines from the narration so the voice doesn't read the title card
    lines = script_text.splitlines()
    narr_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("S2E5") or line.startswith("Abu Bakr at Dhu Khushub"):
            continue
        narr_lines.append(line)
        
    clean_narration = " ".join(narr_lines)
    
    raw_segments = split_narration(clean_narration, target_words=32)
    print(f"Split script into {len(raw_segments)} segments.")
    
    segments = []
    total_duration = 0.0
    
    ken_burns_cycle = ["zoom_in", "pan_right", "zoom_out", "pan_left", "zoom_in", "zoom_out"]
    transition_cycle = ["fade", "crossfade", "fade", "crossfade"]
    
    # Let's add some meaningful text overlays for documentary visual interest
    overlays = {
        1: "DHU KHUSHUB — 632 CE",
        5: "THE FIRST CALIPH",
        9: "THE RIDDA WARS",
        13: "THE ARMY OF USAMAH",
        17: "AL-MADINAH",
        21: "DEFENSE OF THE CITY"
    }
    
    for i, narration in enumerate(raw_segments):
        seg_duration = estimate_speech_duration(narration)
        total_duration += seg_duration
        
        if i == 0:
            seg_type = "hook"
        elif i == len(raw_segments) - 1:
            seg_type = "conclusion"
        else:
            seg_type = "body"
            
        # Emotion Analysis & Voice Shift overrides
        voice_rate = "+0%"
        voice_pitch = "+0Hz"
        
        lower_narration = narration.lower()
        if any(w in lower_narration for w in ["war", "charge", "battle", "fight", "attack", "enemy", "scatter", "reorganize", "intimidated"]):
            voice_rate = "+5%"
            voice_pitch = "+2Hz"
        elif any(w in lower_narration for w in ["grief", "wept", "dying", "illness", "sad", "loss", "death"]):
            voice_rate = "-8%"
            voice_pitch = "-2Hz"
        elif any(w in lower_narration for w in ["gentleness", "softest", "tender"]):
            voice_rate = "-4%"
            voice_pitch = "+1Hz"
            
        # Add text overlay if configured for this scene
        text_overlay = None
        overlay_num = i + 1
        if overlay_num in overlays:
            text_overlay = {
                "text": overlays[overlay_num],
                "position": "bottom_center",
                "duration_seconds": min(4.0, round(seg_duration * 0.7, 1))
            }
            
        segments.append({
            "segment_id": i + 1,
            "type": seg_type,
            "narration": narration,
            "b_roll_keyword": extract_keyword(narration),
            "visual_type": "ai_image",
            "ken_burns": ken_burns_cycle[i % len(ken_burns_cycle)],
            "text_overlay": text_overlay,
            "transition_in": transition_cycle[i % len(transition_cycle)],
            "transition_out": transition_cycle[i % len(transition_cycle)],
            "voice_rate": voice_rate,
            "voice_pitch": voice_pitch
        })
        
    script_dict = {
        "project": {
            "title": "S2E5 -- The Caliph Goes to War",
            "output_filename": "the_caliph_goes_to_war.mp4",
            "voice": "edge:en-GB-RyanNeural",
            "voice_rate": "+0%",
            "voice_pitch": "+0Hz",
            "background_music": None,
            "visual_style": "Cinematic photograph, dramatic natural lighting, high detail historical realism, desert tones",
            "aspect_ratio": "4:3"
        },
        "segments": segments
    }
    
    script_json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache", "planned_script.json")
    os.makedirs(os.path.dirname(script_json_path), exist_ok=True)
    
    with open(script_json_path, "w", encoding="utf-8") as f:
        json.dump(script_dict, f, indent=2)
        
    render_time = calculate_estimated_render_time(len(segments), "edge:en-GB-RyanNeural", total_duration)
    print(f"Saved planned script to: {script_json_path}")
    print(f"Total segments planned: {len(segments)}")
    print(f"Estimated duration: {total_duration} seconds ({total_duration/60:.1f} mins)")
    print(f"Estimated render time: {render_time} seconds ({render_time/60:.1f} mins)")

if __name__ == "__main__":
    main()
