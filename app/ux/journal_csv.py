"""The journal as a spreadsheet.

Plain decimal numbers only - a market cap written as 2.97327E+07 is unreadable in a cell, and
a memecoin price written as 1.23E-09 is worse. Pure: it takes rows and returns bytes."""
import csv
import io

from ..text import plain_number
from .cards import enrich

MONEY_DP = 2
PRICE_DP = 12
HEADERS = ["#", "journal_id", "symbol", "chain", "tracked_on", "date_added", "days_held",
           "amount_invested_usd", "entry_price_usd", "entry_price_source",
           "entry_market_cap_usd", "current_price_usd", "current_market_cap_usd",
           "multiple_x", "value_now_usd", "profit_usd", "profit_pct", "link"]


def _money(value) -> str:
    return plain_number(value, MONEY_DP)


def _row(row: dict) -> list:
    by_price = row["unit"] == "price"          # listed coins have no market cap to show
    return [
        row.get("n", ""), row.get("id", ""), row["symbol"], row.get("chain", ""), row["unit"],
        row["added"].strftime("%Y-%m-%d") if row.get("added") else "", row.get("days_held", ""),
        _money(row["usd"]),
        plain_number(row["entry_price"], PRICE_DP),
        ("estimated from market cap" if row["entry_price_estimated"]
         else ("recorded" if row["entry_price"] else "")),
        "" if by_price else _money(row["entry"]),
        plain_number(row.get("price"), PRICE_DP),
        "" if by_price else _money(row.get("value")),
        plain_number(row["multiple"], 4),
        _money(row["value_now"]),
        _money(row["profit"]),
        plain_number(row["profit_pct"], 2),
        row.get("link", ""),
    ]


def csv_bytes(data: list[dict]) -> bytes:
    """A spreadsheet, not a data dump: one line per holding, then a TOTAL line."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(HEADERS)
    invested = worth = 0.0
    for raw in data:
        row = enrich(raw)
        invested += row["usd"]
        worth += row["value_now"] if row["value_now"] is not None else row["usd"]
        writer.writerow(_row(row))
    if data:
        writer.writerow([])
        writer.writerow(["TOTAL", "", "", "", "", "", "", _money(invested), "", "", "", "", "", "",
                         _money(worth), _money(worth - invested),
                         plain_number(((worth / invested) - 1) * 100 if invested else None, 2), ""])
    return buf.getvalue().encode("utf-8")
