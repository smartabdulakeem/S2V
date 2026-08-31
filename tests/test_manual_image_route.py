"""
The manual route: prompts out, pictures back in, landing on the right shots.

The owner pastes a script, takes the exported prompts to an image tool, drops
the results in a numbered folder, and the app places them. Steps 1, 4 and 5
worked. Steps 2 and 3 were broken, and broken silently.

`plan_image_budget` merges segments into runs when the image count is reduced
and marks every shot that does not own a picture with `share_with`.
`apply_external_prompts` did not know that: it bound prompt *i* to
`all_shots[i]`, sharing shots included. Measured on 60 segments asking for 12
images: ten of the twelve prompts landed on shots that make no picture, ten real
pictures got no prompt, and nothing said so.

`image_prompts.txt` had the matching fault from the other end — one line per
segment, so 60 segments cut to 12 images exported 60 prompts for 12 pictures,
and the numbering meant nothing.

Slot *n* now means the *n*th picture the film actually makes, in all three
places: the pasted prompt, `n.jpg` in the working folder, and the export.
"""

import os
import re
import pytest

from pipeline import library
from pipeline.library import (apply_external_prompts, picture_owning_shots,
                              match_folder_images_by_slot)
from pipeline.text_parser import plan_image_budget
from pipeline.visuals import initialize_project_sourcing


def _script(num_segments=60):
    segments = []
    for i in range(1, num_segments + 1):
        narration = (f"Segment {i} narration about the envoy, the hall and the "
                     f"long road that followed it, told plainly.")
        segments.append({
            "segment_id": i,
            "narration": narration,
            "shots": [{
                "shot_id": f"{i}a",
                "query": f"segment {i} visual",
                "source": "library",
                "pin": None,
                "duration": None,
                "scene": narration,
                "visual_description": f"A described moment belonging to segment {i}",
            }],
        })
    return {
        "project": {"title": "Manual Route Test", "series_slug": "default",
                    "aspect_ratio": "16:9"},
        "segments": segments,
    }


def _budgeted(num_segments=60, images=12):
    """The owner's measured case: 60 segments reduced to 12 pictures."""
    data = _script(num_segments)
    stats = plan_image_budget(data, images)
    assert stats["images_after"] == images, "the budget did not produce what was asked"
    return data


# ---------------------------------------------------------------------------
# The list everything counts from
# ---------------------------------------------------------------------------

def test_the_owning_list_is_the_distinct_picture_count():
    data = _budgeted()
    owning = picture_owning_shots(data)
    total_shots = sum(len(s["shots"]) for s in data["segments"])

    assert len(owning) == 12, "the film does not make the number of pictures asked for"
    assert total_shots == 60
    assert all(not shot.get("share_with") for _, shot in owning)


# ---------------------------------------------------------------------------
# Job 1 — prompts bind to shots that own a picture
# ---------------------------------------------------------------------------

def test_the_measured_case_all_twelve_prompts_land_on_a_picture():
    """60 segments, 12 images, 12 prompts. Ten used to land on shared shots."""
    data = _budgeted()
    pasted = "\n\n".join(f"PROMPT {i}" for i in range(1, 13))

    res = apply_external_prompts(data, pasted)
    assert res["success"]

    bound = [(seg["segment_id"], shot)
             for seg in res["script_data"]["segments"]
             for shot in seg["shots"] if shot.get("prompt_override")]

    assert len(bound) == 12, "not every prompt reached a shot"
    assert all(not shot.get("share_with") for _, shot in bound), \
        "a prompt landed on a shot that shares another shot's picture"

    owning = picture_owning_shots(res["script_data"])
    for i, (_, shot) in enumerate(owning):
        assert shot["prompt_override"] == f"PROMPT {i + 1}", \
            f"picture {i + 1} carries the wrong prompt"


def test_a_shared_shot_never_receives_a_prompt():
    data = _budgeted()
    apply_external_prompts(data, "\n\n".join(f"P{i}" for i in range(1, 13)))

    shared = [shot for seg in data["segments"] for shot in seg["shots"]
              if shot.get("share_with")]
    assert len(shared) == 48, "the measured case no longer has 48 sharing shots"
    assert all(not s.get("prompt_override") for s in shared)


