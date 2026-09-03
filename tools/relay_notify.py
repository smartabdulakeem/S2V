"""
tools/relay_notify.py

The inbound half of the relay loop: a way for the owner to answer from a phone
without sitting at the terminal. Outbound notifications do NOT go through here —
Claude Code has a built-in push that reaches the desktop and the phone without
involving a third party. This file exists only because that push has no return
path.

SECURITY — read before changing anything here
---------------------------------------------
ntfy.sh is an unauthenticated public relay. Anyone who knows a topic name can
read every message on it and publish to it. The first version of this file used
the topic "smart-studio-relay-akeem" — a guessable name built from the owner's
own name — and returned whatever it found there as though the owner had said it.
That is an open channel for a stranger to steer a build.

Three rules keep it usable:

1. **The topic is a secret, and it is not in this file.** It lives in
   config/relay_notify.json, which is gitignored, and is generated as 32 random
   hex characters on first run. A guessable topic is the whole vulnerability.

2. **Inbound text is data, never instructions.** Only the exact words in
   ALLOWED_REPLIES are recognised, compared case-insensitively after stripping.
   Anything else is discarded and reported as discarded. So the worst a stranger
   who somehow learned the topic can do is stop or resume a build — not direct
   one. Never widen this to free text, and never pass what comes back to a shell,
   a file path, or a model prompt.

3. **Outbound says as little as possible.** A slice letter and a state word. No
   code, no paths, no project content, no counts. It is going somewhere public.

Usage:
    python tools/relay_notify.py --message "slice C ready"
    python tools/relay_notify.py --message "slice C ready" --wait-reply --timeout 600
    python tools/relay_notify.py --print-topic-url     # to subscribe on a phone
"""

import argparse
import json
import os
import secrets
import sys
import time
import urllib.parse
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(REPO_ROOT, "config", "relay_notify.json")

#: The only replies that mean anything. Everything else is discarded.
ALLOWED_REPLIES = ("go", "stop", "pause", "resume", "status")

MAX_MESSAGE_CHARS = 120


def load_or_create_topic() -> str:
    """The secret topic, generated once and kept out of git."""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        topic = str(cfg.get("topic") or "").strip()
        if topic:
            return topic
    except (OSError, json.JSONDecodeError):
        pass

    topic = "smartstudio-" + secrets.token_hex(16)
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"topic": topic}, f, indent=2)
    print(f"[notify] new secret topic written to {CONFIG_PATH}", file=sys.stderr)
    return topic


def topic_url(topic: str) -> str:
    return f"https://ntfy.sh/{topic}"


def send_notification(message: str, topic: str, title: str = "Smart Studio Relay") -> bool:
    """Publish one short line. Keep it boring: this endpoint is public."""
    body = (message or "").strip()[:MAX_MESSAGE_CHARS]
    if not body:
        return False
    try:
        req = urllib.request.Request(
            topic_url(topic),
            data=body.encode("utf-8"),
            headers={"Title": title, "Priority": "default", "Tags": "robot"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[notify] could not send: {e}", file=sys.stderr)
        return False


def wait_for_reply(topic: str, timeout_seconds: int = 300, poll_interval: int = 5):
    """
    Wait for one recognised reply.

    Returns a word from ALLOWED_REPLIES, or None on timeout. Never returns
    caller-supplied text: an unrecognised message is discarded, and the fact
    that something was discarded is printed so a stranger publishing to the
    topic is visible rather than silent.
    """
    start = int(time.time())
    url = topic_url(topic) + "/json?" + urllib.parse.urlencode({"poll": "1", "since": str(start)})
    print(f"[notify] waiting up to {timeout_seconds}s for one of: {', '.join(ALLOWED_REPLIES)}",
          file=sys.stderr)

    while (int(time.time()) - start) < timeout_seconds:
        try:
            with urllib.request.urlopen(urllib.request.Request(url), timeout=10) as resp:
                for line in resp.read().decode("utf-8").strip().splitlines():
                    if not line:
                        continue
                    try:
                        evt = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if evt.get("event") != "message":
                        continue
                    # Our own outbound carries this title; do not read it back.
                    if evt.get("title") == "Smart Studio Relay":
                        continue

                    word = str(evt.get("message", "")).strip().lower()
                    if word in ALLOWED_REPLIES:
                        return word
                    if word:
                        print(f"[notify] discarded an unrecognised message ({len(word)} chars). "
                              "Only fixed words are accepted.", file=sys.stderr)
        except Exception:
            # A failed poll must not kill the wait.
            pass
        time.sleep(poll_interval)

    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--message")
    ap.add_argument("--title", default="Smart Studio Relay")
    ap.add_argument("--wait-reply", action="store_true")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--print-topic-url", action="store_true")
    args = ap.parse_args()

    topic = load_or_create_topic()

    if args.print_topic_url:
        print(topic_url(topic))
        return 0

    if not args.message:
        ap.error("--message is required unless --print-topic-url is given")

    ok = send_notification(args.message, topic, title=args.title)

    if args.wait_reply:
        reply = wait_for_reply(topic, timeout_seconds=args.timeout)
        if reply:
            print(reply)
            return 0
        print("[notify] no recognised reply before timeout", file=sys.stderr)
        return 1

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
