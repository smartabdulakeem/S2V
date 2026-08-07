import json
with open('cache/planned_script.json', encoding='utf-8') as f:
    data = json.load(f)
    for s in data['segments'][8:]:
        print(f"Segment {s['segment_id']}:\n{s['narration']}\n")
