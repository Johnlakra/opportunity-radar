"""LevelWatchAgent: alerts when something breaks the previous week/month/quarter/year high or low.

Gold and silver in rupees, every coin in your journal, and anything else you add from /alerts.
A level only counts once its period is COMPLETE, and a level that moved because the calendar
rolled over is never treated as a break. Alert-only, like everything else here."""
import logging

from .. import cream, level_store, levels, levels_data
from ..crypto.http import client
from ..models import Holding
from ..redis_client import r
from ..ux import level_cards

log = logging.getLogger(__name__)
PAUSED_KEY = "lv:paused"
SIDE_KEY = "lv:side"
STALE_LOG_KEY = "lv:stale-logged"
DEFAULT_BUFFER = {"metal": 0.1, "cg": 0.5, "dex": 1.0}
DEFAULT_PRIORITY = 95
CHART = {"metal:XAU": "https://www.tradingview.com/chart/?symbol=OANDA%3AXAUUSD",
         "metal:XAG": "https://www.tradingview.com/chart/?symbol=OANDA%3AXAGUSD"}


class LevelWatchAgent:
    kind = "level_watch"

    def __init__(self, name, cfg):
        self.name = name
        self.metals_periods = cfg.get("metals_periods", "WMQY")
        self.journal_periods = cfg.get("journal_periods", "MQY")
        self.buffer = {**DEFAULT_BUFFER, **(cfg.get("buffer_pct") or {})}
        self.priority = cfg.get("priority") or {}
        self.premium = float(cfg.get("inr_premium_pct", 0) or 0)
        self.bootstrap_silver = bool(cfg.get("bootstrap_silver_from_yahoo", True))

    # ---------------- run ----------------
    async def run(self):
        if r.exists(PAUSED_KEY):
            log.info("[levels] paused")
            return
        level_store.seed_metals(self.metals_periods)
        added, gone = level_store.sync_journal(self.journal_periods)
        if added or gone:
            log.info("[levels] journal sync: +%d, %d switched off", added, gone)
        subs = [s for s in level_store.all_subs(active_only=True) if level_store.periods_of(s)]
        groups = {"metal": [], "cg": [], "dex": []}
        for sub in subs:
            groups.get(sub.asset_key.split(":", 1)[0], []).append(sub)
        async with client() as c:
            for kind, handler in (("metal", self.check_metals), ("cg", self.check_listed),
                                  ("dex", self.check_dex)):
                if not groups[kind]:
                    continue
                try:
                    await handler(c, groups[kind])
                except Exception as exc:                   # one bad feed must not stop the others
                    log.error("[levels] %s failed: %s", kind, exc, exc_info=True)

    # ---------------- gold and silver ----------------
    async def check_metals(self, c, subs):
        quote = await levels_data.metal_quote(c)
        if not quote:
            if r.set(STALE_LOG_KEY, 1, nx=True, ex=3600):
                log.warning("[levels] metals feed is stale or unavailable — skipping this run")
            return
        r.delete(STALE_LOG_KEY)
        today = level_store.local_today().isoformat()
        for sub in subs:
            usd = quote["gold_usd_oz"] if sub.asset_key == levels_data.GOLD else quote["silver_usd_oz"]
            if not usd:
                continue
            per_gram = levels.inr_per_gram(usd, quote["usd_inr"])
            bars = await levels_data.metal_history(c, sub.asset_key, self.bootstrap_silver)
            level_store.record_live(sub.asset_key, today, per_gram, "INR")
            await self.check(sub, per_gram, bars, chart=CHART.get(sub.asset_key))

    # ---------------- listed coins ----------------
    async def check_listed(self, c, subs):
        ids = [s.asset_key.split(":", 1)[1] for s in subs]
        live = await levels_data.cg_prices(c, ids)
        for sub in subs:
            coin_id = sub.asset_key.split(":", 1)[1]
            quote = live.get(coin_id) or {}
            price = quote.get("price")
            if not price:
                continue
            bars, exact = await levels_data.cg_history(c, coin_id, quote.get("symbol") or sub.label)
            await self.check(sub, price, bars, approximate=not exact,
                             chart=f"https://www.coingecko.com/en/coins/{coin_id}",
                             extra=self.holding_lines(sub, price))

    # ---------------- DEX tokens ----------------
    async def check_dex(self, c, subs):
        refs = [s.asset_key.split(":", 1)[1] for s in subs]
        quotes = await levels_data.dex_quotes(c, refs)
        for sub in subs:
            ref = sub.asset_key.split(":", 1)[1]
            quote = quotes.get(ref) or {}
            price = quote.get("price")
            if not price:
                continue
            bars = await levels_data.dex_history(c, ref, quote.get("pool", ""))
            extra = self.holding_lines(sub, quote.get("mcap"))
            if quote.get("mcap"):
                extra.insert(0, f"Market cap {level_cards.money(quote['mcap'])} "
                                "— the course watches this, not the price")
            await self.check(sub, price, bars, chart=quote.get("url"), extra=extra)

    # ---------------- the shared crossing check ----------------
    def buffer_for(self, asset_key: str) -> float:
        return float(self.buffer.get(asset_key.split(":", 1)[0], 0.5))

    async def check(self, sub, price, bars, chart=None, extra=None, approximate=False):
        today = level_store.local_today()
        found = {}
        for period in level_store.periods_of(sub):
            hl = levels.prev_period_hl(bars, period, today)
            if hl:
                found[period] = hl
        for period, (high, low) in found.items():
            pid = levels.period_id(today, period)
            for direction, level in (("up", high), ("down", low)):
                if direction not in level_store.directions_of(sub):
                    continue
                field = levels.state_field(sub.asset_key, period, direction)
                alert, state = levels.decide(r.hget(SIDE_KEY, field), pid, price, level,
                                             direction, self.buffer_for(sub.asset_key))
                r.hset(SIDE_KEY, field, state)
                if alert:
                    await self.announce(sub, period, direction, price, level, found, pid,
                                        chart, extra, approximate)

    async def announce(self, sub, period, direction, price, level, found, pid,
                       chart, extra, approximate):
        text = level_cards.break_card(sub.label, sub.asset_key, period, direction, price, level,
                                      found, sub.source, self.premium, extra, approximate)
        buttons = cream.buttons(
            [("📈 Chart", chart, None), ("📊 Levels", None, f"lv:s:{sub.id}")],
            [("🔕 Turn off this", None, f"lv:t:{sub.id}:{period}")])
        await cream.submit(levels.alert_key(sub.asset_key, period, pid, direction), "levels",
                           int(self.priority.get(period, DEFAULT_PRIORITY)), text, buttons)
        log.info("[levels] %s broke %s %s", sub.asset_key, direction, period)

    # ---------------- your journal, when the coin is in it ----------------
    def holding_lines(self, sub, current_value) -> list[str]:
        from ..db import session
        from sqlmodel import select
        ref = sub.asset_key.split(":", 1)[1]
        kind = "cg" if sub.asset_key.startswith("cg:") else "dex"
        with session() as s:
            holding = s.exec(select(Holding).where(Holding.ref == ref, Holding.kind == kind)).first()
        if not holding:
            return []
        unit = "price" if kind == "cg" else "market cap"
        return [level_cards.holding_line(holding.symbol, holding.entry_value, current_value, unit)]
