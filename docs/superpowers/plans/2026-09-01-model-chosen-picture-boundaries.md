# Model-Chosen Picture Boundaries Implementation Plan

> **How this plan is executed:** Antigravity writes the code, one task at a time, then stops. It
> does not commit and it does not judge its own work. The owner relays the report — test output and
> diff — to Claude, who verifies the code against this plan and fixes what is wrong. A task that
> defeats Antigravity gets broken into smaller steps and handed back, not taken over. The owner is
> not a programmer and does not review code; he relays.
>
> **Reporting rule:** the suite is **549 tests across 43 files** and takes 8-14 minutes. Report the
> real number from `pytest tests/ -q`. A report under 500 has not run the suite and will be sent back.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop dividing the script by a clock to decide where pictures go; let the model that reads the whole script choose the boundaries, with time only as a constraint.

**Architecture:** A narration-timing pass measures each segment's real spoken length via TTS + ffprobe and stores it on the segment. A new planning pass sends the whole script — each line tagged with its seconds — to the description model, which returns *spans* (`first_line`–`last_line`) plus a description for each. A deterministic repair layer guarantees the spans are contiguous, cover every line, and respect a holding range (auto mode) or an exact picture count (manual mode, N as low as 1). The repaired spans are applied to the script by setting `share_with`, exactly as `plan_image_budget` does today, so every downstream consumer — numbering, `image_prompts.txt`, folder matching, WolfCut export — is untouched.

**Tech Stack:** Python 3.12, pytest, existing `pipeline/` modules (`voiceover`, `motion`, `text_parser`, `library`, `shot_description`), ffprobe via `pipeline.composer._find_ffprobe`.

---

## Why this exists

`plan_image_budget` cuts the script at cumulative duration boundaries. Measured on `projects/Before_Adam_The_Story_of_Iblis` (347 segments, ~18 min, budget 60): **18 of the 60 spans contain almost nothing a camera could point at, 7 of them in the first 15 pictures.** Picture 9 covers lines 41–44 — four lines of a narrator comparing source reports, with no subject, action or place in them. No wording change to the description request can fix that; the span has no picture in it, so the model invents one.

The count is also the wrong input. The owner wants one image to hold for 70 seconds where the narration is reflective, and 10 seconds where events move — and, at the far end, the option of one image for a whole 20-minute film.

## What success is, and is not

**Success is fewer picture boundaries landing inside narration with nothing to photograph.** Measured today: 18 of 60. Task 13 re-measures it.

**Success is NOT a smaller picture count.** The film is already 60 pictures at a mean of 18.8 seconds each — cinematic pacing by any standard. There is no "one image per sentence" problem in this codebase and never was; that claim comes from an external report written without measuring. A run of this plan that produces 20 pictures is not thereby better, and judging it that way would let a worse film pass.

The count is an output. Leave it alone and read the empty-span number.

## Order of operations, end to end

Nothing here removes automatic image selection. `plan_shots` still binds an image to every picture the film makes; it simply binds to boundaries a model chose rather than slices a clock cut.

```
1. Audio rendered        real seconds + mp3 path per segment        Tasks 1-2
2. Boundaries chosen     model reads the whole script, returns spans  Tasks 5-6
3. Spans applied         share_with + descriptions onto the shots     Task 7
4. Images bound          UNCHANGED - runs automatically               existing plan_shots
                           pin, then numbered folder (1.jpg -> picture 1),
                           then CLIP retrieval, then gap + written prompt
5. Timeline exported     WolfCut, with no video encode                Task 11
```

Step 4 is the part the owner asked about and the part this plan must not disturb. Task 12 proves it.

## File structure

| File | Responsibility |
|---|---|
| `pipeline/narration_timing.py` | **Create.** Measure real spoken seconds per segment; fall back to the word estimate. |
| `pipeline/picture_plan.py` | **Create.** Build the boundary request, parse the reply, repair spans, apply them to a script. |
| `pipeline/shot_description.py` | **Modify.** Reuse `_build_instruction` for the boundary request. |
| `pipeline/text_parser.py` | **Modify.** `plan_image_budget` keeps working; a new entry point routes to the span planner. |
| `pipeline/library.py` | **Modify.** `plan_shots` reads descriptions off spans instead of asking for them per fixed shot. |
| `app.py` | **Modify.** New `plan_pictures_for_script` (auto and manual modes) and `export_wolfcut_timeline`. `set_image_count` is left alone. |
| `pipeline/wolfcut_export.py` | **Read only.** Already takes an audio path and a duration per segment and measures neither; nothing in it changes. |
| `tests/test_picture_plan.py` | **Modify.** Existing file covers the request shape; add spans, repair, exact count. |
| `tests/test_motion.py` | **Modify.** Long-hold clamp verification. |
| `tests/test_narration_timing.py` | **Create.** Seconds, audio paths, and the two WolfCut maps. |
| `tests/test_span_repair.py` | **Create.** Repair invariants and exact-count edges. |
| `tests/test_span_apply.py` | **Create.** Spans becoming `share_with`, and the app wiring. |
| `tests/test_wolfcut_export.py` | **Modify.** A timeline built from timing alone. |

**Conventions in this repo, follow them:**
- Test names are sentences describing the defect, not `test_function_name`. Docstrings explain what broke and why it mattered.
- Never `git add -A` — it stages ~816 MB including two 310 MB ONNX models. Stage explicit paths.
- Python is `C:/Users/HomePC/AppData/Local/Programs/Python/Python312/python.exe` (not on PATH). Prefix anything printing prompt text with `PYTHONIOENCODING=utf-8`.
- Full suite is ~8-14 minutes and currently **548 passed, 1 xfailed**. Run targeted files during development.
- `cache/` staleness causes phantom failures; tests touching `describe_shots` must patch `_load_disk_cache` / `_save_disk_cache`.

---

### Task 1: Measured narration seconds

**Files:**
- Create: `pipeline/narration_timing.py`
- Test: `tests/test_narration_timing.py`

- [ ] **Step 1: Write the failing test**

```python
"""
Planning used a word count to guess how long a line takes to say.

`WORDS_PER_SECOND = 2.6` is a decent average and wrong on every individual
line: a short line with a long pause after it, a name the voice labours over,
a rhetorical question read slowly. Boundaries placed on that estimate drift
from the audio the viewer actually hears.

The narration is generated anyway. Measuring it costs one ffprobe per segment.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.narration_timing import segment_seconds


def _script(*narrations):
    return {"segments": [{"segment_id": i + 1, "narration": n}
                         for i, n in enumerate(narrations)]}


def test_measured_seconds_are_used_when_they_are_there():
    script = _script("one two three", "four five six")
    script["segments"][0]["narration_seconds"] = 4.5
    script["segments"][1]["narration_seconds"] = 9.25

    assert segment_seconds(script) == [4.5, 9.25]


def test_the_word_estimate_stands_in_until_the_audio_exists():
    script = _script(" ".join(["word"] * 26))
    assert segment_seconds(script) == [10.0]


def test_one_measured_segment_does_not_make_the_others_zero():
    """A half-finished timing pass must not silently zero the rest."""
    script = _script("one two three four five", " ".join(["word"] * 26))
    script["segments"][0]["narration_seconds"] = 3.0

    assert segment_seconds(script) == [3.0, 10.0]


def test_an_empty_narration_takes_no_time():
    assert segment_seconds(_script("")) == [0.0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 "C:/Users/HomePC/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/test_narration_timing.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.narration_timing'`

- [ ] **Step 3: Write minimal implementation**

Create `pipeline/narration_timing.py`:

```python
"""
pipeline/narration_timing.py

How long each line of narration actually takes to say.

Planning guessed from a word count. That average is fine across a film and
wrong on every individual line, and picture boundaries placed on a guess drift
from the audio the viewer hears. The narration is generated anyway, so the
real number is one ffprobe away.
"""

import os
import sys

from pipeline.text_parser import WORDS_PER_SECOND


def estimated_seconds(narration: str) -> float:
    """The word-count stand-in, used until the audio exists."""
    words = len((narration or "").split())
    return round(words / WORDS_PER_SECOND, 3) if words else 0.0


def segment_seconds(script_data: dict) -> list:
    """
    Seconds per segment, in script order.

    Measured where a timing pass has run, estimated everywhere else, so a
    half-finished pass degrades to the old behaviour rather than to zeros.
    """
    out = []
    for seg in (script_data.get("segments") or []):
        measured = seg.get("narration_seconds")
        try:
            measured = float(measured)
        except (TypeError, ValueError):
            measured = None
        if measured and measured > 0:
            out.append(measured)
        else:
            out.append(estimated_seconds(seg.get("narration") or ""))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 "C:/Users/HomePC/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/test_narration_timing.py -q`
Expected: PASS, 4 passed

- [ ] **Step 5: Commit**

