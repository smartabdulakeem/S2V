"""
An image named after a shot's prompt belongs to that shot.

Image tools name their output after the first three to five words of the prompt.
That is an exact link between a picture and the shot it was made for, and it was
being ignored in favour of guessing from pixels — so a user could generate a
unique image for every segment and still watch the app pick something else.

Checked before any visual scoring, and the prompt is remembered on the shot so an
image generated hours after the board was planned is still claimed correctly.
"""

import pytest

from pipeline import library


PROMPT = ("wide establishing shot of Weight Mantle Abu, The Prophet was buried, "
          "7th century Arabian Peninsula, early Islamic era, Shot on 35mm film")


def test_the_framing_opener_is_not_the_subject():
    """Every prompt starts with a framing phrase; it identifies nothing."""
    assert library.prompt_head(PROMPT) == ["weight", "mantle", "abu"]
    assert library.prompt_head("low angle shot of a lone rider") == ["lone", "rider"]


def test_the_head_stops_at_the_subject():
    head = library.prompt_head(PROMPT)
    assert "prophet" not in head, "scene text leaked into the identifying words"
    assert "35mm" not in head


@pytest.mark.parametrize("filename,expected", [
    ("Weight_Mantle_Abu_in_Arabia_202608081549.jpeg", True),
    ("weight mantle abu (1).png", True),
    ("WEIGHT-MANTLE-ABU.jpg", True),
    ("Madinah_outside_borders_7th_century.jpeg", False),
    ("8389f2a74fa3.jpg", False),
    ("Weight_of_something_else.jpg", False),      # one word in common is not a match
])
def test_a_filename_is_matched_against_the_prompt(filename, expected):
    hits = library.prompt_name_match(PROMPT, f"library/images/{filename}")
    assert bool(hits) is expected, f"{filename} -> {hits} hits"


def test_a_short_prompt_cannot_match_on_one_word():
    """Fewer than three identifying words is not enough evidence."""
    assert library.prompt_name_match("shot of fire", "library/images/fire.jpg") == 0


def test_each_image_is_claimed_by_only_one_shot():
    shots = {
        0: "wide establishing shot of Weight Mantle Abu, 7th century",
        1: "wide establishing shot of Madinah outside borders, 7th century",
    }
    paths = ["library/images/Weight_Mantle_Abu_in_Arabia.jpeg",
             "library/images/Madinah_outside_borders_7th.jpeg"]

    out = library.match_shots_by_prompt_name(shots, paths)

    assert out[0].endswith("Weight_Mantle_Abu_in_Arabia.jpeg")
    assert out[1].endswith("Madinah_outside_borders_7th.jpeg")
    assert len(set(out.values())) == 2


def test_two_shots_wanting_the_same_image_do_not_both_get_it():
    shots = {0: "shot of Weight Mantle Abu here", 1: "shot of Weight Mantle Abu there"}
    out = library.match_shots_by_prompt_name(
        shots, ["library/images/Weight_Mantle_Abu.jpeg"])
    assert len(out) == 1


def test_already_used_images_are_not_claimed_again():
    out = library.match_shots_by_prompt_name(
        {0: "shot of Weight Mantle Abu here"},
        ["library/images/Weight_Mantle_Abu.jpeg"],
        excluded={"library/images/Weight_Mantle_Abu.jpeg"},
    )
    assert out == {}


def test_nothing_to_match_is_not_an_error():
    assert library.match_shots_by_prompt_name({}, ["a.jpg"]) == {}
    assert library.match_shots_by_prompt_name({0: "shot of a thing here"}, []) == {}


def test_the_prompt_is_remembered_on_the_shot(tmp_path, monkeypatch):
    """
    The board shows a prompt, the user goes away and generates the picture, and
    comes back later. The shot has to still know what it asked for.
    """
    from PIL import Image
    images = tmp_path / "images"
    images.mkdir(parents=True)
    Image.new("RGB", (64, 64), color=(90, 90, 90)).save(images / "filler.jpg")
    monkeypatch.setattr(library, "ROOT", str(tmp_path))
    monkeypatch.setattr(library, "LIBRARY_DIR", str(tmp_path))
    monkeypatch.setattr(library, "IMAGES_DIR", str(images))
    monkeypatch.setattr(library, "INDEX_PATH", str(tmp_path / "index.npz"))
    monkeypatch.setattr(library, "MANIFEST_PATH", str(tmp_path / "manifest.jsonl"))
    monkeypatch.setattr(library, "REJECTIONS_PATH", str(tmp_path / "rej.jsonl"))
    monkeypatch.setattr(library, "RENDER_USAGE_PATH", str(tmp_path / "use.json"))
    library.reindex(force=True)

    script = {
        "project": {"title": "Memory"},
        "segments": [{"segment_id": 1, "narration": "The water is gone.",
                      "shots": [{"shot_id": "1a", "query": "the flood"}]}],
    }

    library.plan_shots(script, min_score=0.99, weak_band=0.0)

    stored = script["segments"][0]["shots"][0].get("prompt")
    assert stored, "the shot forgot the prompt it advertised"
    assert "flood" in stored.lower()


