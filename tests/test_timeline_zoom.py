"""
tests/test_timeline_zoom.py

Verification for Slice J: Timeline Zoom Behaviour: Anchored Zoom, Fit-to-Window & Keyboard Zoom.
Covers:
1. Zoom anchoring: Playhead holds its screen position across zoom changes.
2. Zoom centering: Playhead centered when outside viewport prior to zoom.
3. Fit-to-window calculation & clamping: (clientWidth - 24) / total clamped to [1, 60], updates slider.
4. Fit-to-window empty film safety: No-op on empty timeline / no film loaded (no division by zero).
5. Keyboard zoom shortcuts: +/= and -/_ zoom multiplicatively (* 1.5, / 1.5).
6. Keyboard 0 fits timeline on timeline pane, but does nothing on script/board panes.
7. Caption auto-scroll (Job 5): Active caption scrolled into view when outside viewport; doesn't move when visible.
8. HTML & CSS compliance: #btn-tl-fit exists, #tl-shortcuts-hint updated, inline styles <= 19.
"""

import json
import os
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

const caps = {{}};
for (let i = 0; i < 20; i++) {{
  caps[`tl-cap-${{i}}`] = makeElem(`tl-cap-${{i}}`);
}}

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
    if (caps[id]) return caps[id];
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


def test_zoom_anchoring_preserves_playhead_offset():
    """
    Test 1: When zooming, the playhead holds its screen position within the viewport.
    Before: playhead at 5.0s, old zoom 8 -> 40px. scrollLeft = 10 -> offset = 30px.
    After: new zoom 20 -> 100px. scrollLeft must become 100 - 30 = 70px.
    """
    res = _run_node("""
    currentScriptData = {
      segments: [
        { narration_seconds: "10.0", shots: [{ shot_id: "s1" }] },
        { narration_seconds: "15.0", shots: [{ shot_id: "s2" }] }
      ]
    };
    tlZoom = 8;
    tlPlayhead = 5.0;
    mockScroll.clientWidth = 800;
    mockScroll.scrollLeft = 10;
    mockZoom.value = "8";

    setTimelineZoom(20);

    const oldOffset = (5.0 * 8) - 10; // 30px
    const newOffset = (5.0 * tlZoom) - mockScroll.scrollLeft;

    console.log(JSON.stringify({
      tlZoom: tlZoom,
      scrollLeft: mockScroll.scrollLeft,
      sliderValue: parseFloat(mockZoom.value),
      oldOffset: oldOffset,
      newOffset: newOffset
    }));
    """)

    assert res["tlZoom"] == 20
    assert res["scrollLeft"] == 70  # 100px playhead - 30px offset
    assert res["sliderValue"] == 20
    assert res["newOffset"] == res["oldOffset"] == 30


def test_zoom_centering_when_playhead_outside_viewport():
    """
    Test 2: When playhead is outside viewport, zoom centers the playhead instead of
    preserving a nonsense offset.
    Viewport: width 200, scrollLeft 0 -> [0, 200].
    Playhead: 40.0s * 8 = 320px (outside viewport!).
    After zoom 10: playhead = 400px. Centered in 200px viewport means offset = 100px,
    so scrollLeft = 400 - 100 = 300px.
    """
    res = _run_node("""
    currentScriptData = {
      segments: [
        { narration_seconds: "50.0", shots: [{ shot_id: "s1" }] }
      ]
    };
    tlZoom = 8;
    tlPlayhead = 40.0;
    mockScroll.clientWidth = 200;
    mockScroll.scrollLeft = 0;

    setTimelineZoom(10);

    const centeredOffset = (tlPlayhead * tlZoom) - mockScroll.scrollLeft;

    console.log(JSON.stringify({
      tlZoom: tlZoom,
      scrollLeft: mockScroll.scrollLeft,
      screenOffset: centeredOffset,
      halfWidth: mockScroll.clientWidth * 0.5
    }));
    """)

    assert res["tlZoom"] == 10
    assert res["scrollLeft"] == 300
    assert res["screenOffset"] == res["halfWidth"] == 100


