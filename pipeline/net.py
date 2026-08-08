"""
Network compatibility shim.

On this machine (and others with a broken or half-configured IPv6 stack), a default
AF_UNSPEC lookup for *.googleapis.com fails outright:

    socket.getaddrinfo("texttospeech.googleapis.com", 443)
      -> [Errno 11002] getaddrinfo failed
    socket.getaddrinfo("texttospeech.googleapis.com", 443, socket.AF_INET)
      -> ok, 172.217.118.4

The AAAA half of the lookup fails in a way that poisons the whole call, so every
Google TTS and Imagen request dies before it is sent. curl and nslookup are unaffected
because they fall back to IPv4 on their own.

install() makes getaddrinfo retry IPv4-only whenever the dual-stack lookup raises.
Nothing else changes: hosts that resolve normally take the original path untouched.
"""

import socket
import threading

_installed = False
_lock = threading.Lock()
_original_getaddrinfo = socket.getaddrinfo


def install() -> bool:
    """Patch socket.getaddrinfo to fall back to IPv4. Idempotent. Returns True if patched."""
    global _installed
    with _lock:
        if _installed:
            return False

        def _getaddrinfo_ipv4_fallback(host, port, family=0, type=0, proto=0, flags=0):
            try:
                return _original_getaddrinfo(host, port, family, type, proto, flags)
            except socket.gaierror:
                # Only retry when the caller did not already pin a family.
                if family not in (0, socket.AF_UNSPEC):
                    raise
                return _original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)

        socket.getaddrinfo = _getaddrinfo_ipv4_fallback
        _installed = True
        return True


def dual_stack_broken(probe_host: str = "texttospeech.googleapis.com") -> bool:
    """True if the default lookup fails but IPv4-only succeeds — the exact fault above."""
    try:
        _original_getaddrinfo(probe_host, 443)
        return False
    except socket.gaierror:
        pass
    try:
        _original_getaddrinfo(probe_host, 443, socket.AF_INET)
        return True
    except socket.gaierror:
        return False        # genuinely offline, not an IPv6 problem
