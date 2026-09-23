"""LevelWatchAgent: alerts when something breaks the previous week/month/quarter/year high or low.

Gold and silver in rupees, every coin in your journal, and anything else you add from /alerts.
A level only counts once its period is COMPLETE, and a level that moved because the calendar
rolled over is never treated as a break. Alert-only, like everything else here."""
import logging
from collections import defaultdict

from .. import cream, level_store, levels, levels_data
from ..config import settings
from ..crypto.http import client
from ..models import Holding
from ..redis_client import r
from ..ux import level_cards

log = logging.getLogger(__name__)
PAUSED_KEY = "lv:paused:{}"   # pausing is per person, so one pause never silences the other
SIDE_KEY = "lv:side"
STALE_LOG_KEY = "lv:stale-logged"
DEFAULT_BUFFER = {"metal": 0.1, "cg": 0.5, "dex": 1.0}
DEFAULT_PRIORITY = 95
def paused(chat_id: str) -> bool:
    return bool(r.exists(PAUSED_KEY.format(chat_id)))


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
        made = level_store.seed_metals(self.metals_periods, settings.level_chat_ids)
        added, gone = level_store.sync_journal(self.journal_periods, settings.chat_ids)
        if made or added or gone:
            log.info("[levels] seeded %d, journal +%d, %d switched off", made, added, gone)

        # One row per person per asset, but the price and the history are fetched once per asset.
        assets = {"metal": defaultdict(list), "cg": defaultdict(list), "dex": defaultdict(list)}
        for sub in level_store.all_subs(active_only=True):
            if level_store.periods_of(sub):
                kind = sub.asset_key.split(":", 1)[0]
                if kind in assets:
                    assets[kind][sub.asset_key].append(sub)
        async with client() as c:
            for kind, handler in (("metal", self.check_metals), ("cg", self.check_listed),
                                  ("dex", self.check_dex)):
                if not assets[kind]:
                    continue
                try:
                    await handler(c, assets[kind])
                except Exception as exc:               # one bad feed must not stop the others
                    log.error("[levels] %s failed: %s", kind, exc, exc_info=True)

    # ---------------- gold and silver ----------------
    async def check_metals(self, c, assets):
        quote = await levels_data.metal_quote(c)
        if not quote:
            if r.set(STALE_LOG_KEY, 1, nx=True, ex=3600):
                log.warning("[levels] metals feed is stale or unavailable — skipping this run")
            return
        r.delete(STALE_LOG_KEY)
        today = level_store.local_today().isoformat()
        for asset_key, subs in assets.items():
            usd = quote["gold_usd_oz"] if asset_key == levels_data.GOLD else quote["silver_usd_oz"]
            if not usd:
                continue
            per_gram = levels.inr_per_gram(usd, quote["usd_inr"])
            bars = await levels_data.metal_history(c, asset_key, self.bootstrap_silver)
            level_store.record_live(asset_key, today, per_gram, "INR")
            await self.check(asset_key, subs, per_gram, bars, chart=CHART.get(asset_key))

    # ---------------- listed coins ----------------
    async def check_listed(self, c, assets):
        ids = [key.split(":", 1)[1] for key in assets]
        live = await levels_data.cg_prices(c, ids)
        for asset_key, subs in assets.items():
            coin_id = asset_key.split(":", 1)[1]
            quote = live.get(coin_id) or {}
            price = quote.get("price")
            if not price:
                continue
            label = quote.get("symbol") or subs[0].label
            bars, exact = await levels_data.cg_history(c, coin_id, label)
            await self.check(asset_key, subs, price, bars, approximate=not exact,
                             chart=f"https://www.coingecko.com/en/coins/{coin_id}",
                             extra=self.holding_lines(asset_key, price))

    # ---------------- DEX tokens ----------------
    async def check_dex(self, c, assets):
        refs = [key.split(":", 1)[1] for key in assets]
        quotes = await levels_data.dex_quotes(c, refs)
        for asset_key, subs in assets.items():
            ref = asset_key.split(":", 1)[1]
            quote = quotes.get(ref) or {}
            price = quote.get("price")
            if not price:
                continue
            bars = await levels_data.dex_history(c, ref, quote.get("pool", ""))
            extra = self.holding_lines(asset_key, quote.get("mcap"))
            if quote.get("mcap"):
                extra.insert(0, f"Market cap {level_cards.money(quote['mcap'])} "
                                "— the course watches this, not the price")
            await self.check(asset_key, subs, price, bars, chart=quote.get("url"), extra=extra)

    # ---------------- the shared crossing check ----------------
    def buffer_for(self, asset_key: str) -> float:
        return float(self.buffer.get(asset_key.split(":", 1)[0], 0.5))

    async def check(self, asset_key, subs, price, bars, chart=None, extra=None, approximate=False):
        """Whether the price crossed is a fact about the market, so it is worked out once.
        Who hears about it is a question per person, so that part loops over the subscribers."""
        today = level_store.local_today()
        wanted = {p for sub in subs for p in level_store.periods_of(sub)}
        found = {}
        for period in sorted(wanted):
            hl = levels.prev_period_hl(bars, period, today)
            if hl:
                found[period] = hl
        for period, (high, low) in found.items():
            pid = levels.period_id(today, period)
            for direction, level in (("up", high), ("down", low)):
                listeners = [s for s in subs
                             if level_store.wants(s, period, direction) and not paused(s.chat_id)]
                if not listeners:
                    continue
                field = levels.state_field(asset_key, period, direction)
                alert, state = levels.decide(r.hget(SIDE_KEY, field), pid, price, level,
                                             direction, self.buffer_for(asset_key))
                r.hset(SIDE_KEY, field, state)
                if not alert:
                    continue
                for sub in listeners:
                    await self.announce(sub, period, direction, price, level, found, pid,
                                        chart, extra, approximate)

    async def announce(self, sub, period, direction, price, level, found, pid,
                       chart, extra, approximate):
        """One message, addressed to the one person whose subscription it is."""
        mine = {p: hl for p, hl in found.items() if p in level_store.periods_of(sub)}
        text = level_cards.break_card(sub.label, sub.asset_key, period, direction, price, level,
                                      mine, sub.source, self.premium, extra, approximate)
        buttons = cream.buttons(
            [("📈 Chart", chart, None), ("📊 Levels", None, f"lv:s:{sub.id}")],
            [("🔕 Turn off this", None, f"lv:t:{sub.id}:{period}")])
        await cream.submit(levels.alert_key(f"{sub.chat_id}:{sub.asset_key}", period, pid, direction),
                           "levels", int(self.priority.get(period, DEFAULT_PRIORITY)), text, buttons,
                           chat_ids=[sub.chat_id])
        log.info("[levels] %s broke %s %s -> chat %s", sub.asset_key, direction, period, sub.chat_id)

    # ---------------- your journal, when the coin is in it ----------------
    def holding_lines(self, asset_key, current_value) -> list[str]:
        from ..db import session
        from sqlmodel import select
        ref = asset_key.split(":", 1)[1]
        kind = "cg" if asset_key.startswith("cg:") else "dex"
        with session() as s:
            holding = s.exec(select(Holding).where(Holding.ref == ref, Holding.kind == kind)).first()
        if not holding:
            return []
        unit = "price" if kind == "cg" else "market cap"
        return [level_cards.holding_line(holding.symbol, holding.entry_value, current_value, unit)]
