# Brief: make the Timeline actually play in the desktop app

Hand this whole file to Antigravity.

**Read `ANTIGRAVITY-RULES.md` first — its standing rules apply.**

**Repo:** `C:\Users\HomePC\Documents\GitHub\Smart-Studio`
**Branch:** `feat/image-budget`. **Do not commit. Do not push.**
**Baseline:** 698 passed + the new WolfCut export tests, 1 xfailed, 0 failures.

---

## The bug, and why it happened

Slice D built playback and it works in the dev server. **In the real desktop app it does nothing.**

The cause is already documented in this repo, at `app.py` ~L405:

> `file://` URLs are refused as subresources by the WebView2 control that hosts this page, so every
> thumbnail rendered as a broken-image icon. Embedding the bytes sidesteps the protocol entirely.

Slice D set the audio source with `pathlib.Path(abs_path).as_uri()`, which produces
`file:///C:/...`. WebView2 refuses it. That is the whole bug.

**Do not fix this with base64.** That is why every *image* in this app is a data URI, and it is the
right answer for a 40 KB thumbnail. The owner's narration track is **27.8 MB**, which is roughly
37 MB base64, pushed through the JS bridge on every play. It also makes seeking impossible to do
well. A different delivery mechanism is needed.

## The fix

**A small HTTP server on localhost, inside the desktop app**, serving media files to the page.
The page then loads `http://127.0.0.1:<port>/media?...`, which WebView2 has no objection to,
and which supports range requests so seeking a 28 MB file works.

`tools/devserver.py` **already implements exactly this** — the `/media` route with an allowlist and
range support. Do not write it twice.

---

## Job 1 — extract the media handler into one shared module

Create `media_server.py` in the repo root, beside `app.py`.

Move the `/media` logic out of `tools/devserver.py` into it, and have the dev server import and use
it. There must be **one** implementation of the allowlist and the range logic when you are done —
if the two files both contain a `Content-Range` header, the job is not finished.

```python
def start_media_server(base_dir: str) -> tuple[str, int, str]:
    """
    Serve project media to the page over localhost.

    Returns (host, port, token). Binds 127.0.0.1 on an ephemeral port, runs on a
    daemon thread so it never holds the app open, and is started once.
    """
```

Requirements, all of which the dev server route already satisfies except the token:

- **Bind `127.0.0.1` only**, never `0.0.0.0`. Port `0`, so the OS picks a free one.
- **Allowlist.** Serve only from `projects/`, `cache/` and `output/` under `base_dir`, compared
  with `os.path.realpath` so `..` cannot walk out. Anything else is **403**. This matters: without
  it the route reads any absolute path on the machine, and `config/settings.json` holds live API
  keys.
- **A random token**, generated at startup with `secrets.token_urlsafe`, required as a query
  parameter. Any local process can reach a localhost port; an unguessable URL is cheap and makes
  this meaningfully harder to poke at. Missing or wrong token is **403**.
- **Range requests.** `206` with a correct `Content-Range` and `Accept-Ranges: bytes`; `416` when
  the start is past the end. Seeking a 19-minute file depends on this.
- **Daemon thread**, started once and reused. Do not start a server per request.

## Job 2 — use it from the desktop app

In `app.py`, start the media server when the window is created and have `prepare_timeline_audio`
return a URL from it:

```
http://127.0.0.1:<port>/media?token=<token>&path=<urlencoded absolute path>
```

**Delete the `pathlib.as_uri()` branch.** There is no case where a `file://` URL is correct here.

Keep the existing dev-server branch working — when `SMART_STUDIO_DEVSERVER` is set, the page is
already being served by `tools/devserver.py` and should keep using its own `/media` route on its
own port. Both paths now go through the shared handler, so they behave identically.

`export_wolfcut_timeline` and `prepare_timeline_audio` both repeat the same md5-of-the-title
fallback for `project_dir`. Pull that into one small helper on `Api` and have both call it. Do not
change what it computes.

## Job 3 — prove it in the real window

**This is the acceptance test and it is the reason the bug shipped.** Slice D was verified on the
dev server only, and the dev server is precisely the environment that does not have this bug.

Launch the real desktop app, open the owner's film, and press play. The film is
`projects/Before_Adam_The_Story_of_Iblis`, all 347 lines are measured, and
`timeline_narration.mp3` is already built beside it — 1159.7 seconds, so no rebuild is needed.

Report:
- that audio was heard,
- the playhead advancing with it,
- the picture in the preview frame changing at a boundary,
- a seek by clicking the lanes landing in the right place and continuing to play.

If you cannot launch the desktop app, **say so plainly and say the fix is unverified.** Do not
report a dev-server test as if it covered this.

---

## Tests

Add `tests/test_media_server.py`:

1. **A file inside `projects/` is served**, with `200` and `Content-Type: audio/mpeg`.
2. **`config/settings.json` is refused with 403.** Name that file specifically — it holds live API
   keys and it is the reason the allowlist exists.
3. **A `..` traversal out of `projects/` is refused with 403**, even though the resolved file
   exists.
4. **A missing or wrong token is refused with 403.**
5. **A range request returns 206**, the correct `Content-Range`, and exactly the requested bytes —
   assert the bytes match that slice of the file, not merely that the status was 206.
6. **`prepare_timeline_audio` returns an `http://127.0.0.1` URL and never a `file:` one.** Assert
   `not src.startswith("file:")` explicitly, so this bug cannot come back silently.

Break the allowlist on purpose once and confirm tests 2 and 3 fail. Paste that.

## Traps

1. **Do not change how images are delivered.** The base64 thumbnail pipeline works and is correct
   for thumbnails. This server exists for media too large to embed. Touching `_thumb` is out of
   scope, however tempting.
2. **Do not bind to `0.0.0.0`** and do not add CORS headers. This server is for one local page.
3. The server must not stop the app exiting — daemon thread.
4. Repo files are **CRLF**. Check byte counts before and after.
5. `config/settings.json` is gitignored and holds live API keys. Never print or commit it.
6. Do not touch `pipeline/timeline_audio.py`, `wolfcut_export.py` or `orchestrator.py`.

## Explicitly NOT in this brief

- Serving images through the new server. A worthwhile follow-up, not this task.
- Music and SFX tracks (Slice F), boundary dragging (Slice E).
- Making `Measure narration` faster. Separate, and the owner has not chosen an approach yet.

## What to report

1. Job 3 in full — what you heard and saw in the **real desktop window**, or a plain statement that
   you could not run it.
2. Tests 2 and 3 failing when you break the allowlist, then passing.
3. Confirmation that `Content-Range` appears in exactly one file in the repo when you are done.
4. `git diff --stat`.
5. Full suite: `pytest tests/ -q`.
6. Anything you could not do, and why.
