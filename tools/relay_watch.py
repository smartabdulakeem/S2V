"""
tools/relay_watch.py

Watches RELAY-STATE.json and prints one line when the relay token comes back to
Claude Code, then exits. Run it in the background: the exit is the notification.

Why this exists
---------------
The relay protocol calls itself "event-driven", but nothing carried the event.
Antigravity writes the state file and stops; Claude Code reads files only when it
is already awake. So a completed slice sat at ready_for=CLAUDE with no one
looking at it, and the owner had to notice and say so by hand. This is the
missing transport.

Arming mid-cycle is safe. The state file is fingerprinted at startup and the
watcher only fires on a *change*, so arming it while the token already says
CLAUDE will not fire on the state that is already being worked on. The normal
sequence is: Claude hands off (ready_for=ANTIGRAVITY, first change, no fire),
Antigravity finishes (ready_for=CLAUDE, second change, fires).

Silence is not success, so it also fires on the ways the loop can break rather
than complete: an unreadable or malformed state file, and RELAY-FEEDBACK.md
appearing (Antigravity halting to report a problem). A stalled relay should
always end in a notification, never in nothing.

Usage:
    python tools/relay_watch.py [--interval 30] [--timeout 0]

    --interval  seconds between polls (default 30)
    --timeout   seconds before giving up and reporting the stall; 0 means never
"""

import argparse
import hashlib
import json
import os
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(REPO_ROOT, "RELAY-STATE.json")
FEEDBACK_PATH = os.path.join(REPO_ROOT, "RELAY-FEEDBACK.md")


def fingerprint(path: str) -> str:
    """A hash of the file's bytes, or a marker for missing/unreadable."""
    try:
        with open(path, "rb") as f:
            return hashlib.sha1(f.read()).hexdigest()
    except OSError:
        return "MISSING"


def read_state():
    """(state_dict, error_string). Exactly one of the two is meaningful."""
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f), None
    except FileNotFoundError:
        return None, "RELAY-STATE.json does not exist"
    except json.JSONDecodeError as e:
        return None, f"RELAY-STATE.json is not valid JSON: {e}"
    except OSError as e:
        return None, f"RELAY-STATE.json could not be read: {e}"


def emit(line: str) -> None:
    print(line, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=30.0)
    ap.add_argument("--timeout", type=float, default=0.0)
    args = ap.parse_args()

    start = time.time()
    baseline = fingerprint(STATE_PATH)
    feedback_at_start = os.path.exists(FEEDBACK_PATH)

    while True:
        if args.timeout and (time.time() - start) > args.timeout:
            emit(
                f"RELAY STALLED: no hand-back after {int(args.timeout)}s. "
                "The token has not returned to Claude. Check whether Antigravity is still running."
            )
            return 0

        current = fingerprint(STATE_PATH)

        # A new RELAY-FEEDBACK.md means Antigravity halted to report a problem.
        # That is a hand-back even if the state file has not caught up.
        if os.path.exists(FEEDBACK_PATH) and not feedback_at_start:
            emit("RELAY: RELAY-FEEDBACK.md appeared — Antigravity halted with a problem to read.")
            return 0

        if current != baseline:
            state, err = read_state()
            if err:
                emit(f"RELAY BROKEN: {err}")
                return 0

            ready_for = str(state.get("ready_for", "")).strip().upper()
            phase = state.get("phase", "?")
            slice_id = state.get("slice", "?")

            if ready_for == "CLAUDE":
                emit(
                    f"RELAY: token is back with Claude. phase={phase} slice={slice_id}. "
                    "Review the working tree, run the suite, commit, write the next brief."
                )
                return 0

            # Some other write (usually Claude's own hand-off). Re-baseline and keep waiting.
            baseline = current

        time.sleep(args.interval)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
