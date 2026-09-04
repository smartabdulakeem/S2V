"""
tools/relay_loop.py

The driver. It watches RELAY-STATE.json and spawns a *fresh* Claude Code session
for each slice, so the relay can run a whole milestone without a human in the
middle and without a single conversation growing to the size of the project.

Why this exists
---------------
Until now the relay's transport was a person. Antigravity finished a slice and
stopped; the state file said ready_for=CLAUDE and nothing read it; the owner had
to notice and say so by hand. tools/relay_watch.py fixed the *noticing* - it
fires once when the token comes back - but something still had to act on it.
This is that something.

The architectural point, and the reason this is a driver and not a long chat:

    State is durable on disk. Sessions are disposable.

Everything the next session needs is already in RELAY-STATE.json,
ANTIGRAVITY-RULES.md, the slice brief, and git history. So there is no value in
keeping a session alive between slices, and there is real cost: every API request
re-sends the whole conversation, which makes a long session quadratic in turns,
and the prompt cache expires across the twenty-plus minutes a slice spends
waiting on Antigravity. A session per slice is a clean 20-30k context that reads
its rules at full strength instead of through a lossy /compact summary.

What this driver can and cannot spawn
-------------------------------------
It spawns **Claude** with `claude -p`, headless, fresh context, one process per
slice. That half is fully automatic.

It cannot spawn **Antigravity**. Antigravity is a separate IDE agent with no CLI
entry point here, so when the token is handed to it the driver notifies and waits
for the state file to change. If Antigravity ever grows a headless invocation,
set `builder_command` in config/relay_loop.json and the driver will run it
instead of waiting. That boundary is deliberate and visible rather than
pretended away.

Governance
----------
Two tiers, matching ANTIGRAVITY-RULES.md:

- **Inside a milestone** the loop runs slice to slice with no human friction.
- **At a milestone boundary** it stops dead, pushes to the owner's phone, and
  waits for an explicit word back. This is the anti-drift gate. Thirty
  unreviewed commits is how a build ends up somewhere nobody chose.

Safety
------
- `--max-slices` caps a single run. An autonomous loop with no ceiling is a
  runaway bill.
- No-progress detection: if a spawned session exits without changing the state
  file, the driver stops rather than respawning the same prompt forever.
- Every subprocess is invoked with an argv list. Never `shell=True`, and nothing
  read out of the state file or a feedback file is ever interpolated into a
  shell. Those files are written by another agent and are treated as data.
- `--dry-run` prints what it would spawn and exits.

Usage:
    python tools/relay_loop.py --max-slices 6
    python tools/relay_loop.py --dry-run
    python tools/relay_loop.py --max-slices 1 --interval 15
"""

import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(REPO_ROOT, "RELAY-STATE.json")
FEEDBACK_PATH = os.path.join(REPO_ROOT, "RELAY-FEEDBACK.md")
RULES_PATH = os.path.join(REPO_ROOT, "ANTIGRAVITY-RULES.md")
NOTIFY_PATH = os.path.join(REPO_ROOT, "tools", "relay_notify.py")
CONFIG_PATH = os.path.join(REPO_ROOT, "config", "relay_loop.json")
LOG_PATH = os.path.join(REPO_ROOT, "reports", "relay_loop.log")

#: Where Claude Code lives when it is not on PATH. Checked in order.
CLAUDE_CANDIDATES = [
    os.path.expandvars(r"%APPDATA%\Claude\claude-code\2.1.255\claude.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\claude\claude.exe"),
]

#: Replies from the phone that mean "carry on". relay_notify.py already
#: guarantees only its fixed vocabulary can reach us.
RESUME_WORDS = ("go", "resume")


# --------------------------------------------------------------------------
# small io helpers
# --------------------------------------------------------------------------

def log(line: str) -> None:
    stamp = datetime.datetime.now().strftime("%H:%M:%S")
    msg = f"[relay {stamp}] {line}"
    print(msg, flush=True)
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except OSError:
        pass


def fingerprint(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return hashlib.sha1(f.read()).hexdigest()
    except OSError:
        return "MISSING"


def read_state():
    """(state, error). Exactly one is meaningful."""
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f), None
    except FileNotFoundError:
        return None, "RELAY-STATE.json does not exist"
    except json.JSONDecodeError as e:
        return None, f"RELAY-STATE.json is not valid JSON: {e}"
    except OSError as e:
        return None, f"RELAY-STATE.json could not be read: {e}"


