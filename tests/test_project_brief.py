"""The consistent opening block shared by every prompt in one script."""

from pipeline.library import draft_project_brief, BRIEF_MAX_WORDS


CFG = {
    "world_anchor": "7th century Arabian Peninsula, early Islamic era",
    "brief_subject": "seventh century Arabia and early Islamic history",
}
SCRIPT = ("Khalid ibn al-Walid rode through the night. Abu Ubaidah held the centre. "
          "Khalid reached the Jordan valley before dawn and Abu Ubaidah followed.")


#: The brief used to open by naming a medium, chosen from the treatment. The
#: picked visual type states the medium already, so the prompt either said it
#: twice or asked for two different things at once — a project set to Paper
#: Collage carried "A documentary photograph of real people and places"
#: alongside "Cut-paper collage on textured board" in all 55 of its prompts.
#: The brief now carries the subject and the recurring figures, nothing else.
_MEDIUM_WORDS = ("photograph", "photo", "illustrated", "illustration",
                 "silhouetted", "silhouette", "collage", "cinematic",
                 "painting", "render", "film", "plate", "still")


def test_the_brief_never_names_a_medium_whatever_the_treatment():
    for treatment in ("documentary", "illustration", "silhouette",
                      "vox_collage", "vignette", None, "not_a_treatment"):
        brief = draft_project_brief("The Battle of the Mud", CFG, SCRIPT, treatment)
        lowered = brief.lower()
        named = [w for w in _MEDIUM_WORDS if w in lowered]
        assert not named, f"treatment {treatment!r} put {named} into the brief: {brief!r}"


def test_the_treatment_no_longer_changes_the_brief():
    """It is accepted so existing callers keep working, and ignored."""
    a = draft_project_brief("X", CFG, SCRIPT, "documentary")
    b = draft_project_brief("X", CFG, SCRIPT, "silhouette")
    c = draft_project_brief("X", CFG, SCRIPT, None)
    assert a == b == c


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
    brief = report.get("project_brief", "")
    assert brief, "plan_shots returned no brief"
    assert "photograph" not in brief.lower(), brief
    assert "seventh century Arabia" in brief, brief


def test_brief_is_stable_for_the_same_inputs():
    a = draft_project_brief("X", CFG, SCRIPT, "documentary")
    b = draft_project_brief("X", CFG, SCRIPT, "documentary")
    assert a == b


from pipeline.library import ensure_project_brief


def test_a_missing_brief_is_drafted():
    info = {"title": "The Battle of the Mud", "series_slug": "islamic_history",
            "visual_type": "architectural_plate"}
    out = ensure_project_brief(info, SCRIPT)
    assert out.strip(), "no brief was drafted"
    assert "photograph" not in out.lower(), out


def test_a_stored_brief_is_redrawn_rather_than_kept():
    """
    It used to be drafted once and never overwritten, to protect a hand-edited
    brief. There is no box to edit it in any more, and freezing it did harm: a
    brief drafted before the visual type was picked went on claiming the wrong
    medium for the life of the project, and changing the visual type could not
    dislodge it.
    """
    info = {"title": "X", "series_slug": "islamic_history",
            "visual_type": "architectural_plate",
            "project_brief": "A documentary photograph of something stale"}
    out = ensure_project_brief(info, SCRIPT)
    assert out != info["project_brief"], "a stale brief survived"
    assert "photograph" not in out.lower(), out


def test_a_blank_brief_is_treated_as_missing():
    info = {"title": "X", "series_slug": "islamic_history",
            "visual_type": "architectural_plate", "project_brief": "   "}
    assert ensure_project_brief(info, SCRIPT).strip()
