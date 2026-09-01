"""
The model is asked for pictures, not for sentences.

A picture does not stand for a line of narration. It stands for a *run* of
lines — 5.8 of them on average in the owner's 347-line film, which makes 60
pictures. The request never said so. It pasted the run's first sentence under
the instruction as the thing to illustrate, so picture 1, which has to carry six
lines about a world before humanity, was written from:

    Before Adam, there was no human being.

A model handed that returns a vague landscape, and it is right to — that is all
the sentence contains. The six lines it actually had to carry were sitting in
the script block above, attached to nothing.

Three further things were wrong with the same request. All 347 shots were sent,
including the 287 carrying `share_with` that never own a picture, so five sixths
of the descriptions were written and thrown away. The film's picture count was
never stated, so a batch of twenty had no idea whether it was writing for a film
of twenty or of sixty. And the batches were numbered 1..20 locally, so nothing
in the reply said where in the film a description belonged.

Now the model sees three things and nothing else: the whole script, how many
pictures the film is made of, and where each one falls in that script. The
excerpt is gone; a picture is named by its number and its span, both of which
point back into the script it has already read.
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pipeline.shot_description as shot_desc_module
from pipeline.shot_description import _build_batch_prompt, _scene_hash, describe_shots


SCRIPT = [
    "Before Adam, there was no human being.",          # 1
    "No cities. No nations.",                          # 2
    "No kings. No wars between human beings.",         # 3
    "No generations. No history as we know it.",       # 4
    "And yet something had already happened here.",    # 5
    "There had been creatures before us.",             # 6
    "They were made of smokeless fire.",               # 7
    "And they walked the earth for an age.",           # 8
]

# Two pictures over eight lines: 1-6 and 7-8.
PICTURES = [
    {"shot_id": "1a", "scene": SCRIPT[0], "picture_number": 1, "first_line": 1, "last_line": 6},
    {"shot_id": "7a", "scene": SCRIPT[6], "picture_number": 2, "first_line": 7, "last_line": 8},
]

PLAN = [{"number": p["picture_number"], "shot_id": p["shot_id"],
         "first_line": p["first_line"], "last_line": p["last_line"]} for p in PICTURES]

CFG = {
    "series_slug": "pre_islamic_prophetic___global_history",
    "prompt_recipe": "Write grounded historical descriptions.",
    "era_block": "",
}


@pytest.fixture(autouse=True)
def clean_cache(tmp_path, monkeypatch):
    shot_desc_module._MEMORY_CACHE.clear()
    monkeypatch.setattr(shot_desc_module, "CACHE_FILE", str(tmp_path / "shot_descriptions.json"))
    monkeypatch.setattr(shot_desc_module, "CACHE_DIR", str(tmp_path))


# ── what the model is shown ───────────────────────────────────────────────────

def test_the_whole_script_still_travels():
    prompt = _build_batch_prompt("INSTRUCTION", PICTURES, script_context=SCRIPT,
                                 picture_plan=PLAN)
    for line in SCRIPT:
        assert line in prompt, f"the model was not shown this line: {line!r}"


def test_the_film_states_how_many_pictures_it_is():
    prompt = _build_batch_prompt("INSTRUCTION", PICTURES, script_context=SCRIPT,
                                 picture_plan=PLAN)
    assert "exactly 2 pictures" in prompt, (
        "the model was never told how many pictures the film needs"
    )


def test_every_picture_says_which_lines_it_carries():
    prompt = _build_batch_prompt("INSTRUCTION", PICTURES, script_context=SCRIPT,
                                 picture_plan=PLAN)
    assert "Picture 1 — script lines 1-6" in prompt
    assert "Picture 2 — script lines 7-8" in prompt


def test_a_one_line_picture_is_not_called_a_range():
    solo = [{"shot_id": "3a", "scene": SCRIPT[2], "picture_number": 1,
             "first_line": 3, "last_line": 3}]
    prompt = _build_batch_prompt("INSTRUCTION", solo, script_context=SCRIPT,
                                 picture_plan=[{"number": 1, "shot_id": "3a",
                                                "first_line": 3, "last_line": 3}])
    assert "Picture 1 — script line 3" in prompt
    assert "lines 3-3" not in prompt


def test_the_excerpt_is_not_pasted_as_the_brief():
    """
    The one that mattered. The script block below the instruction is allowed to
    contain every line — that is the point of sending it. What must not happen
    is the run's first sentence appearing a second time, underneath the picture
    it belongs to, where it reads as the whole brief for that picture.
    """
    prompt = _build_batch_prompt("INSTRUCTION", PICTURES, script_context=SCRIPT,
                                 picture_plan=PLAN)

    plan_section = prompt.split("THE PICTURE PLAN", 1)[1]
    assert SCRIPT[0] not in plan_section, (
        "the run's first sentence was handed to the model as the picture's brief"
    )
    assert prompt.count(SCRIPT[0]) == 1, (
        "the excerpt appears twice — once as script, once as a brief"
    )


def test_a_batch_still_sees_the_pictures_it_is_not_writing():
    """
    Batch three writes pictures 41-60 and must still know 1-40 exist. Coverage
    across a film is unreachable from inside a batch that cannot see the rest.
    """
    second_only = [PICTURES[1]]
    prompt = _build_batch_prompt("INSTRUCTION", second_only, script_context=SCRIPT,
                                 picture_plan=PLAN)

    assert "Picture 1 — script lines 1-6" in prompt, "the batch cannot see the whole plan"
    written_now = prompt.split("WRITE THESE PICTURES NOW", 1)[1]
    assert written_now.strip().endswith("2"), "the batch was asked for the wrong pictures"


def test_no_plan_keeps_the_old_excerpt_form():
    """A caller with only a list of scenes still gets the request it always got."""
    prompt = _build_batch_prompt("INSTRUCTION", PICTURES, script_context=SCRIPT)
    assert "THE MOMENTS TO DESCRIBE" in prompt
    assert "THE PICTURE PLAN" not in prompt


# ── what comes back ───────────────────────────────────────────────────────────

def test_the_reply_is_read_by_picture_number_not_batch_position():
    """
    The reply numbers pictures in the film, so a later batch answers 41, 42, 43
    — numbers with no index inside a twenty-shot batch. Read positionally, batch
    three would either land on the wrong shots or be discarded whole.
    """
    later = [
        {"shot_id": "x", "scene": "a", "picture_number": 41, "first_line": 1, "last_line": 1},
        {"shot_id": "y", "scene": "b", "picture_number": 42, "first_line": 2, "last_line": 2},
    ]
    captured = {}

    class _Prov:
        def identity(self):
            return "gemini", "gemini-2.5-flash"

        def complete_text(self, system, user="", max_tokens=2048):
            captured["prompt"] = system
            return "41. The first of the two\n42. The second of the two"

    res = describe_shots(later, series_cfg=CFG, script_context=SCRIPT, provider=_Prov())

    assert res == {"x": "The first of the two", "y": "The second of the two"}


def test_a_description_is_rehashed_when_its_run_changes():
    """
    The span is most of the brief now, so it belongs in the cache key. Moving the
    image budget changes every run; serving the old answer would describe a
    six-line sweep with a picture written for one line.
    """
    wide = _scene_hash(SCRIPT[0], series_slug="n", prompt_recipe="r", script_context=SCRIPT,
                       span="script lines 1-6", total_pictures=2)
    narrow = _scene_hash(SCRIPT[0], series_slug="n", prompt_recipe="r", script_context=SCRIPT,
                         span="script line 1", total_pictures=8)
    assert wide != narrow, "the cached description ignores the run it has to carry"

    same = _scene_hash(SCRIPT[0], series_slug="n", prompt_recipe="r", script_context=SCRIPT,
                       span="script lines 1-6", total_pictures=2)
    assert wide == same, "the key is not stable for the same run"


# ── which shots are pictures, and how much each one carries ───────────────────

def _flat(*share_with):
    """(script_line, shot) for a film where share_with[i] is None or an owner id."""
    return [(i + 1, {"shot_id": f"{i + 1}a", "share_with": sw})
            for i, sw in enumerate(share_with)]


def test_a_picture_carries_its_owner_s_line_and_every_line_merged_into_it():
    from pipeline.library import picture_runs

    runs = picture_runs(_flat(None, "1a", "1a", "1a", "1a", "1a", None, "7a"))

    assert [r["number"] for r in runs] == [1, 2]
    assert (runs[0]["first_line"], runs[0]["last_line"]) == (1, 6)
    assert (runs[1]["first_line"], runs[1]["last_line"]) == (7, 8)


def test_shots_that_never_own_a_picture_are_not_described():
    """
    347 shots were sent for a 60-picture film. The 287 descriptions written for
    `share_with` shots were thrown away by the caller that asked for them.
    """
    from pipeline.library import picture_runs, picture_owning_shots

    runs = picture_runs(_flat(None, "1a", "1a", None, "4a"))
    assert [r["shot_id"] for r in runs] == ["1a", "4a"]


def test_the_run_count_matches_the_list_everything_else_counts_from():
    """
    Slot n is the nth picture the film makes, everywhere. If these two disagree
    the numbering contract breaks and prompt n stops meaning n.jpg.
    """
    from pipeline.library import picture_runs, picture_owning_shots

    script = {"segments": [
        {"narration": "one", "shots": [{"shot_id": "1a"}]},
        {"narration": "two", "shots": [{"shot_id": "2a", "share_with": "1a"}]},
        {"narration": "three", "shots": [{"shot_id": "3a"}]},
        {"narration": "four", "shots": [{"shot_id": "4a", "share_with": "3a"}]},
        {"narration": "five", "shots": [{"shot_id": "5a"}]},
    ]}
    flat = [(i + 1, shot)
            for i, seg in enumerate(script["segments"])
            for shot in seg["shots"]]

    runs = picture_runs(flat)
    assert len(runs) == len(picture_owning_shots(script))
    assert [r["shot_id"] for r in runs] == [s.get("shot_id") for _seg, s in picture_owning_shots(script)]


# ── who owns the camera ───────────────────────────────────────────────────────

RECIPE_CFG = {
    "series_slug": "recipe_niche",
    "prompt_recipe": "Write grounded historical descriptions.",
    "medium_block": "oil on linen",
    "palette_block": "",
    "era_block": "",
    "world_anchor": "",
    "style_presets": {},
}

PLAIN_CFG = dict(RECIPE_CFG, prompt_recipe="")

# What the model returns when it has been asked to choose the camera itself.
MODEL_WRITTEN = ("An expansive untouched primordial landscape stretching to the horizon under a "
                 "clear ancient sky, seen from a low vantage with dry ground filling the "
                 "foreground, lit by hard overhead sun")


def _compose(cfg, **kw):
    from pipeline import library
    base = dict(shot_query="the empty earth",
                script_context="They marched before dawn through snow.",
                series_slug=cfg["series_slug"], include_negative=False)
    base.update(kw)
    return library.compose_gap_prompt(**base)


@pytest.fixture
def recipe_niche(monkeypatch):
    from pipeline import library
    monkeypatch.setattr(library, "get_series_config", lambda **kw: RECIPE_CFG)


@pytest.fixture
def plain_niche(monkeypatch):
    from pipeline import library
    monkeypatch.setattr(library, "get_series_config", lambda **kw: PLAIN_CFG)


def test_the_composer_stops_arguing_with_the_model_about_the_camera(recipe_niche):
    """
    `default_framing_for` picked framing with `picture_index % 4`. Picture 1 of
    the owner's film is a landscape to the horizon and index 1 is "cinematic
    medium shot, subject filling much of the frame", so the prompt said both.
    """
    from pipeline.prompt_slots import DEFAULT_FRAMING_CYCLE

    out = _compose(RECIPE_CFG, visual_description=MODEL_WRITTEN, shot_position=1)

    for framing in DEFAULT_FRAMING_CYCLE:
        assert framing not in out, f"the composer overrode the model's camera with: {framing}"


def test_the_composer_stops_guessing_the_weather_and_the_light(recipe_niche):
    """The model was asked for the light and the air; the regex tables were not."""
    out = _compose(RECIPE_CFG, visual_description=MODEL_WRITTEN, shot_position=1)
    assert "pre-dawn" not in out, "the keyword table overrode the light the model chose"
    assert "snow" not in out, "the keyword table added weather from the narration"


def test_the_look_of_the_film_is_still_the_app_s(recipe_niche):
    """
    Only the content slots stand down. The look — medium, palette, era, the
    brief, the character bible — is constant across the whole film and is still
    the composer's to append, so it must survive after the model's description.
    """
    out = _compose(RECIPE_CFG, visual_description=MODEL_WRITTEN, shot_position=1)

    assert out.startswith(MODEL_WRITTEN), "the model's description did not lead the prompt"
    look = out.split(MODEL_WRITTEN, 1)[1].strip(" ,.")
    assert look, "nothing of the film's own look reached the prompt"


def test_a_niche_with_no_recipe_keeps_every_slot(plain_niche):
    """
    Built-in descriptions are the short kind and are forbidden to name a camera
    at all, so dropping the slots would leave those prompts with no framing.
    """
    from pipeline.prompt_slots import DEFAULT_FRAMING_CYCLE

    out = _compose(PLAIN_CFG, visual_description="the empty earth under a clear sky",
                   shot_position=1)
    assert any(f in out for f in DEFAULT_FRAMING_CYCLE), "no framing reached the prompt"
    assert "pre-dawn" in out, "the light slot stopped firing for a niche with no recipe"


def test_a_shot_with_no_description_keeps_every_slot(recipe_niche):
    """Nothing was written for this shot, so there is no camera to defer to."""
    from pipeline.prompt_slots import DEFAULT_FRAMING_CYCLE

    out = _compose(RECIPE_CFG, visual_description=None, shot_position=1)
    assert any(f in out for f in DEFAULT_FRAMING_CYCLE), "no framing reached the prompt"