def load_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def find_claude(explicit: str = "") -> str:
    """The Claude Code binary, or '' if it cannot be found."""
    if explicit:
        return explicit if os.path.isfile(explicit) else ""
    on_path = shutil.which("claude")
    if on_path:
        return on_path
    for cand in CLAUDE_CANDIDATES:
        if os.path.isfile(cand):
            return cand
    return ""


def notify(message: str, title: str = "Smart Studio Relay", wait: bool = False,
           timeout: int = 1800) -> str:
    """
    Push one short line to the owner's phone. Returns the reply word when
    `wait` is set, else ''.

    Outbound text is kept boring on purpose - ntfy is a public relay, and
    relay_notify.py truncates to 120 characters regardless.
    """
    argv = [sys.executable, NOTIFY_PATH, "--message", message, "--title", title]
    if wait:
        argv += ["--wait-reply", "--timeout", str(timeout)]
    try:
        proc = subprocess.run(argv, cwd=REPO_ROOT, capture_output=True,
                              text=True, timeout=timeout + 60)
        return (proc.stdout or "").strip().lower()
    except Exception as e:
        log(f"notify failed ({e}); continuing without it")
        return ""


# --------------------------------------------------------------------------
# the prompt handed to each fresh session
# --------------------------------------------------------------------------

def build_reviewer_prompt(state: dict) -> str:
    """
    The whole instruction for one disposable session.

    It is deliberately short. The session reads the durable files itself rather
    than being fed a summary of them - a summary is exactly the lossy step this
    architecture exists to avoid.
    """
    slice_id = state.get("slice", "?")
    slice_title = state.get("slice_title", "")
    branch = state.get("branch", "")
    baseline = state.get("baseline_tests", {}) or {}
    test_cmd = baseline.get("command", "python -m pytest tests/ -q")
    expected = f"{baseline.get('passed', '?')} passed, {baseline.get('xfailed', '?')} xfailed"

    feedback_note = ""
    if os.path.exists(FEEDBACK_PATH):
        feedback_note = (
            "\nRELAY-FEEDBACK.md exists: Antigravity halted with a problem instead of "
            "finishing. Read it first and deal with what it reports before anything else. "
            "Delete it once the problem is resolved.\n"
        )

    return f"""You are the REVIEWER and COMMITTER in an autonomous two-agent relay.
This is a fresh session with no memory of previous slices. Everything you need is on disk.

Read these first, in this order:
  1. ANTIGRAVITY-RULES.md   - standing rules, they bind you too
  2. RELAY-STATE.json       - where the relay is
  3. The brief named in RELAY-STATE.json brief_file
{feedback_note}
Current slice: {slice_id} - {slice_title}
Branch: {branch}
Antigravity has finished building and handed the token back. Its work is uncommitted
in the working tree.

Do this:
  1. Read the diff. Every tests/ change gets read closely - a weakened test, or a test
     that cannot fail, is the failure mode this relay has hit before.
  2. Run the suite yourself: {test_cmd}
     Baseline is {expected}, plus whatever the brief added. Do NOT trust the report's
     numbers; re-run them. Reports here have been accurate on counts and wrong on
     behaviour, in the same document.
  3. Fix what is wrong. If the brief was not met, fix it or say plainly it was not met.
  4. If and only if the suite is green, commit with explicit paths.
     NEVER `git add -A` - it stages ~816 MB including two 310 MB ONNX models.
     Stay on {branch}. Do not push.
  5. Update RELAY-STATE.json: append to history, set baseline_commit to the new commit.
  6. Then decide what happens next:

     - If the milestone still has slices left: write the next brief as
       ANTIGRAVITY-SLICE-<X>.md, set brief_file to it, set ready_for to "ANTIGRAVITY",
       phase to "CLAUDE_BRIEF_READY". The driver hands off automatically.

     - If this slice COMPLETED THE MILESTONE: set phase to "MILESTONE_COMPLETE" and
       ready_for to "OWNER". Do not start the next milestone. The driver will stop and
       ask the owner. This gate is what keeps the build from drifting.

If the suite is red and you cannot fix it: do not commit. Write RELAY-FEEDBACK.md
explaining exactly what is broken, set ready_for to "ANTIGRAVITY", and stop.

Work autonomously. Do not ask for confirmation - nobody is watching this session.
Finish by printing a three-line summary: what landed, the test numbers, what is next."""


