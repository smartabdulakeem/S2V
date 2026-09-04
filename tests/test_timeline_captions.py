"""
tests/test_timeline_captions.py

Verification for Slice H: Timeline Live Playback Visual Sync (Caption Highlighting and Timing).
Covers:
1. tlActiveCaptionIndex returns the right index at start, middle, and end of caption blocks.
2. tlActiveCaptionIndex returns -1 before the first caption and after the last.
3. The boundary belongs to exactly one line: at startsAt, returns the starting line, not the one that ended.
4. DOM is only touched when index changes: 60 frames within one caption call DOM update once.
5. Seeking backward updates the highlight correctly.
6. style.css defines .tl-cap.active with brass styling and z-index elevation.
"""

import json
import os
import subprocess
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_JS = os.path.join(REPO_ROOT, "frontend", "app.js")
STYLE_CSS = os.path.join(REPO_ROOT, "frontend", "style.css")


def _run_node_script(js_code: str) -> dict:
    """Run a Node.js snippet with app.js loaded and return parsed JSON stdout."""
    with open(APP_JS, "r", encoding="utf-8") as f:
        app_code = f.read()

    wrapper = f"""
let document = {{
  querySelectorAll: () => [],
  getElementById: () => null,
  addEventListener: () => {{}}
}};
let window = {{ addEventListener: () => {{}} }};

{app_code}

{js_code}
"""
    res = subprocess.run(["node", "-"], input=wrapper.encode("utf-8"), capture_output=True, check=True)
    return json.loads(res.stdout.decode("utf-8").strip())


def test_caption_index_start_middle_end():
    """
    Test 1: tlActiveCaptionIndex returns the right index at start, middle,
    and end of each caption block.
    """
    res = _run_node_script("""
    const secs = [3.0, 4.0, 5.0];
    const checks = [
      // Caption 0: [0, 3.0)
      tlActiveCaptionIndex(0.0, secs),
      tlActiveCaptionIndex(1.5, secs),
      tlActiveCaptionIndex(2.999, secs),
      // Caption 1: [3.0, 7.0)
      tlActiveCaptionIndex(3.0, secs),
      tlActiveCaptionIndex(5.0, secs),
      tlActiveCaptionIndex(6.999, secs),
      // Caption 2: [7.0, 12.0)
      tlActiveCaptionIndex(7.0, secs),
      tlActiveCaptionIndex(9.5, secs),
      tlActiveCaptionIndex(11.999, secs)
    ];
    console.log(JSON.stringify(checks));
    """)

    assert res == [0, 0, 0, 1, 1, 1, 2, 2, 2]


def test_caption_index_before_first_and_after_last():
    """
    Test 2: Returns -1 before the first caption and after the last caption.
    """
    res = _run_node_script("""
    const secs = [3.0, 4.0, 5.0]; // total 12.0
    const checks = {
      negSmall: tlActiveCaptionIndex(-0.001, secs),
      negLarge: tlActiveCaptionIndex(-10.0, secs),
      exactEnd: tlActiveCaptionIndex(12.0, secs),
      pastEnd: tlActiveCaptionIndex(12.5, secs),
      emptySecs: tlActiveCaptionIndex(0.0, [])
    };
    console.log(JSON.stringify(checks));
    """)

    assert res["negSmall"] == -1
    assert res["negLarge"] == -1
    assert res["exactEnd"] == -1
    assert res["pastEnd"] == -1
    assert res["emptySecs"] == -1


def test_caption_boundary_belongs_to_starting_line():
    """
    Test 3: At a time that is exactly a caption's startsAt, exactly one index
    is returned, and it is the starting line - not the one that just ended.
    Round-trip several boundaries with non-uniform segment lengths.
    """
    res = _run_node_script("""
    const secs = [2.5, 3.5, 4.2, 1.8]; // boundaries at 0, 2.5, 6.0, 10.2, 12.0
    const eps = 0.0001;
    const checks = {
      b0_exact: tlActiveCaptionIndex(0.0, secs),
      b1_before: tlActiveCaptionIndex(2.5 - eps, secs),
      b1_exact: tlActiveCaptionIndex(2.5, secs),
      b1_after: tlActiveCaptionIndex(2.5 + eps, secs),
      b2_before: tlActiveCaptionIndex(6.0 - eps, secs),
      b2_exact: tlActiveCaptionIndex(6.0, secs),
      b2_after: tlActiveCaptionIndex(6.0 + eps, secs),
      b3_before: tlActiveCaptionIndex(10.2 - eps, secs),
      b3_exact: tlActiveCaptionIndex(10.2, secs),
      b3_after: tlActiveCaptionIndex(10.2 + eps, secs),
      end_exact: tlActiveCaptionIndex(12.0, secs)
    };
    console.log(JSON.stringify(checks));
    """)

    assert res["b0_exact"] == 0
    assert res["b1_before"] == 0
    assert res["b1_exact"] == 1   # starting line 1, NOT 0
    assert res["b1_after"] == 1
    assert res["b2_before"] == 1
    assert res["b2_exact"] == 2   # starting line 2, NOT 1
    assert res["b2_after"] == 2
    assert res["b3_before"] == 2
    assert res["b3_exact"] == 3   # starting line 3, NOT 2
    assert res["b3_after"] == 3
    assert res["end_exact"] == -1


