# Antigravity brief — the image budget

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** create `feat/image-budget` off `rebuild/phase-0`.
**Python:** `C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe` (not on PATH).
Prefix any command that prints a prompt with `PYTHONIOENCODING=utf-8`.

**Green baseline before you start: `313 passed, 2 skipped, 1 xfailed`.** The 2 skips are
`test_composer.py` needing a cached segment and are expected. Do not finish below this.

---

## The bug

The owner pastes a 2,000-word script. The board lands showing **44 shots**. Every attempt to
*reduce* the count *raises* it. The target — 25 to 35 images — cannot be reached at any setting.

Why: at parse time each segment gets exactly one shot (`pipeline/text_parser.py:836`). 44 segments
means 44 shots. Then `apply_shot_rhythm` (`pipeline/text_parser.py:162`) runs, per segment:

```python
wanted = max(1, int(round(est_seconds / seconds_per_shot))) if est_seconds else 1
```

`max(1, …)` is applied **per segment**, so the total can never fall below the segment count.
The segment count is a hard floor. Measured on a 44-segment, 2,000-word script:

| slider | seconds/shot | total shots |
|---|---|---|
| 1 | 3s | 256 |
| 2 | 5s | 152 |
| 3 | 7s | 107 |
| 4 | 9s | 83 |
| 5 | 12s | 64 |
| — | 30s | 44 ← floor |
| — | 60s | 44 ← floor |

The slider (`RHYTHM_SECONDS = {1:3, 2:5, 3:7, 4:9, 5:12}`, `frontend/app.js:1062`) spans 64–256.
Its whole range sits **above** the 44 the board landed on, so every move looks like an increase.

## What to build

Replace "shot rhythm" as the primary control with a **direct image count** the user types. The app
then works towards that number exactly.

This app is being launched for other users, not just the owner. The control must be
self-explanatory without a manual.

---

## Task 1 — `plan_image_budget` in `pipeline/text_parser.py`

New function beside `apply_shot_rhythm`. **Do not delete `apply_shot_rhythm`** — other call sites
and tests use it.

```python
def plan_image_budget(script_data: dict, image_count: int) -> dict:
    """
    Re-cut the whole script so it uses exactly image_count images.

    Unlike apply_shot_rhythm, which floors at one shot per segment, this plans
    across the whole script: when fewer images are asked for than there are
    segments, a run of consecutive segments shares one image.

    Returns {"images_before": int, "images_after": int, "segments": int,
             "shared_runs": int}.
    """
```

### Rules — follow exactly

Let `N = image_count`, clamped to `1 <= N <= 500`. Let `S` = number of segments.

Estimate each segment's seconds as `len(narration.split()) / WORDS_PER_SECOND` (2.6, already
defined at `pipeline/text_parser.py:121`).

**Case A — `N >= S` (split segments, as today).**
Distribute N across segments **proportional to each segment's duration**, not evenly, with every
segment getting at least 1. Use largest-remainder so the total is *exactly* N:

1. `raw[i] = N * seg_seconds[i] / total_seconds`
2. `base[i] = max(1, floor(raw[i]))`
3. While `sum(base) > N`: decrement the largest `base[i]` that is `> 1`.
4. While `sum(base) < N`: increment the `base[i]` with the largest fractional remainder.
5. Call the existing `split_narration_for_shots(narration, base[i])` per segment.

**Case B — `N < S` (share images across segments).**
Group consecutive segments into exactly N runs of roughly equal total duration (greedy: walk
segments accumulating seconds, close a run when it reaches `total_seconds / N`, and never leave
fewer runs than remaining segments allow). Then:

- Every segment in a run gets **exactly one shot**.
- Every shot in that run carries the **same `query`**, derived from the **concatenated narration
  of the whole run** via `extract_keyword`.
- Every shot in a run after the first gets a new key **`"share_with": "<shot_id of the run's first shot>"`**.
  The first shot of a run has `share_with: None`.
- Set **`"run_index": <0-based run number>`** and **`"run_position": <0-based position within the run>`**
  on every shot. The renderer will need these; do not omit them.

`share_with` is what makes one image cover several segments: the resolver reuses the first shot's
resolved image for the rest of the run instead of searching again.

