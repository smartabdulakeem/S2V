"""
The Replace modal's backend actions.

Both buttons existed in the UI for a while with nothing behind them: "Never suggest
for this" never wrote a rejection (library/rejections.jsonl did not exist on disk),
and "Retire it" had no implementation at all. These tests call the API methods the
way the modal does.
"""

import json
import os

import pytest
from PIL import Image

import app as smart_studio_app
from pipeline import library


@pytest.fixture
def api(tmp_path, monkeypatch):
    """An Api instance pointed at a throwaway library."""
    images_dir = tmp_path / "library" / "images"
    images_dir.mkdir(parents=True)
    for i in range(3):
        Image.new("RGB", (48, 48), color=(i * 60, 80, 160)).save(images_dir / f"img_{i}.jpg")

    monkeypatch.setattr(library, "ROOT", str(tmp_path))
    monkeypatch.setattr(library, "LIBRARY_DIR", str(tmp_path / "library"))
    monkeypatch.setattr(library, "IMAGES_DIR", str(images_dir))
    monkeypatch.setattr(library, "INDEX_PATH", str(tmp_path / "library" / "index.npz"))
    monkeypatch.setattr(library, "REJECTIONS_PATH", str(tmp_path / "library" / "rejections.jsonl"))
    monkeypatch.setattr(library, "MANIFEST_PATH", str(tmp_path / "library" / "manifest.jsonl"))
    monkeypatch.setattr(library, "RENDER_USAGE_PATH", str(tmp_path / "library" / "render_usage.json"))
    monkeypatch.setattr(smart_studio_app, "BASE_DIR", str(tmp_path))

    library.reindex(force=True)
    return smart_studio_app.Api()


def test_reject_shot_image_writes_a_rejection_search_honours(api, tmp_path):
    """The rejection must reach disk and change what search returns."""
    query = "blue canvas"
    top_path, _ = library.search(query, k=1, min_score=0.0)[0]

    res = api.reject_shot_image(query, top_path)
    assert res["success"] is True

    rejections = tmp_path / "library" / "rejections.jsonl"
    assert rejections.exists(), "rejection was reported saved but no file was written"

    record = json.loads(rejections.read_text(encoding="utf-8").strip().splitlines()[0])
    assert record["query"] == query
    assert record["image_path"] == top_path

    returned = [p for p, _ in library.search(query, k=5, min_score=0.0)]
    assert top_path not in returned, "rejected image is still being suggested"


def test_reject_shot_image_rejects_empty_input(api):
    assert api.reject_shot_image("", "library/images/img_0.jpg")["success"] is False
    assert api.reject_shot_image("a query", "")["success"] is False


def test_retire_moves_the_file_and_drops_it_from_search(api, tmp_path):
    """Retire takes the image out of retrieval but must keep the file recoverable."""
    target = "library/images/img_1.jpg"
    assert (tmp_path / "library" / "images" / "img_1.jpg").exists()

    res = api.retire_library_image(target)
    assert res["success"] is True

    assert not (tmp_path / "library" / "images" / "img_1.jpg").exists()
    retired = tmp_path / "library" / "_retired" / "img_1.jpg"
    assert retired.exists(), "retired image was not recoverable — it must be moved, never deleted"

    indexed = [p.replace("\\", "/") for p in library.load_index()[1]]
    assert target not in indexed, "retired image is still in the search index"


def test_retire_does_not_collide_with_an_existing_retired_name(api, tmp_path):
    """Retiring two images with the same basename must not overwrite the first."""
    retired_dir = tmp_path / "library" / "_retired"
    retired_dir.mkdir(parents=True)
    (retired_dir / "img_2.jpg").write_bytes(b"the original")

    res = api.retire_library_image("library/images/img_2.jpg")
    assert res["success"] is True

    assert (retired_dir / "img_2.jpg").read_bytes() == b"the original"
    assert (retired_dir / "img_2_1.jpg").exists()


def test_retire_reports_a_missing_file_instead_of_claiming_success(api):
    res = api.retire_library_image("library/images/never_existed.jpg")
    assert res["success"] is False
    assert "not found" in res["error"]
