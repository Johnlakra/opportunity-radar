"""Two people, two sets of level alerts, no crossover.
Needs the full runtime, so it skips where that is not installed."""
import pytest

pytest.importorskip("sqlmodel")
pytest.importorskip("telegram")

from app import level_store                                      # noqa: E402
from app.db import init_db, session                              # noqa: E402
from app.models import LevelSub                                  # noqa: E402

ME, FRIEND = "111", "222"
GOLD, SILVER = "metal:XAU", "metal:XAG"


@pytest.fixture(autouse=True)
def database():
    init_db()
    yield
    with session() as s:
        for row in level_store.all_subs():
            s.delete(s.get(LevelSub, row.id))
        s.commit()


def test_each_person_gets_their_own_gold_and_silver():
    assert level_store.seed_metals("WMQY", [ME, FRIEND]) == 4
    assert len(level_store.all_subs(ME)) == 2 and len(level_store.all_subs(FRIEND)) == 2
    assert level_store.by_key(ME, GOLD).id != level_store.by_key(FRIEND, GOLD).id


def test_seeding_twice_adds_nothing():
    level_store.seed_metals("WMQY", [ME, FRIEND])
    assert level_store.seed_metals("WMQY", [ME, FRIEND]) == 0


def test_my_toggles_do_not_touch_his():
    level_store.seed_metals("WMQY", [ME, FRIEND])
    mine, his = level_store.by_key(ME, GOLD), level_store.by_key(FRIEND, GOLD)
    level_store.update(mine.id, periods="MQY", up=False)
    assert level_store.by_key(FRIEND, GOLD).periods == "WMQY"
    assert level_store.by_key(FRIEND, GOLD).up is True
    assert level_store.by_key(ME, GOLD).periods == "MQY"
    assert his.id == level_store.by_key(FRIEND, GOLD).id


def test_turning_mine_off_leaves_his_on():
    level_store.seed_metals("WMQY", [ME, FRIEND])
    level_store.update(level_store.by_key(ME, GOLD).id, active=False)
    assert level_store.by_key(FRIEND, GOLD).active is True


def test_he_cannot_reach_a_row_of_mine():
    level_store.seed_metals("WMQY", [ME, FRIEND])
    mine = level_store.by_key(ME, GOLD)
    assert level_store.get_sub(mine.id, FRIEND) is None        # a button of mine does nothing for him
    assert level_store.get_sub(mine.id, ME).id == mine.id


def test_each_menu_shows_only_its_owner():
    level_store.seed_metals("WMQY", [ME, FRIEND])
    level_store.upsert(ME, "cg:solana", "SOL", "MQY", source="journal")
    assert {s.asset_key for s in level_store.all_subs(FRIEND)} == {GOLD, SILVER}
    assert "cg:solana" in {s.asset_key for s in level_store.all_subs(ME)}


def test_journal_coins_go_only_to_the_people_who_own_the_journal():
    level_store.seed_metals("WMQY", [ME, FRIEND])
    level_store.sync_journal("MQY", [ME])
    assert {s.asset_key for s in level_store.all_subs(FRIEND)} == {GOLD, SILVER}


def test_who_wants_this_break():
    level_store.seed_metals("WMQY", [ME, FRIEND])
    mine = level_store.by_key(ME, GOLD)
    assert level_store.wants(mine, "M", "up")
    level_store.update(mine.id, periods="QY")
    assert not level_store.wants(level_store.by_key(ME, GOLD), "M", "up")
    level_store.update(mine.id, periods="MQY", down=False)
    assert not level_store.wants(level_store.by_key(ME, GOLD), "M", "down")
    level_store.update(mine.id, active=False)
    assert not level_store.wants(level_store.by_key(ME, GOLD), "M", "up")


# ---------------- a new person should not have to wait for the agent ----------------
def test_a_person_gets_their_metals_the_moment_they_ask():
    """Before this, a new guest saw an empty menu until the worker's next 15-minute run."""
    from app.config import settings
    from app import levels_bot
    before_owner, before_guest = settings.telegram_chat_id, settings.telegram_metals_chat_id
    settings.telegram_chat_id, settings.telegram_metals_chat_id = ME, FRIEND
    try:
        assert level_store.all_subs(FRIEND) == []
        levels_bot.ensure_metals(FRIEND)
        assert {s.asset_key for s in level_store.all_subs(FRIEND)} == {GOLD, SILVER}
        levels_bot.ensure_metals(FRIEND)                       # asking again adds nothing
        assert len(level_store.all_subs(FRIEND)) == 2
    finally:
        settings.telegram_chat_id, settings.telegram_metals_chat_id = before_owner, before_guest


def test_a_stranger_is_not_given_rows_by_asking():
    from app.config import settings
    from app import levels_bot
    before_owner, before_guest = settings.telegram_chat_id, settings.telegram_metals_chat_id
    settings.telegram_chat_id, settings.telegram_metals_chat_id = ME, FRIEND
    try:
        levels_bot.ensure_metals("999")
        assert level_store.all_subs("999") == []
    finally:
        settings.telegram_chat_id, settings.telegram_metals_chat_id = before_owner, before_guest