# --------------------------------------------------------------------------
# spawning
# --------------------------------------------------------------------------

def run_claude(claude_bin: str, prompt: str, permission_mode: str,
               timeout_s: int, dry_run: bool) -> int:
    """
    One fresh headless Claude session. Returns its exit code.

    The prompt goes in on stdin rather than argv: a brief plus rules runs well
    past the Windows command-line limit, and stdin has no such ceiling.
    """
    argv = [claude_bin, "-p", "--permission-mode", permission_mode]
    if dry_run:
        log(f"DRY RUN would spawn: {' '.join(argv)}")
        log(f"DRY RUN prompt is {len(prompt)} chars; first line: {prompt.splitlines()[0]}")
        return 0

    log(f"spawning fresh Claude session ({len(prompt)} char prompt, mode={permission_mode})")
    try:
        proc = subprocess.run(
            argv,
            cwd=REPO_ROOT,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired:
        log(f"session exceeded {timeout_s}s and was killed")
        return 124
    except Exception as e:
        log(f"could not spawn Claude: {e}")
        return 1

    out = (proc.stdout or "").strip()
    if out:
        log("session said:")
        for line in out.splitlines()[-12:]:
            print(f"    | {line}", flush=True)
    if proc.returncode != 0:
        for line in (proc.stderr or "").strip().splitlines()[-5:]:
            log(f"stderr: {line}")
    return proc.returncode


def run_builder(builder_command, timeout_s, dry_run: bool) -> bool:
    """
    Invoke the builder if one is configured. Returns True if it ran.

    builder_command comes from config/relay_loop.json and must be a LIST of
    argv parts, never a string handed to a shell.
    """
    if not builder_command:
        return False
    if not isinstance(builder_command, list) or not all(isinstance(p, str) for p in builder_command):
        log("builder_command in config/relay_loop.json must be a list of strings; ignoring it")
        return False
    if dry_run:
        log(f"DRY RUN would spawn builder: {' '.join(builder_command)}")
        return True
    log(f"spawning builder: {builder_command[0]}")
    try:
        subprocess.run(builder_command, cwd=REPO_ROOT, timeout=timeout_s)
        return True
    except Exception as e:
        log(f"builder failed: {e}")
        return False


# --------------------------------------------------------------------------
# the gate
# --------------------------------------------------------------------------

def milestone_gate(state: dict, timeout_s: int, dry_run: bool) -> bool:
    """
    Stop at a milestone boundary and wait for the owner.

    Returns True to carry on into the next milestone, False to end the run.
    This is the only place the loop blocks on a human, and it is the whole
    anti-drift guarantee.
    """
    title = state.get("milestone_title") or state.get("slice_title") or "Milestone"
    log("=" * 68)
    log(f"MILESTONE COMPLETE: {title}")
    log("Relay paused. The owner acks before the next milestone starts.")
    log("=" * 68)

    if dry_run:
        log("DRY RUN would wait for owner ack here")
        return False

    reply = notify(
        "Milestone complete. Reply go to start the next milestone.",
        title="Milestone Complete",
        wait=True,
        timeout=timeout_s,
    )
    if reply in RESUME_WORDS:
        log(f"owner replied '{reply}' - continuing into the next milestone")
        return True
    if reply == "stop":
        log("owner replied 'stop' - ending the run")
        return False
    log("no ack before timeout - ending the run. Nothing is lost; state is on disk.")
    return False


# --------------------------------------------------------------------------
# main loop
# --------------------------------------------------------------------------

def main() -> int:
    cfg = load_config()
    ap = argparse.ArgumentParser(description="Autonomous relay driver for Smart Studio.")
    ap.add_argument("--interval", type=float, default=cfg.get("interval", 30.0),
                    help="seconds between state polls while waiting on the builder")
    ap.add_argument("--max-slices", type=int, default=cfg.get("max_slices", 8),
                    help="ceiling on slices in one run; an uncapped loop is a runaway bill")
    ap.add_argument("--session-timeout", type=int, default=cfg.get("session_timeout", 5400),
                    help="seconds a single Claude session may run (default 90 min; suite is ~9)")
    ap.add_argument("--builder-timeout", type=int, default=cfg.get("builder_timeout", 0),
                    help="seconds to wait for a configured builder; 0 means no limit")
    ap.add_argument("--owner-timeout", type=int, default=cfg.get("owner_timeout", 43200),
                    help="seconds to wait for a milestone ack (default 12 h)")
    ap.add_argument("--permission-mode", default=cfg.get("permission_mode", "bypassPermissions"),
                    help="permission mode for spawned sessions")
    ap.add_argument("--claude-bin", default=cfg.get("claude_bin", ""))
    ap.add_argument("--dry-run", action="store_true",
                    help="print what would be spawned and exit")
    args = ap.parse_args()

    claude_bin = find_claude(args.claude_bin)
    if not claude_bin:
        log("could not find the claude binary. Pass --claude-bin, or set claude_bin in "
            "config/relay_loop.json.")
        return 1
    log(f"driver up. claude={claude_bin}")
    log(f"max-slices={args.max_slices} interval={args.interval}s mode={args.permission_mode}")

    builder_command = cfg.get("builder_command")
    if not builder_command:
        log("no builder_command configured - the driver will notify and wait when the "
            "token is with Antigravity.")

    slices_done = 0
    waiting_logged = False
    last_handled_fp = ""

    while slices_done < args.max_slices:
        state, err = read_state()
        if err:
            log(f"BROKEN: {err}")
            notify("Relay broken: state file unreadable.")
            return 1

        ready = str(state.get("ready_for", "")).strip().upper()
        phase = str(state.get("phase", "")).strip().upper()
        state_fp = fingerprint(STATE_PATH)

        # --- milestone boundary --------------------------------------------
        if phase == "MILESTONE_COMPLETE" or ready == "OWNER":
            if milestone_gate(state, args.owner_timeout, args.dry_run):
                # The owner said go. They, or the next session, set the next
                # milestone's first brief; re-read and carry on.
                waiting_logged = False
                last_handled_fp = ""
                time.sleep(args.interval)
                continue
            return 0

        # --- token is with Claude -------------------------------------------
        if ready == "CLAUDE":
            if state_fp == last_handled_fp:
                log("a session just ran and the state file is unchanged - the relay is not "
                    "advancing. Stopping rather than respawning the same prompt.")
                notify("Relay stalled: no progress after a session. Needs a look.")
                return 1

            waiting_logged = False
            slices_done += 1
            log(f"--- slice {slices_done}/{args.max_slices}: token is with Claude "
                f"(slice {state.get('slice', '?')}) ---")
            last_handled_fp = state_fp

            code = run_claude(claude_bin, build_reviewer_prompt(state),
                              args.permission_mode, args.session_timeout, args.dry_run)
            if args.dry_run:
                return 0
            if code != 0:
                log(f"session exited {code}")
                notify(f"Relay: a session exited {code}. Needs a look.")
                return code
            # Fall through: the next poll reads whatever the session wrote.
            time.sleep(2)
            continue

        # --- token is with the builder ---------------------------------------
        if ready == "ANTIGRAVITY":
            if run_builder(builder_command, args.builder_timeout or None, args.dry_run):
                if args.dry_run:
                    return 0
                time.sleep(2)
                continue

            if not waiting_logged:
                brief = state.get("brief_file") or "(no brief_file set)"
                log(f"token is with Antigravity. Brief: {brief}")
                log("waiting for the state file to change. Ctrl+C is safe - state is on disk.")
                notify(f"Slice {state.get('slice', '?')} ready for Antigravity.")
                waiting_logged = True

            # RELAY-FEEDBACK.md appearing is a hand-back even if the state file
            # has not caught up: the builder halted with a problem.
            if os.path.exists(FEEDBACK_PATH):
                log("RELAY-FEEDBACK.md appeared - the builder halted with a problem.")
                notify("Relay: builder halted with a problem.")
                waiting_logged = False
                time.sleep(args.interval)
                continue

            time.sleep(args.interval)
            continue

        log(f"unrecognised ready_for={ready!r}. Stopping rather than guessing.")
        notify("Relay: unrecognised state. Needs a look.")
        return 1

    log(f"reached the {args.max_slices}-slice ceiling for this run. "
        "State is on disk; start the driver again to carry on.")
    notify(f"Relay paused at its {args.max_slices}-slice ceiling.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("interrupted. Nothing is lost - the relay's state is on disk.")
        sys.exit(130)