# ── Numbered folders ──────────────────────────────────────────────────────────

NUMBERED = [
    "library/new image/1_house_wisdom_found__.jpg",
    "library/new image/2_battle_fahl_shurahbi.jpg",
    "library/new image/12_wide_establishing_sh.jpg",
    "library/new image/47_wide_establishing_sh.jpg",
]


def test_a_numbered_folder_maps_straight_onto_the_shots():
    """
    Image tools truncate filenames to ~20 characters, so a prompt beginning
    "wide establishing shot of" becomes "12_wide_establishing_sh" and carries no
    subject at all — 19 of 47 files in a real folder. The number survives.
    """
    out = library.match_shots_by_number(NUMBERED, 48)

    assert out[0].endswith("1_house_wisdom_found__.jpg")
    assert out[1].endswith("2_battle_fahl_shurahbi.jpg")
    assert out[11].endswith("12_wide_establishing_sh.jpg")
    assert out[46].endswith("47_wide_establishing_sh.jpg")


def test_numbers_beyond_the_board_are_ignored():
    assert library.match_shots_by_number(NUMBERED, 3) == {}


def test_a_hash_name_is_never_read_as_a_number():
    """2ab05c4940ef.jpg must not be shot 2."""
    hashes = ["library/images/2ab05c4940ef.jpg", "library/images/8389f2a74fa3.jpg",
              "library/images/12abcdef.png"]
    assert library.match_shots_by_number(hashes * 4, 48) == {}


def test_a_mostly_unnumbered_folder_is_left_alone():
    """A few numbered files among many is coincidence, not intent."""
    mixed = NUMBERED + [f"library/images/photo_{i}.jpg" for i in range(40)]
    assert library.match_shots_by_number(mixed, 48) == {}


def test_each_number_claims_one_image():
    duplicates = ["library/new image/3_first.jpg", "library/new image/3_second.jpg"]
    out = library.match_shots_by_number(duplicates * 3, 48)
    assert len(set(out.values())) == len(out)


def test_an_empty_folder_is_not_an_error():
    assert library.match_shots_by_number([], 48) == {}
    assert library.match_shots_by_number(NUMBERED, 0) == {}


# ── Number plus words ─────────────────────────────────────────────────────────

def test_words_are_extracted_when_the_filename_kept_any():
    assert library.filename_subject_words(
        "library/new image/1_house_wisdom_found__.jpg") == ["house", "wisdom", "found"]


def test_a_truncated_filename_honestly_reports_no_words():
    """19 of 47 real files were nothing but the framing opener."""
    assert library.filename_subject_words(
        "library/new image/12_wide_establishing_sh.jpg") == []


def test_a_number_from_another_film_is_rejected_by_its_words():
    """
    Every generated set starts at 1, so numbers collide the moment images from
    two scripts share a folder. Words settle which film a picture came from.
    """
    other_film = ["library/images/1_roman_legion_marchi.jpg",
                  "library/images/2_roman_siege_towers_.jpg",
                  "library/images/3_roman_camp_at_dusk_.jpg"]
    prompts = {
        0: "wide establishing shot of house wisdom founding, 7th century",
        1: "wide establishing shot of battle fahl shurahbil, 7th century",
        2: "wide establishing shot of quran states powerfully, 7th century",
    }
    assert library.match_shots_by_number(other_film, 48, shot_prompts=prompts) == {}


def test_a_truncated_name_is_still_trusted_on_its_number():
    """There is nothing to cross-check against, and the number is real evidence."""
    files = ["library/new image/10_wide_establishing_sh.jpg",
             "library/new image/11_wide_establishing_sh.jpg",
             "library/new image/12_wide_establishing_sh.jpg"]
    prompts = {i: "wide establishing shot of something entirely different" for i in range(12)}
    out = library.match_shots_by_number(files, 48, shot_prompts=prompts)
    assert len(out) == 3, "truncated names were rejected for words they never had"


def test_matching_words_keep_the_number():
    files = ["library/new image/1_house_wisdom_found__.jpg",
             "library/new image/2_battle_fahl_shurahbi.jpg",
             "library/new image/3_quran_states_powerfu.jpg"]
    prompts = {
        0: "wide establishing shot of house wisdom founding, 7th century",
        1: "wide establishing shot of battle fahl shurahbil, 7th century",
        2: "wide establishing shot of quran states powerfully, 7th century",
    }
    assert len(library.match_shots_by_number(files, 48, shot_prompts=prompts)) == 3


