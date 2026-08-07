import json

with open('cache/planned_script.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

for s in data['segments'][8:]:
    s['visual_type'] = 'ai_image'
    # Give it a dummy b-roll keyword if it was Placeholder, though it shouldn't matter since the file is present
    if "Placeholder" in s.get('b_roll_keyword', ''):
        s['b_roll_keyword'] = "historical 7th century arabian scene"

with open('cache/planned_script.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
print("Successfully reverted script visual types back to ai_image.")
