"""Live view of the journal: what each holding is worth now, and a spreadsheet you can open.

Read-only. Listed coins are tracked on price, DEX tokens on market cap - the same units the
journal stored at entry, which is what the course's spreadsheet does. The numbering you see
(#1, #2, #3) is the position in this list, so removing one never leaves a gap; the database
id travels inside the buttons, where it cannot be mistyped."""
import csv
import io
from collections import defaultdict
from datetime import datetime, timezone

from ..crypto import coingecko, dexscreener as dx
from ..crypto.http import client
from ..journal import holdings_in_order
from .cards import enrich
from .journal_csv import csv_bytes            # noqa: F401  (re-exported: callers use portfolio.csv_bytes)

COINGECKO_URL = "https://www.coingecko.com/en/coins/{}"


async def dex_quotes(c, refs: list[str]) -> dict[str, dict]:
    """"<chain>:<address>" -> {"mcap", "price", "url"}, one batched call per chain."""
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
            values[f"{chain}:{addr}"] = {"mcap": basics["mcap"], "price": basics["price"],
                                         "url": basics["pair_url"]}
    return values


async def rows() -> list[dict]:
    """Oldest first, numbered from 1. Every derived figure is added by cards.enrich()."""
    holdings = holdings_in_order()
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
    now = datetime.now(timezone.utc)
    out = []
    for position, h in enumerate(holdings, start=1):
        if h.kind == "cg":
            live = live_price = prices.get(h.ref)      # listed coins are tracked on price
            chain, link = "", COINGECKO_URL.format(h.ref)
        else:
            quote = values.get(h.ref) or {}
            live, live_price = quote.get("mcap"), quote.get("price")
            chain, link = h.ref.partition(":")[0], quote.get("url", "")
        added = h.added_at if h.added_at.tzinfo else h.added_at.replace(tzinfo=timezone.utc)
        out.append(enrich({
            "n": position, "id": h.id, "symbol": h.symbol or h.ref, "chain": chain, "kind": h.kind,
            "usd": h.usd, "entry": h.entry_value, "entry_price": h.entry_price,
            "value": live, "price": live_price,
            "unit": "price" if h.kind == "cg" else "market cap",
            "added": added, "days_held": (now - added).days, "ref": h.ref, "link": link,
        }))
    return out
