"""
Windows console-window suppression.

The desktop shortcut launches the app with pythonw.exe so no terminal appears.
But every child process the pipeline starts — ffmpeg, ffprobe, edge-tts, whisper's
own ffmpeg calls — creates its own console window unless told not to, which shows
up as a black rectangle flashing over the UI on almost every action.

There are fourteen subprocess call sites across the pipeline, plus more inside
third-party packages we do not control. Patching Popen once covers all of them,
including the ones we cannot reach.

install() is idempotent and a no-op off Windows. Callers that deliberately pass
their own creationflags keep them.
"""

import subprocess
import sys
import threading

_installed = False
_lock = threading.Lock()

CREATE_NO_WINDOW = 0x08000000


def install() -> bool:
    """Suppress console windows for child processes. Returns True if patched."""
    global _installed
    with _lock:
        if _installed or not sys.platform.startswith("win"):
            return False

        original_init = subprocess.Popen.__init__

        def _init_no_window(self, *args, **kwargs):
            # Respect an explicit choice; only fill in the default.
            if not kwargs.get("creationflags"):
                kwargs["creationflags"] = CREATE_NO_WINDOW
            return original_init(self, *args, **kwargs)

        subprocess.Popen.__init__ = _init_no_window
        _installed = True
        return True
