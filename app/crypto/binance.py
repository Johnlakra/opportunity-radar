"""Daily candles for listed coins, from Binance's public data mirror (no key, no account).

Days are UTC, because that is what the exchange reports. A period boundary can therefore differ
by one bar from a local-midnight view; for week/month/quarter/year highs that is noise."""
from datetime import datetime, timezone

from .http import BINANCE, get_json

KLINES_URL = "https://data-api.binance.vision/api/v3/klines"
QUOTE = "USDT"
MAX_BARS = 1000
# Symbols whose Binance ticker is not simply the CoinGecko symbol uppercased.
SYMBOL_FIXES = {"IOTA": "IOTA", "MIOTA": "IOTA", "WBTC": "WBTC", "WETH": "ETH"}


def symbol_for(ticker: str) -> str:
    ticker = (ticker or "").strip().upper()
    return (SYMBOL_FIXES.get(ticker, ticker) + QUOTE) if ticker else ""


def parse_klines(rows) -> list[dict]:
    """[[open_time, o, h, l, c, ...], ...] -> daily bars, oldest first."""
    bars = []
    for row in rows or []:
        try:
            day = datetime.fromtimestamp(row[0] / 1000, timezone.utc).date().isoformat()
            bar = {"day": day, "o": float(row[1]), "h": float(row[2]),
                   "l": float(row[3]), "c": float(row[4])}
        except (IndexError, TypeError, ValueError):
            continue
        if bar["h"] > 0 and bar["l"] > 0:
            bars.append(bar)
    bars.sort(key=lambda b: b["day"])
    return bars


async def daily_bars(c, ticker: str, limit: int = MAX_BARS) -> list[dict]:
    """Returns [] when the coin is not listed against USDT - the caller falls back to CoinGecko."""
    symbol = symbol_for(ticker)
    if not symbol:
        return []
    try:
        rows = await get_json(c, KLINES_URL, BINANCE,
                              params={"symbol": symbol, "interval": "1d", "limit": min(limit, MAX_BARS)})
    except Exception:
        return []
    return parse_klines(rows)
