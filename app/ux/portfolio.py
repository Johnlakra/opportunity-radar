"""Live view of the journal: what each holding is worth now, as a multiple and in dollars.

Read-only. Listed coins are tracked on price, DEX tokens on market cap - the same units
the journal stored at entry, which is what the course's spreadsheet does."""
import csv
import io
from collections import defaultdict

from sqlmodel import select

from ..crypto import coingecko, dexscreener as dx
from ..crypto.http import client
from ..db import session
from ..models import Holding


async def dex_quotes(c, refs: list[str]) -> dict[str, dict]:
    """"<chain>:<address>" -> {"mcap": ..., "price": ...}, one batched call per chain.
    Market cap drives the multiple; the price is what identifies the coin at a glance."""
    by_chain = defaultdict(list)
    for ref in refs:
        chain, _, addr = (ref or "").partition(":")
        if chain and addr:
            by_chain[chain].append(addr)
    values = {}
    for chain, addrs in by_chain.items():
        try:
            best = dx.best_pairs(chain, await dx.pairs_for(c, chain, addrs))
        except Exception:
            continue
        for addr, pair in best.items():
            basics = dx.basics(pair)
            values[f"{chain}:{addr}"] = {"mcap": basics["mcap"], "price": basics["price"]}
    return values


async def rows() -> list[dict]:
    with session() as s:
        holdings = s.exec(select(Holding).order_by(Holding.added_at)).all()
    if not holdings:
        return []
    prices, values = {}, {}
    async with client() as c:
        cg_ids = [h.ref for h in holdings if h.kind == "cg"]
        if cg_ids:
            try:
                prices = {x["id"]: x.get("current_price") for x in await coingecko.markets(c, ids=cg_ids)}
            except Exception:
                prices = {}
        dex = [h.ref for h in holdings if h.kind != "cg"]
        if dex:
            values = await dex_quotes(c, dex)
    out = []
    for h in holdings:
        if h.kind == "cg":
            live = live_price = prices.get(h.ref)      # listed coins are tracked on price
        else:
            quote = values.get(h.ref) or {}
            live, live_price = quote.get("mcap"), quote.get("price")
        out.append({"id": h.id, "symbol": h.symbol or h.ref, "usd": h.usd, "entry": h.entry_value,
                    "value": live, "price": live_price,
                    "unit": "price" if h.kind == "cg" else "market cap",
                    "added": h.added_at, "ref": h.ref})
    return out


def csv_bytes(data: list[dict]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "symbol", "usd_in", "entry_value", "current_value", "current_price",
                     "multiple", "unit", "added", "ref"])
    for row in data:
        mult = (row["value"] / row["entry"]) if row.get("value") and row.get("entry") else ""
        writer.writerow([row["id"], row["symbol"], f"{row['usd']:.2f}", f"{row['entry']:.6g}",
                         f"{row['value']:.6g}" if row.get("value") else "",
                         f"{row['price']:.12g}" if row.get("price") else "",
                         f"{mult:.4f}" if mult else "",
                         row["unit"], row["added"].strftime("%Y-%m-%d"), row["ref"]])
    return buf.getvalue().encode("utf-8")
