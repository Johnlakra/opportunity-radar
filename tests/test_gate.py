import pytest

from app.gate import ALWAYS_DELIVER, URGENT_MIN, decide


def call(priority, topic_muted=False, category_muted=False, quiet=False):
    return decide(priority, topic_muted, category_muted, quiet)


def test_a_high_score_pings_you_now():
    assert call(URGENT_MIN) == "urgent" and call(99) == "urgent"


def test_an_ordinary_item_waits_for_the_daily_digest():
    assert call(URGENT_MIN - 1) == "queued" and call(10) == "queued"


@pytest.mark.parametrize("muted", [{"topic_muted": True}, {"category_muted": True}])
def test_muting_drops_the_item(muted):
    assert call(90, **muted) == "dropped" and call(50, **muted) == "dropped"


def test_quiet_hours_delay_a_ping_they_never_delete_it():
    assert call(90, quiet=True) == "queued"


def test_holding_protection_ignores_mute_and_quiet_hours():
    for kwargs in ({"topic_muted": True}, {"category_muted": True}, {"quiet": True}):
        assert call(ALWAYS_DELIVER, **kwargs) == "urgent"
    assert call(100, topic_muted=True, category_muted=True, quiet=True) == "urgent"
