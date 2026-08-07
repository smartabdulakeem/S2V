import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import urllib.request
import json
import time
from app import _load_settings

def test_model(model_name):
    settings = _load_settings()
    hf_token = settings.get("huggingface_api_key", "")
    
    url = "https://router.huggingface.co/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {hf_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model_name,
        "messages": [
            {"role": "user", "content": "Say hello!"}
        ],
        "temperature": 0.1,
        "max_tokens": 50
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            print(f"[{model_name}] Success in {time.time() - t0:.2f}s: {content.strip()}")
            return True
    except Exception as e:
        print(f"[{model_name}] Failed in {time.time() - t0:.2f}s: {e}")
        return False

models = [
    "Qwen/Qwen2.5-7B-Instruct",
    "meta-llama/Llama-3.2-3B-Instruct",
    "meta-llama/Meta-Llama-3-8B-Instruct",
    "Qwen/Qwen2.5-72B-Instruct"
]

for m in models:
    test_model(m)
