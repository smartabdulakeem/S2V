import os
import sys
import json
import urllib.request

# Ensure S2V directory is in python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import _load_settings
from pipeline.text_parser import _SPLIT_PROMPT, _GEMINI_URL

def main():
    settings = _load_settings()
    google_key = settings.get("google_api_key", "").strip()
    if not google_key:
        print("[ERROR] google_api_key is missing in settings.json")
        sys.exit(1)
        
    text = (
        "In the year 762, the Caliph Al-Mansur founded a city that would become the beating heart of human civilisation — a city of canals, libraries, and scholars. "
        "He called it Madinat al-Salam. The world would know it as Baghdad."
    )
    
    prompt = _SPLIT_PROMPT.format(
        title="Baghdad Test",
        visual_style="cinematic, highly detailed",
        script=text,
    )
    
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 8192,
        },
    }).encode("utf-8")
    
    print("Calling Gemini API...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={google_key}"
    print("Constructed URL:", url)
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        print("\n--- Raw Gemini Response ---")
        print(raw_text)
        print("---------------------------")
    except urllib.error.HTTPError as he:
        print(f"HTTP Error {he.code}: {he.reason}")
        print("Body:", he.read().decode("utf-8"))

if __name__ == "__main__":
    main()
