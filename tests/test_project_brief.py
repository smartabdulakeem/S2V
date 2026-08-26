"""The consistent opening block shared by every prompt in one script."""

from pipeline.library import draft_project_brief, BRIEF_MAX_WORDS


CFG = {
    "world_anchor": "7th century Arabian Peninsula, early Islamic era",
    "brief_subject": "seventh century Arabia and early Islamic history",
}
SCRIPT = ("Khalid ibn al-Walid rode through the night. Abu Ubaidah held the centre. "
          "Khalid reached the Jordan valley before dawn and Abu Ubaidah followed.")


def test_documentary_treatment_opens_with_documentary_still():
    brief = draft_project_brief("The Battle of the Mud", CFG, SCRIPT, "documentary")
    assert brief.startswith("A documentary photograph of")


def test_illustration_treatment_opens_with_illustration_plate():
    brief = draft_project_brief("The Battle of the Mud", CFG, SCRIPT, "illustration")
    assert brief.startswith("An illustrated scene of")


def test_silhouette_treatment_opens_with_silhouette_study():
    brief = draft_project_brief("X", CFG, SCRIPT, "silhouette")
    assert brief.startswith("A silhouetted scene of")


def test_unknown_treatment_falls_back_to_documentary_still():
    brief = draft_project_brief("X", CFG, SCRIPT, None)
    assert brief.startswith("A documentary photograph of")


def test_brief_names_the_subject_not_the_medium():
    brief = draft_project_brief("X", CFG, SCRIPT, "documentary")
    assert "seventh century Arabia" in brief


def test_brief_carries_no_medium_language_from_the_pack():
    # A pack's world_anchor carries medium language ("... documentary archive",
    # "... tintype archival photograph"). Opening every prompt with that fought
    # the picked visual type: ask for an illustration and the prompt also
    # demanded a photograph. brief_subject carries subject only.
    from pipeline.library import get_series_config
    cfg = get_series_config(series_slug="world_military_history")
    brief = draft_project_brief("X", cfg, SCRIPT, "illustration")
    assert "archive" not in brief.lower(), brief
    assert "photograph" not in brief.lower(), brief


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
    long_cfg = {"brief_subject": " ".join(["subject"] * 60)}
    brief = draft_project_brief("X", long_cfg, SCRIPT, "documentary")
    assert len(brief.split()) <= BRIEF_MAX_WORDS


def test_a_capped_brief_does_not_end_mid_clause():
    long_cfg = {"brief_subject": "a documentary on " + " ".join(["subject"] * 60)}
    brief = draft_project_brief("X", long_cfg, SCRIPT, "documentary")
    assert not brief.rstrip().endswith(("of", "on", "in", "the", "and", ","))


def test_a_hand_edited_brief_is_capped_too():
    from pipeline.library import ensure_project_brief
    info = {"title": "X", "series_slug": "islamic_history",
            "visual_type": "architectural_plate",
            "project_brief": " ".join(["word"] * 80)}
    assert len(ensure_project_brief(info, SCRIPT).split()) <= BRIEF_MAX_WORDS


def test_a_full_name_is_not_split_into_two_characters():
    script = ("Khalid ibn al-Walid rode out. Abu Ubaidah held the centre. "
              "Khalid ibn al-Walid returned. Abu Ubaidah followed.")
    brief = draft_project_brief("X", CFG, script, "documentary")
    assert "Khalid ibn al-Walid" in brief, brief
    assert "Abu Ubaidah" in brief, brief


def test_sentence_openers_are_not_mistaken_for_characters():
    script = ("Then the army moved. Then it rested. "
              "Suddenly the walls fell. Suddenly it was over.")
    brief = draft_project_brief("X", CFG, script, "documentary")
    assert "Then" not in brief, brief
    assert "Suddenly" not in brief, brief


def test_a_hyphenated_name_stays_whole():
    script = "Jean-Baptiste arrived early. Jean-Baptiste left late."
    brief = draft_project_brief("X", CFG, script, "documentary")
    assert "Jean-Baptiste" in brief, brief


def test_plan_shots_returns_the_brief_it_drafted():
    import glob, json
    from pipeline.library import plan_shots
    with open(sorted(glob.glob("samples/*.json"))[0], encoding="utf-8") as f:
        d = json.load(f)
    d.setdefault("project", {})["series_slug"] = "islamic_history"
    d["project"]["visual_type"] = "architectural_plate"
    report = plan_shots(d)
    assert report.get("project_brief", "").startswith("A documentary photograph of"), \
        report.get("project_brief")


def test_brief_is_stable_for_the_same_inputs():
    a = draft_project_brief("X", CFG, SCRIPT, "documentary")
    b = draft_project_brief("X", CFG, SCRIPT, "documentary")
    assert a == b


from pipeline.library import ensure_project_brief


def test_a_missing_brief_is_drafted():
    info = {"title": "The Battle of the Mud", "series_slug": "islamic_history",
            "visual_type": "architectural_plate"}
    out = ensure_project_brief(info, SCRIPT)
    assert out.startswith("A documentary photograph of")


def test_an_existing_brief_is_left_alone():
    info = {"title": "X", "series_slug": "islamic_history",
            "visual_type": "architectural_plate",
            "project_brief": "My own wording, untouched"}
    assert ensure_project_brief(info, SCRIPT) == "My own wording, untouched"


def test_a_blank_brief_is_treated_as_missing():
    info = {"title": "X", "series_slug": "islamic_history",
            "visual_type": "architectural_plate", "project_brief": "   "}
    assert ensure_project_brief(info, SCRIPT).startswith("A documentary photograph of")


def test_no_opener_names_a_physical_object():
    """
    An opener describes the kind of picture, never a thing you could hold.

    "Illustration plate from a documentary on early Islamic history" came back
    from the generator as a decorative plate with that sentence lettered
    underneath, and another frame carried "PLATE 40:" across it. The generator
    draws the nouns it is handed. This guards the whole table, so a future
    opener cannot quietly reintroduce the artefact.
    """
    from pipeline.library import BRIEF_OPENERS

    banned = ("plate", "still", "study", "panel", "print", "poster",
              "page", "sheet", "card", "frame", "clipping")
    for treatment, opener in BRIEF_OPENERS.items():
        words = opener.lower().replace(",", " ").split()
        hit = [w for w in words if w in banned]
        assert not hit, f"{treatment!r} opener names an artefact: {opener!r} ({hit})"
        assert not opener.lower().endswith(" from"), (
            f"{treatment!r} opener says 'from', which implies the picture was cut "
            f"out of a larger printed thing: {opener!r}"
        )