def test_folder_images_land_on_the_same_shots_as_the_prompts(tmp_path):
    """Prompt n and n.jpg must reach the same shot, or the mismatch just moves."""
    data = _budgeted()
    for n in range(1, 13):
        (tmp_path / f"{n}.jpg").write_bytes(b"\xff\xd8\xff\xd9")

    res = apply_external_prompts(
        data, "\n\n".join(f"PROMPT {i}" for i in range(1, 13)), folder=str(tmp_path))
    assert res["success"]

    owning = picture_owning_shots(res["script_data"])
    for i, (_, shot) in enumerate(owning):
        assert shot["prompt_override"] == f"PROMPT {i + 1}"
        assert os.path.basename(shot["resolved"]) == f"{i + 1}.jpg", \
            f"picture {i + 1} took the wrong image"


# ---------------------------------------------------------------------------
# Job 2 — the export matches, one line per picture
# ---------------------------------------------------------------------------

def _exported_lines(data, tmp_path, monkeypatch):
    monkeypatch.setattr("pipeline.visuals._generate_placeholder_image",
                        lambda *a, **k: None)
    project_dir = initialize_project_sourcing(data)
    with open(os.path.join(project_dir, "image_prompts.txt"), encoding="utf-8") as f:
        return [ln.rstrip("\n") for ln in f if ln.strip()]


def test_the_export_is_one_line_per_picture_numbered_from_one(tmp_path, monkeypatch):
    data = _budgeted()
    lines = _exported_lines(data, tmp_path, monkeypatch)

    assert len(lines) == 12, f"exported {len(lines)} prompts for 12 pictures"
    for i, line in enumerate(lines, 1):
        assert line.startswith(f"{i}. "), f"line {i} is misnumbered: {line[:40]}"


def test_the_export_and_the_binding_name_the_same_shots(tmp_path, monkeypatch):
    """Prompt n in the file is the prompt for picture n on the board."""
    data = _budgeted()
    lines = _exported_lines(data, tmp_path, monkeypatch)
    owning = picture_owning_shots(data)

    assert len(lines) == len(owning) == 12
    for i, (_, shot) in enumerate(owning):
        assert shot["visual_description"].lower()[:30] in lines[i].lower(), \
            f"exported line {i + 1} does not describe picture {i + 1}"


def test_the_framing_varies_across_the_film(tmp_path, monkeypatch):
    """Every line carried the same framing: shot_position was never passed."""
    from pipeline.prompt_slots import DEFAULT_FRAMING_CYCLE

    data = _budgeted()
    lines = _exported_lines(data, tmp_path, monkeypatch)

    used = {framing for framing in DEFAULT_FRAMING_CYCLE
            if any(framing in ln for ln in lines)}
    assert len(used) > 1, \
        f"all {len(lines)} exported prompts share one framing phrase"


def test_the_subject_is_the_shots_description_not_a_keyword(tmp_path, monkeypatch):
    data = _budgeted()
    lines = _exported_lines(data, tmp_path, monkeypatch)
    assert all("A described moment belonging to segment" in ln for ln in lines), \
        "the export fell back to extract_keyword instead of visual_description"


def test_a_pasted_prompt_is_exported_unchanged(tmp_path, monkeypatch):
    """A prompt he wrote by hand must survive the round trip verbatim."""
    data = _budgeted()
    verbatim = "A lone rider cresting a dune at dusk, no text anywhere"
    apply_external_prompts(data, "\n\n".join(
        [verbatim] + [f"P{i}" for i in range(2, 13)]))

    lines = _exported_lines(data, tmp_path, monkeypatch)
    assert lines[0] == f"1. {verbatim}"


# ---------------------------------------------------------------------------
# Job 3 — the counts are stated, both ways
# ---------------------------------------------------------------------------

def test_under_supply_reports_both_numbers():
    data = _budgeted()
    res = apply_external_prompts(data, "\n\n".join(f"P{i}" for i in range(1, 10)))

    assert res["total_pictures"] == 12
    assert res["total_shots"] == 60
    assert res["pasted_count"] == 9
    assert res["unprompted_pictures"] == 3
    assert res["unused_prompts"] == 0
    assert "12 pictures" in res["counts"]
    assert "60 shots" in res["counts"]
    assert "9 prompts" in res["counts"]
    assert "3 pictures will fall back to library search" in res["counts"]


