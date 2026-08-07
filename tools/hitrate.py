import os, re, glob, json
import numpy as np, torch, open_clip
from PIL import Image

dev = "cpu"
model, _, pre = open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai", device=dev)
tok = open_clip.get_tokenizer("ViT-B-32")
model.eval()

paths = sorted(glob.glob("library/images/*"))
print(f"indexing {len(paths)} images ...", flush=True)
embs = []
with torch.no_grad():
    for i in range(0, len(paths), 16):
        batch = torch.stack([pre(Image.open(p).convert("RGB")) for p in paths[i:i+16]])
        e = model.encode_image(batch)
        embs.append((e / e.norm(dim=-1, keepdim=True)).cpu().numpy())
I = np.concatenate(embs).astype(np.float32)
np.savez("library/index.npz", emb=I, paths=np.array(paths))
print("index built", I.shape, flush=True)

# ---- queries: real segment prompts ----
qs = []
for pf in glob.glob("projects/*/image_prompts.txt"):
    for line in open(pf, encoding="utf-8", errors="replace"):
        m = re.match(r"^Segment\s+\S+\s*:\s*(.+)$", line.strip())
        if not m: continue
        t = m.group(1)
        t = re.sub(r"^Scene for '[^']*',\s*", "", t)
        t = re.split(r",\s*depicting:", t)[0]
        t = re.sub(r"<[^>]+>", "", t).strip()
        if len(t) > 15: qs.append((os.path.basename(os.path.dirname(pf)), t))
print(f"queries: {len(qs)}", flush=True)

with torch.no_grad():
    T = model.encode_text(tok([q[1] for q in qs], context_length=77))
    T = (T / T.norm(dim=-1, keepdim=True)).cpu().numpy().astype(np.float32)

S = T @ I.T
top = S.max(axis=1)
best = S.argmax(axis=1)
print("\n=== TOP-1 CLIP SIMILARITY ===")
for p in (10, 25, 50, 75, 90):
    print(f"  p{p:<2} {np.percentile(top,p):.3f}")
print(f"  mean {top.mean():.3f}   max {top.max():.3f}")
for th in (0.22, 0.25, 0.28, 0.30):
    print(f"  >= {th}: {(top>=th).sum():3d}/{len(top)}  ({100*(top>=th).mean():.0f}% covered)")
json.dump([{"q": qs[i][1][:110], "score": float(top[i]), "match": os.path.basename(paths[best[i]])}
           for i in np.argsort(-top)[:6]], open("library/_top_examples.json","w"), indent=1)
print("\nbest matches written to library/_top_examples.json")
