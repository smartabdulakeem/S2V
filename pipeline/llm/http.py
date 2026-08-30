"""
pipeline/llm/http.py

One HTTP helper shared by the providers. Gemini's batch call used to carry its
own 429/503 backoff inside shot_description; when that call moved behind the
provider seam the backoff came with it, so a rate-limited minute still costs a
pause rather than a lost description.
"""

import time
import urllib.request
import urllib.error


def urlopen_with_backoff(req: urllib.request.Request, timeout: int = 60,
                         max_retries: int = 3) -> bytes:
    """The response body, retrying 429 and 503 with exponential backoff."""
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                if isinstance(data, (bytes, bytearray)):
                    return bytes(data)
                if isinstance(data, str):
                    return data.encode("utf-8")
                return bytes(data) if data else b""
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
    return b""
