"""
Indexing must cost what changed, not what exists.

reindex() re-embedded the whole library on any change. With 1,176 images that was
182 seconds of CLIP before the storyboard could show anything — and the intended
workflow is growing the library one image at a time, which made the cheapest
action the most expensive one.
"""

import os
import time

import numpy as np
import pytest
from PIL import Image

from pipeline import library


@pytest.fixture
def lib(tmp_path, monkeypatch):
    images_dir = tmp_path / "images"
    images_dir.mkdir(parents=True)
    monkeypatch.setattr(library, "ROOT", str(tmp_path))
    monkeypatch.setattr(library, "LIBRARY_DIR", str(tmp_path))
    monkeypatch.setattr(library, "IMAGES_DIR", str(images_dir))
    monkeypatch.setattr(library, "INDEX_PATH", str(tmp_path / "index.npz"))
    return images_dir


def _add(images_dir, name, colour):
    Image.new("RGB", (64, 64), color=colour).save(images_dir / name)


def _add_after_index(images_dir, name, colour):
    """
    Add an image that is unambiguously newer than the index file.

    Do NOT backdate the index with os.utime to fake this: images written moments
    earlier then look newer than the index too, and every one of them gets
    re-embedded. That made these tests pass alone — where the CLIP model load
    filled the gap — and fail in the full suite where the model was already
    loaded. A real pause is the honest way to order two timestamps.
    """
    time.sleep(0.05)
    _add(images_dir, name, colour)


def test_adding_one_image_only_embeds_that_image(lib):
    for i in range(6):
        _add(lib, f"img_{i}.jpg", (i * 30, 80, 200))
    count, _ = library.reindex(force=True)
    assert count == 6

    notes = []
    _add_after_index(lib, "brand_new.jpg", (10, 220, 10))

    count, _ = library.reindex(on_progress=notes.append)

    assert count == 7
    assert any("Indexing 1 new or changed" in n for n in notes), notes


def test_existing_embeddings_are_reused_not_recomputed(lib):
    for i in range(4):
        _add(lib, f"img_{i}.jpg", (i * 40, 90, 180))
    library.reindex(force=True)
    before_emb, before_paths = library.load_index()
    keep = {p: before_emb[i] for i, p in enumerate(before_paths)}

    _add_after_index(lib, "extra.jpg", (250, 5, 5))
    library.reindex()

    after_emb, after_paths = library.load_index()
    for i, p in enumerate(after_paths):
        if p in keep:
            np.testing.assert_array_almost_equal(
                after_emb[i], keep[p], err_msg=f"{p} was needlessly re-embedded"
            )


def test_deleting_an_image_drops_it_from_the_index(lib):
    for i in range(5):
        _add(lib, f"img_{i}.jpg", (i * 40, 70, 160))
    library.reindex(force=True)

    os.remove(lib / "img_2.jpg")
    count, _ = library.reindex()

    _, paths = library.load_index()
    assert count == 4
    assert not any(p.endswith("img_2.jpg") for p in paths)


def test_a_replaced_image_is_re_embedded(lib):
    _add(lib, "a.jpg", (10, 10, 200))
    _add(lib, "b.jpg", (200, 10, 10))
    library.reindex(force=True)
    before, paths = library.load_index()
    idx = [i for i, p in enumerate(paths) if p.endswith("a.jpg")][0]
    original = before[idx].copy()

    # Overwrite a.jpg with a very different picture, newer than the index.
    time.sleep(0.05)
    Image.new("RGB", (64, 64), color=(240, 240, 20)).save(lib / "a.jpg")
    library.reindex()

    after, after_paths = library.load_index()
    idx2 = [i for i, p in enumerate(after_paths) if p.endswith("a.jpg")][0]
    assert not np.allclose(after[idx2], original), "a changed image kept its stale embedding"


def test_index_stays_aligned_with_paths(lib):
    for i in range(7):
        _add(lib, f"img_{i}.jpg", (i * 25, 60, 140))
    library.reindex(force=True)
    _add_after_index(lib, "late.jpg", (5, 5, 5))
    library.reindex()

    emb, paths = library.load_index()
    assert len(emb) == len(paths) == 8
    norms = np.linalg.norm(emb, axis=1)
    assert np.all(norms > 0.9), "some rows were left as zeros"
