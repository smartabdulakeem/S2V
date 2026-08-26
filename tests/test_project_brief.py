"""The consistent opening block shared by every prompt in one script."""

from pipeline.library import draft_project_brief, BRIEF_MAX_WORDS


CFG = {"world_anchor": "7th century Arabian Peninsula, early Islamic era"}
SCRIPT = ("Khalid ibn al-Walid rode through the night. Abu Ubaidah held the centre. "
          "Khalid reached the Jordan valley before dawn and Abu Ubaidah followed.")


def test_documentary_treatment_opens_with_documentary_still():
    brief = draft_project_brief("The Battle of the Mud", CFG, SCRIPT, "documentary")
    assert brief.startswith("Documentary still from")


def test_illustration_treatment_opens_with_illustration_plate():
    brief = draft_project_brief("The Battle of the Mud", CFG, SCRIPT, "illustration")
    assert brief.startswith("Illustration plate from")


def test_silhouette_treatment_opens_with_silhouette_study():
    brief = draft_project_brief("X", CFG, SCRIPT, "silhouette")
    assert brief.startswith("Silhouette study from")


def test_unknown_treatment_falls_back_to_documentary_still():
    brief = draft_project_brief("X", CFG, SCRIPT, None)
    assert brief.startswith("Documentary still from")


def test_brief_carries_the_world_anchor():
    brief = draft_project_brief("X", CFG, SCRIPT, "documentary")
    assert "7th century Arabian Peninsula" in brief


def test_brief_names_recurring_figures():
    brief = draft_project_brief("X", CFG, SCRIPT, "documentary")
    assert "Khalid" in brief


def test_a_name_used_once_is_not_treated_as_recurring():
    script = "Khalid rode north. Zayd appeared once. Khalid turned back. Khalid rested."
    brief = draft_project_brief("X", CFG, script, "documentary")
    assert "Zayd" not in brief


def test_the_title_never_appears_verbatim():
    brief = draft_project_brief("The Battle of the Mud", CFG, SCRIPT, "documentary")
    assert "The Battle of the Mud" not in brief


def test_brief_is_capped():
    long_cfg = {"world_anchor": " ".join(["anchor"] * 60)}
    brief = draft_project_brief("X", long_cfg, SCRIPT, "documentary")
    assert len(brief.split()) <= BRIEF_MAX_WORDS


def test_brief_is_stable_for_the_same_inputs():
    a = draft_project_brief("X", CFG, SCRIPT, "documentary")
    b = draft_project_brief("X", CFG, SCRIPT, "documentary")
    assert a == b


from pipeline.library import ensure_project_brief


def test_a_missing_brief_is_drafted():
    info = {"title": "The Battle of the Mud", "series_slug": "islamic_history",
            "visual_type": "architectural_plate"}
    out = ensure_project_brief(info, SCRIPT)
    assert out.startswith("Documentary still from")


def test_an_existing_brief_is_left_alone():
    info = {"title": "X", "series_slug": "islamic_history",
            "visual_type": "architectural_plate",
            "project_brief": "My own wording, untouched"}
    assert ensure_project_brief(info, SCRIPT) == "My own wording, untouched"


def test_a_blank_brief_is_treated_as_missing():
    info = {"title": "X", "series_slug": "islamic_history",
            "visual_type": "architectural_plate", "project_brief": "   "}
    assert ensure_project_brief(info, SCRIPT).startswith("Documentary still from")
