# Task for Antigravity — Build the S2V image library

Paste this whole file. Nothing else is needed.

---

## FIRST: stop any fetch you have running

The prompt wording changed. Anything still running is producing outdated images.
Stop it before doing anything else.

---

## What changed and why you are re-running work

Your first six batches (A1–C1) completed correctly — the tool worked, pacing was right,
nothing crashed. But the **prompts were wrong**: they contained no geographic or period
anchor, so 111 of 160 images came back as generic stock scenery — East Asian huts, green
European fields, wrong dress. Six more were corrupt greyscale noise.

That was a defect in the prompt spec, not in your execution.

Both are now fixed:
- Core-theme prompts carry `7th century Arabian Peninsula, early Islamic era, Middle Eastern`
- The fetcher rejects corrupt renders before they reach the library
- `PROMPT_VERSION` bumped to 2, so re-running a batch fetches the corrected version
  instead of skipping it

**A1 A2 A3 B1 B2 B3 C1 must be re-run.** They are included in Stage 1 below.

---

## The command

Run from `C:\Users\HomePC\Documents\GitHub\S2V`:

```bash
python tools/fetch_batches.py <BATCH_IDS>
```

If plain `python` is not on PATH:

```bash
C:\Users\HomePC\AppData\Local\Programs\Python\Python312\python.exe tools/fetch_batches.py <BATCH_IDS>
```

The tool handles downloads, content-hash filenames, deduplication, the manifest,
rate-limit backoff, corrupt-image rejection, and resume. **Do not write your own
downloader.** It is tested and working.

### Downloads go to a review inbox, not straight into the library

New images land in `library/_inbox/`. The operator reviews them as contact sheets and
promotes the good ones into `library/images/` themselves. **You never move files into
`library/images/`, and you never delete anything from `_inbox`.**

Check what you have produced with:

```bash
python tools/promote_inbox.py --stats
```

Report that inbox count after every stage. Promotion is the operator's job, not yours.

---

## STAGE 1 — all free batches (1,275 images)

These use Pollinations and cost nothing. Do all of them, in groups of three so progress
stays visible. Re-runs are free — anything already correct is skipped instantly.

```bash
python tools/fetch_batches.py A1 A2 A3
python tools/fetch_batches.py B1 B2 B3
python tools/fetch_batches.py C1 C2 C3
python tools/fetch_batches.py D1 D2 D3
python tools/fetch_batches.py G1 G2 G3
python tools/fetch_batches.py L1 L2 L3
python tools/fetch_batches.py N1 N2 N3
python tools/fetch_batches.py O1 O2 O3
python tools/fetch_batches.py P1 P2 P3
python tools/fetch_batches.py Q1 Q2 Q3
python tools/fetch_batches.py R1 R2 R3
python tools/fetch_batches.py S1 S2 S3
python tools/fetch_batches.py T1 T2 T3
python tools/fetch_batches.py U1 U2 U3
python tools/fetch_batches.py V1 V2 V3
python tools/fetch_batches.py W1 W2 W3
python tools/fetch_batches.py Z1 Z2 Z3
```

Expect roughly **25 seconds per image**, so about 12 minutes per group of three, and
**8–10 hours total** including rate-limit backoff. That is expected. Let it run.

---

## STAGE 2 — STOP AND ASK

Do **not** start Stage 3 on your own.

When Stage 1 finishes, report back with:

1. Count waiting in `library/_inbox/` (`python tools/promote_inbox.py --stats`)
2. Combined saved / skipped / failed / rejected counts
3. How often rate limiting occurred
4. **A visual spot-check** — open 8 images at random from different batches and describe
   what each actually shows. State plainly whether they look like 7th-century Arabia or
   like generic stock photography. This is the most important thing you report. The last
   round looked fine in the logs and was wrong on screen.

Then wait for a decision before Stage 3.

---

## STAGE 3 — paid batches (775 images, only after approval)

These are human subjects and route to **Google Imagen 4.0, which bills per image**.

```bash
python tools/fetch_batches.py E1 E2 E3
python tools/fetch_batches.py F1 F2 F3
python tools/fetch_batches.py H1 H2 H3
python tools/fetch_batches.py I1 I2 I3
python tools/fetch_batches.py J1 J2 J3
python tools/fetch_batches.py K1 K2 K3
python tools/fetch_batches.py M1 M2 M3
python tools/fetch_batches.py X1 X2 X3
python tools/fetch_batches.py Y1 Y2 Y3
python tools/fetch_batches.py CW1 CW2
python tools/fetch_batches.py MO1 MO2
```

**Hard limit: stop and ask again after 300 Imagen images.** Report the running count
after every group.

---

## Rules

**Only one fetcher at a time.** The operator may also run this tool. Two concurrent
fetchers compete for the same rate limit and both crawl — a recent 4-image test triggered
11 backoffs and the pace widened to 45 seconds. Confirm nothing else is running before
you start.

**Never raise `--workers` above 2.** The default is 2 workers, 1 second apart, widening
automatically on HTTP 429. This is deliberate. If you hit repeated throttling, go slower:

```bash
python tools/fetch_batches.py A1 A2 --workers 1 --delay 5
```

**Check state before a run:**

```bash
ls library/images | wc -l
wc -l library/manifest.jsonl
grep -c '"batch": "A1"' library/manifest.jsonl
```

---

## If something fails

| Symptom | Do this |
|---|---|
| A few `FAILED` lines | Normal. Re-run the same command. |
| `REJECT` lines | Working as intended — a corrupt render was caught. It retries on re-run. |
| Repeated rate limiting | `--workers 1 --delay 5` |
| `unknown batch id` | Run `--list` and use an exact id |
| `ModuleNotFoundError` | `python -m pip install requests pillow numpy` |
| Script crashes outright | A bug. Report the traceback. Do not work around it. |

---

## Do not

- Do not write a new download script
- Do not edit `tools/taxonomy.py` — batch ids come from a fixed shuffle seed, and changing
  it silently repoints every id at different prompts
- Do not raise worker counts to go faster
- Do not run `--all` in one shot; work in the groups above so problems surface early
- Do not start Stage 3 without approval
- Do not touch `pipeline/`, `app.py`, `frontend/`, or `config/settings.json`
- Do not delete anything from `library/images/`, `library/_inbox/`, or `library/_rejected/`
- Do not run `tools/promote_inbox.py` without `--stats` — promoting is the operator's call
