import threading
import urllib.request

import pytest

from app.health import make_server


@pytest.fixture
def base_url():
    server = make_server(port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def test_the_pinger_gets_ok_on_any_path(base_url):
    for path in ("/", "/health"):
        with urllib.request.urlopen(base_url + path, timeout=5) as resp:
            assert resp.status == 200 and resp.read() == b"ok"


def test_a_head_ping_gets_ok_with_no_body(base_url):
    req = urllib.request.Request(base_url + "/health", method="HEAD")
    with urllib.request.urlopen(req, timeout=5) as resp:
        assert resp.status == 200 and resp.read() == b""


def test_port_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("PORT", "0")
    server = make_server()
    try:
        assert server.server_address[1] > 0
    finally:
        server.server_close()
