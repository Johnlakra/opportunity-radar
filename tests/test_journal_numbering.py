"""The number you see is the position in the list, so removing one never leaves a gap.
Needs the full runtime, so it skips where that is not installed."""
import pytest

pytest.importorskip("sqlmodel")
pytest.importorskip("telegram")

from app import journal                                          # noqa: E402
from app.db import init_db, session                              # noqa: E402
from app.models import Holding                                   # noqa: E402


@pytest.fixture(autouse=True)
def database():
    init_db()
    yield
    with session() as s:
        for row in journal.holdings_in_order():
            s.delete(s.get(Holding, row.id))
        s.commit()


def add(symbol, usd=100.0):
    return journal.add_dex_holding(f"solana:{symbol}", symbol, 50_000.0, usd, entry_price=0.0001)


def test_positions_start_at_one_and_follow_the_order_added():
    add("AAA"); add("BBB"); add("CCC")
    assert [h.symbol for h in journal.holdings_in_order()] == ["AAA", "BBB", "CCC"]
    assert journal.holding_at(1).symbol == "AAA" and journal.holding_at(3).symbol == "CCC"


def test_removing_the_first_one_closes_the_gap():
    first, second, third = add("AAA"), add("BBB"), add("CCC")
    journal.remove_holding(first.id)
    assert [h.symbol for h in journal.holdings_in_order()] == ["BBB", "CCC"]
    assert journal.holding_at(1).id == second.id        # BBB is now #1, not #2
    assert journal.holding_at(2).id == third.id


def test_a_number_nobody_has_is_simply_nothing():
    add("AAA")
    assert journal.holding_at(2) is None and journal.holding_at(0) is None
    assert journal.holding_at(-1) is None


def test_the_database_id_never_changes_under_you():
    first, second = add("AAA"), add("BBB")
    journal.remove_holding(first.id)
    assert journal.get_holding(second.id).symbol == "BBB"     # buttons still point at the right row


def test_the_entry_price_is_stored_and_read_back():
    holding = add("AAA")
    assert journal.get_holding(holding.id).entry_price == 0.0001


def test_removing_something_already_gone_is_not_an_error():
    holding = add("AAA")
    assert journal.remove_holding(holding.id) is True
    assert journal.remove_holding(holding.id) is False
