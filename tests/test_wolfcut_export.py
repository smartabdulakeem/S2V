"""
The finished film, exported as an editable WolfCut timeline.

Pictures on one track at their real spoken durations, narration on another,
captions on a third. Written in the DOCUMENT_VERSION = 1 format so WolfCut can
open it.

These tests put a real image file on every shot, the way the resolver does, and
assert each clip points at *that shot's* picture. The first pass of this feature
read four field names that appear nowhere in this codebase, missed every image,
and then wrote zero-byte files so the paths it had guessed would exist. Its
tests passed: they built shots with no images at all, and asserted only that
media paths exist — which the exporter had just made true. A test that cannot
fail is worse than no test, so every assertion here names a specific file.
"""

import os
import json
import pytest

from pipeline.wolfcut_export import write_wolfcut_project, _clean_slug
from pipeline.text_parser import plan_image_budget
from pipeline.visuals import initialize_project_sourcing
from pipeline.library import picture_owning_shots


def _jpeg(path):
    """A small but real file, so an empty one is never mistaken for it."""
    with open(path, "wb") as f:
        f.write(b"\xff\xd8\xff\xe0" + os.path.basename(path).encode() + b"\xff\xd9")
    return str(path)


def _script(tmp_path, num_segments=60, total_duration=300.0, with_images=True):
    """A script shaped the way the pipeline actually produces one."""
    segments, durations_map, audio_paths_map = [], {}, {}
    seg_dur = round(total_duration / num_segments, 3)

    img_dir = tmp_path / "images"
    img_dir.mkdir(exist_ok=True)

    for i in range(1, num_segments + 1):
        durations_map[i] = seg_dur
        aud = tmp_path / f"narration_{i}.mp3"
        aud.write_bytes(b"ID3 dummy narration")
        audio_paths_map[i] = str(aud)

        # A shot's `scene` is its segment's narration — that is how the parser
        # builds one, and how plan_image_budget finds a description to carry
        # across a re-cut. Give it anything else and the carry silently misses.
        narration = f"Narration sentence {i} describing what happened next, plainly."
        shot = {
            "shot_id": f"{i}a",
            "query": f"segment {i} visual",
            "scene": narration,
            "visual_description": f"A described moment belonging to segment {i}",
            "duration": None,
            "share_with": None,
            "source": "library",
            "pin": None,
        }
        if with_images:
            shot["resolved"] = _jpeg(img_dir / f"picture_for_segment_{i}.jpg")

        segments.append({
            "segment_id": i,
            "narration": narration,
            "shots": [shot],
        })

    script_data = {
        "project": {"title": "Historical Odyssey", "series_slug": "default",
                    "aspect_ratio": "16:9"},
        "segments": segments,
    }
    return script_data, audio_paths_map, durations_map


def _budget_and_resolve(data, tmp_path, image_count):
    """
    Reduce the image count, then give each surviving picture an image.

    This is the real order. `plan_image_budget` rebuilds every shot when it
    merges segments into runs, so anything resolved beforehand is dropped
    unless it was pinned — by design, because a run's query is not the query
    any one of its segments had. The resolver runs afterwards. A test that
    resolves first is testing a state the app never reaches.
    """
    plan_image_budget(data, image_count=image_count)
    img_dir = tmp_path / "resolved"
    img_dir.mkdir(exist_ok=True)
    for n, (_, shot) in enumerate(picture_owning_shots(data), 1):
        shot["resolved"] = _jpeg(img_dir / f"resolved_picture_{n}.jpg")
    return data


def _export(tmp_path, script_data, audio_paths_map, durations_map):
    msgs = []
    path = write_wolfcut_project(script_data, audio_paths_map, durations_map,
                                 str(tmp_path), on_progress=msgs.append)
    with open(path, encoding="utf-8") as f:
        return json.load(f), path, msgs


def _track(doc, track_id):
    return [c for c in doc["clips"] if c["trackId"] == track_id]


# ---------------------------------------------------------------------------
# The picture track
# ---------------------------------------------------------------------------

def test_sixty_segments_reduced_to_twelve_gives_twelve_picture_clips(tmp_path):
    data, audio, durs = _script(tmp_path, 60, 300.0, with_images=False)
    _budget_and_resolve(data, tmp_path, 12)
    doc, _, _ = _export(tmp_path, data, audio, durs)

    assert len(_track(doc, "T1")) == 12, "one clip per picture, not per shot"


