import os,re,glob,json
import numpy as np, torch, open_clip
from PIL import Image
d=np.load("library/index.npz",allow_pickle=True); I=d["emb"]; paths=list(d["paths"])
model,_,pre=open_clip.create_model_and_transforms("ViT-B-32",pretrained="openai",device="cpu")
tok=open_clip.get_tokenizer("ViT-B-32"); model.eval()
qs=[]
for pf in glob.glob("projects/*/image_prompts.txt"):
    for line in open(pf,encoding="utf-8",errors="replace"):
        m=re.match(r"^Segment\s+\S+\s*:\s*(.+)$",line.strip())
        if not m: continue
        t=re.sub(r"^Scene for '[^']*',\s*","",m.group(1))
        t=re.sub(r"<[^>]+>","",re.split(r",\s*depicting:",t)[0]).strip()
        if len(t)>15: qs.append(t)
with torch.no_grad():
    T=model.encode_text(tok(qs,context_length=77)); T=(T/T.norm(dim=-1,keepdim=True)).numpy()
S=T@I.T
top1=S.max(axis=1); mean_all=S.mean(axis=1); best=S.argmax(axis=1)
# separation: how far above the *average* image does the best image score?
sep=top1-mean_all
sd=S.std(axis=1)
z=(top1-mean_all)/np.maximum(sd,1e-6)
print("=== SEPARATION (does retrieval beat picking at random?) ===")
print(f"  mean top-1              {top1.mean():.3f}")
print(f"  mean random-image score {mean_all.mean():.3f}")
print(f"  lift                    +{(top1-mean_all).mean():.3f}")
print(f"  z-score of top-1 vs library  mean {z.mean():.2f}  median {np.median(z):.2f}")
print(f"  queries where top-1 is >2sd above library mean: {(z>2).sum()}/{len(z)} ({100*(z>2).mean():.0f}%)")
print(f"  distinct images used as top-1: {len(set(best))}/{len(paths)}")
from collections import Counter
c=Counter(best.tolist()).most_common(3)
print("  most-returned image returned for", [f"{n} queries" for _,n in c])
# contact sheet of 4 best-scoring query/match pairs
order=np.argsort(-z)[:4]
sh=Image.new("RGB",(4*300,169),(18,18,18))
for i,qi in enumerate(order):
    im=Image.open(paths[best[qi]]).convert("RGB").resize((300,169)); sh.paste(im,(i*300,0))
sh.save(os.environ["SP"]+"/matches.png")
print("\n-- best 4 (query -> matched file) --")
for qi in order: print(f"  z={z[qi]:.1f}  {qs[qi][:70]!r} -> {os.path.basename(paths[best[qi]])}")
