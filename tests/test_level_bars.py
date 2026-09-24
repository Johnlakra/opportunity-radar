"""The bot and the level agent can bootstrap the same metal at the same moment.
Needs the full runtime, so it skips where that is not installed."""
import pytest

pytest.importorskip("sqlmodel")

from sqlalchemy import event                                     # noqa: E402
from sqlmodel import Session, select                             # noqa: E402

from app import level_store                                      # noqa: E402
from app.db import init_db, session                              # noqa: E402
from app.models import DailyBar                                  # noqa: E402

KEY = "metal:TEST"
BARS = [{"day": "2024-09-23", "o": 1.0, "h": 2.0, "l": 0.5, "c": 1.5},
        {"day": "2024-09-24", "o": 1.5, "h": 2.5, "l": 1.0, "c": 2.0}]


@pytest.fixture(autouse=True)
def database():
    init_db()
    yield
    with session() as s:
        for row in s.exec(select(DailyBar).where(DailyBar.asset_key == KEY)).all():
            s.delete(row)
        s.commit()


@pytest.fixture
def other_process_writes_first():
    """Just before our first flush, someone else commits 2024-09-23."""
    fired = []

    def before_flush(_sess, _ctx, _instances):
        if fired:
            return
        fired.append(True)
        with session() as other:
            other.add(DailyBar(asset_key=KEY, day="2024-09-23", o=9, h=9, l=9, c=9))
            other.commit()
    event.listen(Session, "before_flush", before_flush)
    yield
    event.remove(Session, "before_flush", before_flush)


def test_saving_bars_someone_else_just_saved_does_not_fail(other_process_writes_first):
    written = level_store.save_bars(KEY, BARS)

    assert written == 2
    assert [b["day"] for b in level_store.load_bars(KEY)] == ["2024-09-23", "2024-09-24"]
    assert level_store.load_bars(KEY)[0]["c"] == 1.5


def test_saving_bars_twice_updates_in_place():
    level_store.save_bars(KEY, BARS)

    assert level_store.save_bars(KEY, BARS) == 2
    assert level_store.bar_count(KEY) == 2
