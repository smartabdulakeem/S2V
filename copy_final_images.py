import os, glob, shutil

src = r"C:\Users\HomePC\.gemini\antigravity\brain\c590e5c6-bc5c-4bb8-a6ac-5c32e2024202"
dst = r"C:\Users\HomePC\Documents\GitHub\S2V\projects\S2E4_-_Ali_s_Silence"

mapping = {
    "9": ["9a.png"],
    "9b": ["9b.png"],
    "10": ["10.png"],
    "11": ["11.png"],
    "12": ["12a.png"],
    "12b": ["12b.png"],
    "13": ["13a.png", "13b.png"],
    "14": ["14.png"],
    "15": ["15a.png", "15b.png"],
    "16": ["16.png"],
    "17": ["17.png"],
    "18": ["18a.png", "18b.png"],
    "19": ["19a.png", "19b.png"]
}

for prefix, targets in mapping.items():
    pattern = os.path.join(src, f"s2e4_segment_{prefix}_*.png")
    files = glob.glob(pattern)
    if files:
        # Find the most recently modified one if there are multiples
        newest = max(files, key=os.path.getmtime)
        for target in targets:
            out_path = os.path.join(dst, target)
            shutil.copy(newest, out_path)
            print(f"Copied {os.path.basename(newest)} to {target}")
    else:
        print(f"No file found for prefix {prefix}")