```bash
git add pipeline/narration_timing.py tests/test_narration_timing.py
git commit -m "feat: measured narration seconds with word-count fallback"
```

---

### Task 2: The timing pass that fills those numbers in

**Files:**
- Modify: `pipeline/narration_timing.py`
- Test: `tests/test_narration_timing.py`

`generate_voiceover` in `pipeline/voiceover.py:883` already caches by file existence in `cache_dir` and returns the mp3 path, so a re-run costs nothing for unchanged segments. Do not build a second cache.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_narration_timing.py`:

```python
from unittest.mock import patch


def test_the_timing_pass_writes_real_seconds_onto_every_segment():
    script = _script("one two three", "four five six")

    with patch("pipeline.narration_timing.generate_voiceover",
               side_effect=lambda **kw: f"/fake/segment_{kw['segment_id']}_audio.mp3"), \
         patch("pipeline.narration_timing.probe_seconds",
               side_effect=lambda path: 4.5 if "segment_1" in path else 9.25):
        stats = measure_narration(script, cache_dir="/fake")

    assert [s["narration_seconds"] for s in script["segments"]] == [4.5, 9.25]
    assert stats["measured"] == 2
    assert stats["failed"] == 0


def test_a_segment_whose_audio_cannot_be_probed_keeps_its_estimate():
    """
    One unreadable mp3 must not zero a segment. A zero-length line collapses
    the boundary maths around it and takes the pacing with it.
    """
    script = _script(" ".join(["word"] * 26), "four five six")

    with patch("pipeline.narration_timing.generate_voiceover",
               side_effect=lambda **kw: f"/fake/segment_{kw['segment_id']}_audio.mp3"), \
         patch("pipeline.narration_timing.probe_seconds",
               side_effect=lambda path: None if "segment_1" in path else 9.25):
        stats = measure_narration(script, cache_dir="/fake")

    assert script["segments"][0].get("narration_seconds") is None
    assert segment_seconds(script) == [10.0, 9.25]
    assert stats["failed"] == 1


def test_a_dead_tts_engine_does_not_take_the_whole_pass_down():
    script = _script("one two three")

    with patch("pipeline.narration_timing.generate_voiceover",
               side_effect=RuntimeError("no engine")):
        stats = measure_narration(script, cache_dir="/fake")

    assert stats["failed"] == 1
    assert stats["measured"] == 0


def test_the_audio_path_is_kept_beside_the_seconds():
    """
    `write_wolfcut_project` takes an audio path per segment and a duration per
    segment, and measures neither itself. Its only caller today is inside the
    render, so a WolfCut timeline costs a full video encode. The timing pass
    produces both maps — keeping the path here is what lets WolfCut export
    without rendering anything.
    """
    script = _script("one two three", "four five six")

    with patch("pipeline.narration_timing.generate_voiceover",
               side_effect=lambda **kw: f"/fake/segment_{kw['segment_id']}_audio.mp3"), \
         patch("pipeline.narration_timing.probe_seconds", return_value=4.0):
        measure_narration(script, cache_dir="/fake")

    assert script["segments"][0]["narration_audio"] == "/fake/segment_1_audio.mp3"
    assert script["segments"][1]["narration_audio"] == "/fake/segment_2_audio.mp3"
```

Add `measure_narration` to the import at the top of the file:

```python
from pipeline.narration_timing import segment_seconds, measure_narration
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 "C:/Users/HomePC/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/test_narration_timing.py -q`
Expected: FAIL — `ImportError: cannot import name 'measure_narration'`

- [ ] **Step 3: Write minimal implementation**

Append to `pipeline/narration_timing.py`:

```python
import subprocess

from pipeline.voiceover import generate_voiceover


def probe_seconds(path: str):
    """Length of an audio file in seconds, or None if it cannot be read."""
    if not path or not os.path.exists(path):
        return None
    try:
        from pipeline.composer import _find_ffprobe
        cmd = [_find_ffprobe(), "-i", path, "-show_entries", "format=duration",
               "-v", "quiet", "-of", "csv=p=0"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        value = float(res.stdout.strip())
        return value if value > 0 else None
    except Exception:
        return None


def measure_narration(script_data: dict, cache_dir: str, google_api_key: str = "",
                      on_progress=None) -> dict:
    """
    Render each segment's narration and record how long it really takes.

    Returns {"measured": int, "failed": int, "seconds": float}.

    A segment that cannot be rendered or probed is left without
    `narration_seconds` rather than being written as zero: `segment_seconds`
    falls back to the word estimate for it, and a zero would collapse the
    boundary maths around that line.
    """
    project = script_data.get("project") or {}
    voice = project.get("voice") or ""
    segments = script_data.get("segments") or []

    measured = failed = 0
    total = 0.0

    for i, seg in enumerate(segments, 1):
        narration = (seg.get("narration") or "").strip()
        if not narration:
            seg["narration_seconds"] = 0.0
            continue

        seg_id = seg.get("segment_id", i)
        if on_progress:
            on_progress(f"Timing segment {i} of {len(segments)}")

        try:
            path = generate_voiceover(
                segment_id=seg_id,
                narration=narration,
                voice=voice,
                voice_rate=project.get("voice_rate", "+0%"),
                voice_pitch=project.get("voice_pitch", "+0Hz"),
                cache_dir=cache_dir,
                google_api_key=google_api_key,
                voice_steering=seg.get("voice_steering", "") or "",
                narrative_tone=project.get("narrative_tone", "") or "",
            )
        except Exception as err:
            sys.stderr.write(f"[narration_timing] segment {seg_id}: {err}\n")
            failed += 1
            continue

        # Kept whether or not the probe succeeds: WolfCut export needs the path
        # and the duration separately, and a readable file with an unreadable
        # duration is still a clip it can lay on the narration track.
        seg["narration_audio"] = path

        seconds = probe_seconds(path)
        if seconds is None:
            failed += 1
            continue

        seg["narration_seconds"] = round(seconds, 3)
        total += seconds
        measured += 1

    return {"measured": measured, "failed": failed, "seconds": round(total, 3)}


def timing_maps(script_data: dict) -> tuple:
    """
    `(audio_paths_map, durations_map)` keyed by segment_id.

    Exactly the two arguments `write_wolfcut_project` takes. It measures
    nothing itself, so these maps are the only thing standing between a script
    and a WolfCut timeline — and building them here means that timeline no
    longer requires a rendered video.
    """
    audio_paths, durations = {}, {}
    seconds = segment_seconds(script_data)
    for i, seg in enumerate(script_data.get("segments") or []):
        seg_id = seg.get("segment_id", i + 1)
        durations[seg_id] = seconds[i] if i < len(seconds) else 0.0
        path = seg.get("narration_audio")
        if path:
            audio_paths[seg_id] = path
    return audio_paths, durations
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 "C:/Users/HomePC/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/test_narration_timing.py -q`
Expected: PASS, 8 passed

- [ ] **Step 5: Commit**

```bash
git add pipeline/narration_timing.py tests/test_narration_timing.py
git commit -m "feat: narration timing pass writes measured seconds and audio paths"
```

---

### Task 3: Span repair — the deterministic safety net

Build this **before** anything asks a model for spans. Every later task depends on being able to take arbitrary input and produce a legal plan.

**Files:**
- Create: `pipeline/picture_plan.py`
- Test: `tests/test_span_repair.py`

**Definitions used throughout:**
- A **span** is `{"first_line": int, "last_line": int, "description": str}`, both bounds inclusive and 1-based.
- `seconds` is a list where `seconds[0]` is the length of line 1.
- A legal plan is: sorted, contiguous, no gaps, no overlaps, first span starts at line 1, last ends at line `n_lines`, at least one span.

- [ ] **Step 1: Write the failing test**

