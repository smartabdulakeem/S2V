# Brief: licence cleanup — the app has to be legal to sell

Hand this whole file to Antigravity.

**Read `ANTIGRAVITY-RULES.md` first — its standing rules apply.**

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget`. **Do not commit. Do not push.**
**Baseline:** 687 passed, 1 xfailed, 0 failures.

---

## What this is for

The owner is going to sell Smart Studio on a subscription. It cannot be sold as it stands: three
GPL-licensed components are bundled or imported, and the worst of them is imported directly into
the Python process.

**The decision is already made and is not open for re-litigation in this task:** edge-tts goes,
Piper goes, and **Kokoro and Supertonic do the voice work**. Both are already wired, already
enabled, and the owner's own film already narrates with `local:kokoro-bm_george`.

Four facts, verified in the code today. Do not re-derive them, but do not contradict them either —
if you find one to be false, **stop and report it** rather than working around it.

1. **`vendor/` is gitignored and untracked.** `git ls-files vendor/` returns nothing. So deleting
   files there is a local and packaging change, not a repo change, and will not show in `git diff`.
   Say what you deleted in the report, because the diff cannot.
2. **`piper.exe` is never invoked.** No `.py` file outside `tests/` references it. `local:piper`
   and `piper:` voice ids already route to Supertonic at `pipeline/voiceover.py:975-978`.
3. **edge-tts is the catch-all.** `pipeline/voiceover.py:1040` is a bare `else:` — every voice id
   that is not Google, Gemini, Supertonic or Kokoro falls through to Edge.
4. **`config/voices.json` holds 58 voices, 12 enabled, of which 2 are Edge** —
   `edge:en-US-GuyNeural` and `edge:en-AU-WilliamNeural`.

---

## Job 1 — remove edge-tts

It is **GPL-3.0** and it is brought in with `import edge_tts` at `pipeline/voiceover.py:585`. That
is linking, which makes all of Smart Studio a derivative work. It also calls a private Microsoft
endpoint that Microsoft never published, so it can stop working without notice.

- Remove `edge-tts>=6.1.9` from `requirements.txt`.
- Delete `_edge_tts_async` (~L584) and `_generate_with_edge_tts` (~L592).
- Delete the "Edge Neural" engine block from `config/voices.json` — all 12 voices.
- Update the module docstring at the top of `voiceover.py`, which currently names
  `"edge:<Name>"` as the default fallback. It must no longer say that.

**The catch-all must not disappear — it must change destination.** Rewrite the `else:` branch at
~L1040 so an unrecognised voice routes to Kokoro. Pick one existing enabled Kokoro voice as the
fallback and name it in a module-level constant, e.g.:

```python
#: Where a voice id we no longer recognise is sent. Kokoro is local, Apache-2.0,
#: and always present, so this can never fail for want of a key or a network.
FALLBACK_VOICE = "local:kokoro-bm_george"
```

The legacy `gemini:` mapping in that same branch currently rewrites to `edge:en-US-GuyNeural`. It
must map to `FALLBACK_VOICE` instead.

**Migration matters here.** The owner has Edge voices enabled in his settings today, and saved
projects may carry `edge:` ids. An `edge:` id must **quietly resolve to `FALLBACK_VOICE` and
render**, not raise and not produce a zero-byte file. A person who saved a project last week must
be able to open it this week.

## Job 2 — delete `vendor/piper/`

`espeak-ng.dll` inside it is **GPL-3.0**. Piper itself is MIT, but the DLL travels with it.

Before deleting, **prove fact 2 above for yourself** and paste the command and its output:

```bash
grep -rn "piper.exe\|vendor/piper" --include=*.py . | grep -v "^./tests"
```

If that returns anything at all, stop and report. If it is empty, delete the whole
`vendor/piper/` folder — `piper.exe`, `espeak-ng.dll`, `piper_phonemize.dll`, `onnxruntime.dll`,
`onnxruntime_providers_shared.dll`, `libtashkeel_model.ort`, `espeak-ng-data/` and `voices/`.

**Leave the `local:piper` and `piper:` prefixes in the `is_supertonic` test alone.** They are the
migration path for anyone who saved a Piper voice, and they already point at Supertonic, which is
correct.

## Job 3 — three files in `vendor/realesrgan/` that must not ship

- **`vcomp140d.dll`** — the *debug* build of Microsoft's OpenMP runtime. The trailing `d` is what
  marks it. Microsoft's redistributable terms permit the release DLL and **forbid** the debug one.
  Delete it. **Keep `vcomp140.dll`.**
- **`onepiece_demo.mp4`** — copyrighted anime footage that ships inside the Real-ESRGAN release and
  has nothing to do with this app. Delete.
- **`input.jpg`, `input2.jpg`** — sample images from the same release. Delete.

Confirm no `.py` file references any of the four before deleting, and paste that check.

## Job 4 — `THIRD-PARTY-NOTICES.txt`

**This applies to the components that are otherwise fine.** BSD, MIT and Apache all permit
commercial use on one condition: ship their licence text and copyright line. There is currently no
file named LICENSE, COPYING or NOTICE anywhere in `vendor/`, so the app is out of compliance even
with the permissive licences.

Create `THIRD-PARTY-NOTICES.txt` in the repo root. One section per component: name, version where
known, licence name, copyright line, and the full licence text. Cover at least:

| Component | Licence |
|---|---|
| moviepy, Pillow, openai-whisper, open-clip-torch, CLIP ViT-B-32 weights | MIT / MIT-CMU |
| requests, rapidocr-onnxruntime, kokoro-onnx | Apache-2.0 |
| pywebview, numpy, scipy, torch, Real-ESRGAN, ncnn | BSD-3-Clause |
| onnxruntime | MIT |
| PyInstaller | GPL-2.0 **with the bootloader exception** — note the exception explicitly, it is what makes shipping a proprietary app legal |
| Supertonic — code | MIT |
| Supertonic — **model weights** | **OpenRAIL-M** |
| Microsoft Visual C++ runtime (`vcomp140.dll`) | Microsoft redistributable terms |

**Supertonic's weights need more than a listing.** OpenRAIL-M permits commercial use but
**requires attribution** and requires the use restrictions — no impersonation without consent, no
harmful use — to be **passed on to end users**. Put the attribution in this file and add a
`TODO(owner): EULA clause` comment beside it. Do not attempt to write the EULA; that is the owner's.

Read each licence from the project itself rather than reciting it from memory. Where you cannot
find an authoritative text, say so in the report rather than inventing one.

---

## Tests

Add `tests/test_licence_cleanup.py`:

1. **edge-tts is gone.** `requirements.txt` contains no `edge-tts`; no `.py` file under `pipeline/`
   or `app.py` contains `edge_tts`; `config/voices.json` contains no id starting `edge:`.
2. **An unknown voice still renders.** Call the routing with a voice id like `"nonsense:whatever"`
   and assert Kokoro is the engine reached — patch the Kokoro generator and assert it was called.
   **Do not** assert merely that no exception was raised; that passes if nothing happens at all.
3. **A saved Edge voice migrates.** A project carrying `edge:en-US-GuyNeural` resolves to
   `FALLBACK_VOICE` and reaches Kokoro. This is the owner's real upgrade path.
4. **A legacy `gemini:` voice migrates** to `FALLBACK_VOICE`, not to anything Edge.
5. **The notices file exists** and names every component in the Job 4 table.

For tests 2–4, **break the code on purpose once** — point the fallback at a non-existent engine —
and confirm each test fails. Paste that. A test that passes either way is worse than no test.

## Traps

1. `config/voices.json` is a list of engine blocks, each with a `voices` array. Removing the Edge
   block means removing one whole element, not editing ids.
2. **`config/settings.json` is gitignored and holds live API keys.** Never print or commit it. But
   the owner's *enabled voices* may live there — check how enablement is persisted, and if a
   removed Edge voice is stored as enabled, make sure the Settings screen does not break on load.
3. Repo files are **CRLF**. Check byte counts before and after; a whole-file line-ending flip makes
   the diff unreviewable and will be sent back.
4. Do not touch `pipeline/composer.py`, the shot cache key, or anything to do with rendering.
5. Do not "helpfully" remove other dependencies. Only edge-tts goes.

## Explicitly NOT in this brief

- **ffmpeg.** `vendor/ffmpeg/bin/` is a GPL-3 build and it is a real blocker, but the fix is a
  packaging decision the owner has not made yet: either stop bundling it and have the app use an
  ffmpeg the user installs, or move to an LGPL build and lose `libx264`/`libx265`. **Leave
  `vendor/ffmpeg/` exactly as it is.** Do not delete it, do not swap it, do not add a downloader.
- The EULA, the licence key check, and anything to do with payment or Paystack.
- `library/`, `assets/` and `skills/` — the image library has its own copyright questions and they
  are not part of this task.

## What to report

1. The `grep` proving `piper.exe` is unreferenced, pasted with its output.
2. The same for the four Real-ESRGAN files.
3. Every file you deleted under `vendor/`, by full path — the diff cannot show these.
4. The new `else:` branch in `voiceover.py`, pasted.
5. Tests 2–4 failing when you break the fallback on purpose, then passing. Paste both.
6. The full suite: `pytest tests/ -q`. Baseline 687 passed, 1 xfailed.
7. Anything you could not do, and why. Silence is not a report.
