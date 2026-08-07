import urllib.request
import json

def test():
    hf_token = "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"
    url = "https://router.huggingface.co/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {hf_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "Qwen/Qwen2.5-72B-Instruct",
        "messages": [
            {"role": "user", "content": "Say hello!"}
        ],
        "temperature": 0.1,
        "max_tokens": 50
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print("Response:", data["choices"][0]["message"]["content"])
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test()
