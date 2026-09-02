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