# Brief: commit and push Smart Studio to GitHub

Hand this whole file to Antigravity. Everything it needs is here.

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Remote:** `origin` → https://github.com/smartabdulakeem/S2V.git

---

## Current state (measured, not assumed)

**Branches — `origin` has only `main`. The other two exist ONLY on this laptop.**

```
origin/main  c366472
main         c1a98ec   10 commits ahead of origin/main, never pushed
rebuild/phase-0  cb8c667   41 commits ahead of main  ← all real work is here
docs/niche-visual-type-spec  f31aa4f   1 commit ahead of rebuild/phase-0
```

`main` is an ancestor of `rebuild/phase-0`. Nothing is divergent, nothing needs merging.

**Uncommitted work sits on `rebuild/phase-0`:** 19 modified tracked files, 91 untracked files.
This includes an entire feature (the Voiceover Studio) that has never been committed in any
form: `pipeline/voice_studio.py`, `frontend/voice_studio.js`, `pipeline/sound.py`,
`config/series/motivational.json`.

---

## ⛔ The landmine — read before running anything

**`git add -A` in this repo stages 816 MB across 110 files.** GitHub rejects any single file
over 100 MB. The push will fail, and the blobs will already be in a commit, which means
rewriting history to recover.

The offenders are re-downloadable model weights that are untracked but **not** in `.gitignore`:

| File | Size |
|---|---|
| `config/kokoro_models/kokoro-v1.0.onnx` | 310.5 MB |
| `config/kokoro/kokoro-v1.0.onnx` | 310.5 MB (byte-identical duplicate) |
| `config/kokoro_models/kokoro-v1.0.int8.onnx` | 88.1 MB |
| `config/kokoro_models/voices-v1.0.bin` | 26.9 MB |
| `config/kokoro/voices-v1.0.bin` | 26.9 MB |

**Step 1 below must happen before any `git add`.**

Do not delete either `config/kokoro/` or `config/kokoro_models/` even though they duplicate
each other. `config/kokoro_models/` is the one the app loads. Deletion is the owner's call,
not part of this task.

---

## Step 1 — Extend `.gitignore` first

Append these lines to `.gitignore`. Purely additive; do not remove existing entries.

```
# ── TTS model weights (764MB, re-downloadable, exceed GitHub's 100MB limit) ──
config/kokoro/
config/kokoro_models/

# ── Generated library thumbnails ─────────────────────────────────────────────
library/_thumbnails/

# ── Pre-refactor backups ─────────────────────────────────────────────────────
*.pre-voicestudio

# ── Google Drive sync scratch ────────────────────────────────────────────────
.tmp.driveupload/
```

---

## Step 2 — Stage on `rebuild/phase-0`

```
git checkout rebuild/phase-0
git add -A
```

---

## Step 3 — VERIFY before committing (do not skip)

```
git diff --cached --stat | tail -5
```

Then confirm nothing oversized is staged:

```
git diff --cached --name-only | while read f; do [ -f "$f" ] && stat -c"%s %n" "$f"; done | sort -rn | head -5
```

**Expected:** the largest staged file is roughly 2.4 MB (`library/index.npz`).
**If any file is over 100,000,000 bytes, STOP** — Step 1 was not applied correctly. Run
`git reset` and fix `.gitignore` before trying again.

---

## Step 4 — Commit

```
git commit -m "feat: Voiceover Studio, image pipeline fixes, and performance guardrails"
```

Suggested body, if a longer message is wanted:

```
Adds the Voiceover Studio (Supertonic, Edge-TTS, Google Cloud TTS, Kokoro)
with history, profiles and clip download. Caps Kokoro's ONNX session to two
intra-op threads in both the Studio and the video pipeline, so synthesis
cannot take every core. Fixes the clip download, which opened a folder
picker instead of a save dialog and failed for every engine.

Also carries pending work across the image pipeline, library retrieval,
compositor and front end.
```

---

## Step 5 — Push all three branches

```
git push -u origin rebuild/phase-0
git push -u origin main
git push -u origin docs/niche-visual-type-spec
```

`main` is 10 commits ahead of `origin/main` and fast-forwards cleanly. **No force-push is
needed anywhere. If git asks for `--force`, stop and report back instead** — that means
something unexpected, and forcing would destroy remote history.

---

## Step 6 — Report back exactly this

Paste the raw output of these four commands. Do not summarise them.

```
git log --oneline -3 rebuild/phase-0
git status --short | head -20
git ls-remote --heads origin
git count-objects -vH | grep size-pack
```

Also state:
- the largest file size reported in Step 3
- whether any command required `--force`
- any command that failed, with its exact error text
