import os, glob, shutil
src = r"C:\Users\HomePC\.gemini\antigravity\brain\c590e5c6-bc5c-4bb8-a6ac-5c32e2024202"
dst = r"C:\Users\HomePC\Documents\GitHub\S2V\projects\S2E4_-_Ali_s_Silence"
for f in glob.glob(os.path.join(src, "s2e4_segment_*.png")):
    base = os.path.basename(f)
    parts = base.split('_')
    seg_id = parts[2]
    out_path = os.path.join(dst, seg_id + ".png")
    shutil.copy(f, out_path)
    print(f"Copied {base} to {seg_id}.png")
