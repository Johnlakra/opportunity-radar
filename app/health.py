"""Tiny web page for free hosts that sleep without web traffic: a pinger hits it, it answers "ok"."""
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_PORT = 10000


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


def main():
    make_server().serve_forever()


if __name__ == "__main__":
    main()