```python
"""
Whatever a model returns, the plan that leaves here is legal.

The model chooses where pictures go, which means it can return spans that
overlap, skip lines, arrive out of order, run past the end of the script, or
miss the count it was given. None of that may reach the script: a gap means
narration with no picture at all, and an overlap means two pictures claiming
the same line and a numbering contract that no longer holds.

Repair is deterministic and always succeeds. There is no failure mode where
the app refuses to plan.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.picture_plan import repair_spans, span_seconds

# Ten lines, four seconds each.
SECONDS = [4.0] * 10
N = 10


def _spans(*pairs):
    return [{"first_line": a, "last_line": b, "description": f"picture at {a}"}
            for a, b in pairs]


def _bounds(spans):
    return [(s["first_line"], s["last_line"]) for s in spans]


def test_a_legal_plan_passes_through_unchanged():
    spans = _spans((1, 4), (5, 7), (8, 10))
    assert _bounds(repair_spans(spans, N, SECONDS, 4.0, 60.0)) == [(1, 4), (5, 7), (8, 10)]


def test_a_gap_is_closed_by_extending_the_span_before_it():
    """Lines 5 and 6 belong to no picture. That is narration over nothing."""
    spans = _spans((1, 4), (7, 10))
    assert _bounds(repair_spans(spans, N, SECONDS, 4.0, 60.0)) == [(1, 6), (7, 10)]


def test_an_overlap_is_resolved_in_favour_of_the_earlier_span():
    spans = _spans((1, 6), (4, 10))
    assert _bounds(repair_spans(spans, N, SECONDS, 4.0, 60.0)) == [(1, 6), (7, 10)]


def test_spans_out_of_order_are_sorted_before_anything_else():
    spans = _spans((8, 10), (1, 4), (5, 7))
    assert _bounds(repair_spans(spans, N, SECONDS, 4.0, 60.0)) == [(1, 4), (5, 7), (8, 10)]


def test_the_plan_always_starts_at_line_one_and_ends_at_the_last_line():
    spans = _spans((3, 7))
    assert _bounds(repair_spans(spans, N, SECONDS, 4.0, 60.0)) == [(1, 10)]


def test_nothing_usable_still_produces_one_picture_over_the_whole_film():
    assert _bounds(repair_spans([], N, SECONDS, 4.0, 60.0)) == [(1, 10)]
    assert _bounds(repair_spans(_spans((99, 200)), N, SECONDS, 4.0, 60.0)) == [(1, 10)]


def test_a_span_shorter_than_the_floor_is_merged_into_a_neighbour():
    """One line is 4s. With a floor of 10s it cannot stand on its own."""
    spans = _spans((1, 4), (5, 5), (6, 10))
    out = repair_spans(spans, N, SECONDS, 10.0, 60.0)
    assert all(span_seconds(s, SECONDS) >= 10.0 for s in out), _bounds(out)
    assert _bounds(out)[0][0] == 1 and _bounds(out)[-1][1] == 10


def test_a_span_longer_than_the_ceiling_is_split():
    """One span of 40s against a 20s ceiling has to become two."""
    out = repair_spans(_spans((1, 10)), N, SECONDS, 4.0, 20.0)
    assert len(out) >= 2
    assert all(span_seconds(s, SECONDS) <= 20.0 + 1e-6 for s in out), _bounds(out)


def test_repair_never_loses_or_duplicates_a_line():
    """The invariant everything else rests on."""
    for spans in (_spans((1, 4), (7, 10)), _spans((1, 6), (4, 10)),
                  _spans((8, 10), (1, 4)), []):
        out = repair_spans(spans, N, SECONDS, 4.0, 60.0)
        covered = [line for s in out for line in range(s["first_line"], s["last_line"] + 1)]
        assert covered == list(range(1, N + 1)), f"{_bounds(out)} does not tile 1..{N}"


def test_the_description_travels_with_its_span():
    out = repair_spans(_spans((1, 4), (5, 10)), N, SECONDS, 4.0, 60.0)
    assert out[0]["description"] == "picture at 1"
    assert out[1]["description"] == "picture at 5"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 "C:/Users/HomePC/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/test_span_repair.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline.picture_plan'`

- [ ] **Step 3: Write minimal implementation**

Create `pipeline/picture_plan.py`:

```python
"""
pipeline/picture_plan.py

Where the pictures go.

The app used to divide the runtime by the picture count and cut there. On the
owner's 18-minute film that put 18 of 60 boundaries inside narration with
nothing to photograph - a narrator comparing source reports, or drawing a moral
- and a model ordered to illustrate those spans invented a cloaked figure on a
ridge, because that is all an empty span supports.

The model that already reads the whole script chooses the boundaries instead.
Time stops deciding where a picture goes and only says how long one may hold.

Everything a model returns passes through `repair_spans` first. It is
deterministic, it always succeeds, and it guarantees the plan tiles the script
exactly once - no gap, no overlap, nothing past the end.
"""

import math
import re


def span_seconds(span: dict, seconds: list) -> float:
    """How long one picture holds, in seconds."""
    first = max(1, int(span.get("first_line") or 1))
    last = min(len(seconds), int(span.get("last_line") or first))
    return round(sum(seconds[first - 1:last]), 3)


def _normalise(spans: list, n_lines: int) -> list:
    """Sorted, contiguous, tiling 1..n_lines exactly once."""
    cleaned = []
    for s in spans or []:
        try:
            first = int(s.get("first_line"))
            last = int(s.get("last_line"))
        except (TypeError, ValueError):
            continue
        if first > last:
            first, last = last, first
        first = max(1, min(n_lines, first))
        last = max(1, min(n_lines, last))
        cleaned.append({"first_line": first, "last_line": last,
                        "description": (s.get("description") or "").strip()})

    cleaned.sort(key=lambda s: (s["first_line"], s["last_line"]))

    out = []
    cursor = 1
    for s in cleaned:
        if s["last_line"] < cursor:
            continue                       # entirely swallowed by what came before
        s["first_line"] = max(s["first_line"], cursor)
        if s["first_line"] > cursor and out:
            out[-1]["last_line"] = s["first_line"] - 1   # close the gap backwards
        elif s["first_line"] > cursor:
            s["first_line"] = cursor                      # nothing before it: pull to the start
        out.append(s)
        cursor = s["last_line"] + 1

    if not out:
        return [{"first_line": 1, "last_line": n_lines, "description": ""}]

    out[0]["first_line"] = 1
    out[-1]["last_line"] = n_lines
    return out


def _merge_at(spans: list, index: int) -> list:
    """Fold span[index + 1] into span[index], keeping the earlier description."""
    merged = dict(spans[index])
    merged["last_line"] = spans[index + 1]["last_line"]
    if not merged["description"]:
        merged["description"] = spans[index + 1]["description"]
    return spans[:index] + [merged] + spans[index + 2:]


def _split(span: dict, seconds: list, parts: int) -> list:
    """Cut one span into `parts` pieces of near-equal duration, on line boundaries."""
    first, last = span["first_line"], span["last_line"]
    lines = list(range(first, last + 1))
    if parts < 2 or len(lines) < 2:
        return [span]
    parts = min(parts, len(lines))

    total = sum(seconds[i - 1] for i in lines)
    target = total / parts

    out, start, run = [], first, 0.0
    for line in lines:
        run += seconds[line - 1]
        remaining_lines = last - line
        remaining_parts = parts - len(out) - 1
        if len(out) < parts - 1 and (run >= target or remaining_lines == remaining_parts):
            out.append({"first_line": start, "last_line": line,
                        "description": span["description"] if not out else ""})
            start, run = line + 1, 0.0
    if start <= last:
        out.append({"first_line": start, "last_line": last,
                    "description": span["description"] if not out else ""})
    return out


def _merge_short(spans: list, seconds: list, min_hold: float) -> list:
    """Fold any picture that cannot hold long enough into the cheaper neighbour."""
    while len(spans) > 1:
        durations = [span_seconds(s, seconds) for s in spans]
        shortest = min(range(len(spans)), key=lambda i: durations[i])
        if durations[shortest] >= min_hold:
            break
        if shortest == 0:
            spans = _merge_at(spans, 0)
        elif shortest == len(spans) - 1:
            spans = _merge_at(spans, shortest - 1)
        elif durations[shortest - 1] <= durations[shortest + 1]:
            spans = _merge_at(spans, shortest - 1)
        else:
            spans = _merge_at(spans, shortest)
    return spans


def _split_long(spans: list, seconds: list, max_hold: float) -> list:
    """Cut any picture that would sit on screen past the ceiling."""
    out = []
    for s in spans:
        dur = span_seconds(s, seconds)
        if dur > max_hold and s["last_line"] > s["first_line"]:
            out.extend(_split(s, seconds, math.ceil(dur / max_hold)))
        else:
            out.append(s)
    return out


def _force_count(spans: list, seconds: list, wanted: int) -> list:
    """Reach exactly `wanted` pictures, merging the cheapest pair or splitting the longest."""
    wanted = max(1, int(wanted))

    while len(spans) > wanted:
        durations = [span_seconds(s, seconds) for s in spans]
        pair = min(range(len(spans) - 1), key=lambda i: durations[i] + durations[i + 1])
        spans = _merge_at(spans, pair)

    while len(spans) < wanted:
        durations = [span_seconds(s, seconds) for s in spans]
        splittable = [i for i, s in enumerate(spans) if s["last_line"] > s["first_line"]]
        if not splittable:
            break                                    # one line per picture already
        longest = max(splittable, key=lambda i: durations[i])
        spans = spans[:longest] + _split(spans[longest], seconds, 2) + spans[longest + 1:]

    return spans


def repair_spans(spans: list, n_lines: int, seconds: list,
                 min_hold: float, max_hold: float, exact_count: int = None) -> list:
    """
    Turn whatever a model returned into a legal picture plan.

    Always succeeds. The result tiles lines 1..n_lines exactly once, in order.
    With `exact_count` the count is met and the holding range is advisory - the
    owner asking for one picture across a twenty-minute film means one picture.
    Without it the holding range governs and the count falls out of the story.
    """
    if n_lines <= 0:
        return []

    out = _normalise(spans, n_lines)
    if exact_count:
        out = _force_count(out, seconds, exact_count)
    else:
        out = _split_long(out, seconds, max_hold)
        out = _merge_short(out, seconds, min_hold)

    for i, s in enumerate(out, 1):
        s["number"] = i
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 "C:/Users/HomePC/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/test_span_repair.py -q`
Expected: PASS, 10 passed

