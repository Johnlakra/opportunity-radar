"""Database-backed checks. They need the full runtime, so they skip where it is not installed."""
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("sqlmodel")
pytest.importorskip("telegram")

from app import news_store                                           # noqa: E402
from app.db import engine, init_db, session                          # noqa: E402
from app.migrate import MIGRATIONS, run                              # noqa: E402
from app.models import Item                                          # noqa: E402


@pytest.fixture(autouse=True)
def database():
    init_db()
    yield
    with session() as s:
        for row in s.exec(__import__("sqlmodel").select(Item)).all():
            s.delete(row)
        s.commit()


def make_item(title="Something worth reading", **kw):
    row = Item(topic="ai", url=f"https://x.io/{title}", title=title, **kw)
    with session() as s:
        s.add(row); s.commit(); s.refresh(row)
        return row


def test_the_migration_is_a_no_op_on_a_fresh_database():
    assert run(engine) == {table: [] for table in MIGRATIONS}


def test_a_reminder_comes_due_and_only_fires_once():
    row = make_item(remind_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    assert [x.id for x in news_store.due_reminders()] == [row.id]
    news_store.mark_reminded(row.id)
    assert news_store.due_reminders() == []


def test_a_reminder_in_the_future_is_not_due_yet():
    make_item(remind_at=datetime.now(timezone.utc) + timedelta(hours=2))
    assert news_store.due_reminders() == []


def test_saving_and_unsaving_round_trips():
    row = make_item()
    assert news_store.set_saved(row.id, True).saved
    assert row.id in [x.id for x in news_store.saved_and_deadlines()]
    assert not news_store.set_saved(row.id, False).saved


def test_a_closed_deadline_drops_off_the_list():
    make_item(deadline_at=datetime.now(timezone.utc) - timedelta(days=5), title="old")
    assert news_store.saved_and_deadlines() == []


def test_search_only_looks_at_what_came_through():
    make_item(title="Gemini free credits for developers")
    assert [x.title for x in news_store.search("gemini")] == ["Gemini free credits for developers"]
    assert news_store.search("nothing like this") == []
    assert news_store.search("ab") == []            # too short to be a useful search
