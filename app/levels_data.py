"""Getting the numbers the level agent needs: live prices, and a year or two of daily bars.

Metals keep their history in the database (it is small and we add to it ourselves each run).
Crypto history is cached in Redis until the next local midnight - it is large, it is free to
re-fetch, and it changes once a day."""
import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import level_store, levels
from .config import settings
from .crypto import binance, coingecko, dexscreener as dx, geckoterminal as gt, metals
from .crypto.chains import CHAINS
from .crypto.http import CG, get_json
from .crypto.regime import CGB, _headers
from .redis_client import r

log = logging.getLogger(__name__)
BARS_KEY = "lv:bars:{}"
BOOTSTRAP_DAYS = 400
GOLD, SILVER = "metal:XAU", "metal:XAG"
MAX_BARS = 1000


# ---------------- caching a day's worth of bars ----------------
def _seconds_to_local_midnight() -> int:
    now = datetime.now(ZoneInfo(settings.timezone))
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=1, second=0, microsecond=0)
    return max(300, int((midnight - now).total_seconds()))


def cached_bars(asset_key: str) -> list[dict] | None:
    raw = r.get(BARS_KEY.format(asset_key))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def cache_bars(asset_key: str, bars: list[dict]) -> None:
    if bars:
        r.set(BARS_KEY.format(asset_key), json.dumps(bars[-MAX_BARS:]), ex=_seconds_to_local_midnight())


# ---------------- metals ----------------
async def metal_history(c, asset_key: str, bootstrap_silver: bool) -> list[dict]:
    """Rupee-per-gram bars. Bootstrapped once, then topped up by our own live polls."""
    if level_store.has_bootstrap(asset_key):
        return level_store.load_bars(asset_key)
    if asset_key == GOLD:
        usd_bars = await metals.gold_history(c)
    elif bootstrap_silver:
        usd_bars = await metals.silver_history(c)
    else:
        return []
    if not usd_bars:
        return []
    start, end = metals.history_window(usd_bars, BOOTSTRAP_DAYS)
    rates = await metals.fx_history(c, start, end)
    inr_bars = metals.to_inr_bars(usd_bars, rates)
    level_store.save_bars(asset_key, inr_bars, "INR", own=False)
    log.info("[levels] bootstrapped %d bars for %s", len(inr_bars), asset_key)
    return level_store.load_bars(asset_key)


async def metal_quote(c) -> dict | None:
    """Live gold, silver and the rupee rate - or None when the feed is stale."""
    return await metals.spot(c)


# ---------------- listed coins ----------------
async def cg_history(c, coin_id: str, symbol: str) -> tuple[list[dict], bool]:
    """(bars, exact). Binance gives real daily highs and lows; CoinGecko only gives closes,
    so levels built from it are approximate and the alert says so."""
    cached = cached_bars(f"cg:{coin_id}")
    if cached is not None:
        return cached, bool(cached and cached[0].get("exact", True))
    bars = await binance.daily_bars(c, symbol)
    exact = bool(bars)
    if not bars:
        bars = await _cg_closes(c, coin_id)
    for bar in bars:
        bar["exact"] = exact
    cache_bars(f"cg:{coin_id}", bars)
    return bars, exact


async def _cg_closes(c, coin_id: str) -> list[dict]:
    """A year of daily closes, used as high=low=close. Never as good as real candles."""
    try:
        chart = await get_json(c, f"{CGB}/coins/{coin_id}/market_chart", CG, headers=_headers(),
                               params={"vs_currency": "usd", "days": 365, "interval": "daily"})
    except Exception as exc:
        log.info("[levels] no history for %s: %s", coin_id, exc)
        return []
    bars = []
    for stamp, close in chart.get("prices") or []:
        try:
            day = datetime.utcfromtimestamp(stamp / 1000).date().isoformat()
            price = float(close)
        except (TypeError, ValueError, OSError):
            continue
        if price > 0:
            bars.append({"day": day, "o": price, "h": price, "l": price, "c": price})
    bars.sort(key=lambda b: b["day"])
    return bars


async def cg_prices(c, coin_ids: list[str]) -> dict[str, dict]:
    """One call for every listed coin you watch."""
    if not coin_ids:
        return {}
    try:
        rows = await coingecko.markets(c, ids=coin_ids)
    except Exception as exc:
        log.warning("[levels] CoinGecko prices failed: %s", exc)
        return {}
    return {x["id"]: {"price": x.get("current_price"), "symbol": (x.get("symbol") or "").upper(),
                      "mcap": x.get("market_cap")} for x in rows}


# ---------------- DEX tokens ----------------
async def dex_quotes(c, refs: list[str]) -> dict[str, dict]:
    """"<chain>:<address>" -> {price, mcap, url, pool}, batched per chain."""
    from collections import defaultdict
    by_chain = defaultdict(list)
    for ref in refs:
        chain, _, addr = ref.partition(":")
        if chain in CHAINS and addr:
            by_chain[chain].append(addr)
    out = {}
    for chain, addrs in by_chain.items():
        try:
            best = dx.best_pairs(chain, await dx.pairs_for(c, chain, addrs))
        except Exception as exc:
            log.warning("[levels] DexScreener %s failed: %s", chain, exc)
            continue
        for addr, pair in best.items():
            basics = dx.basics(pair)
            out[f"{chain}:{addr}"] = {"price": basics["price"], "mcap": basics["mcap"],
                                      "url": basics["pair_url"], "pool": basics["pool"],
                                      "symbol": basics["symbol"]}
    return out


async def dex_history(c, ref: str, pool: str) -> list[dict]:
    chain, _, _addr = ref.partition(":")
    cached = cached_bars(f"dex:{ref}")
    if cached is not None:
        return cached
    network = (CHAINS.get(chain) or {}).get("gecko")
    bars = []
    if network and pool:
        try:
            bars = levels.bars_from_ohlcv(await gt.ohlcv(c, network, pool, "day", 1, MAX_BARS))
        except Exception as exc:
            log.info("[levels] no candles for %s: %s", ref, exc)
    cache_bars(f"dex:{ref}", bars)
    return bars