def test_each_clip_points_at_that_shots_own_picture(tmp_path):
    """
    The contract: picture n on the timeline is the picture belonging to the nth
    picture-owning shot. Asserted against the file the resolver put on the shot,
    not against a filename pattern.
    """
    data, audio, durs = _script(tmp_path, 60, 300.0, with_images=False)
    _budget_and_resolve(data, tmp_path, 12)
    doc, _, _ = _export(tmp_path, data, audio, durs)

    clips = _track(doc, "T1")
    owning = picture_owning_shots(data)
    media_by_id = {m["id"]: m for m in doc["media"]}

    assert len(clips) == len(owning) == 12
    for i, (_, shot) in enumerate(owning):
        expected = os.path.abspath(shot["resolved"])
        actual = media_by_id[clips[i]["mediaId"]]["path"]
        assert actual == expected, (
            f"picture {i + 1} points at {os.path.basename(actual)}, "
            f"expected {os.path.basename(expected)}")
        assert os.path.getsize(actual) > 0, "the timeline points at an empty file"


def test_clip_n_prompt_n_and_the_nth_picture_are_the_same_shot(tmp_path):
    data, audio, durs = _script(tmp_path, 60, 300.0, with_images=False)
    _budget_and_resolve(data, tmp_path, 12)

    project_dir = initialize_project_sourcing(data)
    with open(os.path.join(project_dir, "image_prompts.txt"), encoding="utf-8") as f:
        prompt_lines = [l.strip() for l in f if l.strip()]

    doc, _, _ = _export(tmp_path, data, audio, durs)
    clips = _track(doc, "T1")
    owning = picture_owning_shots(data)
    media_by_id = {m["id"]: m for m in doc["media"]}

    assert len(clips) == len(prompt_lines) == len(owning) == 12
    for i, (_, shot) in enumerate(owning):
        assert prompt_lines[i].startswith(f"{i + 1}. ")
        assert shot["visual_description"][:30].lower() in prompt_lines[i].lower()
        assert media_by_id[clips[i]["mediaId"]]["path"] == os.path.abspath(shot["resolved"])


def test_shared_shots_collapse_into_one_clip_of_their_combined_length(tmp_path):
    data, audio, durs = _script(tmp_path, 60, 300.0, with_images=False)
    _budget_and_resolve(data, tmp_path, 12)
    doc, _, _ = _export(tmp_path, data, audio, durs)

    clips = _track(doc, "T1")
    total_shots = sum(len(s["shots"]) for s in data["segments"])
    assert total_shots == 60 and len(clips) == 12
    # Twelve clips still cover the whole film, so each spans its shared run.
    assert abs(sum(c["duration"] for c in clips) - sum(durs.values())) < 0.01


def test_picture_clips_are_contiguous_and_end_at_the_narration_length(tmp_path):
    data, audio, durs = _script(tmp_path, 30, 150.0, with_images=False)
    _budget_and_resolve(data, tmp_path, 6)
    doc, _, _ = _export(tmp_path, data, audio, durs)

    expected_start = 0.0
    for clip in _track(doc, "T1"):
        assert abs(clip["start"] - expected_start) < 0.002
        expected_start += clip["duration"]
    assert abs(expected_start - sum(durs.values())) < 0.005


# ---------------------------------------------------------------------------
# A picture that has no image yet
# ---------------------------------------------------------------------------

def test_a_picture_with_no_image_is_skipped_and_named(tmp_path):
    """No file is invented to make the export look complete."""
    data, audio, durs = _script(tmp_path, 4, 20.0)
    data["segments"][1]["shots"][0].pop("resolved")

    before = set(os.listdir(tmp_path))
    doc, _, msgs = _export(tmp_path, data, audio, durs)
    after = set(os.listdir(tmp_path))

    assert len(_track(doc, "T1")) == 3, "the picture with no image was still placed"
    assert "3 of 4 pictures placed" in msgs[0]
    assert "picture 2" in msgs[0]

    invented = {f for f in (after - before) if f.endswith((".jpg", ".png"))}
    assert not invented, f"the export invented image files: {invented}"


def test_no_zero_byte_file_is_ever_written(tmp_path):
    data, audio, durs = _script(tmp_path, 6, 30.0, with_images=False)
    _export(tmp_path, data, audio, durs)

    for root, _, files in os.walk(tmp_path):
        for name in files:
            path = os.path.join(root, name)
            if name.endswith((".jpg", ".png")):
                assert os.path.getsize(path) > 0, f"{name} is an empty placeholder"


