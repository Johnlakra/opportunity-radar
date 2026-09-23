"""The export has to open cleanly in a spreadsheet. Scientific notation does not."""
import csv
import io
from datetime import datetime, timezone

from app.text import plain_number
from app.ux.cards import enrich, profit_text
from app.ux.journal_csv import HEADERS, csv_bytes

ADDED = datetime(2026, 9, 20, tzinfo=timezone.utc)


def dex_row(**kw):
    base = dict(n=1, id=2, symbol="UTYA", chain="ton", usd=210.0, entry=29_732_700.0,
                value=29_732_700.0, price=0.02973, entry_price=None, unit="market cap",
                added=ADDED, days_held=3, link="https://dexscreener.com/ton/x")
    base.update(kw)
    return base


def listed_row(**kw):
    base = dict(n=2, id=5, symbol="SOL", chain="", usd=100.0, entry=150.0, value=212.5,
                price=212.5, entry_price=150.0, unit="price", added=ADDED, days_held=114,
                link="https://www.coingecko.com/en/coins/solana")
    base.update(kw)
    return base


def parse(rows):
    text = csv_bytes(rows).decode()
    return list(csv.reader(io.StringIO(text)))


NUMERIC = ["amount_invested_usd", "entry_price_usd", "entry_market_cap_usd", "current_price_usd",
           "current_market_cap_usd", "multiple_x", "value_now_usd", "profit_usd", "profit_pct"]


def numbers(rows):
    """Only the cells that hold a number, which are the ones a spreadsheet parses."""
    return [dict(zip(HEADERS, line))[column] for line in parse(rows)[1:] if len(line) == len(HEADERS)
            for column in NUMERIC]


def test_no_number_is_ever_written_in_scientific_notation():
    written = numbers([dex_row(), listed_row(),
                       dex_row(price=0.00000000123, value=1_900_000_000.0)])
    assert written, "expected some numbers to check"
    for cell in written:
        assert "e" not in cell.lower() and "E" not in cell, cell
        assert cell == "" or cell.lstrip("-").replace(".", "", 1).isdigit(), cell


def test_a_big_market_cap_reads_as_digits():
    body = dict(zip(HEADERS, parse([dex_row()])[1]))
    assert body["entry_market_cap_usd"] == "29732700"
    assert body["current_market_cap_usd"] == "29732700"


def test_a_tiny_price_keeps_its_decimals():
    body = dict(zip(HEADERS, parse([dex_row(price=0.00000000123)])[1]))
    assert body["current_price_usd"] == "0.00000000123"


def test_the_columns_a_person_actually_wants_are_all_there():
    for column in ("symbol", "chain", "date_added", "days_held", "amount_invested_usd",
                   "entry_price_usd", "current_price_usd", "multiple_x", "value_now_usd",
                   "profit_usd", "profit_pct", "link"):
        assert column in HEADERS


def test_a_recorded_entry_price_is_marked_as_recorded():
    body = dict(zip(HEADERS, parse([listed_row()])[1]))
    assert body["entry_price_usd"] == "150" and body["entry_price_source"] == "recorded"
    assert body["multiple_x"] == "1.4167" and body["profit_usd"] == "41.67"


def test_an_older_row_says_its_entry_price_was_worked_out():
    body = dict(zip(HEADERS, parse([dex_row()])[1]))
    assert body["entry_price_source"] == "estimated from market cap"
    assert body["entry_price_usd"]


def test_a_listed_coin_leaves_the_market_cap_columns_empty():
    body = dict(zip(HEADERS, parse([listed_row()])[1]))
    assert body["entry_market_cap_usd"] == "" and body["current_market_cap_usd"] == ""


def test_the_last_line_totals_the_lot():
    total = parse([dex_row(), listed_row()])[-1]
    assert total[0] == "TOTAL"
    assert dict(zip(HEADERS, total))["value_now_usd"] == "351.67"
    assert dict(zip(HEADERS, total))["profit_usd"] == "41.67"


def test_an_empty_journal_still_produces_a_valid_file():
    assert parse([]) == [HEADERS]


def test_a_coin_with_no_live_price_does_not_break_the_file():
    body = dict(zip(HEADERS, parse([dex_row(value=None, price=None)])[1]))
    assert body["multiple_x"] == "" and body["value_now_usd"] == "" and body["symbol"] == "UTYA"


def test_plain_number_never_uses_exponents():
    assert plain_number(29_732_700.0) == "29732700"
    assert plain_number(0.00000000123) == "0.00000000123"
    assert plain_number(1.23e-9) == "0.00000000123"
    assert plain_number(210.0, 2) == "210"
    assert plain_number(41.666666, 2) == "41.67"
    assert plain_number(None) == "" and plain_number("") == "" and plain_number("abc") == ""


def test_a_gain_of_a_few_cents_is_called_flat_not_plus_zero():
    assert profit_text(0.12) == "flat" and profit_text(-0.12) == "flat"
    assert profit_text(3.5) == "+$3.50" and profit_text(-1234.0) == "-$1,234"


def test_an_entry_price_is_worked_back_from_the_market_cap_ratio():
    row = enrich(dex_row(value=59_465_400.0))          # doubled
    assert round(row["entry_price"], 6) == round(0.02973 / 2, 6)
    assert row["entry_price_estimated"] and round(row["multiple"], 2) == 2.0