def test_fit_timeline_to_window_calculation_and_clamping():
    """
    Test 3 & 4: fitTimelineToWindow computes (clientWidth - 24) / total,
    clamps to [0.2, 60], and updates the slider.
    """
    res = _run_node("""
    currentScriptData = {
      segments: [
        { narration_seconds: "100.0", shots: [{ shot_id: "s1" }] }
      ]
    }; // total = 100.0s
    mockScroll.clientWidth = 824;
    fitTimelineToWindow();
    const fitExact = tlZoom;
    const sliderExact = parseFloat(mockZoom.value);

    // Test upper clamp: 3s film in 804px window -> (804-24)/3 = 260 -> clamped to 60
    currentScriptData = {
      segments: [
        { narration_seconds: "3.0", shots: [{ shot_id: "s1" }] }
      ]
    };
    mockScroll.clientWidth = 804;
    fitTimelineToWindow();
    const fitClampedMax = tlZoom;

    // A 33-minute film in an 824px window wants (824-24)/2000 = 0.4 px/s.
    // The old floor of 1 clamped that away, which is why Fit did not fit.
    // It must now survive unclamped.
    currentScriptData = {
      segments: [
        { narration_seconds: "2000.0", shots: [{ shot_id: "s1" }] }
      ]
    };
    mockScroll.clientWidth = 824;
    fitTimelineToWindow();
    const fitLongFilm = tlZoom;

    // A floor still exists, just lower: (824-24)/5000 = 0.16 -> clamped to 0.2
    currentScriptData = {
      segments: [
        { narration_seconds: "5000.0", shots: [{ shot_id: "s1" }] }
      ]
    };
    mockScroll.clientWidth = 824;
    fitTimelineToWindow();
    const fitClampedMin = tlZoom;

    console.log(JSON.stringify({
      fitExact: fitExact,
      sliderExact: sliderExact,
      fitClampedMax: fitClampedMax,
      fitLongFilm: fitLongFilm,
      fitClampedMin: fitClampedMin
    }));
    """)

    # (824 - 24) / 100.0 = 8.0
    assert res["fitExact"] == pytest.approx(8.0)
    assert res["sliderExact"] == pytest.approx(8.0)
    # (804 - 24) / 3.0 = 260 -> clamped to 60
    assert res["fitClampedMax"] == 60.0
    # (824 - 24) / 2000.0 = 0.4, under the old floor of 1 and now unclamped
    assert res["fitLongFilm"] == pytest.approx(0.4)
    # (824 - 24) / 5000.0 = 0.16 -> clamped to the new floor of 0.2
    assert res["fitClampedMin"] == pytest.approx(0.2)


def test_fit_timeline_empty_timeline_safe_noop():
    """
    Test 4: fitTimelineToWindow on empty timeline is a safe no-op.
    Never divides by zero, crashes, or produces NaN / Infinity.
    """
    res = _run_node("""
    currentScriptData = null;
    tlZoom = 8;
    mockZoom.value = "8";

    let err1 = null;
    try {
      fitTimelineToWindow();
    } catch (e) {
      err1 = e.message;
    }
    const zoomAfterNull = tlZoom;

    currentScriptData = { segments: [] };
    let err2 = null;
    try {
      fitTimelineToWindow();
    } catch (e) {
      err2 = e.message;
    }
    const zoomAfterEmpty = tlZoom;

    console.log(JSON.stringify({
      err1: err1,
      err2: err2,
      zoomAfterNull: zoomAfterNull,
      zoomAfterEmpty: zoomAfterEmpty
    }));
    """)

    assert res["err1"] is None
    assert res["err2"] is None
    assert res["zoomAfterNull"] == 8
    assert res["zoomAfterEmpty"] == 8


def test_keyboard_zoom_multiplicative_steps():
    """
    Test 5: Keyboard shortcuts + / = and - / _ zoom multiplicatively (1.5x / /1.5).
    """
    res = _run_node("""
    currentScriptData = {
      segments: [{ narration_seconds: "20.0", shots: [{ shot_id: "s1" }] }]
    };
    timelinePaneAttr["data-on"] = "1";
    document.activeElement = { tagName: "BODY", isContentEditable: false };
    tlZoom = 8.0;

    const press = (k) => {
      let prevented = false;
      const ev = { key: k, preventDefault: () => { prevented = true; } };
      listeners["keydown"].forEach(h => h(ev));
      return { zoom: tlZoom, prevented: prevented };
    };

    const step1 = press("+"); // 8 * 1.5 = 12
    const step2 = press("="); // 12 * 1.5 = 18
    const step3 = press("-"); // 18 / 1.5 = 12
    const step4 = press("_"); // 12 / 1.5 = 8

    console.log(JSON.stringify({
      step1: step1,
      step2: step2,
      step3: step3,
      step4: step4
    }));
    """)

    assert res["step1"]["zoom"] == pytest.approx(12.0)
    assert res["step1"]["prevented"] is True

    assert res["step2"]["zoom"] == pytest.approx(18.0)
    assert res["step2"]["prevented"] is True

    assert res["step3"]["zoom"] == pytest.approx(12.0)
    assert res["step3"]["prevented"] is True

    assert res["step4"]["zoom"] == pytest.approx(8.0)
    assert res["step4"]["prevented"] is True


