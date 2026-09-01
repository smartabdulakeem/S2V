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

#: Lines like "12-19: a description", or "12: a description" for one line.
_SPAN_LINE = re.compile(r"^\s*(\d+)\s*(?:[-\u2013]\s*(\d+))?\s*[:.)]\s*(.+?)\s*$")

# The request is pasted into a browser chat, because there are no API credits,
# and those chats format lists with markdown. A bullet, a bold range or a
# "Picture 3" label in front of a span dropped that span, and a reply whose
# every line is dropped parses as nothing - which repair_spans answers with one
# picture for the whole film. Good answers were being thrown away in silence.
_MARKUP = re.compile(r"^\s*(?:[-*\u2022>]+\s+)?"
                     r"(?:(?:picture|image|shot)\s*\d+\s*[\u2014\u2013:\-]?\s*)?"
                     r"(?:(?:script\s+)?lines?\s+)?", re.IGNORECASE)
_WRAPPED = re.compile(r"^\((\d+(?:\s*[-\u2013\u2014]\s*\d+)?)\)")


def _unformat(raw_line: str) -> str:
    """The span line as it would read without the chat's markup around it."""
    line = (raw_line or "").replace("**", "").replace("__", "").strip()
    line = _MARKUP.sub("", line, count=1)
    return _WRAPPED.sub(r"\1", line.strip())


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
        m = _SPAN_LINE.match(_unformat(raw))
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