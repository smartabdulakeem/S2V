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