- [ ] **Step 5: Commit**

```bash
git add pipeline/picture_plan.py tests/test_span_repair.py
git commit -m "feat: deterministic span repair guaranteeing a legal picture plan"
```

---

### Task 4: Exact count, down to one picture for a whole film

**Files:**
- Modify: `tests/test_span_repair.py`

`_force_count` is already written. This task proves the owner's stated edge cases hold, because they are the ones that will break silently.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_span_repair.py`:

```python
# ── manual override ───────────────────────────────────────────────────────────

def test_one_picture_can_carry_the_entire_film():
    """
    The owner's words: "I also want flexibility enough that I can decide to
    choose one or two images for a 20-minute video, maybe if that may speak to
    the whole video."
    """
    out = repair_spans(_spans((1, 3), (4, 6), (7, 10)), N, SECONDS,
                       10.0, 20.0, exact_count=1)
    assert _bounds(out) == [(1, 10)]


def test_two_pictures_split_the_film_near_the_middle_by_time():
    out = repair_spans(_spans((1, 10)), N, SECONDS, 10.0, 20.0, exact_count=2)
    assert len(out) == 2
    a, b = (span_seconds(s, SECONDS) for s in out)
    assert abs(a - b) <= 4.0, _bounds(out)


def test_the_exact_count_beats_the_holding_range():
    """
    One picture over a 40s film breaks a 20s ceiling. The owner asked for one
    picture, so he gets one picture — the range is advisory in manual mode and
    the ceiling must not quietly split it back into two.
    """
    out = repair_spans(_spans((1, 10)), N, SECONDS, 4.0, 20.0, exact_count=1)
    assert len(out) == 1
    assert span_seconds(out[0], SECONDS) == 40.0


def test_asking_for_more_pictures_than_lines_stops_at_one_per_line():
    out = repair_spans(_spans((1, 10)), N, SECONDS, 4.0, 20.0, exact_count=25)
    assert len(out) == N
    assert _bounds(out) == [(i, i) for i in range(1, N + 1)]


def test_the_count_is_met_exactly_at_every_size_in_between():
    for wanted in range(1, N + 1):
        out = repair_spans(_spans((1, 4), (5, 7), (8, 10)), N, SECONDS,
                           4.0, 20.0, exact_count=wanted)
        assert len(out) == wanted, f"asked {wanted}, got {len(out)}"
        covered = [ln for s in out for ln in range(s["first_line"], s["last_line"] + 1)]
        assert covered == list(range(1, N + 1))


def test_pictures_are_numbered_from_one_in_film_order():
    out = repair_spans(_spans((1, 4), (5, 7), (8, 10)), N, SECONDS, 4.0, 60.0)
    assert [s["number"] for s in out] == [1, 2, 3]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 "C:/Users/HomePC/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/test_span_repair.py -q -k "exact or one_picture or two_pictures or numbered or count_is_met"`
Expected: Most pass from Task 3's implementation. If `test_the_exact_count_beats_the_holding_range` fails, `_force_count` is being run after `_split_long` — fix the ordering in `repair_spans` so `exact_count` short-circuits the range entirely (the `if exact_count: ... else: ...` branch already does this; do not add a range pass after it).

- [ ] **Step 3: Write minimal implementation**

No new implementation if all pass. If `test_two_pictures_split_the_film_near_the_middle_by_time` fails, the `_split` target arithmetic is drifting; verify `target = total / parts` uses the span's own total, not the film's.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 "C:/Users/HomePC/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/test_span_repair.py -q`
Expected: PASS, 16 passed

- [ ] **Step 5: Commit**

```bash
git add tests/test_span_repair.py
git commit -m "test: exact picture count holds from one to one-per-line"
```

---

### Task 5: Ask the model where the pictures go

**Files:**
- Modify: `pipeline/picture_plan.py`
- Test: `tests/test_picture_plan.py` (existing file — append; do not rewrite it)

The request reuses `_build_instruction(series_cfg)` from `pipeline/shot_description.py`, which already carries the niche recipe, the standing exclusions, the `never_depict` and `never_show_face` rules and the output contract. Only the framing around it changes.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_picture_plan.py`:

```python
# ── asking the model where the pictures go ────────────────────────────────────

from pipeline.picture_plan import build_plan_request, parse_plan_reply

PLAN_SCRIPT = [
    "Before Adam, there was no human being.",
    "No cities. No nations.",
    "Some describe him as belonging to a group called jinn.",
    "And the reports differ over how his position should be understood.",
    "Iblis became involved in fighting the rebellious jinn.",
]
PLAN_SECONDS = [3.0, 2.5, 5.0, 4.5, 4.0]


def test_the_request_shows_every_line_with_its_length():
    req = build_plan_request("INSTRUCTION", PLAN_SCRIPT, PLAN_SECONDS, 8.0, 75.0)
    assert "[1] (3.0s) Before Adam, there was no human being." in req
    assert "[5] (4.0s) Iblis became involved in fighting the rebellious jinn." in req


def test_the_request_states_the_runtime_and_the_holding_range():
    req = build_plan_request("INSTRUCTION", PLAN_SCRIPT, PLAN_SECONDS, 8.0, 75.0)
    assert "19 seconds" in req
    assert "at least 8" in req and "at most 75" in req


def test_the_request_says_a_stretch_may_carry_no_picture_of_its_own():
    """
    The whole point. Without this the model fills every gap in the runtime with
    an invented figure, which is what 18 of 60 spans got.
    """
    req = build_plan_request("INSTRUCTION", PLAN_SCRIPT, PLAN_SECONDS, 8.0, 75.0)
    assert "carry no picture of its own" in req
    assert "let the picture before it hold" in req.lower()


def test_the_request_demands_full_coverage():
    req = build_plan_request("INSTRUCTION", PLAN_SCRIPT, PLAN_SECONDS, 8.0, 75.0)
    assert "line 1 to line 5" in req
    assert "gap" in req.lower() and "overlap" in req.lower()


def test_a_fixed_count_replaces_the_holding_range_in_the_request():
    req = build_plan_request("INSTRUCTION", PLAN_SCRIPT, PLAN_SECONDS, 8.0, 75.0,
                             exact_count=2)
    assert "exactly 2 pictures" in req
    assert "at least 8" not in req


def test_the_reply_is_read_back_into_spans():
    reply = ("1-2: An untouched primordial landscape, no people, no structures\n"
             "3-4: A distant ember-lit silhouette on a ridge, no face, no horns\n"
             "5-5: Dark silhouettes clashing amid embers, no human corpses\n")
    spans = parse_plan_reply(reply, n_lines=5)

    assert [(s["first_line"], s["last_line"]) for s in spans] == [(1, 2), (3, 4), (5, 5)]
    assert spans[1]["description"].startswith("A distant ember-lit silhouette")


def test_a_single_line_picture_may_be_written_without_a_range():
    spans = parse_plan_reply("1-4: first\n5: last\n", n_lines=5)
    assert [(s["first_line"], s["last_line"]) for s in spans] == [(1, 4), (5, 5)]


def test_commentary_around_the_answer_is_ignored():
    """Models preamble. The parser must not turn 'Here is the plan:' into a picture."""
    reply = ("Here is the plan for your film:\n\n"
             "1-3: something\n"
             "4-5: something else\n\n"
             "Let me know if you would like changes.")
    spans = parse_plan_reply(reply, n_lines=5)
    assert [(s["first_line"], s["last_line"]) for s in spans] == [(1, 3), (4, 5)]


def test_an_empty_reply_returns_nothing_rather_than_guessing():
    """repair_spans turns nothing into one whole-film picture. That is its job, not the parser's."""
    assert parse_plan_reply("", n_lines=5) == []
    assert parse_plan_reply("I cannot help with that.", n_lines=5) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 "C:/Users/HomePC/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/test_picture_plan.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_plan_request'`

- [ ] **Step 3: Write minimal implementation**

Append to `pipeline/picture_plan.py`:

