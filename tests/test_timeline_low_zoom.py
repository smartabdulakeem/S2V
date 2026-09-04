"""
tests/test_timeline_low_zoom.py

Verification for Slice L: The Timeline at Low Zoom.
Covers:
1. Handle hit area & seam positioning: Handle is rendered into the lane at clip seam, width >= 8px.
2. Overlap suppression: When two boundaries are closer than 8px, later handle wins and earlier is suppressed.
3. Accessibility & keyboard preservation: Handle keeps tabindex="0", role="slider", ARIA attributes, and onkeydown.
4. Micro label threshold: Clips < 24px do not render .tl-clip-head; clips >= 24px do.
5. Zoom to selection calculation & clamping: (clientWidth - 24) / pic.seconds clamped to [0.2, 60].
6. Safe no-op on no selection or no film loaded: No error, no division by zero.
7. Keyboard '.' shortcut gated to Timeline pane: Zoom on timeline, no-op on script pane.
8. HTML & CSS compliance: #tl-shortcuts-hint updated, inline styles <= 19.
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

function makeElem(id) {{
  return {{
    id: id,
    innerHTML: "",
    textContent: "",
    value: "8",
    dataset: {{}},
    classList: {{
      add: function(c) {{ this[c] = true; }},
      remove: function(c) {{ delete this[c]; }},
      toggle: function(c, v) {{ if (v) this[c] = true; else delete this[c]; }}
    }},
    style: {{}},
    setAttribute: () => {{}},
    removeAttribute: () => {{}},
    hasAttribute: () => false,
    clientWidth: 800,
    scrollLeft: 0,
    disabled: false,
    title: "",
    focus: function() {{ this.focused = true; }},
    addEventListener: () => {{}},
    removeEventListener: () => {{}}
  }};
}}

const mockScroll = makeElem("tl-scroll");
const mockZoom = makeElem("tl-zoom");
const mockLanes = makeElem("tl-lanes");
const mockRuler = makeElem("tl-ruler");
const mockStatus = makeElem("tl-status");
const mockLaneP = makeElem("tl-lane-pictures");
const mockLaneN = makeElem("tl-lane-narration");
const mockLaneM = makeElem("tl-lane-music");
const mockLaneS = makeElem("tl-lane-sfx");
const mockLaneC = makeElem("tl-lane-captions");
const mockPlayBtn = makeElem("btn-tl-play");
const mockClock = makeElem("tl-clock");
const mockPlayhead = makeElem("tl-playhead");
const mockAudio = makeElem("tl-audio");
const mockMusicAudio = makeElem("tl-music-audio");

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
    if (id === "tl-zoom") return mockZoom;
    if (id === "tl-lanes") return mockLanes;
    if (id === "tl-ruler") return mockRuler;
    if (id === "tl-status") return mockStatus;
    if (id === "tl-lane-pictures") return mockLaneP;
    if (id === "tl-lane-narration") return mockLaneN;
    if (id === "tl-lane-music") return mockLaneM;
    if (id === "tl-lane-sfx") return mockLaneS;
    if (id === "tl-lane-captions") return mockLaneC;
    if (id === "btn-tl-play") return mockPlayBtn;
    if (id === "tl-clock") return mockClock;
    if (id === "tl-playhead") return mockPlayhead;
    if (id === "tl-audio") return mockAudio;
    if (id === "tl-music-audio") return mockMusicAudio;
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
        raise RuntimeError(f"Node exited with {res.returncode}:\\n{res.stderr.decode('utf-8')}")
    return json.loads(res.stdout.decode("utf-8").strip())


def test_handle_hit_area_and_seam_positioning():
    """
    Test 1: Boundary handle is rendered into the lane at the seam between clips,
    and has a hit area >= 8px wide in style.css.
    """
    res = _run_node("""
    currentScriptData = {
      segments: [
        { narration_seconds: "10.0", shots: [{ shot_id: "s1" }] },
        { narration_seconds: "15.0", shots: [{ shot_id: "s2" }] }
      ]
    };
    tlZoom = 8;
    renderTimelineScreen();

    // Verify handle is in mockLaneP.innerHTML
    const html = mockLaneP.innerHTML;
    const hasHandle = html.includes('class="tl-clip-handle"');
    const handleSeamMatch = html.match(/style="left:([0-9.]+)px;?"/);
    const seamX = handleSeamMatch ? parseFloat(handleSeamMatch[1]) : null;

    console.log(JSON.stringify({
      hasHandle: hasHandle,
      seamX: seamX,
      expectedSeamX: 10.0 * 8 // 80px
    }));
    """)

    assert res["hasHandle"] is True
    assert res["seamX"] == pytest.approx(80.0)

    # Also verify style.css defines width >= 8px and transform: translateX(-50%) on .tl-clip-handle
    with open(STYLE_CSS, "r", encoding="utf-8") as f:
        css = f.read()
    match = re.search(r"\.tl-clip-handle\s*\{([^}]+)\}", css)
    assert match, "Could not find .tl-clip-handle in style.css"
    block = match.group(1)
    w_match = re.search(r"width:\s*(\d+)px", block)
    assert w_match and int(w_match.group(1)) >= 8, f"Handle width must be >= 8px, got {w_match.group(1) if w_match else 'none'}"
    assert "translateX(-50%)" in block


def test_handle_overlap_suppression():
    """
    Test 2: When two boundaries are closer than 8px (minHandleHit), the later
    handle wins and the earlier is suppressed.
    """
    res = _run_node("""
    currentScriptData = {
      segments: [
        { narration_seconds: "10.0", shots: [{ shot_id: "s1" }] }, // pic 1: startsAt 0s, dur 10s
        { narration_seconds: "0.5", shots: [{ shot_id: "s2" }] },  // pic 2: startsAt 10s, dur 0.5s -> at zoom 10: 100px
        { narration_seconds: "10.0", shots: [{ shot_id: "s3" }] }  // pic 3: startsAt 10.5s -> at zoom 10: 105px (delta 5px < 8px)
      ]
    };
    tlZoom = 10;
    renderTimelineScreen();

    const html = mockLaneP.innerHTML;
    // Check which handles are rendered via unique pointerdown handlers
    const hasHandlePic2 = html.includes('timelineHandlePointerDown(event, 2)');
    const hasHandlePic3 = html.includes('timelineHandlePointerDown(event, 3)');

    console.log(JSON.stringify({
      hasHandlePic2: hasHandlePic2,
      hasHandlePic3: hasHandlePic3
    }));
    """)

    # Later boundary (Pic 3 at 105px) wins; earlier boundary (Pic 2 at 100px) suppressed
    assert res["hasHandlePic3"] is True
    assert res["hasHandlePic2"] is False


def test_handle_accessibility_attributes():
    """
    Test 3: Handle preserves tabindex="0", role="slider", ARIA values, and onkeydown.
    """
    res = _run_node("""
    currentScriptData = {
      segments: [
        { narration_seconds: "10.0", shots: [{ shot_id: "s1" }] },
        { narration_seconds: "15.0", shots: [{ shot_id: "s2" }] }
      ]
    };
    tlZoom = 8;
    renderTimelineScreen();

    const html = mockLaneP.innerHTML;
    console.log(JSON.stringify({
      hasTabindex: html.includes('tabindex="0"'),
      hasRole: html.includes('role="slider"'),
      hasAriaValuenow: html.includes('aria-valuenow="2"'),
      hasAriaValuemin: html.includes('aria-valuemin='),
      hasAriaValuemax: html.includes('aria-valuemax='),
      hasOnkeydown: html.includes('onkeydown="timelineHandleKeyDown(event, 2)"')
    }));
    """)

    assert res["hasTabindex"] is True
    assert res["hasRole"] is True
    assert res["hasAriaValuenow"] is True
    assert res["hasAriaValuemin"] is True
    assert res["hasAriaValuemax"] is True
    assert res["hasOnkeydown"] is True


def test_micro_clip_label_threshold():
    """
    Test 4: Clips with width < 24px omit .tl-clip-head entirely; clips >= 24px render it.
    """
    res = _run_node(r"""
    currentScriptData = {
      segments: [
        // pic 1: 10s at zoom 1 -> 10px (< 24px)
        { narration_seconds: "10.0", shots: [{ shot_id: "s1" }] },
        // pic 2: 30s at zoom 1 -> 30px (>= 24px)
        { narration_seconds: "30.0", shots: [{ shot_id: "s2" }] }
      ]
    };
    tlZoom = 1;
    renderTimelineScreen();

    const html = mockLaneP.innerHTML;
    // Extract clip 1 block and clip 2 block
    const clip1Match = html.match(/id="tl-clip-1"[^]*?<\/div>/);
    const clip2Match = html.match(/id="tl-clip-2"[^]*?<\/div>/);

    const clip1Html = clip1Match ? clip1Match[0] : "";
    const clip2Html = clip2Match ? clip2Match[0] : "";

    console.log(JSON.stringify({
      clip1HasHead: clip1Html.includes('tl-clip-head'),
      clip2HasHead: clip2Html.includes('tl-clip-head'),
      clip1HasTitle: clip1Html.includes('title="Picture 1'),
      clip2HasTitle: clip2Html.includes('title="Picture 2')
    }));
    """)

    # 10px clip omits label head but retains title attribute
    assert res["clip1HasHead"] is False
    assert res["clip1HasTitle"] is True

    # 30px clip keeps label head
    assert res["clip2HasHead"] is True
    assert res["clip2HasTitle"] is True


def test_zoom_to_selection_calculation_and_clamping():
    """
    Test 5: zoomTimelineToSelection calculates (clientWidth - 24) / pic.seconds
    and clamps to [0.2, 60].
    """
    res = _run_node("""
    currentScriptData = {
      segments: [
        // pic 1: 100.0s -> in 824px window: (824-24)/100 = 8.0 px/s
        { narration_seconds: "100.0", shots: [{ shot_id: "s1" }] },
        // pic 2: 5.0s -> (824-24)/5 = 160 px/s -> clamped to 60.0
        { narration_seconds: "5.0", shots: [{ shot_id: "s2" }] },
        // pic 3: 5000.0s -> (824-24)/5000 = 0.16 px/s -> clamped to 0.2
        { narration_seconds: "5000.0", shots: [{ shot_id: "s3" }] }
      ]
    };
    mockScroll.clientWidth = 824;

    // Test 1: Select pic 1
    tlSelected = 1;
    zoomTimelineToSelection();
    const zoomPic1 = tlZoom;

    // Test 2: Select pic 2 (upper clamp 60)
    tlSelected = 2;
    zoomTimelineToSelection();
    const zoomPic2 = tlZoom;

    // Test 3: Select pic 3 (lower clamp 0.2)
    tlSelected = 3;
    zoomTimelineToSelection();
    const zoomPic3 = tlZoom;

    console.log(JSON.stringify({
      zoomPic1: zoomPic1,
      zoomPic2: zoomPic2,
      zoomPic3: zoomPic3
    }));
    """)

    assert res["zoomPic1"] == pytest.approx(8.0)
    assert res["zoomPic2"] == pytest.approx(60.0)
    assert res["zoomPic3"] == pytest.approx(0.2)


def test_zoom_to_selection_safe_noop():
    """
    Test 6: zoomTimelineToSelection with no selection or no film is a safe no-op.
    """
    res = _run_node("""
    currentScriptData = {
      segments: [{ narration_seconds: "10.0", shots: [{ shot_id: "s1" }] }]
    };
    tlZoom = 8.0;
    tlSelected = null; // No selection

    let errNoSel = null;
    try {
      zoomTimelineToSelection();
    } catch (e) {
      errNoSel = e.message;
    }
    const zoomAfterNoSel = tlZoom;

    currentScriptData = null; // No film
    let errNoFilm = null;
    try {
      zoomTimelineToSelection();
    } catch (e) {
      errNoFilm = e.message;
    }
    const zoomAfterNoFilm = tlZoom;

    console.log(JSON.stringify({
      errNoSel: errNoSel,
      errNoFilm: errNoFilm,
      zoomAfterNoSel: zoomAfterNoSel,
      zoomAfterNoFilm: zoomAfterNoFilm
    }));
    """)

    assert res["errNoSel"] is None
    assert res["errNoFilm"] is None
    assert res["zoomAfterNoSel"] == 8.0
    assert res["zoomAfterNoFilm"] == 8.0


def test_keyboard_dot_zoom_gated_to_timeline():
    """
    Test 7: Keyboard '.' triggers zoomTimelineToSelection on Timeline pane,
    but does nothing on Script pane.
    """
    res = _run_node("""
    currentScriptData = {
      segments: [{ narration_seconds: "100.0", shots: [{ shot_id: "s1" }] }]
    };
    mockScroll.clientWidth = 824;
    tlSelected = 1;
    document.activeElement = { tagName: "BODY", isContentEditable: false };

    // Case 1: Inactive timeline pane (Script pane active)
    timelinePaneAttr["data-on"] = "0";
    tlZoom = 24.0;
    let preventedScript = false;
    const ev1 = { key: ".", preventDefault: () => { preventedScript = true; } };
    listeners["keydown"].forEach(h => h(ev1));
    const zoomScript = tlZoom;

    // Case 2: Active timeline pane
    timelinePaneAttr["data-on"] = "1";
    tlZoom = 24.0;
    let preventedTimeline = false;
    const ev2 = { key: ".", preventDefault: () => { preventedTimeline = true; } };
    listeners["keydown"].forEach(h => h(ev2));
    const zoomTimeline = tlZoom;

    console.log(JSON.stringify({
      preventedScript: preventedScript,
      zoomScript: zoomScript,
      preventedTimeline: preventedTimeline,
      zoomTimeline: zoomTimeline
    }));
    """)

    assert res["preventedScript"] is False
    assert res["zoomScript"] == 24.0

    assert res["preventedTimeline"] is True
    assert res["zoomTimeline"] == pytest.approx(8.0)


def test_shortcuts_hint_and_html_budget():
    """
    Test 8: Verify #tl-shortcuts-hint contains '+/-/0: Zoom', '.: Zoom sel', and inline styles <= 19.
    """
    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        html = f.read()

    assert 'id="tl-shortcuts-hint"' in html
    assert '+/-/0: Zoom' in html
    assert '.: Zoom sel' in html

    inline_styles = html.count('style="')
    assert inline_styles <= 19, f"Inline styles {inline_styles} exceeds budget 19"
def test_handle_follows_the_seam_during_a_drag():
    """
    Test 9: The handle must move with the boundary while it is being dragged.

    Before this slice the handle was a child of the clip at left:0, so when
    timelineHandlePointerMove moved currClip.style.left the handle rode along for
    free. Slice L moved the handle into the lane with its own absolute left, and
    pointermove was never taught to update it - so the clip edge slid while the
    handle the user was holding sat still until pointerup re-rendered.

    No test drove pointermove, so nothing caught it. This one does.
    """
    res = _run_node("""
    // Six lines, paired into three pictures, so picture 2's boundary has room to move.
    const seg = (id, share) => ({
      segment_id: id,
      narration_seconds: "10.0",
      narration: "line " + id,
      shots: [share ? { shot_id: "s" + id, share_with: true } : { shot_id: "s" + id }]
    });
    currentScriptData = { segments: [seg(1,false), seg(2,true), seg(3,false),
                                     seg(4,true), seg(5,false), seg(6,true)] };
    tlZoom = 8;

    // A drag needs a lane rect and clip elements the preview can write to.
    mockLanes.getBoundingClientRect = () => ({ left: 0, top: 0, width: 4000, height: 60 });
    const clips = {};
    const baseGet = document.getElementById;
    document.getElementById = (id) => {
      if (id.indexOf("tl-clip-") === 0) {
        if (!clips[id]) { clips[id] = makeElem(id); clips[id].querySelector = () => null; }
        return clips[id];
      }
      return baseGet(id);
    };

    const handle = makeElem("the-handle");
    handle.setPointerCapture = () => {};
    handle.releasePointerCapture = () => {};

    renderTimelineScreen();

    timelineHandlePointerDown({
      button: 0, pointerType: "mouse", pointerId: 1, currentTarget: handle,
      stopPropagation() {}, preventDefault() {}
    }, 2);

    const startedOn = tlDragState ? tlDragState.fromLine : null;
    const leftBefore = handle.style.left;

    // Drag right to 30s, which is a later narration line than the boundary started on.
    timelineHandlePointerMove({
      pointerId: 1, clientX: 30 * tlZoom,
      stopPropagation() {}, preventDefault() {}
    });

    const moved = tlDragState ? tlDragState.currentLine !== tlDragState.fromLine : false;
    const expected = tlDragState
      ? (tlLineStartTime(tlDragState.currentLine) * tlZoom).toFixed(1) + "px"
      : null;

    console.log(JSON.stringify({
      startedOn: startedOn,
      leftBefore: leftBefore === undefined ? null : leftBefore,
      leftAfter: handle.style.left === undefined ? null : handle.style.left,
      expected: expected,
      moved: moved
    }));
    """)

    assert res["startedOn"] is not None, "the drag never started; the fixture is wrong, not the code"
    assert res["moved"] is True, "the drag did not cross a line boundary; nothing to assert"
    assert res["leftAfter"] is not None, (
        "the handle was never repositioned during the drag - it sits still while the "
        "clip edge slides away"
    )
    assert res["leftAfter"] == res["expected"], (
        f"handle sits at {res['leftAfter']}, seam is at {res['expected']}"
    )


def test_handles_render_as_siblings_of_clips_not_inside_them():
    """
    Test 10: The whole point of the slice. .tl-clip sets overflow:hidden, so a handle
    nested inside a clip is cropped to that clip's width - a 3px clip gives a 3px grab
    target. Handles must be emitted into the lane alongside the clips, after all of
    them, so nothing crops them.

    Asserting the CSS alone is not enough: translateX(-50%) on a handle that is still
    a child of an overflow:hidden clip is still cropped.
    """
    res = _run_node("""
    currentScriptData = {
      segments: [
        { narration_seconds: "10.0", shots: [{ shot_id: "s1" }] },
        { narration_seconds: "10.0", shots: [{ shot_id: "s2" }] },
        { narration_seconds: "10.0", shots: [{ shot_id: "s3" }] }
      ]
    };
    tlZoom = 8;
    renderTimelineScreen();

    const html = mockLaneP.innerHTML;
    console.log(JSON.stringify({
      firstHandleAt: html.indexOf("tl-clip-handle"),
      lastClipOpenAt: html.lastIndexOf('class="tl-clip '),
      handleCount: (html.match(/tl-clip-handle/g) || []).length,
      clipCount: (html.match(/class="tl-clip /g) || []).length
    }));
    """)

    assert res["handleCount"] == 2, "three pictures means two interior boundaries"
    assert res["clipCount"] == 3
    assert res["firstHandleAt"] > res["lastClipOpenAt"], (
        "handles are emitted before the last clip opens, so at least one is nested "
        "inside a clip and will be cropped by overflow:hidden"
    )
