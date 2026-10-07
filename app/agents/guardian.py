"""GuardianAgent: protects what you already hold (your journal).
- take-profit multiples reached (course: take profits in parts)          -> priority 96 (always delivered)
- DEX token's website/Telegram disappeared (course: exit when community leaves) -> priority 96
- down >= X% from entry: reports whether the community is intact (informational) -> priority 72"""
import logging
from datetime import datetime, timezone

from sqlmodel import select

from .. import cream
from ..crypto import coingecko, dexscreener as dx, socials
from ..crypto.http import client
from ..db import session
from ..models import Holding
from ..notifier import esc
from ..text import price as fmt_price
from ..redis_client import r

log = logging.getLogger(__name__)

class GuardianAgent:
    kind = "guardian"

    def __init__(self, name, cfg):
        self.name = name
        self.tp = cfg.get("take_profit_multiples", [2, 3, 5, 10])
        self.dd_alert = cfg.get("drawdown_alert_pct", 30) / 100

    async def run(self):
        with session() as s:
            holdings = s.exec(select(Holding)).all()
        if not holdings:
            return
        async with client() as c:
            prices = {}
            cg_ids = [h.ref for h in holdings if h.kind == "cg"]
            if cg_ids:
                for x in await coingecko.markets(c, ids=cg_ids):
                    prices[x["id"]] = x.get("current_price")
            for h in holdings:
                if h.kind == "cg":
                    await self.check(h, prices.get(h.ref), None)
                else:
                    chain, addr = h.ref.split(":", 1)
                    try:
                        pair = dx.best_pairs(chain, await dx.pairs_for(c, chain, [addr])).get(addr)
                    except Exception as exc:
                        # A fetch failure is not a dead token - skip it, never raise a false alarm.
                        log.warning("[guardian] %s price lookup failed, skipping this run: %s", h.symbol or chain, exc)
                        continue
                    if not pair:
                        await self.check(h, None, {"dead": True, "why": "no trading pair found"})
                        continue
                    b = dx.basics(pair)
                    health = {"dead": False, "why": ""}
                    if b["websites"] and not await socials.website_alive(c, b["websites"][0]):
                        health = {"dead": True, "why": "website is down"}
                    tg = await socials.telegram_members(c, b["telegram"]) if b["telegram"] else None
                    prev_tg = r.get(f"guard:tg:{h.id}")
                    if b["telegram"] and tg is None and prev_tg:
                        health = {"dead": True, "why": "Telegram group disappeared"}
                    if tg is not None:
                        r.set(f"guard:tg:{h.id}", tg)
                    if not (b["websites"] or b["telegram"] or b["twitter"]):
                        health = {"dead": True, "why": "all socials removed"}
                    await self.check(h, b["mcap"], health, b["pair_url"], b["price"])

    async def check(self, h: Holding, value, health, url=None, price=None):
        name = esc(h.symbol or h.ref)
        # Listed coins are tracked on price, DEX tokens on market cap - either way, show the price.
        now = price if price is not None else (value if h.kind == "cg" else None)
        at = f" · now {fmt_price(now)}" if now else ""
        btns = cream.buttons([("📊 Chart", url, None)]) if url else "[]"
        if health and health["dead"]:
            await cream.submit(f"dead:{h.id}", "guardian", 96,
                               f"<b>🚨 {name}: community signal lost</b>{at} — {esc(health['why'])}.\n"
                               "Course rule: when the team/community leaves, exit and move on. Your call.", btns)
        if not value or not h.entry_value:
            return
        mult = value / h.entry_value
        for lvl in self.tp:
            if mult >= lvl and not r.sismember(f"guard:tp:{h.id}", lvl):
                r.sadd(f"guard:tp:{h.id}", lvl)
                await cream.submit(f"tp:{h.id}:{lvl}", "guardian", 96,
                                   f"<b>📈 {name} is {mult:.1f}x from your entry</b>{at} "
                                   f"(${h.usd:,.0f} → ~${h.usd * mult:,.0f})\n"
                                   "Course rule: take profits in parts (not all at once if you're a large holder); "
                                   "recover your initial stake first.", btns)
        if mult <= 1 - self.dd_alert:
            week = datetime.now(timezone.utc).strftime("%G%V")
            state = "community looks intact" if not (health and health["dead"]) else "community signals are gone"
            await cream.submit(f"dd:{h.id}:{week}", "guardian", 72,
                               f"<b>📉 {name} is {1 - mult:.0%} below entry</b>{at} — {state}.\n"
                               "Course: only consider adding if the community is intact and within your plan; "
                               "never more than you can afford to lose.", btns)
