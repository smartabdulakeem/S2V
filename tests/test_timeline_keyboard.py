"""
tests/test_timeline_keyboard.py

Verification for Slice I: Timeline NLE Keyboard Transport, Shuttle Controls & 3-Stage Navigation.
Covers:
1. Nudge arithmetic: Left/Right (\u00b11s default, \u00b15s with Shift), J shuttle (-2s).
2. Bounds clamping: Home (0:00), End (total), nudging clamped to [0, total].
3. Clip stepping: ArrowUp / ArrowDown clip index navigation clamped between [0, count-1].
4. Input focus guard: Typing inside INPUT, TEXTAREA, SELECT, or isContentEditable does not trigger shortcuts.
5. 3-Stage navigation: 1 -> script, 2 -> board, 3 -> timeline.
6. Inactive timeline guard: Transport keys (Space, Arrows, Home, End, JKL) do not fire when timeline pane is not active.
7. 1-Click Storyboard-to-Timeline hand-off focuses timeline container.
8. HTML & CSS compliance: .tl-shortcuts-hint in index.html & style.css, inline style count <= 19.
"""

import json
import os
import re
import subprocess
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_JS = os.path.join(REPO_ROOT, "frontend", "app.js")
INDEX_HTML = os.path.join(REPO_ROOT, "frontend", "index.html")
STYLE_CSS = os.path.join(REPO_ROOT, "frontend", "style.css")


def _run_node(js_code: str) -> dict:
    """Run a Node.js harness with app.js loaded and return parsed JSON stdout."""
    with open(APP_JS, "r", encoding="utf-8") as f:
        app_code = f.read()

    wrapper = f"""
const listeners = {{}};
let activeElem = {{ tagName: "BODY", isContentEditable: false, closest: () => null }};
let timelinePaneAttr = {{ "data-pane": "timeline", "data-on": "1" }};
let panes = [
  {{ dataset: {{ pane: "script" }}, getAttribute: (k) => k === "data-pane" ? "script" : (k === "data-on" ? (timelinePaneAttr["data-on"] === "1" ? null : "1") : null), setAttribute: () => {{}}, removeAttribute: () => {{}} }},
  {{ dataset: {{ pane: "board" }}, getAttribute: (k) => k === "data-pane" ? "board" : null, setAttribute: () => {{}}, removeAttribute: () => {{}} }},
  {{ dataset: {{ pane: "timeline" }}, getAttribute: (k) => timelinePaneAttr[k] || null, setAttribute: (k, v) => {{ timelinePaneAttr[k] = v; }}, removeAttribute: (k) => {{ delete timelinePaneAttr[k]; }} }}
];

const mockScroll = {{
  clientWidth: 800,
  scrollLeft: 0,
  hasAttribute: (a) => false,
  setAttribute: (a, v) => {{}},
  focus: () => {{ mockScroll.focused = true; }}
}};

let document = {{
  addEventListener: (event, handler) => {{
    if (!listeners[event]) listeners[event] = [];
    listeners[event].push(handler);
  }},
  querySelectorAll: (sel) => {{
    if (sel === ".pane") return panes;
    if (sel.includes("pane")) return panes;
    return [];
  }},
  querySelector: (sel) => {{
    if (sel.includes('data-pane="timeline"')) return panes[2];
    return null;
  }},
  getElementById: (id) => {{
    if (id === "tl-scroll") return mockScroll;
    if (id === "tl-lanes") return mockScroll;
    return null;
  }}
}};

Object.defineProperty(document, "activeElement", {{
  get: () => activeElem,
  set: (val) => {{
    activeElem = val;
    if (activeElem && !activeElem.closest) {{
      activeElem.closest = () => null;
    }}
  }}
}});

let window = {{
  addEventListener: () => {{}},
  document: document
}};

// Load app.js
{app_code}

// Test harness execution
{js_code}
"""
    res = subprocess.run(["node", "-"], input=wrapper.encode("utf-8"), capture_output=True)
    if res.returncode != 0:
        raise RuntimeError(f"Node exited with {res.returncode}:\n{res.stderr.decode('utf-8')}")
    return json.loads(res.stdout.decode("utf-8").strip())


