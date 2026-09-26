"""Things that used to fail quietly on a free host: sleep, used-up quotas, unreachable chats."""
from app.health import self_ping_url
from app.llm import is_daily_quota
from app.preflight import chat_warnings


def test_self_ping_only_on_render_and_can_be_turned_off():
    assert self_ping_url({}) is None
    assert self_ping_url({"RENDER_EXTERNAL_URL": "https://radar.onrender.com/"}) == \
        "https://radar.onrender.com/health"
    assert self_ping_url({"RENDER_EXTERNAL_URL": "https://radar.onrender.com", "SELF_PING": "0"}) is None


def test_a_used_up_daily_quota_is_told_apart_from_a_per_minute_limit():
    daily = Exception("429 RESOURCE_EXHAUSTED. quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier")
    minute = Exception("429 RESOURCE_EXHAUSTED. quotaId: GenerateRequestsPerMinutePerProjectPerModel-FreeTier")
    assert is_daily_quota(daily)
    assert not is_daily_quota(minute)
    assert not is_daily_quota(Exception("500 internal error"))


def test_an_unreachable_metals_chat_is_explained_at_boot():
    replies = {"111": {"ok": True}, "-222": {"ok": False, "description": "Bad Request: chat not found"}}
    warnings = chat_warnings({"111": "main", "-222": "metals"}, lambda cid: replies[cid])
    assert len(warnings) == 1
    assert "metals chat -222" in warnings[0] and "press Start" in warnings[0]


def test_a_network_error_during_the_check_never_leaks_details():
    def boom(_):
        raise RuntimeError("https://api.telegram.org/botSECRET/getChat")
    warnings = chat_warnings({"111": "main"}, boom)
    assert warnings == ["could not check main chat 111: RuntimeError"]
