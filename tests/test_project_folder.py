"""
A project can work from its own small folder, and one image can carry a film.

Curating twenty pictures you chose is far quicker than steering retrieval across
twelve hundred, and some work — a motivational piece — is one image held for
fifteen minutes while the cutting and the motion carry it. Retrieval excluded any
image already used, so that second case was impossible: one match and ninety-four
gaps. `allow_image_reuse` existed as a setting that nothing read.
"""

import pytest
from PIL import Image

from pipeline import library


@pytest.fixture
def lib(tmp_path, monkeypatch):
    images_dir = tmp_path / "images"
    (images_dir / "motivation").mkdir(parents=True)
    (images_dir / "_inbox").mkdir(parents=True)
    monkeypatch.setattr(library, "ROOT", str(tmp_path))
    monkeypatch.setattr(library, "LIBRARY_DIR", str(tmp_path))
    monkeypatch.setattr(library, "IMAGES_DIR", str(images_dir))
    monkeypatch.setattr(library, "INDEX_PATH", str(tmp_path / "index.npz"))
    monkeypatch.setattr(library, "MANIFEST_PATH", str(tmp_path / "manifest.jsonl"))
    monkeypatch.setattr(library, "REJECTIONS_PATH", str(tmp_path / "rejections.jsonl"))
    monkeypatch.setattr(library, "RENDER_USAGE_PATH", str(tmp_path / "usage.json"))
    library._DESC_CACHE.clear()
    return images_dir


def _img(path, colour):
    Image.new("RGB", (64, 64), color=colour).save(path)


def test_subfolders_are_indexed_and_workspaces_are_not(lib):
    _img(lib / "root_one.jpg", (10, 20, 200))
    _img(lib / "motivation" / "sunrise.jpg", (250, 180, 40))
    _img(lib / "_inbox" / "unreviewed.jpg", (5, 5, 5))

    files = library.get_image_files()
    names = [f.replace("\\", "/") for f in files]

    assert any("root_one.jpg" in n for n in names)
    assert any("motivation/sunrise.jpg" in n for n in names)
    assert not any("_inbox" in n for n in names), "an inbox image was indexed"


def test_list_image_folders_reports_counts(lib):
    _img(lib / "root.jpg", (1, 2, 3))
    for i in range(3):
        _img(lib / "motivation" / f"m{i}.jpg", (i * 60, 100, 100))

    folders = library.list_image_folders()
    assert {"name": "motivation", "count": 3} in folders
    assert not any(f["name"].startswith("_") for f in folders)


def test_a_folder_restricts_retrieval_to_itself(lib):
    _img(lib / "outside.jpg", (10, 20, 200))
    _img(lib / "motivation" / "inside.jpg", (250, 180, 40))
    library.reindex(force=True)

    scoped = library.search("anything", k=10, min_score=0.0, folder="motivation")
    whole = library.search("anything", k=10, min_score=0.0)

    assert scoped, "the folder returned nothing at all"
    assert all("motivation/" in p for p, _ in scoped), scoped
    assert len(whole) > len(scoped)


def test_an_unknown_folder_returns_nothing_rather_than_everything(lib):
    _img(lib / "outside.jpg", (10, 20, 200))
    library.reindex(force=True)
    assert library.search("anything", k=5, min_score=0.0, folder="does_not_exist") == []


# ── Reuse ─────────────────────────────────────────────────────────────────────

def test_without_reuse_a_used_image_is_never_returned(lib):
    _img(lib / "only.jpg", (200, 100, 50))
    library.reindex(force=True)
    used = {"images/only.jpg"}
    assert library.search("anything", k=5, min_score=0.0, exclude=used, allow_reuse=False) == []


def test_with_reuse_one_image_can_serve_every_shot(lib):
    """The motivational case: a single picture, a whole film."""
    _img(lib / "motivation" / "only.jpg", (200, 100, 50))
    library.reindex(force=True)

    script = {
        "project": {"title": "Motivation", "image_folder": "motivation", "allow_image_reuse": True},
        "segments": [
            {"segment_id": i, "narration": "keep going",
             "shots": [{"shot_id": f"{i}a", "query": "sunrise over mountains"}]}
            for i in range(1, 9)
        ],
    }

    report = library.plan_shots(script, min_score=0.0, weak_band=0.0)

    assert report["gaps"] == 0, "a one-image project still produced gaps"
    used = [r["best_path"] for r in report["shot_reports"]]
    assert all("only.jpg" in p for p in used)
    assert len(used) == 8


def test_reuse_still_prefers_a_fresh_image_when_one_exists(lib):
    """Repeats are a fallback, not a shortcut — variety wins while it can."""
    for i in range(4):
        _img(lib / "motivation" / f"m{i}.jpg", (i * 60, 90, 180))
    library.reindex(force=True)

    script = {
        "project": {"title": "Variety", "image_folder": "motivation", "allow_image_reuse": True},
        "segments": [
            {"segment_id": i, "narration": "n",
             "shots": [{"shot_id": f"{i}a", "query": "blue canvas"}]}
            for i in range(1, 5)
        ],
    }
    report = library.plan_shots(script, min_score=0.0, weak_band=0.0)
    used = [r["best_path"] for r in report["shot_reports"]]

    assert len(set(used)) == 4, f"repeated an image while unused ones remained: {used}"
