"""
Greedy versus optimal assignment, on this library's own images.

The test mirrors the real workflow: an image was generated from a shot's prompt
and its filename records that prompt. Given those prompts as the shot queries,
how many images end up on the shot they were made for?

Ground truth is exact, so this measures pairing rather than opinion.

    python tools/benchmark_assignment.py
"""

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import library  # noqa: E402


def benchmark_set(limit=96):
    pairs = []
    for path in library.get_image_files():
        rel = os.path.relpath(path, library.ROOT).replace("\\", "/")
        desc = library.describe_image(rel)
        if desc and len(desc.split()) >= 4:
            pairs.append((rel, desc))
        if len(pairs) >= limit:
            break
    return pairs


def greedy(queries, paths, emb, floor):
    """One shot at a time, first come first served — the old behaviour."""
    scores = library.score_matrix(queries, paths, emb, floor)
    taken, out = set(), {}
    for i in range(len(queries)):
        row = scores[i].copy()
        for j in taken:
            row[j] = -np.inf
        j = int(np.argmax(row))
        if np.isfinite(row[j]):
            taken.add(j)
            out[i] = j
    return out


def main():
    pairs = benchmark_set()
    if len(pairs) < 10:
        print("Not enough descriptively-named images to measure.")
        return

    paths = [p for p, _ in pairs]
    queries = [d for _, d in pairs]
    truth = {i: i for i in range(len(pairs))}      # image i was made for query i

    emb_all, all_paths = library.load_index()
    lookup = {p.replace("\\", "/"): k for k, p in enumerate(all_paths)}
    idx = [lookup[p] for p in paths if p in lookup]
    if len(idx) != len(paths):
        print("Some benchmark images are missing from the index; run Refresh library.")
        return
    emb = np.asarray(emb_all)[idx]
    floor = library.get_calibrated_min_score(series_slug="islamic_history")

    print(f"benchmark: {len(pairs)} images, each generated from one prompt")
    print(f"match floor: {floor}\n")

    t = time.time()
    g = greedy(queries, paths, emb, floor)
    g_time = time.time() - t
    g_correct = sum(1 for i, j in g.items() if j == truth[i])

    t = time.time()
    o = library.optimal_assignment(queries, paths, emb, floor)
    o_time = time.time() - t
    o_correct = sum(1 for i, (p, _) in o.items() if p == paths[truth[i]])

    n = len(pairs)
    print(f"{'method':<24} {'correct pairings':>18} {'accuracy':>10} {'time':>8}")
    print("-" * 64)
    print(f"{'greedy (before)':<24} {g_correct:>10} / {n:<5} {g_correct/n*100:>9.1f}% {g_time*1000:>7.0f}ms")
    print(f"{'optimal (after)':<24} {o_correct:>10} / {n:<5} {o_correct/n*100:>9.1f}% {o_time*1000:>7.0f}ms")

    if g_correct:
        print(f"\nchange: {(o_correct - g_correct)} more shots got the image made for them "
              f"({(o_correct/max(1,g_correct) - 1) * 100:+.0f}%)")


if __name__ == "__main__":
    main()
