import os
import re
from html.parser import HTMLParser
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(REPO_ROOT, "frontend", "index.html")
APP_JS = os.path.join(REPO_ROOT, "frontend", "app.js")
VOICE_JS = os.path.join(REPO_ROOT, "frontend", "voice_studio.js")


class ButtonParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.buttons = []
        self._current_tag = None
        self._current_attrs = {}
        self._current_line = 0
        self._current_text = []

    def handle_starttag(self, tag, attrs):
        if tag == "button":
            self._current_tag = "button"
            self._current_attrs = dict(attrs)
            self._current_line = self.getpos()[0]
            self._current_text = []

    def handle_data(self, data):
        if self._current_tag == "button":
            self._current_text.append(data)

    def handle_endtag(self, tag):
        if tag == "button" and self._current_tag == "button":
            self.buttons.append({
                "attrs": self._current_attrs,
                "line": self._current_line,
                "text": "".join(self._current_text).strip(),
                "onclick": self._current_attrs.get("onclick", ""),
                "class": self._current_attrs.get("class", ""),
            })
            self._current_tag = None
            self._current_attrs = {}
            self._current_text = []


def _defined_functions(*js_files):
    funcs = set()
    for js_path in js_files:
        if not os.path.exists(js_path):
            continue
        with open(js_path, "r", encoding="utf-8") as f:
            js_text = f.read()
        for m in re.finditer(r'(?:function\s+([a-zA-Z0-9_$]+)|(?:async\s+function\s+([a-zA-Z0-9_$]+))|(?:(?:window\.)?([a-zA-Z0-9_$]+)\s*=\s*(?:async\s*)?(?:function|\([^)]*\)\s*=>)))', js_text):
            for name in m.groups():
                if name:
                    funcs.add(name)
    return funcs


def test_every_button_does_something():
    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        html = f.read()

    parser = ButtonParser()
    parser.feed(html)

    defined = _defined_functions(APP_JS, VOICE_JS)

    failures = []
    for btn in parser.buttons:
        classes = btn["class"].split()
        onclick = btn["onclick"]

        if "card-toggle" in classes or "lib-tab" in classes or "plan-seg-btn" in classes or "nav" in classes:
            continue

        if onclick:
            fn_match = re.match(r'^\s*([a-zA-Z0-9_$]+)\s*\(', onclick)
            if fn_match:
                fn_name = fn_match.group(1)
                if fn_name in defined or fn_name in {"alert", "confirm", "prompt", "setPlanMode", "switchPane"}:
                    continue
            else:
                if "document." in onclick or "window." in onclick:
                    continue

        failures.append(f"Line {btn['line']}: <button class='{btn['class']}'> label='{btn['text']}' onclick='{onclick}'")

    assert not failures, "Dead buttons found in index.html:\n" + "\n".join(failures)


def test_deleted_sections_are_gone():
    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        html = f.read()

    deleted_ids = [
        "card-body-defaults",
        "card-body-spending",
        "card-body-performance",
        "card-body-pronunciation",
        "card-body-lang-packs",
    ]
    found = [i for i in deleted_ids if i in html]
    assert not found, f"Deleted aria-controls IDs still present in index.html: {found}"


def test_the_handoff_exists():
    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        html = f.read()
    with open(APP_JS, "r", encoding="utf-8") as f:
        js = f.read()

    assert 'id="btn-open-timeline"' in html, "id='btn-open-timeline' not found in index.html"
    assert "openTimelineFromBoard" in js, "openTimelineFromBoard not defined in app.js"


def test_the_duplicates_are_gone():
    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        html = f.read()

    assert "btn-open-wolfcut-board" not in html, "btn-open-wolfcut-board still in index.html"
    assert "btn-start-render-board" not in html, "btn-start-render-board still in index.html"
    assert "btn-render-film" in html, "btn-render-film missing in index.html"


def test_the_invented_coverage_card_is_gone():
    """
    The Images tab printed a coverage breakdown - "Landscapes & terrain: strong",
    "Battle & aftermath: thin" - from four literals with inline colours. Nothing
    in the library carries a category: manifest.jsonl records subject, setting,
    light and shot, and no taxonomy exists anywhere to score against. This is the
    Spending panel again, so the card goes rather than gets faked.
    """
    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        html = f.read()

    invented = [
        "Landscapes &amp; terrain",
        "Crowds &amp; councils",
        "Battle &amp; aftermath",
    ]
    found = [phrase for phrase in invented if phrase in html]
    assert not found, f"Invented coverage rows are back in index.html: {found}"


def test_housekeeping_figures_come_from_the_backend():
    """
    Both Housekeeping numbers must be written by loadLibraryData, never typed.
    "Retired" was a literal 6, and "Active indexed images" shipped a 1,309
    placeholder that stood until - and only if - the backend answered.
    """
    with open(INDEX_HTML, "r", encoding="utf-8") as f:
        html = f.read()
    with open(APP_JS, "r", encoding="utf-8") as f:
        js = f.read()

    assert 'id="house-retired-count"' in html, "Retired has no id for app.js to write into"
    assert "1,309" not in html, "the 1,309 placeholder is back in index.html"

    active = re.search(r'"house-active-count"\)\.textContent\s*=\s*res\.total_images', js)
    assert active, "app.js no longer writes Active indexed images from the backend"

    retired = re.search(r'"house-retired-count"\)\.textContent\s*=\s*res\.retired_count', js)
    assert retired, "app.js does not write Retired from the backend"
