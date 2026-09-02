# media_server.py
"""
Local media server for streaming large audio and media files to WebView2 and the dev server.

WebView2 refuses file:// URLs as subresources, and base64 embedding is too heavy
for large files (e.g. 28MB narration tracks) while breaking range-based seeking.
This server serves allowed files over 127.0.0.1 on an ephemeral port with an
allowlist, a security token, and HTTP 206 Partial Content (range requests).
"""

import os
import sys
import json
import secrets
import shutil
import mimetypes
import threading
import urllib.parse
import http.server
from typing import Optional, Tuple


_SERVER_LOCK = threading.Lock()
_MEDIA_SERVER: Optional[Tuple[str, int, str]] = None


def is_path_allowed(file_path: str, base_dir: str) -> bool:
    """
    Allow only files under projects/, cache/, and output/ of base_dir.
    Uses os.path.realpath so symlinks and '..' traversal cannot escape.
    """
    allowed_roots = [
        os.path.realpath(os.path.join(base_dir, sub))
        for sub in ("projects", "cache", "output")
    ]
    real = os.path.realpath(file_path)
    return any(
        real == root or real.startswith(root + os.sep)
        for root in allowed_roots
    )


def serve_media(
    handler: http.server.BaseHTTPRequestHandler,
    base_dir: str,
    expected_token: Optional[str] = None
) -> None:
    """
    Common handler for /media requests.
    Used by both media_server.py and tools/devserver.py.
    """
    query = urllib.parse.urlparse(handler.path).query
    params = urllib.parse.parse_qs(query)

    # 1. Token check (if expected_token is configured)
    if expected_token is not None:
        token = (params.get("token") or [""])[0]
        if not token or token != expected_token:
            handler.send_response(403)
            handler.send_header("Content-Type", "application/json")
            handler.end_headers()
            handler.wfile.write(json.dumps({"error": "forbidden - invalid token"}).encode("utf-8"))
            return

    # 2. File path check
    file_path = (params.get("path") or [""])[0]
    if not file_path or not os.path.isfile(file_path):
        handler.send_response(404)
        handler.send_header("Content-Type", "application/json")
        handler.end_headers()
        handler.wfile.write(json.dumps({"error": "file not found"}).encode("utf-8"))
        return

    # 3. Allowlist check
    if not is_path_allowed(file_path, base_dir):
        handler.send_response(403)
        handler.send_header("Content-Type", "application/json")
        handler.end_headers()
        handler.wfile.write(json.dumps({"error": "forbidden - path not allowed"}).encode("utf-8"))
        return

    file_size = os.path.getsize(file_path)
    ctype = mimetypes.guess_type(file_path)[0] or "audio/mpeg"

    # 4. Range request handling
    range_header = handler.headers.get("Range")
    if range_header and range_header.startswith("bytes="):
        try:
            ranges = range_header[6:].split("-", 1)
            start = int(ranges[0]) if ranges[0] else 0
            end = int(ranges[1]) if ranges[1] else file_size - 1
            if start >= file_size:
                handler.send_response(416)
                handler.send_header("Content-Range", f"bytes */{file_size}")
                handler.send_header("Accept-Ranges", "bytes")
                handler.end_headers()
                return

            end = min(end, file_size - 1)
            length = end - start + 1

            handler.send_response(206)
            handler.send_header("Content-Type", ctype)
            handler.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            handler.send_header("Content-Length", str(length))
            handler.send_header("Accept-Ranges", "bytes")
            handler.send_header("Cache-Control", "no-cache")
            handler.end_headers()

            with open(file_path, "rb") as f:
                f.seek(start)
                chunk_size = 64 * 1024
                bytes_left = length
                while bytes_left > 0:
                    read_len = min(chunk_size, bytes_left)
                    buf = f.read(read_len)
                    if not buf:
                        break
                    handler.wfile.write(buf)
                    bytes_left -= len(buf)
            return
        except Exception as err:
            sys.stderr.write(f"Range request error: {err}\n")
            return

    # 5. Full file response
    handler.send_response(200)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Content-Length", str(file_size))
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Cache-Control", "no-cache")
    handler.end_headers()
    with open(file_path, "rb") as f:
        shutil.copyfileobj(f, handler.wfile)


class _MediaRequestHandler(http.server.BaseHTTPRequestHandler):
    base_dir: str = ""
    token: str = ""

    def log_message(self, format, *args):
        # Suppress routine HTTP log noise on stdout
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/media":
            serve_media(self, self.base_dir, expected_token=self.token)
        else:
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "not found"}).encode("utf-8"))


def start_media_server(base_dir: str) -> tuple[str, int, str]:
    """
    Serve project media to the page over localhost.

    Returns (host, port, token). Binds 127.0.0.1 on an ephemeral port, runs on a
    daemon thread so it never holds the app open, and is started once.
    """
    global _MEDIA_SERVER
    with _SERVER_LOCK:
        if _MEDIA_SERVER is not None:
            return _MEDIA_SERVER

        host = "127.0.0.1"
        token = secrets.token_urlsafe(16)

        class BoundHandler(_MediaRequestHandler):
            pass

        BoundHandler.base_dir = os.path.abspath(base_dir)
        BoundHandler.token = token

        server = http.server.ThreadingHTTPServer((host, 0), BoundHandler)
        port = server.server_address[1]

        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        _MEDIA_SERVER = (host, port, token)
        return _MEDIA_SERVER