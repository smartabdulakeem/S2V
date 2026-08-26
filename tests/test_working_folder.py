"""
Working from any folder on the machine.

A working folder is the handful of pictures chosen for one video, kept wherever
the user keeps them — a desktop folder, a Drive folder, anywhere. It is not a
library subfolder and may never become one; moving images into the library is the
user's decision, not the app's.
"""

import os

import pytest
from PIL import Image

from pipeline import library


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A library, plus a working folder that sits outside it."""
    images_dir = tmp_path / "library" / "images"
    images_dir.mkdir(parents=True)
    for i in range(4):
        Image.new("RGB", (64, 64), color=(i * 50, 70, 190)).save(images_dir / f"lib_{i}.jpg")

    outside = tmp_path / "Desktop" / "my project images"
    outside.mkdir(parents=True)

    monkeypatch.setattr(library, "ROOT", str(tmp_path))
    monkeypatch.setattr(library, "LIBRARY_DIR", str(tmp_path / "library"))
    monkeypatch.setattr(library, "IMAGES_DIR", str(images_dir))
    monkeypatch.setattr(library, "INDEX_PATH", str(tmp_path / "library" / "index.npz"))
    monkeypatch.setattr(library, "MANIFEST_PATH", str(tmp_path / "library" / "manifest.jsonl"))
    monkeypatch.setattr(library, "REJECTIONS_PATH", str(tmp_path / "library" / "rej.jsonl"))
    monkeypatch.setattr(library, "RENDER_USAGE_PATH", str(tmp_path / "library" / "use.json"))
    monkeypatch.setattr(library, "FOLDER_INDEX_DIR", str(tmp_path / "cache" / "folder_index"))
    library._DESC_CACHE.clear()
    library.reindex(force=True)
    return images_dir, outside


def _img(path, colour):
    Image.new("RGB", (64, 64), color=colour).save(path)


def test_a_folder_outside_the_library_can_be_indexed(workspace):
    _, outside = workspace
    _img(outside / "sunrise over mountains.jpg", (250, 180, 40))
    _img(outside / "lone figure walking.jpg", (40, 40, 90))

    count, _ = library.index_folder(str(outside))
    assert count == 2

    emb, paths = library.load_folder_index(str(outside))
    assert len(paths) == 2
    # This folder is outside the *library* but still inside the project, so the
    # portable form is relative. Genuinely external folders are covered by
    # test_a_folder_outside_the_project_keeps_an_absolute_path.
    assert all(library.resolve_library_path(p) for p in paths), paths


def test_search_uses_only_the_working_folder(workspace):
    _, outside = workspace
    _img(outside / "sunrise.jpg", (250, 180, 40))
    library.index_folder(str(outside))

    results = library.search("anything", k=10, min_score=0.0, folder=str(outside))

    assert results, "the working folder returned nothing"
    assert all("sunrise" in p for p, _ in results)
    assert not any("lib_" in p for p, _ in results)


def test_the_whole_library_is_used_when_no_folder_is_set(workspace):
    results = library.search("anything", k=10, min_score=0.0)
    assert any("lib_" in p for p, _ in results)


def test_plan_shots_honours_a_working_folder(workspace):
    _, outside = workspace
    _img(outside / "sunrise over mountains.jpg", (250, 180, 40))
    library.index_folder(str(outside))

    script = {
        "project": {"title": "Outside", "image_folder": str(outside), "allow_image_reuse": True},
        "segments": [
            {"segment_id": i, "narration": "n",
             "shots": [{"shot_id": f"{i}a", "query": "sunrise over mountains"}]}
            for i in range(1, 5)
        ],
    }
    report = library.plan_shots(script, min_score=0.0, weak_band=0.0)

    assert report["gaps"] == 0
    assert all("sunrise" in r["best_path"] for r in report["shot_reports"])


def test_adding_an_image_to_the_working_folder_is_picked_up(workspace):
    _, outside = workspace
    _img(outside / "first.jpg", (10, 200, 10))
    library.index_folder(str(outside))
    assert len(library.load_folder_index(str(outside))[1]) == 1

    _img(outside / "second.jpg", (200, 10, 10))
    emb, paths = library.load_folder_index(str(outside))

    assert len(paths) == 2, "a new image in the working folder was not picked up"


def test_a_remembered_library_image_does_not_survive_the_switch(workspace):
    """
    The board remembers what each shot settled on so one fix does not reshuffle
    the rest. That memory is consulted before any search, so choosing a working
    folder changed nothing at all: every shot still held a library image.
    """
    _, outside = workspace
    _img(outside / "sunrise over mountains.jpg", (250, 180, 40))
    library.index_folder(str(outside))

    script = {
        "project": {"title": "Switch", "image_folder": str(outside), "allow_image_reuse": True},
        "segments": [{
            "segment_id": 1, "narration": "n",
            "shots": [{"shot_id": "1a", "query": "sunrise over mountains",
                       "resolved": "library/images/lib_0.jpg", "resolved_score": 0.31}],
        }],
    }

    report = library.plan_shots(script, min_score=0.0, weak_band=0.0)
    best = report["shot_reports"][0]["best_path"]

    assert "lib_0.jpg" not in best, "a library image survived the switch to a working folder"
    assert "sunrise" in best


def test_a_remembered_image_inside_the_folder_is_kept(workspace):
    """Stability still holds within the chosen source."""
    _, outside = workspace
    _img(outside / "a.jpg", (250, 180, 40))
    _img(outside / "b.jpg", (30, 60, 200))
    library.index_folder(str(outside))
    kept = os.path.join(str(outside), "b.jpg").replace("\\", "/")

    script = {
        "project": {"title": "Keep", "image_folder": str(outside), "allow_image_reuse": True},
        "segments": [{
            "segment_id": 1, "narration": "n",
            "shots": [{"shot_id": "1a", "query": "anything",
                       "resolved": kept, "resolved_score": 0.30}],
        }],
    }
    report = library.plan_shots(script, min_score=0.0, weak_band=0.0)
    assert report["shot_reports"][0]["best_path"] == kept


def test_clearing_out_of_scope_choices_reports_what_it_dropped(workspace):
    _, outside = workspace
    inside = os.path.join(str(outside), "keep.jpg").replace("\\", "/")

    script = {"segments": [
        {"segment_id": 1, "shots": [{"shot_id": "1a", "source": "pin",
                                     "pin": "library/images/lib_0.jpg"}]},
        {"segment_id": 2, "shots": [{"shot_id": "2a",
                                     "resolved": "library/images/lib_1.jpg",
                                     "resolved_score": 0.3}]},
        {"segment_id": 3, "shots": [{"shot_id": "3a", "source": "pin", "pin": inside}]},
    ]}

    cleared = library.clear_out_of_scope_choices(script, str(outside))

    assert cleared == {"pins": 1, "resolved": 1}
    assert "pin" not in script["segments"][0]["shots"][0]
    assert script["segments"][0]["shots"][0]["source"] == "library"
    assert "resolved" not in script["segments"][1]["shots"][0]
    assert script["segments"][2]["shots"][0]["pin"] == inside, "an in-folder pin was dropped"


def test_clearing_with_no_folder_keeps_everything(workspace):
    script = {"segments": [
        {"segment_id": 1, "shots": [{"shot_id": "1a", "source": "pin",
                                     "pin": "library/images/lib_0.jpg"}]},
    ]}
    assert library.clear_out_of_scope_choices(script, "") == {"pins": 0, "resolved": 0}
    assert script["segments"][0]["shots"][0]["pin"] == "library/images/lib_0.jpg"


def test_a_folder_inside_the_project_yields_relative_paths(workspace, monkeypatch, tmp_path):
    """
    A working folder is often a folder of the project itself. Storing those
    images absolutely made every pin fail validation with "path must stay inside
    the project", so no render could start.
    """
    _, _ = workspace
    inside = tmp_path / "library" / "_downloads"
    inside.mkdir(parents=True)
    _img(inside / "picked.jpg", (10, 200, 30))

    library.index_folder(str(inside))
    _, paths = library.load_folder_index(str(inside))

    assert paths, "nothing indexed"
    assert not os.path.isabs(paths[0]), f"stored an absolute path: {paths[0]}"
    assert paths[0] == "library/_downloads/picked.jpg"


def test_a_folder_outside_the_project_keeps_an_absolute_path(tmp_path, monkeypatch):
    """There is no relative path to give for a desktop folder."""
    monkeypatch.setattr(library, "ROOT", str(tmp_path / "repo"))
    monkeypatch.setattr(library, "FOLDER_INDEX_DIR", str(tmp_path / "cache"))
    outside = tmp_path / "elsewhere"
    outside.mkdir(parents=True)
    _img(outside / "far away.jpg", (200, 40, 40))

    library.index_folder(str(outside))
    _, paths = library.load_folder_index(str(outside))

    assert os.path.isabs(paths[0].replace("/", os.sep))


def test_scope_matches_relative_and_absolute_forms(tmp_path, monkeypatch):
    monkeypatch.setattr(library, "ROOT", str(tmp_path))
    monkeypatch.setattr(library, "IMAGES_DIR", str(tmp_path / "library" / "images"))
    folder = str(tmp_path / "library" / "_downloads")

    assert library._path_in_scope("library/_downloads/a.jpg", folder)
    assert library._path_in_scope(os.path.join(folder, "a.jpg"), folder)
    assert not library._path_in_scope("library/images/other.jpg", folder)
    assert library._path_in_scope("anything at all.jpg", "")


def test_an_empty_or_missing_folder_is_handled(workspace, tmp_path):
    _, outside = workspace
    count, _ = library.index_folder(str(outside))
    assert count == 0
    assert library.folder_image_files(str(tmp_path / "nope")) == []
