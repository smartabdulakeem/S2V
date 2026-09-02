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
# Models number their own answers: "1: 1-6: a wide landscape". The leading
# number was read as the whole span, so the picture covered one line and the
# real range ended up inside the description. Stripped only when a range
# actually follows, so a genuine one-line answer - "7: a close shot" - survives.
_RENUMBERED = re.compile(r"^\d+\s*[:.)]\s*(?=\d+\s*[-\u2013\u2014]\s*\d+\s*[:.)])")


def _unformat(raw_line: str) -> str:
    """The span line as it would read without the chat's markup around it."""
    line = (raw_line or "").replace("**", "").replace("__", "").strip()
    line = _MARKUP.sub("", line, count=1)
    line = _RENUMBERED.sub("", line.strip(), count=1)
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


# Asking the model not to write negations gets it right most of the time, and
# "most of the time" still puts "devoid of any human presence" on the opening
# picture of a film. An image model reads that as a request for human presence,
# so the clause is removed rather than argued about.
_NEGATION_CLAUSE = re.compile(
    r"(?:^|(?<=[,;]))\s*(?:and\s+|but\s+|with\s+|the\s+air\s+is\s+)?"
    r"(?:no|not|without|avoid(?:ing)?|free\s+of|devoid\s+of|empty\s+of|"
    r"absent|lacking|bare\s+of|untouched\s+by)\b[^,;.]*",
    re.IGNORECASE)


def strip_negations(text: str) -> str:
    """
    Remove clauses that describe what is not there.

    Text encoders do not parse negation: "no wings" raises the odds of wings.
    The instruction forbids it and the model mostly complies, so this is the
    guarantee behind the request rather than a replacement for it. If removing
    the negations would leave nothing, the original is kept - a flawed
    description still beats an empty one.
    """
    if not text:
        return text
    cleaned = _NEGATION_CLAUSE.sub("", text)
    if cleaned == text:
        return text          # nothing removed: leave the wording exactly alone
    cleaned = re.sub(r"\s*,\s*(?=[,.])", "", cleaned)
    cleaned = re.sub(r"(?:\s*,)+\s*", ", ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;")
    # Only guards against a description that was nothing but its negation.
    if len(cleaned) < 12:
        return text.strip()
    if not cleaned.endswith((".", "!", "?")):
        cleaned += "."
    return cleaned


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
                      "description": strip_negations(description)})
    return spans

import sys

#: Boundaries and a description for every picture come back in one reply, so the
#: ceiling has to cover the whole film. Only generated tokens are billed, so an
#: unused ceiling costs nothing and a short one silently truncates the plan.
# One export came back with a description ending "and a single, distant," -
# the reply ran out of room mid-sentence. Nineteen rich descriptions is well
# past 8192 tokens once the model reasons before answering.
PLAN_REPLY_CEILING = 32768


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

    # Hoisted: the same instruction carries the niche recipe, the standing
    # exclusions and the depiction rules into the describe pass below.
    instruction = _build_instruction(series_cfg)
    request = build_plan_request(instruction, script_lines,
                                 seconds, min_hold, max_hold, exact_count)

    reply = ""
    try:
        reply = provider.complete_text(system=request, user="",
                                       max_tokens=PLAN_REPLY_CEILING) or ""
    except Exception as err:
        sys.stderr.write(f"[picture_plan] the picture plan fell back to one image: {err}\n")

    spans = repair_spans(parse_plan_reply(reply, n), n, seconds,
                         min_hold, max_hold, exact_count)

    # Repair can create pictures the model never described - splitting to meet an
    # exact count is the common way. A picture with no description falls back to
    # raw search keywords when the prompt is assembled, so it is asked for here
    # and borrowed from a neighbour only if that also fails.
    clear_cross_references(spans)
    describe_missing_spans(spans, script_lines, instruction, provider)
    # A rewrite can come back leaning on a neighbour again. Twice is enough:
    # borrowing a neighbour's words is better than describing a picture nobody
    # generating this one can see.
    clear_cross_references(spans)
    fill_undescribed(spans)
    return spans

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

_NUMBERED_LINE = re.compile(r"^\s*(\d+)\s*[:.)]\s*(.+?)\s*$")