```python
#: Lines like "12-19: a description", or "12: a description" for one line.
_SPAN_LINE = re.compile(r"^\s*(\d+)\s*(?:[-\u2013]\s*(\d+))?\s*[:.)]\s*(.+?)\s*$")


def _clock(seconds: float) -> str:
    """`3 minutes 12 seconds`, or `47 seconds` when it is under a minute."""
    total = int(round(seconds))
    minutes, secs = divmod(total, 60)
    if not minutes:
        return f"{secs} seconds"
    return f"{minutes} minute{'s' if minutes != 1 else ''} {secs} seconds"


def build_plan_request(instruction: str, script_lines: list, seconds: list,
                       min_hold: float, max_hold: float,
                       exact_count: int = None) -> str:
    """
    The request that asks a model where the pictures belong.

    It is handed the whole script with the length of every line, and it decides
    the boundaries. The app used to decide them by dividing the runtime, which
    put boundaries inside narration that has nothing to photograph.
    """
    n = len(script_lines)
    total = sum(seconds[:n])

    lines = [instruction, "", "THE FULL SCRIPT",
             "Every line, with how long it takes to say.", ""]
    for i, text in enumerate(script_lines[:n], 1):
        clean = " ".join((text or "").split())
        lines.append(f"[{i}] ({seconds[i - 1]:.1f}s) {clean}")

    lines += ["", "WHERE THE PICTURES GO",
              f"This film runs {_clock(total)} across {n} lines of narration.",
              "You decide where a picture belongs and where one does not."]

    if exact_count:
        lines.append(f"Use exactly {int(exact_count)} pictures, no more and no fewer.")
    else:
        lines.append(f"A picture must hold for at least {min_hold:g} seconds "
                     f"and at most {max_hold:g}.")

    lines += [
        "",
        "A stretch of narration may carry no picture of its own. When the",
        "narrator compares sources, hedges between reports, or draws a lesson,",
        "there is nothing new for a camera to look at.",
        "In that case, let the picture before it hold through the stretch rather",
        "than inventing something to fill the time. A picture invented to fill",
        "time is worse than no cut at all.",
        "",
        f"Cover every line from line 1 to line {n}. Leave no gap and no overlap:",
        "each line belongs to exactly one picture, and the pictures run in order.",
        "",
        "Answer one line per picture, and nothing else:",
        "<first line>-<last line>: <description>",
    ]
    return "\n".join(lines)


def parse_plan_reply(reply_text: str, n_lines: int) -> list:
    """
    Read a model's answer back into spans.

    Anything that is not a span line is dropped rather than guessed at. An
    unusable reply returns an empty list; `repair_spans` decides what to do
    about that, so the failure has exactly one home.
    """
    spans = []
    for raw in (reply_text or "").splitlines():
        m = _SPAN_LINE.match(raw)
        if not m:
            continue
        first = int(m.group(1))
        last = int(m.group(2)) if m.group(2) else first
        description = m.group(3).strip()
        if first < 1 or first > n_lines or not description:
            continue
        spans.append({"first_line": first, "last_line": last,
                      "description": description})
    return spans
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 "C:/Users/HomePC/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/test_picture_plan.py -q`
Expected: PASS — the existing tests in that file plus 9 new

- [ ] **Step 5: Commit**

```bash
git add pipeline/picture_plan.py tests/test_picture_plan.py
git commit -m "feat: ask the model where pictures belong, parse spans from the reply"
```

---

### Task 6: Run the pass end to end

**Files:**
- Modify: `pipeline/picture_plan.py`
- Test: `tests/test_picture_plan.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_picture_plan.py`:

```python
# ── the whole pass ────────────────────────────────────────────────────────────

from pipeline.picture_plan import plan_pictures

PLAN_CFG = {
    "series_slug": "pre_islamic_prophetic___global_history",
    "prompt_recipe": "Write grounded historical descriptions.",
    "era_block": "",
    "negative_block": "modern elements, text, watermark",
    "never_depict": ["Allah"],
    "never_show_face": ["Iblis"],
}


class _Provider:
    def __init__(self, reply):
        self.reply, self.prompt = reply, None

    def identity(self):
        return "gemini", "gemini-2.5-flash"

    def complete_text(self, system, user="", max_tokens=2048):
        self.prompt = system
        return self.reply


def test_the_pass_returns_a_legal_plan_from_a_good_reply():
    prov = _Provider("1-2: an untouched landscape\n3-4: an ember-lit ridge\n5-5: embers clashing")
    spans = plan_pictures(PLAN_SCRIPT, PLAN_SECONDS, series_cfg=PLAN_CFG,
                          provider=prov, min_hold=4.0, max_hold=75.0)

    assert [(s["first_line"], s["last_line"]) for s in spans] == [(1, 2), (3, 4), (5, 5)]
    assert [s["number"] for s in spans] == [1, 2, 3]


def test_the_niche_rules_travel_with_the_boundary_request():
    """The model writes descriptions here too, so it needs the depiction rules."""
    prov = _Provider("1-5: everything")
    plan_pictures(PLAN_SCRIPT, PLAN_SECONDS, series_cfg=PLAN_CFG,
                  provider=prov, min_hold=4.0, max_hold=75.0)

    assert "must never be identifiable: Iblis" in prov.prompt
    assert "modern elements, text, watermark" in prov.prompt


def test_a_broken_reply_still_produces_a_usable_film():
    """Overlapping, out of order, past the end — and the film still plans."""
    prov = _Provider("4-99: late\n1-2: early\n2-3: overlapping")
    spans = plan_pictures(PLAN_SCRIPT, PLAN_SECONDS, series_cfg=PLAN_CFG,
                          provider=prov, min_hold=1.0, max_hold=75.0)

    covered = [ln for s in spans for ln in range(s["first_line"], s["last_line"] + 1)]
    assert covered == [1, 2, 3, 4, 5]


def test_a_dead_provider_gives_one_picture_rather_than_no_film():
    class _Dead:
        def identity(self):
            return "gemini", "gemini-2.5-flash"

        def complete_text(self, system, user="", max_tokens=2048):
            raise RuntimeError("provider is down")

    spans = plan_pictures(PLAN_SCRIPT, PLAN_SECONDS, series_cfg=PLAN_CFG,
                          provider=_Dead(), min_hold=4.0, max_hold=75.0)
    assert [(s["first_line"], s["last_line"]) for s in spans] == [(1, 5)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 "C:/Users/HomePC/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/test_picture_plan.py -q -k "the_pass or niche_rules or broken_reply or dead_provider"`
Expected: FAIL — `ImportError: cannot import name 'plan_pictures'`

- [ ] **Step 3: Write minimal implementation**

Append to `pipeline/picture_plan.py`:

```python
import sys

#: Boundaries and a description for every picture come back in one reply, so the
#: ceiling has to cover the whole film. Only generated tokens are billed, so an
#: unused ceiling costs nothing and a short one silently truncates the plan.
PLAN_REPLY_CEILING = 8192


def plan_pictures(script_lines: list, seconds: list, series_cfg: dict = None,
                  provider=None, min_hold: float = 8.0, max_hold: float = 75.0,
                  exact_count: int = None) -> list:
    """
    Where the pictures go and what each one shows, in one pass over the film.

    Always returns a legal plan. A refusal, a mangled reply or a dead provider
    all end at the same place: one picture over the whole film, which is a film
    the owner can still work with.
    """
    from pipeline.shot_description import _build_instruction

    n = len(script_lines)
    if n == 0:
        return []

    if provider is None:
        from pipeline.llm.factory import get_llm_provider
        provider = get_llm_provider()

    request = build_plan_request(_build_instruction(series_cfg), script_lines,
                                 seconds, min_hold, max_hold, exact_count)

    reply = ""
    try:
        reply = provider.complete_text(system=request, user="",
                                       max_tokens=PLAN_REPLY_CEILING) or ""
    except Exception as err:
        sys.stderr.write(f"[picture_plan] the picture plan fell back to one image: {err}\n")

    return repair_spans(parse_plan_reply(reply, n), n, seconds,
                        min_hold, max_hold, exact_count)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 "C:/Users/HomePC/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/test_picture_plan.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pipeline/picture_plan.py tests/test_picture_plan.py
git commit -m "feat: plan_pictures runs the boundary pass with a safe fallback"
```

---

### Task 7: Write the spans into the script

**Files:**
- Modify: `pipeline/picture_plan.py`
- Test: `tests/test_span_apply.py`

`share_with` is the existing contract: the first shot of a run owns the picture, the rest point at it. `picture_owning_shots` and `picture_runs` in `pipeline/library.py` already read it, so nothing downstream changes.

- [ ] **Step 1: Write the failing test**

