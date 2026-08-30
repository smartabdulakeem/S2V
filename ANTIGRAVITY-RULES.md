# Standing rules for Antigravity

Every brief in this repo inherits these. They do not need repeating inside a brief, but a brief may
add to them.

---

## Stop when the report is written

**Do not commit. Do not push. Do not keep working after the report.**

Leave the work in the working tree and stop. The report is the end of the task. Claude reviews the
working tree against the brief, fixes what is wrong, and commits once it is clean.

This exists because on 30 Aug two agents edited `pipeline/wolfcut_export.py` inside the same ninety
seconds — one function was rewritten three times, one edit was rejected outright, and
`pipeline/text_parser.py` was changed outside the brief to make a failing test pass. Nobody could
say what the file contained. Work that has stopped can be reviewed. Work still moving cannot.

## Never change production code to make a test pass

If a test fails, the first question is whether the test is wrong. On the same day, a test failed
because it resolved images *before* `plan_image_budget` — an order the app never runs in. The fix
was one line in the test. What was written instead was a change to `plan_image_budget` itself,
altering committed behaviour that another test covers.

Change the code when the code is wrong. Say so in the report either way.

## Never weaken a test

The vignette limit was once raised from 0.40 to 0.45 and reported as "passes cleanly". Every
`tests/` diff is read. If an existing test must change, quote it before and after and justify it in
one sentence.

## A test that cannot fail is worse than no test

Two shapes to avoid, both real:

- **Asserting something the code under test just created.** The WolfCut exporter wrote zero-byte
  files so its guessed paths would exist, and its test asserted that every media path exists. It
  passed, and the export was broken.
- **`assert A or B` across both possible outcomes.** `endswith(f"{n}.jpg") or shot_id in path`
  passes whichever branch runs. So does `assert "installed" in result`.

Assert the specific thing: this clip points at *this file*. Then break the code on purpose and
confirm the test fails.

## Report what you did not do

A skipped acceptance check must be named as skipped. The WolfCut brief required a screenshot of the
exported file open in WolfCut; the report did not mention it, and the twelve blank frames it would
have shown went unnoticed until review.

"I could not do X because Y" is a good report. Silence is not.

## Numbers in a report are checked

Every count, every test total, every "verified" is re-run against the code. Reports have been
accurate on test counts and wrong on what the code does, in the same document. Paste real output,
not a description of it.

---

## Repo rules

- **Branch:** `feat/image-budget`. Stay on it.
- **Never** run `git add -A` — it stages ~816 MB including two 310 MB ONNX models. Stage explicit paths.
- **Never** run `git checkout -- library/index.npz`. If it shows as modified, leave it; say so in the report.
- **Do not work in a git worktree** — no gitignored assets, so render tests always fail there.
- **`config/settings.json` is gitignored and holds live API keys.** Never print it, never commit it,
  never paste its contents into a report.
- **A stale `cache/` causes phantom failures.** Tests touching `describe_shots` must patch
  `_load_disk_cache` / `_save_disk_cache` rather than read the real `cache/planning/`.
- **The shot cache key is `v9`** (`composer.py`). If what a shot renders can change, bump it.
- **Inline `style="` in `index.html` is capped at 19** and is currently at 19, all dynamic state.
  Layout goes in `style.css`.
- **Full suite is ~8 minutes.** Current baseline: **507 passed, 1 xfailed, 0 failures**.
- Python is not on PATH: `C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe`.
  Prefix anything printing prompt text with `PYTHONIOENCODING=utf-8`.