def test_nudge_arithmetic_and_bounds():
    """
    Test 1 & 2: Verify playhead nudging arithmetic (\u00b11s, \u00b15s with shift, -2s J shuttle)
    and bounds clamping between [0, total].
    """
    res = _run_node("""
    currentScriptData = {
      segments: [
        { narration_seconds: "10.0" },
        { narration_seconds: "15.0" }
      ]
    }; // total = 25.0s
    tlPlayhead = 10.0;

    const dispatch = (key, shiftKey = false) => {
      let defaultPrevented = false;
      const ev = {
        key: key,
        code: key === " " ? "Space" : key,
        shiftKey: shiftKey,
        preventDefault: () => { defaultPrevented = true; }
      };
      listeners["keydown"].forEach(h => h(ev));
      return { playhead: tlPlayhead, prevented: defaultPrevented };
    };

    const results = {};

    // 1s backward
    results.left = dispatch("ArrowLeft");
    // 5s backward with shift
    results.shiftLeft = dispatch("ArrowLeft", true);
    // 1s forward
    results.right = dispatch("ArrowRight");
    // 5s forward with shift
    results.shiftRight = dispatch("ArrowRight", true);
    // J shuttle (-2s)
    results.j = dispatch("j");
    // Capital J (-2s)
    results.capJ = dispatch("J");

    // Home jump to 0
    results.home = dispatch("Home");
    // Underflow clamping past 0
    results.underflow = dispatch("ArrowLeft", true);

    // End jump to 25.0
    results.end = dispatch("End");
    // Overflow clamping past 25.0
    results.overflow = dispatch("ArrowRight", true);

    console.log(JSON.stringify(results));
    """)

    # Starting at 10.0:
    assert res["left"]["playhead"] == 9.0
    assert res["left"]["prevented"] is True
    # 9.0 - 5.0 = 4.0:
    assert res["shiftLeft"]["playhead"] == 4.0
    # 4.0 + 1.0 = 5.0:
    assert res["right"]["playhead"] == 5.0
    # 5.0 + 5.0 = 10.0:
    assert res["shiftRight"]["playhead"] == 10.0
    # 10.0 - 2.0 = 8.0:
    assert res["j"]["playhead"] == 8.0
    # 8.0 - 2.0 = 6.0:
    assert res["capJ"]["playhead"] == 6.0

    # Home jumps to 0.0:
    assert res["home"]["playhead"] == 0.0
    # Underflow clamped at 0.0:
    assert res["underflow"]["playhead"] == 0.0

    # End jumps to total (25.0):
    assert res["end"]["playhead"] == 25.0
    # Overflow clamped at 25.0:
    assert res["overflow"]["playhead"] == 25.0


def test_input_guard_prevents_shortcuts():
    """
    Test 4: When activeElement is an INPUT, TEXTAREA, SELECT, or isContentEditable,
    shortcuts are ignored and default is NOT prevented.
    """
    res = _run_node("""
    currentScriptData = {
      segments: [{ narration_seconds: "10.0" }]
    };
    tlPlayhead = 5.0;

    let switched = null;
    switchPane = (p) => { switched = p; };

    const testTag = (tag, isEditable = false) => {
      document.activeElement = { tagName: tag, isContentEditable: isEditable, closest: () => null };
      let prevented = false;
      const ev = {
        key: "1",
        shiftKey: false,
        preventDefault: () => { prevented = true; }
      };
      listeners["keydown"].forEach(h => h(ev));
      return { prevented, switched };
    };

    const checks = {
      input: testTag("INPUT"),
      textarea: testTag("TEXTAREA"),
      select: testTag("SELECT"),
      editable: testTag("DIV", true),
      normalBody: testTag("BODY", false)
    };

    console.log(JSON.stringify(checks));
    """)

    assert res["input"]["prevented"] is False
    assert res["input"]["switched"] is None

    assert res["textarea"]["prevented"] is False
    assert res["textarea"]["switched"] is None

    assert res["select"]["prevented"] is False
    assert res["select"]["switched"] is None

    assert res["editable"]["prevented"] is False
    assert res["editable"]["switched"] is None

    # Normal BODY focus DOES trigger
    assert res["normalBody"]["prevented"] is True
    assert res["normalBody"]["switched"] == "script"


