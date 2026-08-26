"""
Compare retrieval models on this library's own images.

The test is the real task: an image was generated from a prompt, and the filename
records that prompt. Given the prompt, can the model find the image it made?
Ground truth is exact, so this measures identification rather than opinion.

    python tools/benchmark_retrieval.py
    python tools/benchmark_retrieval.py --models ViT-B-32/openai ViT-B-16-SigLIP/webli
"""

import argparse
import os
import re
import sys
import time

import numpy as np
import torch
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import library  # noqa: E402


def descriptive_images(limit=120):
    """Images whose filename is the prompt they were generated from."""
    out = []
    for path in library.get_image_files():
        rel = os.path.relpath(path, library.ROOT).replace("\\", "/")
        desc = library.describe_image(rel)
        # Needs to read like a prompt, not a hash or a one-word name.
        if desc and len(desc.split()) >= 4:
            out.append((path, desc))
        if len(out) >= limit:
            break
    return out


def encode(model_name, pretrained, pairs, batch=32):
    import open_clip
    t0 = time.time()
    model, _, preprocess = open_clip.create_model_and_transforms(model_name, pretrained=pretrained)
    tokenizer = open_clip.get_tokenizer(model_name)
    model.eval()
    load_s = time.time() - t0

    t0 = time.time()
    img_vecs = []
    for i in range(0, len(pairs), batch):
        tensors = [preprocess(Image.open(p).convert("RGB")) for p, _ in pairs[i:i + batch]]
        with torch.no_grad():
            f = model.encode_image(torch.stack(tensors))
            f /= f.norm(dim=-1, keepdim=True)
        img_vecs.append(f.cpu().numpy())
    img = np.vstack(img_vecs).astype(np.float32)
    index_s = time.time() - t0

    t0 = time.time()
    with torch.no_grad():
        t = model.encode_text(tokenizer([d for _, d in pairs]))
        t /= t.norm(dim=-1, keepdim=True)
    txt = t.cpu().numpy().astype(np.float32)
    query_s = (time.time() - t0) / max(1, len(pairs))

    return img, txt, load_s, index_s, query_s


def score(img, txt):
    """Rank of the correct image for each prompt (1 is perfect)."""
    sims = np.dot(txt, img.T)                       # queries x images
    order = np.argsort(-sims, axis=1)
    ranks = np.array([int(np.where(order[i] == i)[0][0]) + 1 for i in range(len(txt))])
    return {
        "top1": float((ranks == 1).mean()),
        "top5": float((ranks <= 5).mean()),
        "median_rank": float(np.median(ranks)),
        "mean_rank": float(ranks.mean()),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+",
                    default=["ViT-B-32-quickgelu/openai", "ViT-B-16-SigLIP/webli"])
    ap.add_argument("--limit", type=int, default=120)
    args = ap.parse_args()

    pairs = descriptive_images(args.limit)
    print(f"benchmark set: {len(pairs)} images whose filename records their prompt\n")
    if len(pairs) < 10:
        print("Not enough descriptively-named images to measure anything. "
              "Generate images with prompt-based filenames first.")
        return

    print(f"{'model':<28} {'top-1':>7} {'top-5':>7} {'median':>7} {'mean':>7} "
          f"{'load':>7} {'index':>8} {'query':>8}")
    print("-" * 88)
    for spec in args.models:
        name, _, pretrained = spec.partition("/")
        try:
            img, txt, load_s, index_s, query_s = encode(name, pretrained or "openai", pairs)
        except Exception as e:
            print(f"{name:<28} FAILED: {type(e).__name__}: {str(e)[:40]}")
            continue
        s = score(img, txt)
        print(f"{name:<28} {s['top1']*100:>6.1f}% {s['top5']*100:>6.1f}% "
              f"{s['median_rank']:>7.0f} {s['mean_rank']:>7.1f} "
              f"{load_s:>6.1f}s {index_s:>7.1f}s {query_s*1000:>7.0f}ms")


if __name__ == "__main__":
    main()
