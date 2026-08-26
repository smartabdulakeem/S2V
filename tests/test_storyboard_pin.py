"""
The storyboard's Replace flow: a user's chosen image must survive a re-plan.

Before this, plan_shots() read only shot_id/query/min_score/narration, so any image
the user picked on the board was discarded the moment coverage refreshed and CLIP
re-picked whatever it liked. These tests pin that behaviour down.
"""

import os
import pytest
from PIL import Image

from pipeline import library
from pipeline import composer


def _library(tmp_path, monkeypatch, n=4):
    """A throwaway library of n images, indexed. Returns the images dir."""
    images_dir = tmp_path / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        img = Image.new("RGB", (64, 64), color=(i * 40, 90, 200 - i * 30))
        img.save(images_dir / f"img_{i}.jpg")

    monkeypatch.setattr(library, "ROOT", str(tmp_path))
    monkeypatch.setattr(library, "LIBRARY_DIR", str(tmp_path))
    monkeypatch.setattr(library, "IMAGES_DIR", str(images_dir))
    monkeypatch.setattr(library, "INDEX_PATH", str(tmp_path / "index.npz"))
    monkeypatch.setattr(library, "REJECTIONS_PATH", str(tmp_path / "rejections.jsonl"))
    monkeypatch.setattr(library, "RENDER_USAGE_PATH", str(tmp_path / "render_usage.json"))
    library.reindex(force=True)
    return images_dir


def _script(shots):
    return {
        "project": {"title": "Pin Test"},
        "segments": [{"segment_id": 1, "narration": "a test segment", "shots": shots}],
    }


def test_pinned_shot_is_kept_instead_of_researched(tmp_path, monkeypatch):
    """A pinned shot reports the pinned image, not whatever CLIP would have chosen."""
    images_dir = _library(tmp_path, monkeypatch)

    pinned = images_dir / "my_own_image.jpg"
    Image.new("RGB", (64, 64), color=(255, 0, 0)).save(pinned)

    script = _script([{
        "shot_id": "1a",
        "query": "blue canvas",
        "source": "pin",
        "pin": "images/my_own_image.jpg",
    }])

    report = library.plan_shots(script, min_score=0.0, weak_band=0.0)
    shot = report["shot_reports"][0]

    assert shot["state"] == "pinned"
    assert shot["best_path"] == "images/my_own_image.jpg"
    assert shot.get("pin_missing") is not True


def test_pinned_shot_counts_as_covered_not_as_a_gap(tmp_path, monkeypatch):
    """A pinned shot must not inflate the gap counter — the user already solved it."""
    _library(tmp_path, monkeypatch)
    pinned = tmp_path / "images" / "chosen.jpg"
    Image.new("RGB", (64, 64), color=(10, 200, 10)).save(pinned)

    # A query nothing can match, so without the pin this shot would be a gap.
    script = _script([{
        "shot_id": "1a",
        "query": "zzzz nonsense query nothing matches",
        "source": "pin",
        "pin": "images/chosen.jpg",
    }])

    report = library.plan_shots(script, min_score=0.99, weak_band=0.0)

    assert report["gaps"] == 0
    assert report["pinned"] == 1
    assert report["shot_reports"][0]["state"] == "pinned"


def test_pinned_image_is_reserved_against_reuse(tmp_path, monkeypatch):
    """Diversity still holds: a pinned image cannot be handed to another shot too."""
    images_dir = _library(tmp_path, monkeypatch)
    pinned_rel = "images/img_0.jpg"
    assert (images_dir / "img_0.jpg").exists()

    script = _script([
        {"shot_id": "1a", "query": "blue canvas", "source": "pin", "pin": pinned_rel},
        {"shot_id": "1b", "query": "blue canvas"},
    ])

    report = library.plan_shots(script, min_score=0.0, weak_band=0.0)
    first, second = report["shot_reports"]

    assert first["best_path"] == pinned_rel
    assert second["best_path"] != pinned_rel, "pinned image was reused on another shot"


def test_missing_pin_falls_back_to_search_and_says_so(tmp_path, monkeypatch):
    """A stale pin must not brick the board — fall back, but flag it rather than hide it."""
    _library(tmp_path, monkeypatch)

    script = _script([{
        "shot_id": "1a",
        "query": "blue canvas",
        "source": "pin",
        "pin": "images/deleted_since.jpg",
    }])

    report = library.plan_shots(script, min_score=0.0, weak_band=0.0)
    shot = report["shot_reports"][0]

    assert shot["pin_missing"] is True
    assert shot["state"] != "pinned"
    assert shot["best_path"] is not None, "should have fallen back to a real search result"


def test_alternatives_are_offered_on_every_shot(tmp_path, monkeypatch):
    """Replace needs candidates to offer on any shot, not only weak ones."""
    _library(tmp_path, monkeypatch, n=5)

    script = _script([{"shot_id": "1a", "query": "blue canvas"}])
    report = library.plan_shots(script, min_score=0.0, weak_band=0.0)

    assert len(report["shot_reports"][0]["alternatives"]) >= 2


# ── Render-time pin resolution ────────────────────────────────────────────────

def test_library_relative_pin_resolves_at_render_time(tmp_path):
    """
    A pin written by the storyboard is library-relative ("library/images/x.jpg").
    Resolution used to try only <project_dir>/<pin>, so those pins silently fell
    back to the retrieved image and the user's choice vanished in the render.
    """
    repo_root = tmp_path / "repo"
    project_dir = repo_root / "projects" / "ep1"
    lib_images = repo_root / "library" / "images"
    project_dir.mkdir(parents=True)
    lib_images.mkdir(parents=True)

    pinned = lib_images / "chosen.jpg"
    Image.new("RGB", (32, 32), color=(1, 2, 3)).save(pinned)

    resolved = composer._resolve_pin_path(
        "library/images/chosen.jpg", str(project_dir), root=str(repo_root)
    )
    assert resolved == str(pinned)


def test_project_relative_pin_still_resolves(tmp_path):
    """The existing project-local pin form must keep working."""
    repo_root = tmp_path / "repo"
    project_dir = repo_root / "projects" / "ep1"
    project_dir.mkdir(parents=True)

    pinned = project_dir / "1.jpg"
    Image.new("RGB", (32, 32), color=(4, 5, 6)).save(pinned)

    resolved = composer._resolve_pin_path("1.jpg", str(project_dir), root=str(repo_root))
    assert resolved == str(pinned)


def test_unresolvable_pin_returns_none(tmp_path):
    """An unresolvable pin returns None so the caller can fall back deliberately."""
    project_dir = tmp_path / "projects" / "ep1"
    project_dir.mkdir(parents=True)

    assert composer._resolve_pin_path("nope.jpg", str(project_dir), root=str(tmp_path)) is None
    assert composer._resolve_pin_path("", str(project_dir), root=str(tmp_path)) is None