def test_a_project_tag_before_the_number_is_understood():
    """
    A project tag in front of the number still parses.

    Copy all prompts no longer emits one - a tag at the head of the prompt came
    back burnt into the picture as a slate - but the user is free to name files
    that way themselves, and it remains the only thing keeping two films from
    both producing a 1_.
    """
    tagged = ["library/new image/thebat1_house_wisdom.jpg",
              "library/new image/thebat2_battle_fahl.jpg",
              "library/new image/thebat3_quran_states.jpg"]
    out = library.match_shots_by_number(tagged, 48)
    assert len(out) == 3
    assert out[0].endswith("thebat1_house_wisdom.jpg")


def test_no_prompts_available_falls_back_to_the_number_alone():
    assert len(library.match_shots_by_number(NUMBERED, 48, shot_prompts=None)) == 4


def test_parse_external_prompts_blank_lines():
    raw_text = """
    A wide establishing shot of the desert citadel at dawn.

    
    One adult male figure walking alone through the sands.


    A close-up on the ancient manuscript and inkwell.
    """
    prompts = library.parse_external_prompts(raw_text)
    assert len(prompts) == 3
    assert prompts[0] == "A wide establishing shot of the desert citadel at dawn."
    assert prompts[1] == "One adult male figure walking alone through the sands."
    assert prompts[2] == "A close-up on the ancient manuscript and inkwell."


def test_match_folder_images_by_slot_numbered_and_fallback():
    # Numbered paths bind directly to slots
    paths_numbered = [
        "C:/work/3_oasis.jpg",
        "C:/work/1_citadel.jpg",
        "C:/work/2-manuscript.png"
    ]
    matched, is_fallback = library.match_folder_images_by_slot(paths_numbered, slot_count=3)
    assert is_fallback is False
    assert matched[0].endswith("1_citadel.jpg")
    assert matched[1].endswith("2-manuscript.png")
    assert matched[2].endswith("3_oasis.jpg")

    # Unnumbered paths fall back to sorted alphabetical order
    paths_unnumbered = [
        "C:/work/oasis.jpg",
        "C:/work/citadel.jpg",
        "C:/work/manuscript.png"
    ]
    matched_sorted, is_fallback_sorted = library.match_folder_images_by_slot(paths_unnumbered, slot_count=3)
    assert is_fallback_sorted is True
    # Alphabetical: citadel, manuscript, oasis
    assert matched_sorted[0].endswith("citadel.jpg")
    assert matched_sorted[1].endswith("manuscript.png")
    assert matched_sorted[2].endswith("oasis.jpg")


def test_apply_external_prompts_full_storyboard(tmp_path):
    from PIL import Image
    work_dir = tmp_path / "work_folder"
    work_dir.mkdir()
    Image.new("RGB", (64, 64), color=(10, 10, 10)).save(work_dir / "1_citadel.jpg")
    Image.new("RGB", (64, 64), color=(20, 20, 20)).save(work_dir / "3_oasis.jpg")

    script = {
        "project": {"title": "Test External Prompts", "image_folder": str(work_dir)},
        "segments": [
            {
                "segment_id": 1,
                "narration": "First line.",
                "shots": [{"shot_id": "1a", "query": "old query 1"}]
            },
            {
                "segment_id": 2,
                "narration": "Second line.",
                "shots": [{"shot_id": "2a", "query": "old query 2"}]
            },
            {
                "segment_id": 3,
                "narration": "Third line.",
                "shots": [{"shot_id": "3a", "query": "old query 3"}]
            }
        ]
    }

    pasted = """
    Prompt One: Desert citadel

    Prompt Two: Lone figure

    Prompt Three: Oasis
    """

    res = library.apply_external_prompts(script, pasted, folder=str(work_dir))
    assert res["success"] is True
    assert res["prompts_count"] == 3
    assert res["matched_count"] == 2
    assert res["missing_slots"] == [2]
    # The summary now leads with both counts — how many pictures the film needs
    # and how many prompts were pasted — before the match result.
    assert "This film needs 3 pictures across 3 shots. You pasted 3 prompts." in res["summary"]
    assert "2 images matched, slot 2 missing." in res["summary"]

    # Verify shot prompt overrides
    shots = [s for seg in res["script_data"]["segments"] for s in seg["shots"]]
    assert shots[0]["prompt_override"] == "Prompt One: Desert citadel"
    assert shots[0]["resolved"].endswith("1_citadel.jpg")
    assert shots[1]["prompt_override"] == "Prompt Two: Lone figure"
    assert "resolved" not in shots[1]
    assert shots[2]["prompt_override"] == "Prompt Three: Oasis"
    assert shots[2]["resolved"].endswith("3_oasis.jpg")