**Both cases:** preserve the existing pin carry-over behaviour from `apply_shot_rhythm` (the
`carried` list — a user's deliberate pin on the first shot survives a re-plan), and keep emitting
the `scene` key (the slice of narration a shot covers) — without it every shot in a segment shares
one prompt.

### Edge cases that must work

- `N == 1` — one image for the entire script, one run, every segment one shot, all sharing.
- `N == S` — exactly one image per segment, no sharing, no splitting.
- A segment with empty narration — counts as 0 seconds, still gets its 1 shot.
- A single-segment script with `N == 10` — 10 shots in that one segment.
- `N` larger than the sentence count — `split_narration_for_shots` already handles this; don't
  duplicate its logic.

**`images_after` must equal `N` in every case.** This is the acceptance test.

---

## Task 2 — resolver honours `share_with`

Find where shots are resolved to images (`pipeline/library.py`, the `plan_shots` path — grep
`resolved_score`). When a shot carries `share_with`, it must **not** run its own library search.
It copies `resolved`, `resolved_score`, and `source` from the referenced shot.

This is the point of the feature: 3 images across 44 segments means **3 searches, not 44**. Getting
this wrong means the owner still waits for 44 searches and still gets 44 different pictures.

If the referenced shot failed to resolve, the sharing shot falls back to its own search — never
leave it blank.

---

## Task 3 — the planning-board control

In `frontend/index.html`, in the storyboard pane (`data-pane="board"`, line 169), replace the
`shot-rhythm-slider` row with a number input:

```
How many images?  [ 31 ]   ~2,000 words · 12.8 min · about 25s per image
```

- `<input type="number" id="image-count" min="1" max="500">`
- The hint text updates live as the user types: word count, estimated runtime, and the resulting
  seconds-per-image (`est_seconds / N`). Recompute on `input`, not only on `change`.
- On load, prefill with the **suggested** count: `max(1, round(est_seconds / 25))`. One image per
  25 seconds. For reference: 500 words → 8, 1,000 → 15, 2,000 → 31, 3,500 → 54, 5,000 → 77.
- Add a short line under the input, always visible:
  *"Fewer images means each one is held longer with a slow pan. One image can carry a whole script."*
- Apply on blur or Enter, not on every keystroke — re-planning is not free.

**Keep the rhythm slider** as a secondary control, relabelled and placed after the number input.
Changing the slider updates the number input to the count that rhythm implies, and vice versa;
they must never disagree on screen. This is the owner's "it might adjust it using the adjustment
thing in the planning board".

### The trap that will bite you

Setting `.value` in JS fires no `change` event. If you set the number input from the slider handler
(or the reverse) and rely on an event to sync the other, they will silently desync. Call the update
function directly. This exact bug already cost this repo a feature once — see trap 3 in
`HANDOFF-IMAGE-PROMPTS.md`.

---

## Task 4 — the API method

In `app.py`, beside `set_shot_rhythm` (line 551), add:

```python
def set_image_count(self, script_data: dict, image_count: int) -> dict:
```

Mirror `set_shot_rhythm`'s structure exactly — same error handling, same return shape, same
persistence of the preference. Persist as `image_count` in the same place `shot_rhythm_seconds`
is persisted (`app.py:334`). Leave `set_shot_rhythm` in place and working.

---

## Task 5 — tests

New file `tests/test_image_budget.py`. Cover, at minimum:

1. `N > S`, `N == S`, `N < S`, `N == 1` — **`images_after == N` in every one.**
2. `N < S` produces exactly N distinct `query` values, and every non-first shot in a run has
   `share_with` pointing at its run's first shot.
3. A pinned first shot survives a re-plan at a different N.
4. Segment durations drive the distribution: a segment twice as long as another gets roughly twice
   the images when `N > S`.
5. The resolver reuses the shared image — a run of 5 segments triggers **one** search, not 5.
   Mock the search so you can count calls.

---

## Do not touch

- `pipeline/composer.py` — the renderer. Motion continuity across a shared image is being handled
  separately; leave it alone entirely.
- `pipeline/prompt_slots.py`, `BRIEF_OPENERS`, `world_anchor` handling, or anything in
  `pipeline/library.py` other than the `share_with` resolver change in Task 2. Two other fixes are
  in flight there and will conflict.
- The `style_presets` / `visual_type` machinery.

---

## Report back with

1. The exact final pytest line.
2. `images_after == N` demonstrated for N = 1, 5, 31, 44, 100 on a real 44-segment script — paste
   the actual numbers, not a claim that it works.
3. The search-call count for a 44-segment script at N = 3. It must be 3.
4. Anything you changed beyond this brief, and why.
5. Any command that failed, even if you recovered.

Claims of "verified" without pasted output will be rejected on review. A previous report described
interactive behaviour as "Passed" when nothing had been run.