def test_dom_guard_only_touches_dom_on_index_change():
    """
    Test 4: The DOM is only touched when the index changes.
    Advancing the playhead across 60 frames within one caption touches the DOM once.
    """
    res = _run_node_script("""
    const secs = [3.0, 4.0];
    currentScriptData = {
      segments: secs.map(s => ({ narration_seconds: s, narration: 'test' }))
    };

    let addCount = 0;
    let removeCount = 0;

    const elements = {
      'tl-cap-0': {
        classList: {
          add: (cls) => { if (cls === 'active') addCount++; },
          remove: (cls) => { if (cls === 'active') removeCount++; }
        },
        style: { left: '0px' }
      },
      'tl-cap-1': {
        classList: {
          add: (cls) => { if (cls === 'active') addCount++; },
          remove: (cls) => { if (cls === 'active') removeCount++; }
        },
        style: { left: '100px' }
      }
    };

    document.getElementById = (id) => elements[id] || null;
    document.querySelector = (sel) => null;

    tlActiveCapIndex = -1;

    // Simulate 60 frames inside caption 0 (t = 0.0 to 2.95s, 50ms steps)
    for (let frame = 0; frame < 60; frame++) {
      updateTimelineActiveCaption(frame * 0.05);
    }
    const initialAdd = addCount;
    const initialRemove = removeCount;

    // Advance to frame 61 at t = 3.0s (switches to caption 1)
    updateTimelineActiveCaption(3.0);
    const boundaryAdd = addCount;
    const boundaryRemove = removeCount;

    // Simulate 30 more frames inside caption 1 (t = 3.05 to 4.5s)
    for (let frame = 1; frame <= 30; frame++) {
      updateTimelineActiveCaption(3.0 + frame * 0.05);
    }
    const finalAdd = addCount;
    const finalRemove = removeCount;

    console.log(JSON.stringify({
      initialAdd, initialRemove,
      boundaryAdd, boundaryRemove,
      finalAdd, finalRemove
    }));
    """)

    # Inside caption 0: added once on frame 0, never re-added on frames 1-59
    assert res["initialAdd"] == 1
    assert res["initialRemove"] == 0

    # At boundary t = 3.0: cap 0 removed once, cap 1 added once
    assert res["boundaryAdd"] == 2
    assert res["boundaryRemove"] == 1

    # Within caption 1: no further additions or removals
    assert res["finalAdd"] == 2
    assert res["finalRemove"] == 1


def test_seeking_backward_updates_highlight():
    """
    Test 5: Seeking backward updates the active caption highlight.
    """
    res = _run_node_script("""
    const secs = [3.0, 3.0, 3.0, 3.0]; // 4 caps, 3s each
    currentScriptData = {
      segments: secs.map(s => ({ narration_seconds: s, narration: 'test' }))
    };

    const activeStates = { 0: false, 1: false, 2: false, 3: false };
    const elements = {};
    for (let i = 0; i < 4; i++) {
      elements['tl-cap-' + i] = {
        classList: {
          add: (cls) => { if (cls === 'active') activeStates[i] = true; },
          remove: (cls) => { if (cls === 'active') activeStates[i] = false; }
        },
        style: { left: (i * 50) + 'px' }
      };
    }

    document.getElementById = (id) => elements[id] || null;
    document.querySelector = (sel) => null;

    tlActiveCapIndex = -1;

    // Step 1: Seek forward to t = 7.5s (Caption 2)
    updateTimelineActiveCaption(7.5);
    const stateAt7_5 = { ...activeStates, idx: tlActiveCapIndex };

    // Step 2: Seek backward to t = 4.0s (Caption 1)
    updateTimelineActiveCaption(4.0);
    const stateAt4_0 = { ...activeStates, idx: tlActiveCapIndex };

    // Step 3: Seek backward to t = 1.0s (Caption 0)
    updateTimelineActiveCaption(1.0);
    const stateAt1_0 = { ...activeStates, idx: tlActiveCapIndex };

    // Step 4: Seek before start to t = -1.0s
    updateTimelineActiveCaption(-1.0);
    const stateAtNeg = { ...activeStates, idx: tlActiveCapIndex };

    console.log(JSON.stringify({ stateAt7_5, stateAt4_0, stateAt1_0, stateAtNeg }));
    """)

    assert res["stateAt7_5"]["idx"] == 2
    assert res["stateAt7_5"]["2"] is True

    assert res["stateAt4_0"]["idx"] == 1
    assert res["stateAt4_0"]["1"] is True
    assert res["stateAt4_0"]["2"] is False

    assert res["stateAt1_0"]["idx"] == 0
    assert res["stateAt1_0"]["0"] is True
    assert res["stateAt1_0"]["1"] is False

    assert res["stateAtNeg"]["idx"] == -1
    assert res["stateAtNeg"]["0"] is False


def test_caption_active_style_rule():
    """
    Test 6: style.css defines .tl-cap.active with brass styling and z-index elevation.
    """
    with open(STYLE_CSS, "r", encoding="utf-8") as f:
        css = f.read()

    assert ".tl-cap.active" in css, ".tl-cap.active selector must exist in style.css"
    at = css.find(".tl-cap.active")
    open_b = css.index("{", at)
    close_b = css.index("}", open_b)
    rule = css[open_b + 1:close_b]

    assert "color: var(--brass)" in rule, ".tl-cap.active must use brass text color"
    assert "border-color: var(--brass)" in rule, ".tl-cap.active must have brass border"
    assert "z-index" in rule, ".tl-cap.active must have z-index elevation"
