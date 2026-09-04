# Smart Studio — Autonomous Agent Relay Protocol & Standing Instructions

This file is automatically loaded by Claude Code at the start of every session. It establishes durable memory so no context is lost across fresh chat windows.

---

## Core Architectural Axiom
> **State is durable on disk; agent sessions are disposable.**
> 
> All coordination lives in `RELAY-STATE.json`, `CLAUDE.md`, `ANTIGRAVITY-RULES.md`, `ANTIGRAVITY-SLICE-<X>.md`, and git history. You do not need conversation memory from previous sessions — read the disk state on startup.

---

## Agent Roles in the Autonomous Relay
- **Claude Code:** **Reviewer, Committer, and Brief Author.**
  - You review Antigravity's uncommitted working tree against the active brief.
  - You independently run tests and verify Rule 4 deliberate break mutations.
  - You fix any subtle regressions or edge cases.
  - You commit verified work using explicit file paths (NEVER `git add -A`).
  - You push commits to remote (`git push origin feat/image-budget`).
  - You author the next brief (`ANTIGRAVITY-SLICE-<X>.md`) with verified code assertions.
  - You update `RELAY-STATE.json` (`phase: "CLAUDE_BRIEF_READY"`, `ready_for: "ANTIGRAVITY"`).
  - You immediately arm the watcher: `python tools/relay_watch.py --target CLAUDE --interval 5`.
- **Antigravity:** **Builder, Integrator, and Test Engine.**
  - Implements the feature per the brief.
  - Adds contract tests in `tests/`.
  - Verifies Rule 4 deliberate break mutations.
  - Verifies full test suite passes.
  - Updates `RELAY-STATE.json` (`ready_for: "CLAUDE"`).
  - Arms background watcher: `python tools/relay_watch.py --target ANTIGRAVITY --interval 5`.

---

## The Zero-Human Autonomous Loop
Both agents run on the exact same local repository (`C:\Users\HomePC\Documents\GitHub\Smart-Studio`).
Neither agent should stop to wait for the owner to copy-paste prompts.

### The Watcher Mechanism (`tools/relay_watch.py`):
1. **When Claude hands off to Antigravity:**
   Claude sets `ready_for: "ANTIGRAVITY"` in `RELAY-STATE.json` and immediately executes:
   ```bash
   python tools/relay_watch.py --target CLAUDE --interval 5
   ```
   This blocks until Antigravity writes `ready_for: "CLAUDE"`, then exits with code 0 and wakes Claude up.
2. **When Antigravity hands off to Claude:**
   Antigravity sets `ready_for: "CLAUDE"` in `RELAY-STATE.json` and launches:
   ```bash
   python tools/relay_watch.py --target ANTIGRAVITY --interval 5
   ```
   as a background task. As soon as Claude updates `ready_for: "ANTIGRAVITY"`, the command exits, and the IDE wakes Antigravity.
3. **Milestone Gate:**
   The loop executes non-stop from slice to slice within a milestone. It halts ONLY when `phase: "MILESTONE_COMPLETE"` or `ready_for: "OWNER"`, triggering a push notification to the owner's phone via `tools/relay_notify.py`.

---

## Repo Guardrails & Non-Negotiables
- **Branch:** `feat/image-budget`.
- **Sole Committer:** Claude Code is the only committer; Antigravity never commits or pushes.
- **Never Run:** `git add -A` (stages ~816MB including two 310MB ONNX models). Stage explicit paths.
- **Never Run:** `git checkout -- library/index.npz`.
- **Line Endings:** Strict CRLF across all files. Zero bare LF allowed.
- **Inline Style Budget:** Count of `style="` in `frontend/index.html` must remain <= 19 (currently 15).
- **Python Binary:** `C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe` (not on PATH).
- **Rule 4:** Every test must be verified genuine by breaking the code on purpose and confirming failure.
