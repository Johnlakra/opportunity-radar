import logging

from app.preflight import quiet_http_logs, redis_problem


def test_a_compose_only_redis_address_is_explained():
    msg = redis_problem("redis://redis:6379/0")
    assert msg and "Upstash" in msg


def test_localhost_redis_is_flagged_too():
    assert redis_problem("redis://localhost:6379/0")


def test_a_hosted_redis_address_passes():
    assert redis_problem("rediss://default:pw@eu1-x.upstash.io:6379") is None


def test_request_urls_holding_the_bot_token_stay_out_of_the_logs():
    quiet_http_logs()
    assert not logging.getLogger("httpx").isEnabledFor(logging.INFO)
    assert logging.getLogger("httpx").isEnabledFor(logging.WARNING)
