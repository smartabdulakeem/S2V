"""
Projects must survive closing the app.

Planned scripts were written to a file in Windows TEMP, and the only way back was
the "Open JSON Script…" picker. Closing the app therefore lost every image placed
by hand on the board — and TEMP is cleared by Windows on its own schedule. The
JSON portal is gone; projects live under projects/ and reopen by themselves.
"""

import json
import os

import pytest

import app as smart_studio_app


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(smart_studio_app, "BASE_DIR", str(tmp_path))
    monkeypatch.setattr(smart_studio_app.Api, "LAST_PROJECT_PATH",
                        str(tmp_path / "config" / "last_project.json"))
    return smart_studio_app.Api()


def _script(title="S2E6 — The Long Retreat", pin="library/images/chosen.jpg"):
    return {
        "project": {"title": title},
        "segments": [{
            "segment_id": 1, "narration": "n",
            "shots": [{"shot_id": "1a", "query": "q", "source": "pin", "pin": pin}],
        }],
    }


def test_a_project_is_saved_under_the_projects_folder(api, tmp_path):
    """
    Not in the system temp directory, where the planner used to put it. Asserting
    "not under Temp" is meaningless here — pytest's own sandbox lives there — so
    the real property is that it lands in the app's own projects folder under a
    stable name.
    """
    res = api.save_project(_script())

    assert res["success"]
    assert os.path.exists(res["path"])
    assert os.path.dirname(os.path.dirname(res["path"])) == str(tmp_path / "projects")
    assert os.path.basename(res["path"]) == "script.json"


def test_it_reopens_with_the_images_you_placed(api):
    api.save_project(_script(pin="library/images/i_chose_this.jpg"))

    got = api.get_last_project()

    assert got["found"] is True
    assert got["segments"] == 1
    assert got["script_data"]["segments"][0]["shots"][0]["pin"] == "library/images/i_chose_this.jpg"


def test_the_newest_save_is_the_one_that_reopens(api):
    api.save_project(_script(title="First"))
    api.save_project(_script(title="Second"))

    assert api.get_last_project()["title"] == "Second"


def test_nothing_saved_yet_is_not_an_error(api):
    got = api.get_last_project()
    assert got["success"] is True and got["found"] is False


def test_a_deleted_project_does_not_break_startup(api):
    res = api.save_project(_script())
    os.remove(res["path"])

    got = api.get_last_project()

    assert got["success"] is True
    assert got["found"] is False, "startup would have tried to open a file that is gone"


def test_an_awkward_title_still_makes_a_usable_folder(api):
    res = api.save_project(_script(title='S2E2 — "The Weight of the Mantle": part 1/2'))

    assert res["success"]
    assert os.path.exists(res["path"])
    # The folder name must be a legal path, but the real title is preserved.
    assert json.load(open(res["path"], encoding="utf-8"))["project"]["title"].startswith("S2E2")


def test_an_untitled_project_still_saves(api):
    res = api.save_project({"project": {}, "segments": []})
    assert res["success"]
    assert os.path.exists(res["path"])
