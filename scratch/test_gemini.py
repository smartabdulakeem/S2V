import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import urllib.request
import json
from app import _load_settings

def test_url(url_template, model):
    settings = _load_settings()
    key = settings.get("google_api_key", "")
    url = url_template.format(model=model, key=key)
    
    body = json.dumps({
        "contents": [{"parts": [{"text": "Hello!"}]}]
    }).encode("utf-8")
    
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"[{model}] Success!")
            return True
    except Exception as e:
        print(f"[{model}] Failed: {e}")
        return False

models = [
    "gemini-2.0-flash",
    "gemini-2.0-flash-exp",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]

url_templates = [
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
    "https://generativelanguage.googleapis.com/v1/models/{model}:generateContent?key={key}",
]

for url_t in url_templates:
    print(f"Testing URL template: {url_t}")
    for m in models:
        test_url(url_t, m)