def _describe_request(instruction: str, spans: list, script_lines: list,
                      wanted: list) -> str:
    """Ask for the pictures that have no description, and only those."""
    out = [instruction, "",
           "PICTURES THAT STILL NEED A DESCRIPTION",
           "Each one below is a picture with no description yet. Write one for",
           "each, from the narration it carries.", ""]
    for i in wanted:
        span = spans[i]
        first = max(1, int(span.get("first_line") or 1))
        last = min(len(script_lines), int(span.get("last_line") or first))
        out.append(f"Picture {i + 1} - script lines {first}-{last}")
        for line_no in range(first, last + 1):
            text = " ".join((script_lines[line_no - 1] or "").split())
            out.append(f"[{line_no}] {text}")
        out.append("")
    out += ["Answer one line per picture, and nothing else:",
            "<picture number>: <description>"]
    return "\n".join(out)


# "The same primordial landscape, but now with drifting embers" was picture two
# of a real export. Nothing generates picture one first and hands it over: every
# image is made alone, so a description that leans on its neighbour describes
# nothing at all. These are asked for again rather than patched, because there
# is no way to repair the reference without knowing what it pointed at.
_REFERS_ELSEWHERE = re.compile(
    r"\b(?:the\s+same|as\s+(?:before|above|in\s+the\s+(?:previous|last|first))|"
    r"same\s+as|previously|the\s+previous\s+(?:scene|shot|image|picture)|"
    r"this\s+scene\s+continues|continuing\s+from|now\s+with|"
    r"identical\s+to|matching\s+the\s+(?:previous|earlier))\b",
    re.IGNORECASE)


def refers_to_another_picture(text: str) -> bool:
    """Does this description only make sense next to another one?"""
    return bool(_REFERS_ELSEWHERE.search(text or ""))


def clear_cross_references(spans: list) -> int:
    """Blank any description that leans on another picture, so it is rewritten."""
    cleared = 0
    for span in spans:
        if refers_to_another_picture(span.get("description") or ""):
            span["description"] = ""
            cleared += 1
    return cleared


def describe_missing_spans(spans: list, script_lines: list, instruction: str,
                           provider, max_tokens: int = PLAN_REPLY_CEILING) -> int:
    """
    Write a description for every picture that has none. Returns how many landed.

    Splitting a span to meet an exact count leaves its pieces blank, and a blank
    picture falls back to the shot's raw search keywords at prompt assembly -
    which is how a real 30-picture export came out as 3 written prompts and 27
    noun piles. Asking again for just the blanks is what closes that gap.
    """
    wanted = [i for i, s in enumerate(spans)
              if not (s.get("description") or "").strip()]
    if not wanted or provider is None:
        return 0

    try:
        reply = provider.complete_text(
            system=_describe_request(instruction, spans, script_lines, wanted),
            user="", max_tokens=max_tokens) or ""
    except Exception as err:
        sys.stderr.write(f"[picture_plan] descriptions fell back: {err}\\n")
        return 0

    filled = 0
    for raw_line in reply.splitlines():
        m = _NUMBERED_LINE.match(_unformat(raw_line))
        if not m:
            continue
        index = int(m.group(1)) - 1
        text = m.group(2).strip()
        # Answered by picture number, never by position in the reply: a model
        # that answers out of order would otherwise shift every description.
        if 0 <= index < len(spans) and text and index in wanted:
            spans[index]["description"] = strip_negations(text)
            filled += 1
    return filled


def fill_undescribed(spans: list) -> int:
    """
    Last resort: a still-blank picture borrows its nearest neighbour's words.

    A neighbour repeated is a weaker picture. A pile of search keywords is not a
    picture at all, and that is what the alternative is. With nothing written
    anywhere there is nothing honest to borrow, so the blanks are left alone.
    """
    borrowed = 0
    last = ""
    for span in spans:
        if (span.get("description") or "").strip():
            last = span["description"].strip()
        elif last:
            span["description"] = last
            borrowed += 1

    nxt = ""
    for span in reversed(spans):
        if (span.get("description") or "").strip():
            nxt = span["description"].strip()
        elif nxt:
            span["description"] = nxt
            borrowed += 1
    return borrowed