```python
"""
A picture plan becomes `share_with` on the shots, and nothing downstream knows.

`share_with` is how the app has always said "these segments share one image".
Writing the model's spans through the same field means numbering, prompt
export, folder matching and the WolfCut timeline all keep working untouched.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.picture_plan import apply_spans
from pipeline.library import picture_owning_shots


def _script(n):
    return {"segments": [
        {"segment_id": i + 1, "narration": f"line {i + 1}",
         "shots": [{"shot_id": f"{i + 1}a", "query": "q", "scene": f"line {i + 1}"}]}
        for i in range(n)]}


SPANS = [
    {"number": 1, "first_line": 1, "last_line": 3, "description": "the first picture"},
    {"number": 2, "first_line": 4, "last_line": 5, "description": "the second picture"},
]


def test_the_first_line_of_a_span_owns_the_picture():
    script = _script(5)
    apply_spans(script, SPANS)

    owners = [shot.get("shot_id") for _seg, shot in picture_owning_shots(script)]
    assert owners == ["1a", "4a"]


def test_every_other_line_in_the_span_points_at_that_owner():
    script = _script(5)
    apply_spans(script, SPANS)

    shots = [seg["shots"][0] for seg in script["segments"]]
    assert [s.get("share_with") for s in shots] == [None, "1a", "1a", None, "4a"]


def test_the_description_lands_on_the_owning_shot_only():
    script = _script(5)
    apply_spans(script, SPANS)

    shots = [seg["shots"][0] for seg in script["segments"]]
    assert shots[0]["visual_description"] == "the first picture"
    assert shots[3]["visual_description"] == "the second picture"
    assert "visual_description" not in shots[1]


def test_applying_a_new_plan_clears_the_old_one():
    """A re-plan must not leave a shot pointing at an owner that no longer owns."""
    script = _script(5)
    apply_spans(script, SPANS)
    apply_spans(script, [{"number": 1, "first_line": 1, "last_line": 5,
                          "description": "one picture now"}])

    shots = [seg["shots"][0] for seg in script["segments"]]
    assert [s.get("share_with") for s in shots] == [None, "1a", "1a", "1a", "1a"]
    assert len(picture_owning_shots(script)) == 1


def test_the_report_says_what_was_applied():
    script = _script(5)
    stats = apply_spans(script, SPANS)
    assert stats == {"pictures": 2, "segments": 5}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 "C:/Users/HomePC/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/test_span_apply.py -q`
Expected: FAIL — `ImportError: cannot import name 'apply_spans'`

- [ ] **Step 3: Write minimal implementation**

Append to `pipeline/picture_plan.py`:

```python
def apply_spans(script_data: dict, spans: list) -> dict:
    """
    Write a picture plan onto the script as `share_with`, and return a report.

    One shot per segment: the plan is about which narration a picture carries,
    and a segment is the unit of narration. A segment carrying several shots is
    collapsed to its first, which is what sharing already means for it.
    """
    segments = script_data.get("segments") or []
    owner_of = {}
    description_of = {}

    for span in spans:
        first = max(1, int(span["first_line"]))
        last = min(len(segments), int(span["last_line"]))
        if first > len(segments):
            continue
        owner_seg = segments[first - 1]
        owner_id = ((owner_seg.get("shots") or [{}])[0].get("shot_id")
                    or f"{owner_seg.get('segment_id', first)}a")
        description_of[owner_id] = (span.get("description") or "").strip()
        for line in range(first, last + 1):
            owner_of[line] = (owner_id, line == first)

    for i, seg in enumerate(segments, 1):
        shots = seg.get("shots") or []
        shot = shots[0] if shots else {"shot_id": f"{seg.get('segment_id', i)}a",
                                       "query": "documentary shot",
                                       "scene": seg.get("narration", "")}
        owner_id, is_owner = owner_of.get(i, (None, True))

        shot["share_with"] = None if (is_owner or owner_id is None) else owner_id
        if is_owner and owner_id and description_of.get(owner_id):
            shot["visual_description"] = description_of[owner_id]
        elif not is_owner:
            shot.pop("visual_description", None)

        seg["shots"] = [shot]

    return {"pictures": sum(1 for s in segments if not s["shots"][0].get("share_with")),
            "segments": len(segments)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 "C:/Users/HomePC/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/test_span_apply.py -q`
Expected: PASS, 5 passed

- [ ] **Step 5: Commit**

```bash
git add pipeline/picture_plan.py tests/test_span_apply.py
git commit -m "feat: apply picture spans to a script through share_with"
```

---

### Task 8: Wire it into the app

**Files:**
- Modify: `app.py:795-807` (`set_image_count`)
- Test: `tests/test_span_apply.py`

`plan_image_budget` stays exactly as it is. It is the fallback when no model is reachable and it is still what `set_image_count` uses for the `N >= segments` case.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_span_apply.py`:

```python
from unittest.mock import patch


def test_auto_mode_lets_the_story_decide_the_count():
    from app import SmartStudioAPI

    script = _script(20)
    fake = [{"number": 1, "first_line": 1, "last_line": 12, "description": "a"},
            {"number": 2, "first_line": 13, "last_line": 20, "description": "b"}]

    with patch("pipeline.picture_plan.plan_pictures", return_value=fake):
        res = SmartStudioAPI().plan_pictures_for_script(script, image_count=None)

    assert res["success"] is True
    assert res["images_after"] == 2
    assert len(picture_owning_shots(script)) == 2