def test_3_stage_navigation():
    """
    Test 5: Global 1, 2, 3 keys switch panes.
    """
    res = _run_node("""
    let switches = [];
    switchPane = (p) => { switches.push(p); };
    document.activeElement = { tagName: "BODY", isContentEditable: false };

    const press = (k) => {
      const ev = { key: k, preventDefault: () => {} };
      listeners["keydown"].forEach(h => h(ev));
    };

    press("1");
    press("2");
    press("3");

    console.log(JSON.stringify(switches));
    """)

    assert res == ["script", "board", "timeline"]


def test_inactive_timeline_guard():
    """
    Test 6: Transport shortcuts do nothing when Timeline is not the active pane.
    """
    res = _run_node("""
    currentScriptData = { segments: [{ narration_seconds: "10.0" }] };
    tlPlayhead = 5.0;
    timelinePaneAttr["data-on"] = "0"; // Inactive
    document.activeElement = { tagName: "BODY", isContentEditable: false };

    let playToggled = false;
    timelineTogglePlay = () => { playToggled = true; };

    let prevented = false;
    const ev = { key: "ArrowLeft", preventDefault: () => { prevented = true; } };
    listeners["keydown"].forEach(h => h(ev));

    const spaceEv = { key: " ", preventDefault: () => {} };
    listeners["keydown"].forEach(h => h(spaceEv));

    console.log(JSON.stringify({
      playhead: tlPlayhead,
      prevented: prevented,
      playToggled: playToggled
    }));
    """)

    assert res["playhead"] == 5.0
    assert res["prevented"] is False
    assert res["playToggled"] is False


def test_jkl_shuttle_controls():
    """
    Test 7: J/K/L shuttle keys trigger reverse nudge, pause, and play toggle.
    """
    res = _run_node("""
    currentScriptData = { segments: [{ narration_seconds: "20.0" }] };
    tlPlayhead = 10.0;
    timelinePaneAttr["data-on"] = "1";
    document.activeElement = { tagName: "BODY", isContentEditable: false };

    let paused = false;
    let played = false;
    timelinePauseAudio = () => { paused = true; };
    timelineTogglePlay = () => { played = true; };

    const press = (k) => {
      let prevented = false;
      const ev = { key: k, preventDefault: () => { prevented = true; } };
      listeners["keydown"].forEach(h => h(ev));
      return prevented;
    };

    const prevK = press("k");
    const prevL = press("l");
    const prevJ = press("j");

    console.log(JSON.stringify({
      paused,
      played,
      playheadAfterJ: tlPlayhead,
      prevK,
      prevL,
      prevJ
    }));
    """)

    assert res["paused"] is True
    assert res["played"] is True
    assert res["playheadAfterJ"] == 8.0
    assert res["prevK"] is True
    assert res["prevL"] is True
    assert res["prevJ"] is True


def test_open_timeline_from_board_focus():
    """
    Test 8: openTimelineFromBoard sets focus on the timeline container.
    """
    res = _run_node("""
    currentScriptData = { segments: [{ narration_seconds: "10.0" }] };
    mockScroll.focused = false;
    renderTimelineScreen = () => {};
    switchPane = () => {};

    openTimelineFromBoard();

    console.log(JSON.stringify({ focused: mockScroll.focused }));
    """)

    assert res["focused"] is True


def test_picture_clip_stepping():
    """
    Test 3: ArrowUp / ArrowDown steps to previous / next picture clip.
    """
    res = _run_node("""
    currentScriptData = {
      segments: [
        { segment_id: 1, narration_seconds: "10.0", shots: [{ shot_id: "1a" }] },
        { segment_id: 2, narration_seconds: "10.0", shots: [{ shot_id: "2a" }] },
        { segment_id: 3, narration_seconds: "10.0", shots: [{ shot_id: "3a" }] }
      ]
    };
    tlPlayhead = 0.0;
    tlSelected = 1;
    timelinePaneAttr["data-on"] = "1";
    document.activeElement = { tagName: "BODY", isContentEditable: false };

    let seekDirection = null;
    timelineSeekPicture = (dir) => { seekDirection = dir; };

    const press = (key) => {
      let prevented = false;
      const ev = { key: key, preventDefault: () => { prevented = true; } };
      listeners["keydown"].forEach(h => h(ev));
      return { dir: seekDirection, prevented };
    };

    const up = press("ArrowUp");
    const down = press("ArrowDown");

    console.log(JSON.stringify({ up, down }));
    """)

    assert res["up"]["dir"] == -1
    assert res["up"]["prevented"] is True
    assert res["down"]["dir"] == 1
    assert res["down"]["prevented"] is True


