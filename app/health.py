"""Tiny web page for free hosts that sleep without web traffic: a pinger hits it, it answers "ok".

Render's free web service sleeps after 15 minutes with no inbound request, and a sleeping
container runs no scheduler - news arrives late or not at all. So the page also pings its own
public address (RENDER_EXTERNAL_URL, set by Render) every 10 minutes. An outside pinger such as
UptimeRobot still helps: it wakes the service if it ever does fall asleep."""
import logging
import os
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_PORT = 10000
SELF_PING_SECONDS = 10 * 60        # under Render's 15-minute idle limit
SELF_PING_TIMEOUT = 30
log = logging.getLogger(__name__)


class Health(BaseHTTPRequestHandler):
    """Every path answers 200 "ok" - the pinger only needs a live reply, not a real check."""

    def do_GET(self):
        self._ok(b"ok")

    def do_HEAD(self):
        self._ok(b"")

    def _ok(self, body):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", "2")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def log_message(self, *args):
        pass  # a ping every 10 minutes would just clutter the logs


def make_server(port=None):
    port = int(os.environ.get("PORT", DEFAULT_PORT)) if port is None else port
    return ThreadingHTTPServer(("0.0.0.0", port), Health)


def self_ping_url(env=None) -> str | None:
    """Where to ping, or None: off unless on Render, and SELF_PING=0 turns it off there too."""
    env = os.environ if env is None else env
    base = (env.get("RENDER_EXTERNAL_URL") or "").rstrip("/")
    if not base.startswith("https://") or env.get("SELF_PING", "1") == "0":
        return None
    return base + "/health"


def keep_awake(url: str, every: int = SELF_PING_SECONDS):
    while True:
        time.sleep(every)
        try:
            with urllib.request.urlopen(url, timeout=SELF_PING_TIMEOUT) as resp:
                resp.read()
        except Exception as exc:           # a missed ping is fine; the next one comes in 10 min
            log.warning("self-ping failed: %s", exc)


def main():
    url = self_ping_url()
    if url:
        threading.Thread(target=keep_awake, args=(url,), daemon=True).start()
    make_server().serve_forever()


if __name__ == "__main__":
    main()