def test_keyboard_0_fits_only_on_timeline_pane():
    """
    Test 6: Keyboard 0 fits timeline when on Timeline pane, but does nothing when
    on Script or Board panes.
    """
    res = _run_node("""
    currentScriptData = {
      segments: [{ narration_seconds: "100.0", shots: [{ shot_id: "s1" }] }]
    };
    mockScroll.clientWidth = 824; // fit zoom is 8.0
    document.activeElement = { tagName: "BODY", isContentEditable: false };

    // Case 1: Inactive timeline pane (Script pane active)
    timelinePaneAttr["data-on"] = "0";
    tlZoom = 24.0;
    let preventedScript = false;
    const ev1 = { key: "0", preventDefault: () => { preventedScript = true; } };
    listeners["keydown"].forEach(h => h(ev1));
    const zoomScript = tlZoom;

    // Case 2: Active timeline pane
    timelinePaneAttr["data-on"] = "1";
    tlZoom = 24.0;
    let preventedTimeline = false;
    const ev2 = { key: "0", preventDefault: () => { preventedTimeline = true; } };
    listeners["keydown"].forEach(h => h(ev2));
    const zoomTimeline = tlZoom;

    console.log(JSON.stringify({
      preventedScript: preventedScript,
      zoomScript: zoomScript,
      preventedTimeline: preventedTimeline,
      zoomTimeline: zoomTimeline
    }));
    """)

    # On script pane, 0 does nothing
    assert res["preventedScript"] is False
    assert res["zoomScript"] == 24.0

    # On timeline pane, 0 triggers fit
    assert res["preventedTimeline"] is True
    assert res["zoomTimeline"] == pytest.approx(8.0)


def test_caption_auto_scroll_inside_and_outside_viewport():
    """
    Test 7 (Job 5): Active caption is scrolled into view when outside the viewport,
    and does NOT move the scroll position when already visible.
    """
    res = _run_node("""
    currentScriptData = {
      segments: [
        { narration_seconds: "5.0", shots: [{ shot_id: "s1" }] },
        { narration_seconds: "5.0", shots: [{ shot_id: "s2" }] },
        { narration_seconds: "5.0", shots: [{ shot_id: "s3" }] },
        { narration_seconds: "5.0", shots: [{ shot_id: "s4" }] }
      ]
    }; // total = 20.0s
    tlZoom = 10; // 10 px/s

    mockScroll.clientWidth = 100;
    mockScroll.scrollLeft = 0;

    caps["tl-cap-0"].style.left = "0px";
    caps["tl-cap-1"].style.left = "50px";
    caps["tl-cap-2"].style.left = "100px";
    caps["tl-cap-3"].style.left = "150px";

    tlActiveCapIndex = -1;

    // Event A: Seek to 16.0s (Segment 3). capLeft = 150px.
    // Viewport is [0, 100]. capLeft 150px is > scrollLeft + view - 40 (60px).
    // Auto-scroll triggers! x = 16.0 * 10 = 160px.
    // scrollLeft becomes Math.max(0, 160 - 100 * 0.35) = 160 - 35 = 125px.
    tlPlayhead = 16.0;
    updateTimelineActiveCaption(16.0);
    const scrollAfterA = mockScroll.scrollLeft;

    // Event B: Now set scrollLeft = 100. Viewport [100, 200].
    // capLeft = 150px.
    // Safe region: scrollLeft + 40 = 140. scrollLeft + view - 40 = 160.
    // 150 is safely within [140, 160]!
    mockScroll.scrollLeft = 100;
    tlActiveCapIndex = -1;
    tlPlayhead = 16.0;
    updateTimelineActiveCaption(16.0);
    const scrollAfterB = mockScroll.scrollLeft;

    console.log(JSON.stringify({
      scrollAfterA: scrollAfterA,
      scrollAfterB: scrollAfterB
    }));
    """)

    # Event A: outside viewport -> scrolled
    assert res["scrollAfterA"] == 125
    # Event B: inside safe bounds -> untouched!
    assert res["scrollAfterB"] == 100