# ---------------------------------------------------------------------------
# Narration, captions, and the document itself
# ---------------------------------------------------------------------------

def test_narration_clips_lie_end_to_end(tmp_path):
    data, audio, durs = _script(tmp_path, 10, 50.0)
    doc, _, _ = _export(tmp_path, data, audio, durs)

    clips = _track(doc, "T2")
    assert len(clips) == 10
    running = 0.0
    for i, seg_id in enumerate(durs):
        assert abs(clips[i]["start"] - running) < 0.002
        assert abs(clips[i]["duration"] - durs[seg_id]) < 0.002
        running += clips[i]["duration"]
    assert abs(running - sum(durs.values())) < 0.005


def test_captions_become_text_clips_at_their_cue_times(tmp_path):
    data, audio, durs = _script(tmp_path, 5, 25.0)
    (tmp_path / "historical_odyssey.srt").write_text(
        "1\n00:00:01,000 --> 00:00:03,500\nIn ancient times\n\n"
        "2\n00:00:04,000 --> 00:00:07,000\nThe desert spanned far\n\n",
        encoding="utf-8")

    doc, _, _ = _export(tmp_path, data, audio, durs)
    caps = _track(doc, "T3")

    assert len(caps) == 2
    assert abs(caps[0]["start"] - 1.0) < 0.01
    assert abs(caps[0]["duration"] - 2.5) < 0.01
    assert caps[0]["text"]["content"] == "In ancient times"
    assert caps[0]["mediaId"] == ""


def test_the_title_and_aspect_ratio_come_from_the_project(tmp_path):
    """Read from the top level, every film was called "Project" and came out 16:9."""
    data, audio, durs = _script(tmp_path, 3, 15.0)
    data["project"]["title"] = "The Long Retreat"
    data["project"]["aspect_ratio"] = "9:16"

    doc, path, _ = _export(tmp_path, data, audio, durs)

    assert doc["name"] == "The Long Retreat"
    assert (doc["video"]["width"], doc["video"]["height"]) == (1080, 1920)
    assert os.path.basename(path) == "the_long_retreat.wolfcut"


def test_every_reference_in_the_document_resolves(tmp_path):
    data, audio, durs = _script(tmp_path, 5, 25.0)
    doc, _, _ = _export(tmp_path, data, audio, durs)

    media_ids = {m["id"] for m in doc["media"]}
    track_ids = {t["id"] for t in doc["tracks"]}

    assert doc["activeTimelineId"] == "TL1"
    assert doc["timelines"][0]["id"] == "TL1"
    for clip in doc["clips"]:
        assert clip["trackId"] in track_ids
        if clip["kind"] == "text":
            assert clip["mediaId"] == "" and clip["text"]["content"]
        else:
            assert clip["mediaId"] in media_ids


def test_every_media_path_is_absolute_and_real(tmp_path):
    data, audio, durs = _script(tmp_path, 4, 20.0)
    doc, _, _ = _export(tmp_path, data, audio, durs)

    assert doc["media"], "a film with pictures exported no media"
    for m in doc["media"]:
        assert os.path.isabs(m["path"])
        assert os.path.exists(m["path"])
        assert os.path.getsize(m["path"]) > 0


def test_the_document_round_trips(tmp_path):
    data, audio, durs = _script(tmp_path, 3, 15.0)
    doc, _, _ = _export(tmp_path, data, audio, durs)

    assert doc["wolfcut"] == "0.1.0"
    assert doc["version"] == 1
    assert len(doc["tracks"]) == 3
    assert json.loads(json.dumps(doc)) == doc


def test_a_film_without_captions_is_still_valid(tmp_path):
    data, audio, durs = _script(tmp_path, 3, 15.0)
    doc, _, _ = _export(tmp_path, data, audio, durs)

    assert _track(doc, "T3") == []
    assert len(_track(doc, "T1")) == 3
    assert len(_track(doc, "T2")) == 3


@pytest.mark.parametrize("raw,expected", [
    ("The Long Retreat", "the_long_retreat"),
    ("  S2E6 — Fall  ", "s2e6_fall"),
    ("", "project"),
])
def test_slugs(raw, expected):
    assert _clean_slug(raw) == expected


# ---------------------------------------------------------------------------
# Timeline export without a render
# ---------------------------------------------------------------------------

