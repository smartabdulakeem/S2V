# Smart Studio — Strategic Architecture Revision & 3-Stage Workflow Blueprint

This document records the owner's strategic decisions regarding the front-end redesign, the WolfCut licensing review, the 15-picture pacing validation, and the refined **3-Stage Production Pipeline** (Script → Storyboard → Timeline).

---

## 1. Executive Alignment & Findings Accepted

1. **WolfCut / Concat Licensing:** Accepted. Building our native Python/JS timeline with track layouts, audio waveforms, and playheads carries zero copyright or patent obligations. The existing pinned `.wolfcut` exporter remains an optional secondary feature.
2. **The 15-Picture Validation (Task 13 / `ACCEPTANCE-FINDINGS.md`):** Accepted. The mathematical proof that 15 pictures starves only 13% of spans (vs. 78% starved at 60 pictures) vindicates the owner's storytelling instinct. The pacing target is locked at 10–20 pictures for documentary films.
3. **Audio-First Order of Operations:** Confirmed. Measuring real audio (`Measure Narration` via Kokoro/Piper + `ffprobe`) precedes final boundary planning so all 15 scene cuts snap to 100% measured speech timestamps.

---

## 2. The 3-Stage Studio Pipeline (Closing the Production Gap)

After analyzing whether to merge the Storyboard directly into the Timeline, the owner identified a critical real-world workflow requirement: **when a script is first planned, the image files do not exist yet.**

Opening a timeline full of 15 blank placeholder blocks creates unnecessary friction for prompt copying and image generation. Therefore, the app maintains **three distinct, highly specialized stages**:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ STAGE 1: SCRIPT SCREEN (Text & Narration)                                   │
│ • Write/paste narration text.                                               │
│ • Select Voice Actor & Series Style Preset.                                 │
│ • Click [ "Measure Narration" ] → Generates audio & exact timestamps.       │
│ • Click [ "Next: Storyboard" ]                                              │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STAGE 2: STORYBOARD SCREEN (The Visual & Image Generation Hub)              │
│ • AI displays the 15 clean scene cards with exact timecodes & prompts.      │
│ • Click [ "📋 Export 15 Prompts for Flux" ] (1-click copy for AI generator).│
│ • Generate images in Flux → Click [ "📁 Drop Image Folder" ] / Auto-match.  │
│ • Bulk visual review: inspect all 15 images side-by-side; swap any weak one.│
│ • Click [ "➡️ Open in Timeline" ]                                            │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ STAGE 3: TIMELINE SCREEN (Playback, Assembly & Render)                      │
│ • Video Preview Player + 4 synchronized tracks (Pictures, Voice, Captions,  │
│   Music/SFX).                                                               │
│ • Press [ ▶ Play ] to watch the film in real-time with full audio sync.     │
│ • Fine-tune clip boundaries by dragging edges while listening.              │
│ • Balance background music / sound effects.                                 │
│ • Click [ 🚀 RENDER FILM ]                                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Slice A — Button Audit & Streamlining Protocol

The application currently has **92 buttons** across 7 screens. 

### The Core Principle:
> *"Do not remove what is genuinely needed, and do not keep what is redundant or obsolete."*

### Protocol for Claude in Slice A:
Before modifying or deleting any button:
1. Claude will generate a comprehensive **Keep / Kill / Move Inventory** covering all 92 buttons across each screen.
2. For each button, the inventory will state in one line:
   * **Action:** `KEEP` / `KILL` / `MOVE`
   * **Screen & Button Name**
   * **Exact Purpose / Rationale**
3. **The owner will review and approve this inventory before any button is removed from code.**

---

## 4. Execution Roadmap (Slices A through F)

* **Slice A — Button Inventory & Storyboard Streamlining:** Present the 92-button Keep/Kill/Move audit; streamline the Storyboard to the essential 4 master actions (`Auto/Exact`, `Export Prompts`, `Import Folder/Library Match`, `Open Timeline`).
* **Slice B — Camera Motion & Window Dimensions:** Add the motion amount slider in Settings (scaling travel percentages) and persist window dimensions between launches.
* **Slice C — Audio-First Execution:** Run `Measure Narration` across all 347 lines on `Before Adam` to establish real millisecond boundaries.
* **Slice D — Timeline Playback:** Wire the audio engine to drive the playhead, waveform, and real-time visual preview on the Timeline screen.
* **Slice E — Interactive Boundary Adjustment:** Enable dragging clip boundaries on the timeline while listening, without triggering a re-plan.
* **Slice F — Music & Sound Effects Tracks:** Enable background music and SFX tracks under the narration track.

---

## 5. Invitation for Claude's Strategic Input

Claude is invited to review this 3-Stage blueprint and share his technical assessment:
* How he plans to structure the **Keep/Kill/Move** inventory in Slice A.
* Any technical nuances or recommendations for connecting the Storyboard hand-off cleanly into the Timeline player (Slice D).