def test_manual_mode_passes_the_count_straight_through():
    from app import SmartStudioAPI

    script = _script(20)
    seen = {}

    def _capture(script_lines, seconds, **kw):
        seen.update(kw)
        return [{"number": 1, "first_line": 1, "last_line": 20, "description": "one"}]

    with patch("pipeline.picture_plan.plan_pictures", side_effect=_capture):
        SmartStudioAPI().plan_pictures_for_script(script, image_count=1)

    assert seen["exact_count"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 "C:/Users/HomePC/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/test_span_apply.py -q -k "auto_mode or manual_mode"`
Expected: FAIL — `AttributeError: 'SmartStudioAPI' object has no attribute 'plan_pictures_for_script'`

- [ ] **Step 3: Write minimal implementation**

Add to `app.py`, directly below `set_image_count`:

```python
    def plan_pictures_for_script(self, script_data: dict, image_count: int = None,
                                 min_hold: float = 8.0, max_hold: float = 75.0) -> dict:
        """
        Let the model decide where the pictures go.

        `image_count` None means the story decides how many and the holding
        range governs. A number means exactly that many, and the range steps
        aside — one picture across a twenty-minute film is a legitimate answer.
        """
        try:
            from pipeline.picture_plan import plan_pictures, apply_spans
            from pipeline.narration_timing import segment_seconds
            from pipeline.library import get_series_config

            segments = script_data.get("segments") or []
            lines = [(seg.get("narration") or "").strip() for seg in segments]
            seconds = segment_seconds(script_data)

            project = script_data.get("project") or {}
            series_cfg = get_series_config(series_slug=project.get("series_slug"),
                                           project_title=project.get("title"))

            spans = plan_pictures(lines, seconds, series_cfg=series_cfg,
                                  min_hold=min_hold, max_hold=max_hold,
                                  exact_count=int(image_count) if image_count else None)
            stats = apply_spans(script_data, spans)

            from pipeline.text_parser import assign_effects, style_of
            assign_effects(script_data, style_of(script_data))

            return {"success": True, "script_data": script_data,
                    "images_after": stats["pictures"], "segments": stats["segments"]}
        except Exception as e:
            return {"success": False, "error": str(e)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 "C:/Users/HomePC/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/test_span_apply.py -q`
Expected: PASS, 7 passed

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_span_apply.py
git commit -m "feat: plan_pictures_for_script endpoint with auto and manual modes"
```

---

### Task 9: A long hold must not sweep across the frame

**Files:**
- Modify: `tests/test_motion.py`

`travel_for` in `pipeline/motion.py:120` already clamps to `prof["max"]`. This proves the owner's concern is covered so nobody "fixes" it later.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_motion.py`:

```python
def test_a_picture_held_for_minutes_barely_moves():
    """
    The owner's concern, in his words: "This may affect the image editing, I
    mean the moving, zooming in, zooming out ... but I know there's always a
    way around that where we're not zooming that much."

    Travel is clamped, so an image held ten minutes travels no further than one
    held five seconds — the same distance over 120x the time, which is 120x
    slower. Nothing needs adding; this is here so nothing removes it.
    """
    from pipeline.motion import travel_for, MOTION_STYLES

    ceiling = MOTION_STYLES["ken_burns"]["max"]

    assert travel_for("ken_burns", 600.0) == ceiling
    assert travel_for("ken_burns", 75.0) == ceiling
    assert travel_for("ken_burns", 5.0) < ceiling


def test_the_static_style_still_holds_perfectly_still_at_any_length():
    from pipeline.motion import travel_for

    assert travel_for("static", 600.0) == 0.0
    assert travel_for("static", 8.0) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 "C:/Users/HomePC/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/test_motion.py -q -k "held_for_minutes or holds_perfectly_still"`
Expected: PASS immediately — the clamp already exists. If `travel_for("ken_burns", 5.0) < ceiling` fails, check `rate * 5.0 = 0.25` against `max = 0.24`; lower the sample to 3.0 seconds and note why in the test.

- [ ] **Step 3: Write minimal implementation**

None. This task documents an existing guarantee.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 "C:/Users/HomePC/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/test_motion.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_motion.py
git commit -m "test: motion travel stays clamped for very long holds"
```

---

### Task 10: The export carries the plan the model made

**Files:**
- Modify: `pipeline/visuals.py` (`write_prompt_request`)
- Test: `tests/test_manual_image_route.py`

The no-key export must show real timecodes, so an external AI can pace its descriptions to the seconds available.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_manual_image_route.py`:

```python
def test_the_export_says_when_each_picture_is_on_screen(tmp_path, monkeypatch):
    """
    "Picture 7 - script lines 31-36" tells an outside AI nothing about pace.
    "Picture 7 - 02:14 to 02:33" tells it it has nineteen seconds to fill.
    """
    from pipeline.visuals import write_prompt_request

    data = _budgeted(60, 12)
    for i, seg in enumerate(data["segments"], 1):
        seg["narration_seconds"] = 5.0

    monkeypatch.setattr("pipeline.visuals._generate_placeholder_image", lambda *a, **k: None)
    text = open(write_prompt_request(data), encoding="utf-8").read()
    body = text.split("=" * 70, 1)[1]

    assert re.search(r"^Picture 1 .*00:00 to 00:2[05]", body, re.M), body[:600]
    assert re.search(r"^Picture 12 ", body, re.M)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 "C:/Users/HomePC/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/test_manual_image_route.py -q -k "when_each_picture"`
Expected: FAIL — the plan block prints only line numbers

- [ ] **Step 3: Write minimal implementation**

In `pipeline/shot_description.py`, extend `_span_label` to take optional timing:

```python
def _span_label(entry: dict) -> str:
    """`02:14 to 02:33 (script lines 7-13)`, or line numbers alone when untimed."""
    first, last = entry.get("first_line"), entry.get("last_line")
    if not first:
        return "position unknown"
    lines = (f"script line {first}" if not last or last == first
             else f"script lines {first}-{last}")

    start, end = entry.get("starts_at"), entry.get("ends_at")
    if start is None or end is None:
        return lines

    def _mmss(value):
        minutes, secs = divmod(int(round(float(value))), 60)
        return f"{minutes:02d}:{secs:02d}"

    return f"{_mmss(start)} to {_mmss(end)} ({lines})"
```

In `pipeline/visuals.py`, inside `write_prompt_request`, populate the two new keys when building `pictures`. Immediately after the `pictures = [...]` comprehension add:

```python
    # On-screen times, so an outside AI can pace a description to the seconds
    # it actually has. Estimated until the narration has been rendered.
    from pipeline.narration_timing import segment_seconds
    seconds = segment_seconds(script_dict)
    elapsed = 0.0
    for p in pictures:
        p["starts_at"] = round(elapsed, 3)
        elapsed += sum(seconds[p["first_line"] - 1:p["last_line"]])
        p["ends_at"] = round(elapsed, 3)
```

Then pass them through in the `picture_plan=` argument of the `_build_batch_prompt` call:

```python
        picture_plan=[{"number": p["picture_number"], "shot_id": p["shot_id"],
                       "first_line": p["first_line"], "last_line": p["last_line"],
                       "starts_at": p["starts_at"], "ends_at": p["ends_at"]}
                      for p in pictures],
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 "C:/Users/HomePC/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/test_manual_image_route.py tests/test_picture_plan.py -q`
Expected: PASS. `test_every_picture_says_which_lines_it_carries` in `tests/test_picture_plan.py` passes untimed spans and must still see `Picture 1 — script lines 1-6`.

- [ ] **Step 5: Commit**

```bash
git add pipeline/shot_description.py pipeline/visuals.py tests/test_manual_image_route.py
git commit -m "feat: prompt request states when each picture is on screen"
```

---

### Task 11: A WolfCut timeline without rendering a video

**Files:**
- Modify: `app.py`
- Test: `tests/test_wolfcut_export.py`

`write_wolfcut_project(script_data, audio_paths_map, durations_map, project_dir)` measures nothing. Its only caller today is `pipeline/orchestrator.py:539`, inside the render — so a timeline costs a full video encode, which is why the editor-bridge route has never been usable. Task 2 produces both maps. This connects them.

The picture track is built from `share_with` runs, so the model-chosen boundaries from Tasks 5-8 become the clip boundaries in the editor. That is the whole reason to do this now rather than later.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_wolfcut_export.py`:

```python
def test_a_timeline_can_be_built_from_timing_alone(tmp_path):
    """
    The editor bridge without a render. The narration is generated and probed,
    the picture boundaries come from the plan, and the timeline is written —
    no video encode anywhere in that sentence.
    """
    from pipeline.narration_timing import timing_maps
    from pipeline.picture_plan import apply_spans

    audio = tmp_path / "seg.mp3"
    audio.write_bytes(b"\x00" * 64)

    script = {
        "project": {"title": "Timing Only", "aspect_ratio": "16:9"},
        "segments": [
            {"segment_id": i + 1, "narration": f"line {i + 1}",
             "narration_seconds": 5.0, "narration_audio": str(audio),
             "shots": [{"shot_id": f"{i + 1}a", "query": "q", "scene": f"line {i + 1}"}]}
            for i in range(6)
        ],
    }
    apply_spans(script, [
        {"number": 1, "first_line": 1, "last_line": 4, "description": "the long hold"},
        {"number": 2, "first_line": 5, "last_line": 6, "description": "the second"},
    ])

    audio_paths, durations = timing_maps(script)
    assert durations == {i: 5.0 for i in range(1, 7)}

    path = write_wolfcut_project(script, audio_paths, durations, str(tmp_path))

    import json
    doc = json.load(open(path, encoding="utf-8"))
    picture_track = doc["tracks"][0]
    assert len(picture_track["clips"]) == 2, "the plan's two pictures did not become two clips"
    assert picture_track["clips"][0]["duration"] == 20.0, "the four-line hold was not collapsed"
    assert picture_track["clips"][1]["start"] == 20.0, "the second picture starts in the wrong place"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 "C:/Users/HomePC/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/test_wolfcut_export.py -q -k "timing_alone"`
Expected: FAIL — `ImportError: cannot import name 'timing_maps'` until Task 2 is complete. If Task 2 is done and this still fails, read the failure: `doc["tracks"][0]` may not be the picture track in this document version — check `write_wolfcut_project`'s docstring, which names T1 Pictures, T2 Narration, T3 Captions, and index accordingly rather than changing the export.

- [ ] **Step 3: Write minimal implementation**

Add to `app.py`, below `plan_pictures_for_script`:

```python
    def export_wolfcut_timeline(self, script_data: dict, project_dir: str) -> dict:
        """
        Write a WolfCut timeline from the narration timing, with no video render.

        The export has always been able to do this — it takes an audio path and
        a duration per segment and measures neither. It was only ever called
        from inside the renderer, so a timeline cost a full encode.
        """
        try:
            from pipeline.narration_timing import timing_maps
            from pipeline.wolfcut_export import write_wolfcut_project

            audio_paths, durations = timing_maps(script_data)
            if not audio_paths:
                return {"success": False,
                        "error": "No narration audio yet. Run the timing pass first."}

            path = write_wolfcut_project(script_data, audio_paths, durations, project_dir)
            return {"success": True, "path": path, "segments": len(durations)}
        except Exception as e:
            return {"success": False, "error": str(e)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 "C:/Users/HomePC/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/test_wolfcut_export.py -q`
Expected: PASS — the existing WolfCut tests plus the new one

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_wolfcut_export.py
git commit -m "feat: WolfCut timeline from narration timing without a render"
```

---

### Task 12: The whole chain, in order

**Files:**
- Test: `tests/test_span_apply.py`

The owner's question, and the one thing no earlier task proves: **after the audio is rendered and the boundaries are chosen, are images still picked automatically?**

They are. `plan_shots` binds an image to every picture-owning shot — a pin first, then a numbered folder image, then CLIP retrieval from the library, then a gap with a prompt written for it. This plan does not touch any of that. What changes is only that it now binds to spans a model chose instead of slices a clock cut.

But `plan_shots` also calls `describe_shots`, and Task 7 has already put a description on every owning shot. Nothing yet proves it will not throw those away and ask the model again. Prove it.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_span_apply.py`:

```python
# ── the whole chain ───────────────────────────────────────────────────────────

def test_planning_after_spans_does_not_ask_the_model_to_describe_again():
    """
    `apply_spans` writes a description onto every owning shot. `plan_shots`
    then runs `describe_shots`, which must recognise them as already written.

    If it does not, every re-plan pays for the descriptions twice and — worse —
    the second answer is written for a shot rather than for the span, which is
    the exact defect this whole plan exists to remove.
    """
    from pipeline.shot_description import describe_shots

    script = _script(5)
    apply_spans(script, SPANS)

    owning = [seg["shots"][0] for seg in script["segments"]
              if not seg["shots"][0].get("share_with")]
    shots_for_desc = [{"shot_id": s["shot_id"], "scene": s["scene"],
                       "picture_number": i + 1, "first_line": i + 1, "last_line": i + 1,
                       "visual_description": s.get("visual_description")}
                      for i, s in enumerate(owning)]

    class _MustNotBeCalled:
        def identity(self):
            return "gemini", "gemini-2.5-flash"

        def complete_text(self, system, user="", max_tokens=2048):
            raise AssertionError("describe_shots asked the model for descriptions it already had")

    out = describe_shots(shots_for_desc, series_cfg={"prompt_recipe": "r"},
                         provider=_MustNotBeCalled())

    assert out["1a"] == "the first picture"
    assert out["4a"] == "the second picture"


def test_a_numbered_folder_image_still_binds_to_the_picture_it_names():
    """
    The numbering contract, across the new boundaries. `3.jpg` is the third
    picture the film makes — whoever decided where that picture starts.
    """
    from pipeline.library import match_folder_images_by_slot

    script = _script(9)
    apply_spans(script, [
        {"number": 1, "first_line": 1, "last_line": 4, "description": "first"},
        {"number": 2, "first_line": 5, "last_line": 6, "description": "second"},
        {"number": 3, "first_line": 7, "last_line": 9, "description": "third"},
    ])

    owners = picture_owning_shots(script)
    assert len(owners) == 3

    matched, fell_back = match_folder_images_by_slot(
        ["/imgs/1_a.jpg", "/imgs/2_b.jpg", "/imgs/3_c.jpg"], len(owners))
    assert fell_back is False
    assert matched[2].endswith("3_c.jpg"), "picture 3 did not receive 3.jpg"


def test_every_picture_the_film_makes_has_a_description_to_bind_to():
    """A picture with no description falls back to two-word keyword search."""
    script = _script(9)
    apply_spans(script, [
        {"number": 1, "first_line": 1, "last_line": 4, "description": "first"},
        {"number": 2, "first_line": 5, "last_line": 9, "description": "second"},
    ])

    for _seg, shot in picture_owning_shots(script):
        assert (shot.get("visual_description") or "").strip(), shot["shot_id"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONIOENCODING=utf-8 "C:/Users/HomePC/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/test_span_apply.py -q -k "does_not_ask or numbered_folder or has_a_description"`
Expected: These should PASS without new code. `describe_shots` already returns an existing `visual_description` untouched when one is present (`pipeline/shot_description.py`, the `if existing_desc:` branch of the cache loop).

If `test_planning_after_spans_does_not_ask_the_model_to_describe_again` FAILS, the descriptions are being rejected by `is_valid_description` before they are kept. Check that `series_cfg` carries a non-empty `prompt_recipe` — with no recipe the built-in gates apply and a long description is discarded. Do not weaken `is_valid_description`; pass the real niche config through instead.

- [ ] **Step 3: Write minimal implementation**

None expected. This task proves an existing guarantee holds across the new boundaries; it exists so nobody removes it.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONIOENCODING=utf-8 "C:/Users/HomePC/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/test_span_apply.py -q`
Expected: PASS, 10 passed

- [ ] **Step 5: Commit**

```bash
git add tests/test_span_apply.py
git commit -m "test: images still bind automatically across model-chosen boundaries"
```

---

### Task 13: Prove it on the real film

**Files:** none — this is the acceptance check. It is the only task whose result decides whether the work was worth doing.

- [ ] **Step 1: Run the full suite**

Run: `PYTHONIOENCODING=utf-8 "C:/Users/HomePC/AppData/Local/Programs/Python/Python312/python.exe" -m pytest tests/ -q`
Expected: 548 pre-existing tests still pass, plus everything added here. Zero failures.

- [ ] **Step 2: Measure the new boundaries against the old ones**

```bash
PYTHONIOENCODING=utf-8 "C:/Users/HomePC/AppData/Local/Programs/Python/Python312/python.exe" - <<'EOF'
import json, re, statistics
from pipeline.picture_plan import plan_pictures, span_seconds
from pipeline.narration_timing import segment_seconds
from pipeline.library import get_series_config

d = json.load(open('projects/Before_Adam_The_Story_of_Iblis/script.json', encoding='utf-8'))
segs = d["segments"]
lines = [(s.get("narration") or "").strip() for s in segs]
seconds = segment_seconds(d)
cfg = get_series_config(series_slug=d["project"]["series_slug"],
                        project_title=d["project"]["title"])

spans = plan_pictures(lines, seconds, series_cfg=cfg, min_hold=8.0, max_hold=75.0)
holds = [span_seconds(s, seconds) for s in spans]
print(f"pictures: {len(spans)} (was 60)")
print(f"hold: min {min(holds):.1f}s max {max(holds):.1f}s median {statistics.median(holds):.1f}s")

ABSTRACT = re.compile(r"\b(some|other|several) (reports?|describe|say)\b|\baccording to\b|"
                      r"\breports? (differ|describe|converge)\b|\ba person can\b|"
                      r"\bthis is where\b|\bbecause he was\b", re.I)
CONCRETE = re.compile(r"\b(earth|ground|fire|clay|water|mountain|sky|desert|garden|gate|hall|"
                      r"stone|blood|dust|light|throne|tree|river|cave|sand|smoke|wall|body|hand|"
                      r"walked|stood|fought|knelt|bowed|struck|built|rose|fell|shed|sent)\b", re.I)
empty = sum(1 for s in spans
            if len(CONCRETE.findall(" ".join(lines[s["first_line"]-1:s["last_line"]]))) <= 1
            and ABSTRACT.search(" ".join(lines[s["first_line"]-1:s["last_line"]])))
print(f"spans with almost nothing to photograph: {empty} (was 18 of 60)")
EOF
```

**Pass condition:** spans with nothing to photograph drops well below 18. If it does not, the model is ignoring the "a stretch may carry no picture of its own" paragraph — iterate on that wording in `build_plan_request` before touching anything else. The number, not the suite, is what says whether this worked.

- [ ] **Step 3: Read the first fifteen descriptions**

```bash
PYTHONIOENCODING=utf-8 "C:/Users/HomePC/AppData/Local/Programs/Python/Python312/python.exe" -c "import json; from pipeline.visuals import write_prompt_request; print(write_prompt_request(json.load(open('projects/Before_Adam_The_Story_of_Iblis/script.json',encoding='utf-8'))))"
```

Paste into any chat, read pictures 1-15. That stretch is where the owner stopped generating last time — seven of those fifteen spans previously had no picture in them. Judge by reading, not by the suite.

- [ ] **Step 4: Commit nothing here**

This task produces evidence, not code. Report the two numbers — picture count and empty-span count — before deciding what to do next.

---

## What this plan does not do

- **`plan_image_budget` is not deleted.** It stays as the offline fallback and for the `N >= segments` split case. Removing it is a separate decision once the model route has proven itself on a real film.
- **The audio-first pass is not wired into the render pipeline.** Task 2 builds `measure_narration`; running it automatically before planning is a UI decision the owner has not made yet. Until then `segment_seconds` returns the word estimate and everything works.
- **No frontend work.** `plan_pictures_for_script` and `export_wolfcut_timeline` exist and are callable; putting an "auto" option next to the image-count box in `frontend/index.html`, or an "Export timeline" button, is deliberately out of scope. Inline `style="` there is capped at 19 and is at 19, so any layout goes in `style.css`.

- **The WolfCut acceptance test is still outstanding.** Task 11 proves the file is written with the right clip boundaries. Nobody has yet opened a `.wolfcut` file in WolfCut itself. That remains the one test only the owner can run.

## Why the WolfCut order matters

Doing the timing pass first is not merely convenient for WolfCut — it is what makes the editor bridge real. Three things have to be true for a timeline to be worth opening, and after Task 11 all three are:

1. **Real durations, with no render.** `write_wolfcut_project` never measured anything itself. It was simply never called from anywhere except inside the encoder, so a timeline cost a full video pass.
2. **Picture clips that mean something.** The picture track collapses `share_with` runs into single clips. Before this plan those runs came from dividing the clock, so the timeline inherited boundaries falling inside narration with nothing to photograph. After Tasks 5-8 the clip boundaries are editorial choices — which is what makes them worth nudging by hand rather than fighting.
3. **Nothing writes back over the owner's edits.** A clip stretched in WolfCut is his decision; no task here reaches back into the timeline.