def test_html_and_css_hud_spec():
    """
    Test 9: Verify .tl-shortcuts-hint is in index.html and style.css,
    and inline style count remains <= 19.
    """
    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        html = f.read()
    with open(STYLE_CSS, "r", encoding="utf-8") as f:
        css = f.read()

    # Verify HUD element
    assert "tl-shortcuts-hint" in html
    assert "tl-shortcuts-hint" in css
    assert "Shortcuts" in html

    # Inline style budget assertion
    style_count = len(re.findall(r'style="', html))
    assert style_count <= 19, f"Inline style count {style_count} exceeds budget 19"


def test_transport_keys_survive_with_no_film_loaded():
    """
    Test 10: The Timeline pane is a supported empty state - renderTimelineScreen
    draws "no film loaded" - so every transport key must be a no-op there, not a
    crash. End computed the film's total itself instead of going through
    timelineSeek, and the play path read currentScriptData.segments directly;
    both threw on a null script. Reachable by opening the app and pressing 3.
    """
    res = _run_node("""
    const fakeAudio = {
      paused: true, currentTime: 0, dataset: {}, src: "",
      load() {}, play() { return Promise.resolve(); },
      pause() { this.paused = true; }, addEventListener() {}
    };
    const baseGet = document.getElementById;
    document.getElementById = (id) => (id === "tl-audio" ? fakeAudio : baseGet(id));

    currentScriptData = null;              // nothing loaded yet
    tlPlayhead = 0;
    timelinePaneAttr["data-on"] = "1";     // Timeline pane is showing "no film loaded"
    document.activeElement = { tagName: "BODY", isContentEditable: false };

    const errors = [];
    const press = (key) => {
      try {
        const ev = { key: key, code: key === " " ? "Space" : key, preventDefault: () => {} };
        listeners["keydown"].forEach(h => h(ev));
      } catch (err) {
        errors.push(key + ": " + err.message);
      }
    };

    (async () => {
      ["End", "Home", "ArrowRight", "ArrowLeft", "ArrowUp", "ArrowDown", "j", "k", "l"].forEach(press);
      let spaceError = null;
      try {
        await timelineTogglePlay();        // what Space calls
      } catch (err) {
        spaceError = err.message;
      }
      console.log(JSON.stringify({ errors, spaceError, playhead: tlPlayhead }));
    })();
    """)

    assert res["errors"] == [], f"transport keys threw with no film loaded: {res['errors']}"
    assert res["spaceError"] is None, f"play path threw with no film loaded: {res['spaceError']}"
    assert res["playhead"] == 0


def test_key_3_focuses_timeline_container():
    """
    Test 11: The 3 key is the keyboard route into the Timeline, so it must leave
    the lane container focused - same hand-off openTimelineFromBoard performs.
    Without this, 3 lands on the pane but the very next Space goes nowhere.
    """
    res = _run_node("""
    let switched = null;
    const attrs = {};
    switchPane = (p) => { switched = p; };
    mockScroll.focused = false;
    mockScroll.setAttribute = (k, v) => { attrs[k] = v; };
    document.activeElement = { tagName: "BODY", isContentEditable: false };

    listeners["keydown"].forEach(h => h({ key: "3", preventDefault: () => {} }));

    console.log(JSON.stringify({
      switched: switched,
      focused: !!mockScroll.focused,
      tabindex: attrs["tabindex"] || null
    }));
    """)

    assert res["switched"] == "timeline"
    assert res["focused"] is True
    assert res["tabindex"] == "-1"
