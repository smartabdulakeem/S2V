import os

ext_dir = r"C:\Users\HomePC\Documents\GitHub\google-flow-automator"
for root, dirs, files in os.walk(ext_dir):
    for file in files:
        if file.endswith((".js", ".html", ".json", ".css")):
            filepath = os.path.join(root, file)
            print(f"\n========================================")
            print(f"FILE: {file} ({filepath})")
            print(f"========================================")
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    print(f.read())
            except Exception as e:
                print(f"Error reading {file}: {e}")
