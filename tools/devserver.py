"""
Run the real app in an ordinary browser, against the real Python backend.

Development only. The shipped app is app.py in a PyWebView window; nothing here
is imported by it. This exists because the UI could not be exercised without
that window, so every frontend change was written blind and judged by a test
suite that has never once been able to tell whether the board looked right.

It serves frontend/ and turns `window.pywebview.api.<name>(...)` into
`POST /api/<name>`, dispatched to the same Api object app.py hands the window.
Same code, same settings, same projects on disk.

    C:\\Users\\HomePC\\AppData\\Local\\Programs\\Python\\Python312\\python.exe tools/devserver.py

Then open http://127.0.0.1:8765/.

Two things the window provides that a browser cannot:
  - Native file dialogs. POST /dev/pick with {"path": "..."} to set what the
    next dialog returns, then trigger the button that opens it.
  - window.evaluate_js, which the backend uses to push render and timing
    progress. Those calls are queued and the page polls /dev/js for them.
"""

import json
import mimetypes
import os
import shutil
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ["SMART_STUDIO_DEVSERVER"] = "1"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(BASE_DIR, "frontend")
sys.path.insert(0, BASE_DIR)

import app as app_module  # noqa: E402  (needs BASE_DIR on the path first)


# The page checks `window.pywebview.api` to decide it is not in web mode, and
# waits for `pywebviewready` before booting. A Proxy answers for every method
# name, so this never needs updating when the Api class gains one.
SHIM = """
<script>
window.pywebview = {
  api: new Proxy({}, {
    get: function (_t, name) {
      if (name === "then") return undefined;   // not a thenable
      return function () {
        var args = Array.prototype.slice.call(arguments);
        return fetch("/api/" + String(name), {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(args)
        }).then(function (r) { return r.json(); }).then(function (out) {
          if (out && out.__dev_error) throw new Error(out.__dev_error);
          return out;
        });
      };
    }
  })
};
// Whatever the backend would have pushed through evaluate_js.
setInterval(function () {
  fetch("/dev/js").then(function (r) { return r.json(); }).then(function (list) {
    (list || []).forEach(function (src) {
      try { (0, eval)(src); } catch (e) { console.error("pushed js failed", e); }
    });
  }).catch(function () {});
}, 400);
window.addEventListener("DOMContentLoaded", function () {
  window.dispatchEvent(new Event("pywebviewready"));
});
</script>
"""


class DevWindow:
    """Stands in for the PyWebView window object the Api holds."""

    def __init__(self):
        self.next_dialog = None
        self.pushed = []
        self._lock = threading.Lock()

    def create_file_dialog(self, *args, **kwargs):
        path = self.next_dialog
        self.next_dialog = None
        if not path:
            raise RuntimeError(
                "No file dialog in a browser. POST /dev/pick {\"path\": \"...\"} first."
            )
        return [path]

    def evaluate_js(self, src):
        with self._lock:
            self.pushed.append(src)

    def drain(self):
        with self._lock:
            out, self.pushed = self.pushed, []
        return out

    # The Api touches these only when it owns a real window.
    def restore(self):
        pass


WINDOW = DevWindow()
API = app_module.Api()
API.set_window(WINDOW)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        # One line per API call is useful; static files are noise.
        if self.path.startswith("/api/") or self.path.startswith("/dev/pick"):
            sys.stderr.write("  %s %s\n" % (self.command, self.path))

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if path == "/dev/js":
            return self._send(200, json.dumps(WINDOW.drain()))

        if path == "/media":
            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            file_path = (params.get("path") or [""])[0]
            if not file_path or not os.path.isfile(file_path):
                return self._send(404, json.dumps({"error": "file not found"}))

            # Only ever serve generated media. Without this the route reads any
            # absolute path on the machine, and config/settings.json holds live
            # API keys — a dev tool is not a reason to leave that open.
            allowed_roots = [
                os.path.realpath(os.path.join(BASE_DIR, sub))
                for sub in ("projects", "cache", "output")
            ]
            real = os.path.realpath(file_path)
            if not any(
                real == root or real.startswith(root + os.sep)
                for root in allowed_roots
            ):
                return self._send(403, json.dumps({"error": "path not allowed"}))

            file_size = os.path.getsize(file_path)
            ctype = mimetypes.guess_type(file_path)[0] or "audio/mpeg"

            range_header = self.headers.get("Range")
            if range_header and range_header.startswith("bytes="):
                try:
                    ranges = range_header[6:].split("-", 1)
                    start = int(ranges[0]) if ranges[0] else 0
                    end = int(ranges[1]) if ranges[1] else file_size - 1
                    if start >= file_size:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{file_size}")
                        self.end_headers()
                        return

                    end = min(end, file_size - 1)
                    length = end - start + 1

                    self.send_response(206)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                    self.send_header("Content-Length", str(length))
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()

                    with open(file_path, "rb") as f:
                        f.seek(start)
                        chunk_size = 64 * 1024
                        bytes_left = length
                        while bytes_left > 0:
                            read_len = min(chunk_size, bytes_left)
                            buf = f.read(read_len)
                            if not buf:
                                break
                            self.wfile.write(buf)
                            bytes_left -= len(buf)
                    return
                except Exception as err:
                    sys.stderr.write(f"Range request error: {err}\n")

            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            with open(file_path, "rb") as f:
                shutil.copyfileobj(f, self.wfile)
            return

        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        target = os.path.normpath(os.path.join(FRONTEND, rel))
        if not target.startswith(FRONTEND) or not os.path.isfile(target):
            return self._send(404, json.dumps({"error": "not found: " + rel}))

        if os.path.basename(target).lower() == "index.html":
            with open(target, "r", encoding="utf-8") as f:
                html = f.read()
            # Before app.js runs, so isWebMode is false from the first line.
            html = html.replace("</head>", SHIM + "</head>", 1)
            return self._send(200, html, "text/html; charset=utf-8")

        ctype = mimetypes.guess_type(target)[0] or "application/octet-stream"
        with open(target, "rb") as f:
            return self._send(200, f.read(), ctype)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"[]"
        try:
            payload = json.loads(raw.decode("utf-8") or "[]")
        except Exception as e:
            return self._send(400, json.dumps({"__dev_error": "bad JSON: %s" % e}))

        if path == "/dev/pick":
            WINDOW.next_dialog = (payload or {}).get("path") or None
            return self._send(200, json.dumps({"ok": True, "path": WINDOW.next_dialog}))

        if not path.startswith("/api/"):
            return self._send(404, json.dumps({"__dev_error": "no such route"}))

        name = path[len("/api/"):]
        method = getattr(API, name, None)
        if name.startswith("_") or not callable(method):
            return self._send(404, json.dumps({"__dev_error": "no api method %r" % name}))

        try:
            result = method(*(payload if isinstance(payload, list) else [payload]))
        except Exception as e:
            import traceback
            traceback.print_exc()
            return self._send(200, json.dumps({"__dev_error": "%s: %s" % (type(e).__name__, e)}))

        try:
            return self._send(200, json.dumps(result, ensure_ascii=False, default=str))
        except Exception as e:
            return self._send(200, json.dumps({"__dev_error": "unserialisable reply: %s" % e}))


def main():
    port = 8765
    for i, arg in enumerate(sys.argv):
        if arg == "--port" and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    print("Smart Studio (dev) on http://127.0.0.1:%d/" % port)
    print("Serving %s" % FRONTEND)
    server.serve_forever()


if __name__ == "__main__":
    main()
