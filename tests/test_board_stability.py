"""
Choosing an image for one shot must not break another.

Alternatives were computed as each shot was planned, excluding only the images
earlier shots had taken. A shot could therefore be offered an image that a later
shot was already using as its best match; accepting the offer handed it over and
left the other shot to fall back or become a gap. Fixing one broke another.

Also covers the two v1-only assumptions that failed every AI-planned render:
the orchestrator read seg["b_roll_keyword"], and pins never reached the visuals
stage because it looked only at the v1 use_base_image field.
"""

import pytest
from PIL import Image

from pipeline import library
from pipeline.visuals import segment_keyword, segment_pin


def _library(tmp_path, monkeypatch, n=6):
    images_dir = tmp_path / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        Image.new("RGB", (64, 64), color=(i * 35, 90, 200 - i * 20)).save(images_dir / f"img_{i}.jpg")

    monkeypatch.setattr(library, "ROOT", str(tmp_path))
    monkeypatch.setattr(library, "LIBRARY_DIR", str(tmp_path))
    monkeypatch.setattr(library, "IMAGES_DIR", str(images_dir))
    monkeypatch.setattr(library, "INDEX_PATH", str(tmp_path / "index.npz"))
    monkeypatch.setattr(library, "REJECTIONS_PATH", str(tmp_path / "rejections.jsonl"))
    monkeypatch.setattr(library, "RENDER_USAGE_PATH", str(tmp_path / "render_usage.json"))
    library.reindex(force=True)


def test_alternatives_never_offer_an_image_another_shot_is_using(tmp_path, monkeypatch):
    _library(tmp_path, monkeypatch)

    script = {
        "project": {"title": "Board"},
        "segments": [
            {"segment_id": i, "narration": "n",
             "shots": [{"shot_id": f"{i}a", "query": "blue canvas"}]}
            for i in range(1, 5)
        ],
    }

    report = library.plan_shots(script, min_score=0.0, weak_band=0.0)

    assigned = {r["best_path"] for r in report["shot_reports"] if r["best_path"]}
    for r in report["shot_reports"]:
        for alt in r["alternatives"]:
            alt_path = alt[0] if isinstance(alt, (list, tuple)) else alt
            assert alt_path not in assigned, (
                f"shot {r['shot_id']} was offered {alt_path}, which another shot is using"
            )


def _remember(script, report):
    """What the board does after a plan: record what each shot settled on."""
    by_key = {(r["segment_id"], r["shot_id"]): r for r in report["shot_reports"]}
    for seg in script["segments"]:
        for shot in seg["shots"]:
            r = by_key.get((seg["segment_id"], shot["shot_id"]))
            if r and r["best_path"]:
                shot["resolved"] = r["best_path"]
                shot["resolved_score"] = r["best_score"]


def test_pinning_one_shot_leaves_the_others_alone(tmp_path, monkeypatch):
    """The whole point: a deliberate choice must not reshuffle the rest of the board."""
    _library(tmp_path, monkeypatch)

    script = {
        "project": {"title": "Board"},
        "segments": [
            {"segment_id": i, "narration": "n",
             "shots": [{"shot_id": f"{i}a", "query": "blue canvas"}]}
            for i in range(1, 5)
        ],
    }

    before = library.plan_shots(script, min_score=0.0, weak_band=0.0)
    _remember(script, before)
    others_before = {r["shot_id"]: r["best_path"] for r in before["shot_reports"][1:]}

    # Now pin shot 1 to a spare image, exactly as Replace does.
    taken = {r["best_path"] for r in before["shot_reports"]}
    spare = next(p for p in [f"images/img_{i}.jpg" for i in range(6)] if p not in taken)
    script["segments"][0]["shots"][0].update({"source": "pin", "pin": spare})

    after = library.plan_shots(script, min_score=0.0, weak_band=0.0)
    others_after = {r["shot_id"]: r["best_path"] for r in after["shot_reports"][1:]}

    assert after["shot_reports"][0]["best_path"] == spare
    assert others_after == others_before, "pinning one shot disturbed the others"


def test_a_second_replan_changes_nothing(tmp_path, monkeypatch):
    """Refreshing coverage repeatedly must be a no-op, not a reshuffle."""
    _library(tmp_path, monkeypatch)
    script = {
        "project": {"title": "Board"},
        "segments": [
            {"segment_id": i, "narration": "n",
             "shots": [{"shot_id": f"{i}a", "query": "blue canvas"}]}
            for i in range(1, 5)
        ],
    }

    first = library.plan_shots(script, min_score=0.0, weak_band=0.0)
    _remember(script, first)
    second = library.plan_shots(script, min_score=0.0, weak_band=0.0)

    assert ([r["best_path"] for r in second["shot_reports"]]
            == [r["best_path"] for r in first["shot_reports"]])


def test_a_resolved_image_that_vanished_is_replanned(tmp_path, monkeypatch):
    """A remembered image that no longer exists must not become a broken shot."""
    _library(tmp_path, monkeypatch)
    script = {
        "project": {"title": "Board"},
        "segments": [{
            "segment_id": 1, "narration": "n",
            "shots": [{"shot_id": "1a", "query": "blue canvas",
                       "resolved": "images/deleted.jpg", "resolved_score": 0.4}],
        }],
    }

    report = library.plan_shots(script, min_score=0.0, weak_band=0.0)
    shot = report["shot_reports"][0]

    assert shot["best_path"] != "images/deleted.jpg"
    assert shot["best_path"] is not None


# ── The two v1-only assumptions ───────────────────────────────────────────────

def test_segment_keyword_reads_both_schema_versions():
    v1 = {"segment_id": 1, "b_roll_keyword": "desert caravan"}
    v2 = {"segment_id": 1, "shots": [{"shot_id": "1a", "query": "lone rider at dusk"}]}
    empty = {"segment_id": 1, "shots": []}

    assert segment_keyword(v1) == "desert caravan"
    assert segment_keyword(v2) == "lone rider at dusk"
    assert segment_keyword(empty) == ""  # must not raise


def test_segment_keyword_does_not_raise_on_a_planned_segment():
    """seg["b_roll_keyword"] raised KeyError on all 117 segments of a real script."""
    planned = {"segment_id": 7, "narration": "text", "shots": [{"shot_id": "7a", "query": "flood"}]}
    assert "b_roll_keyword" not in planned
    assert segment_keyword(planned) == "flood"


def test_segment_pin_finds_a_storyboard_pin():
    seg = {
        "segment_id": 3,
        "shots": [{"shot_id": "3a", "source": "pin", "pin": "library/images/mine.jpg"}],
    }
    assert segment_pin(seg) == "library/images/mine.jpg"


def test_segment_pin_falls_back_to_v1_and_ignores_unpinned_shots():
    assert segment_pin({"segment_id": 1, "use_base_image": "1.jpg"}) == "1.jpg"
    assert segment_pin({"segment_id": 1, "shots": [{"shot_id": "1a", "source": "library"}]}) is None