def test_a_timeline_can_be_built_from_timing_alone(tmp_path):
    """
    The editor bridge without a render. The narration is generated and probed,
    the picture boundaries come from the plan, and the timeline is written -
    no video encode anywhere in that sentence.
    """
    from pipeline.picture_plan import apply_spans

    # Six segments at 5.0s each
    data, audio, durs = _script(tmp_path, 6, 30.0, with_images=False)
    for k in durs:
        durs[k] = 5.0

    # apply_spans giving picture 1 lines 1-4 and picture 2 lines 5-6
    apply_spans(data, [
        {"number": 1, "first_line": 1, "last_line": 4, "description": "the first"},
        {"number": 2, "first_line": 5, "last_line": 6, "description": "the second"},
    ])

    img_dir = tmp_path / "resolved"
    img_dir.mkdir(exist_ok=True)
    # Give picture 1 and picture 2 real image files
    data["segments"][0]["shots"][0]["resolved"] = _jpeg(img_dir / "pic1.jpg")
    data["segments"][4]["shots"][0]["resolved"] = _jpeg(img_dir / "pic2.jpg")

    doc, _, _ = _export(tmp_path, data, audio, durs)

    pic_clips = _track(doc, "T1")
    assert len(pic_clips) == 2, f"Expected 2 picture clips, got {len(pic_clips)}"
    assert pic_clips[0]["duration"] == 20.0, f"Expected first duration 20.0, got {pic_clips[0]['duration']}"
    assert pic_clips[1]["start"] == 20.0, f"Expected second starting at 20.0, got {pic_clips[1]['start']}"


def test_export_timeline_calls_zero_encoders(tmp_path, monkeypatch):
    """
    No encoder runs. Patch the ffmpeg runner and assert it was called zero times.
    """
    import subprocess
    from app import Api

    api = Api()
    calls = []

    def fake_run(*args, **kwargs):
        calls.append(args)
        raise AssertionError(f"ffmpeg/encoder was called unexpectedly with {args}!")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(subprocess, "Popen", fake_run)

    data, audio, durs = _script(tmp_path, 6, 30.0, with_images=True)
    for i, seg in enumerate(data["segments"], 1):
        seg["narration_seconds"] = durs[i]
        seg["narration_audio"] = audio[i]

    res = api.export_wolfcut_timeline(data, str(tmp_path))
    assert res["success"] is True
    assert len(calls) == 0, f"Expected zero encoder calls, got {len(calls)}"
    assert os.path.exists(res["path"])


def test_export_timeline_no_audio_returns_clear_failure_without_raising(tmp_path):
    """
    A film with no narration audio returns clear failure, and does not raise.
    """
    from app import Api

    api = Api()
    data, _, _ = _script(tmp_path, 6, 30.0, with_images=True)
    for seg in data["segments"]:
        seg.pop("narration_audio", None)
        seg.pop("narration_seconds", None)

    res = api.export_wolfcut_timeline(data, str(tmp_path))
    assert res["success"] is False
    assert "Narration has not been recorded yet" in res["error"]
    assert "Measure narration" in res["error"]
    assert res["path"] is None


def test_export_timeline_captions_empty_without_srt_and_doc_valid(tmp_path):
    """
    Captions are empty without an SRT, and the document is still valid — every
    mediaId on a clip exists in media[], every trackId exists in tracks[].
    """
    from app import Api

    api = Api()
    data, audio, durs = _script(tmp_path, 6, 30.0, with_images=True)
    for i, seg in enumerate(data["segments"], 1):
        seg["narration_seconds"] = durs[i]
        seg["narration_audio"] = audio[i]

    res = api.export_wolfcut_timeline(data, str(tmp_path))
    assert res["success"] is True
    assert res["captions"] == 0

    with open(res["path"], "r", encoding="utf-8") as f:
        doc = json.load(f)

    # Captions track has 0 clips
    assert _track(doc, "T3") == []

    media_ids = {m["id"] for m in doc["media"]}
    track_ids = {t["id"] for t in doc["tracks"]}

    assert len(doc["clips"]) > 0
    for clip in doc["clips"]:
        assert clip["trackId"] in track_ids, f"Clip trackId {clip['trackId']} not in tracks"
        if clip.get("mediaId"):
            assert clip["mediaId"] in media_ids, f"Clip mediaId {clip['mediaId']} not in media"