def test_html_and_css_hud_spec():
    """
    Test 8: Fit button and shortcuts hint in index.html and inline style budget <= 19.
    """
    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        html = f.read()

    # Fit button exists with onclick and id
    assert 'id="btn-tl-fit"' in html
    assert 'onclick="fitTimelineToWindow()"' in html

    # Shortcuts hint updated with zoom keys
    assert 'id="tl-shortcuts-hint"' in html
    assert '+/-/0: Zoom' in html

    # Inline style ratchet: cap 19 (baseline was 15)
    inline_styles = html.count('style="')
    assert inline_styles <= 19, f"Inline style count {inline_styles} exceeds budget of 19"
def test_zoom_floor_allows_sub_one_pixels_per_second():
    """
    Test 9: The zoom floor is 0.2 px/s, not 1. A film longer than about 13 minutes
    needs sub-1 px/s to fit an 800px window at all, so a floor of 1 made Fit a lie.
    Measured live on the owner's film before this fix: tlZoom 1, lanes_scrollWidth
    1160, scroll_clientWidth 823 (reports/verification_gate/slice_k_dom.json).
    """
    res = _run_node("""
    currentScriptData = { segments: [{ narration_seconds: "100.0", shots: [{ shot_id: "s1" }] }] };
    const out = {};
    setTimelineZoom(0.5);   out.half = tlZoom;
    setTimelineZoom(0.2);   out.atFloor = tlZoom;
    setTimelineZoom(0.05);  out.belowFloor = tlZoom;
    setTimelineZoom(999);   out.aboveCeiling = tlZoom;
    console.log(JSON.stringify(out));
    """)

    assert res["half"] == pytest.approx(0.5), "0.5 px/s must survive; the old floor clamped it to 1"
    assert res["atFloor"] == pytest.approx(0.2)
    assert res["belowFloor"] == pytest.approx(0.2), "the floor still exists, it is just lower"
    assert res["aboveCeiling"] == 60.0, "the ceiling is untouched"


def test_fit_actually_fits_the_owners_film():
    """
    Test 10: The regression this slice exists for. Before Adam is 1159.677s. Fit must
    leave the lane no wider than the viewport, which is what "fit" means.
    """
    res = _run_node("""
    // 1159.677s, the owner's real film, in 66 segments.
    const segs = [];
    for (let i = 0; i < 66; i++) segs.push({ narration_seconds: "17.571", shots: [{ shot_id: "s" + i }] });
    currentScriptData = { segments: segs };
    mockScroll.clientWidth = 823;   // measured in the live window

    fitTimelineToWindow();
    const total = segmentSecondsList(currentScriptData).reduce((a, b) => a + b, 0);
    console.log(JSON.stringify({
      total: total,
      zoom: tlZoom,
      laneWidthPx: total * tlZoom,
      viewportPx: 823,
      fits: (total * tlZoom) <= 823,
      tickInterval: tlTickInterval()
    }));
    """)

    assert res["fits"] is True, (
        f"Fit left a {res['laneWidthPx']:.0f}px lane in an 823px window at zoom {res['zoom']}"
    )
    assert res["zoom"] < 1.0, "an 18-minute film needs sub-1 px/s; if this passes at >=1 the film is too short"
    # 90 / 0.689 = 131 -> the existing table's 300s entry. Ticks must not collapse.
    assert res["tickInterval"] >= 60, f"ticks would crowd at {res['tickInterval']}s spacing"


def test_slider_can_reach_what_the_setter_allows():
    """
    Test 11: The slider and setTimelineZoom must share one floor, or the mouse cannot
    reach what the keyboard and Fit can. The mock cannot catch this - its .value is a
    plain property with no min/step validation - so this reads the markup, the same way
    the inline-style budget is enforced.
    """
    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        html = f.read()

    start = html.index('id="tl-zoom"')
    tag = html[html.rindex("<input", 0, start):html.index(">", start) + 1]

    assert 'min="0.2"' in tag, f"slider floor must match setTimelineZoom's 0.2; got: {tag}"
    assert 'max="60"' in tag, f"slider ceiling must stay 60; got: {tag}"
    # Without a fractional step the slider snaps to whole numbers while tlZoom stays
    # fractional after a fit, so the thumb and the real zoom silently disagree.
    assert 'step="any"' in tag, f"slider needs step=\"any\" to express fractional zoom; got: {tag}"