def test_over_supply_reports_both_numbers():
    data = _budgeted()
    res = apply_external_prompts(data, "\n\n".join(f"P{i}" for i in range(1, 16)))

    assert res["pasted_count"] == 15
    assert res["total_pictures"] == 12
    assert res["unused_prompts"] == 3
    assert res["unprompted_pictures"] == 0
    assert "15 prompts" in res["counts"]
    assert "3 prompts more than this film has pictures" in res["counts"]


def test_an_exact_match_says_so_without_a_warning():
    data = _budgeted()
    res = apply_external_prompts(data, "\n\n".join(f"P{i}" for i in range(1, 13)))

    assert res["unprompted_pictures"] == 0
    assert res["unused_prompts"] == 0
    assert "fall back" not in res["counts"]
    assert "more than" not in res["counts"]


# ---------------------------------------------------------------------------
# The unreduced film still behaves
# ---------------------------------------------------------------------------

def test_a_film_with_no_sharing_binds_every_shot(tmp_path, monkeypatch):
    data = _script(8)
    res = apply_external_prompts(data, "\n\n".join(f"P{i}" for i in range(1, 9)))

    assert res["total_pictures"] == 8
    assert res["total_shots"] == 8
    lines = _exported_lines(res["script_data"], tmp_path, monkeypatch)
    assert len(lines) == 8


# ---------------------------------------------------------------------------
# The whole route with no API key: the app states its own segmentation.
# ---------------------------------------------------------------------------

def test_the_prompt_request_asks_for_exactly_the_pictures_the_film_needs(tmp_path, monkeypatch):
    """
    The owner's fear: the app cuts the script up its own way, and an outside AI
    asked to write prompts from the same script cannot know how. It does not
    have to guess — the app writes the request, numbered, and the numbering is
    the contract for the paste box and the image folder alike.
    """
    from pipeline.visuals import write_prompt_request

    data = _budgeted(60, 12)
    monkeypatch.setattr("pipeline.visuals._generate_placeholder_image", lambda *a, **k: None)
    path = write_prompt_request(data)
    text = open(path, encoding="utf-8").read()

    assert "This film needs exactly 12 pictures" in text
    assert "THE 12 MOMENTS TO DESCRIBE" in text

    moments = [ln for ln in text.splitlines()
               if re.match(r"^\d+\.( \(script line \d+\))? \S", ln)
               and "MOMENTS" not in ln]
    numbered = [ln for ln in moments if ln.split(".")[0].isdigit()]
    assert len(numbered) >= 12, f"only {len(numbered)} moments listed"
    for i in range(1, 13):
        assert any(ln.startswith(f"{i}.") for ln in numbered), f"moment {i} missing"


def test_the_request_carries_the_whole_script_and_the_niche_recipe(tmp_path, monkeypatch):
    from pipeline.visuals import write_prompt_request

    data = _budgeted(20, 5)
    monkeypatch.setattr("pipeline.visuals._generate_placeholder_image", lambda *a, **k: None)
    text = open(write_prompt_request(data), encoding="utf-8").read()

    assert "THE FULL SCRIPT" in text
    for seg in data["segments"]:
        assert seg["narration"][:40] in text, "a script line is missing from the request"
    assert "1.jpg" in text and "Paste External Prompts" in text


def test_a_reply_to_the_request_binds_one_prompt_per_picture(tmp_path, monkeypatch):
    """The loop closes: n moments out, n prompts back, n pictures bound."""
    from pipeline.visuals import write_prompt_request

    data = _budgeted(60, 12)
    monkeypatch.setattr("pipeline.visuals._generate_placeholder_image", lambda *a, **k: None)
    write_prompt_request(data)

    reply = "\n\n".join(f"A picture for moment {i}" for i in range(1, 13))
    res = apply_external_prompts(data, reply)

    assert res["prompts_count"] == 12
    assert res["unprompted_pictures"] == 0 and res["unused_prompts"] == 0
    for i, (_, shot) in enumerate(picture_owning_shots(data), 1):
        assert shot["prompt_override"] == f"A picture for moment {i}"
