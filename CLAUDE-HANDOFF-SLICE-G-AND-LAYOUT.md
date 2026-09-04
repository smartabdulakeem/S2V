# HANDOFF BRIEF FOR CLAUDE CODE: SLICE G & TIMELINE STUDIO LAYOUT FIX

**Date:** 2026-09-04
**Target Agent:** Claude Code (Reviewer & Committer)
**Author:** Antigravity (Project Manager & Verifier)
**Branch:** feat/image-budget
**Working Tree State:** Clean, tested changes uncommitted in working tree
**Baseline Suite:** 1258 passed, 1 xfailed, 0 failures (up from 1249)

---

## 1. Executive Summary

This handoff packages two critical achievements ready for your review, verification, and commit:
1. **Slice G (Audio Sync & Playback Fidelity):** Implemented real-time sound effects scheduling in tlAnimLoop, pure linear music fade-in/fade-out in musicGainAt, and 0.25s deadband music clock drift resyncing in checkMusicDrift.
2. **Timeline Transport & Studio Layout Fix:** Diagnosed and fixed the critical visual overlap bug reported by the owner (where adding sound effects or music tracks occluded #btn-tl-play). Upgraded the Timeline to a true professional NLE fixed-viewport workstation (height: 100%; overflow: hidden), anchored the transport bar with dedicated brass play button styling, and eliminated page-level vertical scrollbar blowout.

All 31 targeted tests in tests/test_music_and_sfx.py and tests/test_frontend_controls.py pass. Zero bare \n line endings (strict CRLF verified).

---

## 2. Changes Made in Working Tree

### A. Audio Sync Engine (frontend/app.js)
- **Job 1 (SFX Scheduler):**
  - Added sfxAudioPool caching preloaded HTMLAudioElements resolved via the local media server.
  - Built sorted schedule {filmTime, name, src} computed once when playback begins or effects change (buildSfxSchedule).
  - Added frame-crossing detection in tlAnimLoop that fires effects exactly once at their scheduled timestamp.
  - Implemented seeking/scrubbing machine-gun guard: resets cursor on seek without triggering past audio.
  - Added in-flight pause handler: pausing narration immediately halts active sound effects.
  - Removed outdated disclaimer: "Sound effects will be heard in the final render".
- **Job 2 (Honest Music Fades):**
  - Added musicGainAt(filmTime, totalSeconds, project) implementing pure linear fade-in and fade-out matching ffmpeg afade.
  - Unified all flat-volume sites (L2389, L2403, L3264) to call musicGainAt.
- **Job 3 (Clock Drift Resynchronization):**
  - Added checkMusicDrift(narrationTime, musicAudio, musicDuration) inside tlAnimLoop.
  - Resyncs music to narrationTime % musicDuration only when drift exceeds the 0.25s deadband, preventing audible stutter.

### B. Timeline Studio Layout & Transport Bar Anchoring (frontend/style.css)
- **Bug Root Cause:** .pane had overflow-y: auto. The rigid aspect-ratio: 16/9 on .tl-frame pushed .tl-transport down as .tl-tracks expanded (from 150px to 202px+ when Music & SFX lanes were added). .tl-tracks painted directly on top of #btn-tl-play (isCoveredByTracks: true), occluding the bottom 11-40px of the transport bar.
- **NLE Studio Redesign:**
  - .pane[data-pane="timeline"]: overflow: hidden; height: 100%; display: flex; flex-direction: column; gap: 10px; padding: 12px 16px;.
  - .tl-top: flex: 1 1 0%; min-height: 180px; overflow: hidden; with grid-template-columns: 1fr 310px;.
  - .tl-preview: height: 100%; min-height: 0; overflow: hidden;.
  - .tl-frame: Flexible flex: 1 1 0%; min-height: 0; max-height: 100%; with img { max-width: 100%; max-height: 100%; object-fit: contain; }. The preview dynamically adapts to fill available vertical space without pushing sibling controls down.
  - .tl-transport: flex-shrink: 0; background: var(--surface-2); border: 1px solid var(--line); padding: 6px 12px;.
  - #btn-tl-play: Styled with brass accent (color: var(--brass); border-color: var(--brass); font-weight: 600; min-width: 46px;).
  - .tl-tracks: flex-shrink: 0; permanently anchored below the transport bar with guaranteed 10px spacing.
- **Live DOM Verification:** Measured in live WebView2 DOM: isPlayCovered: false, gapBetweenTransportAndTracks: 10px, paneScrollTop: 0, paneScrollHeight == paneClientHeight (zero page scrollbar).

### C. Automated Tests
- tests/test_music_and_sfx.py: 8 contract tests added for Slice G + Claude's 9th midpoint seek test.
- tests/test_frontend_controls.py: Added test_timeline_transport_and_tracks_do_not_overlap regression test.

---

## 3. Instructions for Claude Code

Please execute the following review, test, commit, and handoff sequence:

### Step 1: Review Working Tree Diff
Verify the changes in:
- frontend/app.js
- frontend/style.css
- tests/test_music_and_sfx.py
- tests/test_frontend_controls.py
- RELAY-STATE.json

### Step 2: Run Independent Verification
Execute the test command to verify the suite:
`powershell
C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe -m pytest tests/test_music_and_sfx.py tests/test_frontend_controls.py -q
`
Expected: 31 passed in ~12 seconds.
(Full suite baseline: 1258 passed, 1 xfailed, 0 failures.)

### Step 3: Git Commit (Sole Committer Rule)
Stage explicit files (NEVER use git add -A):
`powershell
git add frontend/app.js frontend/style.css tests/test_music_and_sfx.py tests/test_frontend_controls.py tools/relay_loop.py ANTIGRAVITY-SLICE-G.md ANTIGRAVITY-RULES.md RELAY-STATE.json RELAY-HANDOFF.md reports/verification_gate/gate_results.json
git commit -m "feat(timeline): slice G - audio sync, honest fades & studio transport fix"
`

### Step 4: Advance the Milestone
Decide the next slice for Milestone 2:
- **Option A (Final Milestone 2 Slice):** Formulate ANTIGRAVITY-SLICE-H.md targeting Caption lane timing and picture-change accuracy against live audio clock during real-time playback. Set brief_file: "ANTIGRAVITY-SLICE-H.md", ready_for: "ANTIGRAVITY", and phase: "CLAUDE_BRIEF_READY" in RELAY-STATE.json.
- **Option B (Milestone 2 Complete):** If caption and picture boundary timing are verified frame-accurate against audio.currentTime, advance phase to "MILESTONE_COMPLETE" and ready_for to "OWNER" for phone sign-off before Milestone 3.
