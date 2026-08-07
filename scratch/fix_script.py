import json

script_path = r"C:\Users\HomePC\Documents\GitHub\S2V\cache\planned_script.json"

with open(script_path, "r", encoding="utf-8") as f:
    data = json.load(f)

for seg in data["segments"]:
    seg["visual_type"] = "ai_image"
    seg["transition_in"] = "fade"
    seg["transition_out"] = "fade"

with open(script_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("Successfully updated planned_script.json with visual_type and transition fields!")
