import json
with open(r'C:\Users\HomePC\.gemini\antigravity\brain\c590e5c6-bc5c-4bb8-a6ac-5c32e2024202\.system_generated\logs\transcript.jsonl', 'r', encoding='utf-8') as f:
    with open('keywords.txt', 'w', encoding='utf-8') as out:
        for line in f:
            data = json.loads(line)
            content = data.get('content', '')
            if content and '"segment_id": 9' in content and 'b_roll_keyword' in content:
                out.write(content + '\n---\n')
