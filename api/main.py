import os
import sys
import json
import asyncio
import tempfile
import base64
from flask import Flask, request, jsonify

# Add parent directory to sys.path to import pipeline modules
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(base_dir)

from pipeline.ai_agent import generate_storyboard_plan
from pipeline.voiceover import generate_voiceover

app = Flask(__name__)

@app.route('/api/get_version', methods=['GET'])
def get_version():
    return jsonify({"version": "2.0.0 (Cloud)"})

@app.route('/api/preview_voice', methods=['POST'])
def preview_voice():
    try:
        data = request.get_json() or {}
        voice_id = data.get("voice_id", "")
        hf_key = data.get("hf_token", "")
        
        sample_text = (
            "Welcome. This is a cloud preview of the selected voice. "
            "You are listening to the narration quality."
        )
        
        # Write to Vercel's writable /tmp directory
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False, dir="/tmp") as f:
            tmp_path = f.name
            
        generate_voiceover(
            segment_id=0,
            narration=sample_text,
            voice=voice_id,
            voice_rate="+0%",
            voice_pitch="+0Hz",
            cache_dir="/tmp",
            huggingface_api_key=hf_key
        )
        
        generated_file = os.path.join("/tmp", "segment_0_audio.mp3")
        
        if not os.path.exists(generated_file):
            return jsonify({"success": False, "error": "Voice file was not generated."})
            
        with open(generated_file, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode("utf-8")
            
        try:
            os.unlink(generated_file)
            os.unlink(tmp_path)
        except OSError:
            pass
            
        return jsonify({"success": True, "audio_b64": audio_b64})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/parse_plain_text', methods=['POST'])
def parse_plain_text():
    try:
        data = request.get_json() or {}
        text = data.get("text", "")
        title = data.get("title", "")
        voice = data.get("voice", "")
        filename = data.get("filename", "")
        visual_style = data.get("visual_style", "")
        aspect_ratio = data.get("aspect_ratio", "16:9")
        hf_token = data.get("hf_token", "")

        res = generate_storyboard_plan(
            text=text,
            title=title,
            voice=voice,
            output_filename=filename,
            visual_style=visual_style,
            hf_token=hf_token
        )

        if not res.get("success"):
            return jsonify({"success": False, "errors": [res.get("error_msg", "Failed to plan storyboard")]})

        script_dict = res["script"]
        script_dict["project"]["aspect_ratio"] = aspect_ratio
        
        return jsonify({
            "success": True,
            "path": "cloud_script",
            "title": script_dict["project"]["title"],
            "segment_count": len(script_dict["segments"]),
            "estimated_duration": round(res["estimated_duration"]),
            "estimated_render_time": res["estimated_render_time"],
            "voice": script_dict["project"]["voice"],
            "output_filename": script_dict["project"]["output_filename"],
            "aspect_ratio": aspect_ratio,
            "fallback": res.get("fallback", False),
            "script_data": script_dict
        })
    except Exception as e:
        return jsonify({"success": False, "errors": [str(e)]})

@app.route('/api/save_edited_script', methods=['POST'])
def save_edited_script():
    return jsonify({"success": True})

@app.route('/api/start_render', methods=['POST'])
def start_render():
    return jsonify({
        "success": False, 
        "error": "Video rendering requires intense CPU rendering and FFmpeg binaries which are blocked by Vercel cloud function timeouts. To render the final video, please run this app locally using: python app.py"
    })

# fallback handler
@app.route('/api/', defaults={'path': ''})
@app.route('/api/<path:path>')
def catch_all(path):
    return jsonify({"error": "API route not found"}), 404
