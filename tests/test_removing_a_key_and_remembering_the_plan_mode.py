"""
Two faults the board carried in silence.

1. Clearing an API key in Settings did nothing. Saving is guarded by
   `if (keyVal)`, so an emptied field reads as "no change" - and that guard has
   to stay, because `get_settings` never sends real keys to the browser, so
   every field is blank on load and an always-save would wipe a working key the
   first time any other provider was tested. Removing a key is a different
   intention from saving one and now has its own door.

2. The Auto/Exact toggle reset to Auto on every load while the saved plan did
   not, so a film pinned to an exact count came back reading "Auto" - and
   pressing Re-plan then quietly changed what had been asked for.
"""

import pytest

from app import Api


@pytest.fixture
def api(monkeypatch):
    """An Api whose settings live in memory, never on the owner's disk."""
    saved = {}
    monkeypatch.setattr("app._save_settings", lambda s: saved.update(s))
    a = Api()
    a._settings = {
        "google_api_key": "real-google-key",
        "google_tts_api_key": "real-tts-key",
        "anthropic_api_key": "real-anthropic-key",
        "openai_api_key": "",
        "deepseek_api_key": "real-deepseek-key",
    }
    a._saved = saved
    return a


# ── removing a key ───────────────────────────────────────────────────────────

def test_a_key_can_be_removed(api):
    out = api.remove_api_key("anthropic")

    assert out["success"] is True
    assert out["removed"] is True
    assert api._settings["anthropic_api_key"] == ""


def test_removing_one_key_leaves_every_other_alone(api):
    """The whole reason the always-save fix was rejected."""
    api.remove_api_key("anthropic")

    assert api._settings["google_api_key"] == "real-google-key"
    assert api._settings["google_tts_api_key"] == "real-tts-key"
    assert api._settings["deepseek_api_key"] == "real-deepseek-key"


def test_the_removal_reaches_the_disk(api):
    api.remove_api_key("deepseek")
    assert api._saved.get("deepseek_api_key") == "", "the key was cleared in memory only"


def test_gemini_and_google_name_the_same_key(api):
    """The UI says gemini; the settings file says google_api_key."""
    assert api.remove_api_key("gemini")["removed"] is True
    assert api._settings["google_api_key"] == ""


def test_removing_a_key_that_was_never_set_is_not_an_error(api):
    out = api.remove_api_key("openai")
    assert out["success"] is True
    assert out["removed"] is False, "it should say plainly that there was nothing there"


def test_an_unknown_provider_is_refused(api):
    out = api.remove_api_key("hotmail")
    assert out["success"] is False
    assert "hotmail" in out["error"]
    assert api._settings["google_api_key"] == "real-google-key"


@pytest.mark.parametrize("name", ["", None, "  "])
def test_a_missing_provider_name_removes_nothing(api, name):
    assert api.remove_api_key(name)["success"] is False
    assert api._settings["google_api_key"] == "real-google-key"


def test_every_secret_the_settings_screen_shows_can_be_removed():
    """
    A key the UI can set but not remove is a trap. These are the ones
    `get_settings` deliberately reduces to a set/not-set flag.
    """
    removable = set(Api.PROVIDER_KEY_NAMES.values())
    for secret in Api.SECRET_SETTING_KEYS:
        assert secret in removable, f"{secret} can be set but never removed"


# ── remembering how the plan was asked for ───────────────────────────────────

def script(lines=6):
    return {
        "project": {"title": "Plan Mode", "series_slug": None},
        "segments": [
            {"segment_id": i, "narration": f"line {i} of the film",
             "shots": [{"shot_id": f"{i}a", "query": "q", "scene": f"line {i}"}]}
            for i in range(1, lines + 1)
        ],
    }


@pytest.fixture
def planning_api(monkeypatch):
    """Planning without a model: the spans come back already decided."""
    monkeypatch.setattr("pipeline.picture_plan.plan_pictures",
                        lambda lines, seconds, **kw: [
                            {"number": 1, "first_line": 1, "last_line": 3, "description": "one"},
                            {"number": 2, "first_line": 4, "last_line": 6, "description": "two"},
                        ])
    monkeypatch.setattr("app._save_settings", lambda s: None)
    return Api()


def test_an_exact_plan_is_remembered_as_exact(planning_api):
    data = script()
    out = planning_api.plan_pictures_for_script(data, image_count=2)

    assert out["success"] is True
    assert data["project"]["plan_mode"] == "exact"
    assert data["project"]["plan_count"] == 2


def test_an_auto_plan_is_remembered_as_auto(planning_api):
    data = script()
    planning_api.plan_pictures_for_script(data, image_count=None,
                                          min_hold=9.0, max_hold=55.0)

    assert data["project"]["plan_mode"] == "auto"
    assert data["project"]["plan_count"] is None
    assert data["project"]["plan_min_hold"] == 9.0
    assert data["project"]["plan_max_hold"] == 55.0


def test_the_hold_range_is_remembered_so_the_board_stops_contradicting_itself(planning_api):
    data = script()
    planning_api.plan_pictures_for_script(data, image_count=None,
                                          min_hold=12.0, max_hold=30.0)

    assert (data["project"]["plan_min_hold"],
            data["project"]["plan_max_hold"]) == (12.0, 30.0)


def test_re_planning_replaces_the_record(planning_api):
    """Asking again in the other mode must not leave the old answer behind."""
    data = script()
    planning_api.plan_pictures_for_script(data, image_count=2)
    assert data["project"]["plan_mode"] == "exact"

    planning_api.plan_pictures_for_script(data, image_count=None)
    assert data["project"]["plan_mode"] == "auto"
    assert data["project"]["plan_count"] is None
