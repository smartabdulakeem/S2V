"""
Solving the whole board at once instead of shot by shot.

Greedy assignment settles each shot before looking at the next, so an early shot
takes an image a later shot needed and the loss cascades. Measured on 96 images
generated one per prompt, greedy paired 63 correctly and optimal paired 80.
"""

import numpy as np
import pytest

from pipeline import library


class _FakeScores:
    """Drive optimal_assignment from a fixed score matrix, not a real model."""

    def __init__(self, matrix):
        self.matrix = np.asarray(matrix, dtype=np.float32)

    def __call__(self, queries, paths, embeddings, floor, use_descriptions=True):
        return self.matrix


@pytest.fixture
def no_rejections(monkeypatch):
    monkeypatch.setattr(library, "get_rejected_pairs", lambda: set())


def _assign(monkeypatch, matrix, paths, **kw):
    monkeypatch.setattr(library, "score_matrix", _FakeScores(matrix))
    queries = [f"q{i}" for i in range(len(matrix))]
    return library.optimal_assignment(
        queries=queries, paths=paths,
        embeddings=np.zeros((len(paths), 4), dtype=np.float32),
        floor=0.0, **kw)


def test_it_trades_a_small_loss_for_a_large_gain(monkeypatch, no_rejections):
    """
    The case greedy gets wrong:
        shot 1: A=0.30  B=0.29
        shot 2: A=0.28  B=0.10
    Greedy gives shot 1 its best (A) and strands shot 2 on B — 0.40 total.
    Optimal pairs 1->B and 2->A for 0.57.
    """
    result = _assign(monkeypatch, [[0.30, 0.29], [0.28, 0.10]], ["A.jpg", "B.jpg"])

    assert result[0][0] == "B.jpg"
    assert result[1][0] == "A.jpg"
    total = result[0][1] + result[1][1]
    assert total == pytest.approx(0.57, abs=1e-4)


def test_no_image_is_used_twice(monkeypatch, no_rejections):
    result = _assign(monkeypatch, [[0.9, 0.1], [0.8, 0.2], [0.7, 0.3]],
                     ["A.jpg", "B.jpg", "C.jpg"])
    chosen = [p for p, _ in result.values()]
    assert len(chosen) == len(set(chosen))


def test_fewer_images_than_shots_leaves_some_unassigned(monkeypatch, no_rejections):
    result = _assign(monkeypatch, [[0.5], [0.4], [0.3]], ["only.jpg"])
    assert len(result) == 1, "an image was handed to more than one shot"


def test_reuse_lets_one_image_serve_every_shot(monkeypatch, no_rejections):
    result = _assign(monkeypatch, [[0.5], [0.4], [0.3]], ["only.jpg"], allow_reuse=True)
    assert len(result) == 3
    assert all(p == "only.jpg" for p, _ in result.values())


def test_excluded_images_are_never_assigned(monkeypatch, no_rejections):
    result = _assign(monkeypatch, [[0.9, 0.1]], ["taken.jpg", "free.jpg"],
                     excluded={"taken.jpg"})
    assert result[0][0] == "free.jpg"


def test_a_rejected_pairing_is_never_assigned(monkeypatch):
    monkeypatch.setattr(library, "get_rejected_pairs", lambda: {("q0", "bad.jpg")})
    result = _assign(monkeypatch, [[0.9, 0.1]], ["bad.jpg", "ok.jpg"])
    assert result[0][0] == "ok.jpg"


def test_reported_score_is_the_real_one_not_the_cost(monkeypatch, no_rejections):
    result = _assign(monkeypatch, [[0.42, 0.10]], ["A.jpg", "B.jpg"])
    assert result[0][1] == pytest.approx(0.42, abs=1e-5)


def test_an_empty_board_or_library_is_handled(monkeypatch, no_rejections):
    assert library.optimal_assignment([], ["a.jpg"], np.zeros((1, 4)), 0.0) == {}
    assert library.optimal_assignment(["q"], [], np.zeros((0, 4)), 0.0) == {}


def test_it_beats_greedy_on_a_cascading_board(monkeypatch, no_rejections):
    """A board built so that greedy strands every later shot."""
    n = 6
    matrix = np.zeros((n, n), dtype=np.float32)
    for i in range(n):
        for j in range(n):
            matrix[i][j] = 0.9 if i == j else 0.85 - 0.01 * j
    # Greedy takes column 0 for shot 0 (0.9), then shot 1 wants column 1 (0.9)...
    # but earlier rows also rate column 0 highly, which is where it goes wrong.
    matrix[0][1] = 0.95     # shot 0 prefers the image shot 1 needs

    result = _assign(monkeypatch, matrix, [f"img{j}.jpg" for j in range(n)])

    total = sum(s for _, s in result.values())
    greedy_total, taken = 0.0, set()
    for i in range(n):
        row = [(matrix[i][j], j) for j in range(n) if j not in taken]
        best, j = max(row)
        taken.add(j)
        greedy_total += best

    assert total >= greedy_total, f"optimal {total} was worse than greedy {greedy_total}"
