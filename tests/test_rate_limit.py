"""A provider that keeps answering 429 is left alone for a while instead of being hammered."""
import asyncio

import httpx
import pytest

from app.crypto import http


def _run(coro):
    return asyncio.run(coro)


def _client(statuses: list[int], hits: list[str]):
    def handler(request):
        hits.append(str(request.url))
        code = statuses.pop(0) if statuses else 200
        return httpx.Response(code, json={"ok": True}, headers={"Retry-After": "3"} if code == 429 else {})
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    slept = []

    async def fake_sleep(secs):
        slept.append(secs)
    monkeypatch.setattr(http.asyncio, "sleep", fake_sleep)
    return slept


def test_a_single_429_is_retried_after_the_servers_retry_after(no_sleep):
    hits = []
    throttle = http.Throttle(6000)
    data = _run(http.get_json(_client([429], hits), "https://x.test/a", throttle))
    assert data == {"ok": True}
    assert len(hits) == 2
    assert 3 in no_sleep


def test_two_429s_raise_rate_limited_and_cool_the_provider_down():
    hits = []
    throttle = http.Throttle(6000)
    c = _client([429, 429], hits)
    with pytest.raises(http.RateLimited):
        _run(http.get_json(c, "https://x.test/a", throttle))
    assert throttle.cooling()
    with pytest.raises(http.RateLimited):
        _run(http.get_json(c, "https://x.test/b", throttle))
    assert len(hits) == 2, "no request is sent while the provider is cooling down"


def test_cooldown_ends(monkeypatch):
    throttle = http.Throttle(6000)
    throttle.cool_down(60)
    assert throttle.cooling()
    later = http.time.monotonic() + 61
    monkeypatch.setattr(http.time, "monotonic", lambda: later)
    assert not throttle.cooling()


def test_retry_after_is_capped_and_garbage_falls_back():
    assert http.retry_after_seconds("5") == 5
    assert http.retry_after_seconds("9999") == http.MAX_RETRY_WAIT
    assert http.retry_after_seconds("Wed, 21 Oct 2026 07:28:00 GMT") == http.DEFAULT_RETRY_WAIT
    assert http.retry_after_seconds(None) == http.DEFAULT_RETRY_WAIT
