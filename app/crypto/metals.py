"""Gold and silver in rupees, from keyless sources.

xaus.com gives live spot and a daily XAU/USD history; frankfurter gives the daily USD-INR rate;
Yahoo's chart endpoint (unofficial, optional) backfills silver. Everything is parsed defensively -
a metals outage must never take the rest of the radar down with it."""
from datetime import date, datetime, timedelta, timezone

import httpx

from .http import FX, XAUS, YF, get_json

SPOT_URL = "https://xaus.com/api/v1/spot"
HISTORY_URL = "https://xaus.com/api/v1/history"
FX_URL = "https://api.frankfurter.dev/v1/{start}..{end}"          # api.frankfurter.app redirects here
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
SILVER_SYMBOL = "SI=F"
GOLD_SYMBOL = "GC=F"
USD_INR_SYMBOL = "INR=X"
MAX_SPOT_AGE_SEC = 600
# Yahoo is the fallback when xaus.com runs out of keyless quota. Its quotes lag ~10 minutes,
# so it gets a wider window; the rupee rate moves slowly and may be up to a day old.
YAHOO_MAX_AGE_SEC = 1800
YAHOO_FX_MAX_AGE_SEC = 86400
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (compatible; opportunity-radar/0.4; personal)"}


def _number(value):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out > 0 else None


def parse_spot(payload: dict, max_age_sec: int = MAX_SPOT_AGE_SEC, now=None) -> dict | None:
    """Live gold, silver and USD-INR. None when the feed says it is not fresh - a level break
    called on a stale quote is worse than no alert at all."""
    payload = payload or {}
    state = payload.get("data_state") or {}
    if str(state.get("status", "")).lower() != "fresh":
        return None
    age = _age_seconds(payload.get("updated_at") or state.get("as_of"), now)
    if age is None or age > max_age_sec:
        return None
    gold, silver, fx = (_number(payload.get("spot_usd_oz")), _number(payload.get("silver_usd_oz")),
                        _number(payload.get("fx_rate")))
    if not (gold and fx):
        return None
    return {"gold_usd_oz": gold, "silver_usd_oz": silver, "usd_inr": fx,
            "as_of": payload.get("updated_at"), "age_seconds": age}


def _age_seconds(stamp, now=None) -> float | None:
    if not stamp:
        return None
    try:
        moment = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return max(0.0, ((now or datetime.now(timezone.utc)) - moment).total_seconds())


def parse_history(payload: dict) -> list[dict]:
    """Daily XAU/USD bars, oldest first. The feed has no open, so the close stands in for it."""
    bars = []
    for point in (payload or {}).get("points") or []:
        day, high, low, close = (point.get("d"), _number(point.get("h")),
                                 _number(point.get("l")), _number(point.get("c")))
        if not (day and high and low and close):
            continue
        bars.append({"day": str(day)[:10], "o": close, "h": high, "l": low, "c": close})
    bars.sort(key=lambda b: b["day"])
    return bars


def parse_fx(payload: dict) -> dict[str, float]:
    """{"YYYY-MM-DD": rate}. Frankfurter only publishes on business days."""
    out = {}
    for day, rates in ((payload or {}).get("rates") or {}).items():
        rate = _number((rates or {}).get("INR"))
        if rate:
            out[str(day)[:10]] = rate
    return out


def parse_yahoo_price(payload: dict, now=None) -> tuple[float, float] | None:
    """(last price, age in seconds) from Yahoo's chart metadata, or None."""
    try:
        meta = (payload or {})["chart"]["result"][0]["meta"]
    except (KeyError, IndexError, TypeError):
        return None
    price, stamp = _number(meta.get("regularMarketPrice")), meta.get("regularMarketTime")
    if not price or not isinstance(stamp, (int, float)):
        return None
    moment = datetime.fromtimestamp(stamp, timezone.utc)
    return price, max(0.0, ((now or datetime.now(timezone.utc)) - moment).total_seconds())


def parse_yahoo(payload: dict) -> list[dict]:
    """Daily bars from Yahoo's chart endpoint. Unofficial, so every field is treated as optional."""
    try:
        result = (payload or {})["chart"]["result"][0]
        stamps = result["timestamp"]
        quote = result["indicators"]["quote"][0]
    except (KeyError, IndexError, TypeError):
        return []
    bars = []
    for i, stamp in enumerate(stamps or []):
        high, low = _number(_at(quote.get("high"), i)), _number(_at(quote.get("low"), i))
        close = _number(_at(quote.get("close"), i))
        if not (high and low and close):
            continue
        bars.append({"day": datetime.fromtimestamp(stamp, timezone.utc).date().isoformat(),
                     "o": _number(_at(quote.get("open"), i)) or close,
                     "h": high, "l": low, "c": close})
    bars.sort(key=lambda b: b["day"])
    return bars


def _at(series, index):
    try:
        return series[index]
    except (TypeError, IndexError):
        return None


def to_inr_bars(usd_bars: list[dict], fx_by_day: dict[str, float]) -> list[dict]:
    """Convert USD-per-ounce bars to INR per gram, using each day's rate.

    Currency markets close at weekends while metals history does not, so the last known rate is
    carried forward. Bars before the first known rate are dropped rather than guessed."""
    from ..levels import inr_per_gram
    out, rate = [], None
    for bar in sorted(usd_bars, key=lambda b: b["day"]):
        rate = fx_by_day.get(bar["day"], rate)
        if not rate:
            continue
        out.append({"day": bar["day"], "currency": "INR",
                    **{key: inr_per_gram(bar[key], rate) for key in ("o", "h", "l", "c")}})
    return out


# ---------------- fetching ----------------
async def spot(c, currency: str = "INR") -> dict | None:
    """Live gold, silver and USD-INR: xaus.com first, Yahoo when it is down or out of quota.
    None when neither has a fresh quote - the caller treats that as stale and skips the run."""
    try:
        payload = await get_json(c, SPOT_URL, XAUS,
                                 params={"currency": currency, "unit": "gram", "compact": 1})
    except httpx.HTTPError:
        payload = None
    return parse_spot(payload) or await yahoo_spot(c)


async def _yahoo_price(c, symbol: str, max_age: float) -> float | None:
    try:
        payload = await get_json(c, YAHOO_URL.format(symbol=symbol), YF,
                                 params={"range": "1d", "interval": "5m"}, headers=BROWSER_UA)
    except httpx.HTTPError:
        return None
    found = parse_yahoo_price(payload)
    return found[0] if found and found[1] <= max_age else None


async def yahoo_spot(c) -> dict | None:
    """COMEX front-month futures - the same series silver's history already comes from."""
    gold = await _yahoo_price(c, GOLD_SYMBOL, YAHOO_MAX_AGE_SEC)
    fx = await _yahoo_price(c, USD_INR_SYMBOL, YAHOO_FX_MAX_AGE_SEC) if gold else None
    if not (gold and fx):
        return None
    silver = await _yahoo_price(c, SILVER_SYMBOL, YAHOO_MAX_AGE_SEC)
    return {"gold_usd_oz": gold, "silver_usd_oz": silver, "usd_inr": fx,
            "as_of": datetime.now(timezone.utc).isoformat(), "age_seconds": None, "source": "yahoo"}


async def gold_history(c) -> list[dict]:
    """xaus.com daily history, or Yahoo's gold futures when xaus.com is down or out of quota."""
    try:
        bars = parse_history(await get_json(c, HISTORY_URL, XAUS))
    except httpx.HTTPError:
        bars = []
    return bars or await _yahoo_history(c, GOLD_SYMBOL)


async def fx_history(c, start: date, end: date) -> dict[str, float]:
    url = FX_URL.format(start=start.isoformat(), end=end.isoformat())
    return parse_fx(await get_json(c, url, FX, params={"from": "USD", "to": "INR"}))


async def silver_history(c, span: str = "2y") -> list[dict]:
    """Unofficial endpoint, gated by config. Returns [] on any problem."""
    return await _yahoo_history(c, SILVER_SYMBOL, span)


async def _yahoo_history(c, symbol: str, span: str = "2y") -> list[dict]:
    try:
        payload = await get_json(c, YAHOO_URL.format(symbol=symbol), YF,
                                 params={"range": span, "interval": "1d"}, headers=BROWSER_UA)
    except Exception:
        return []
    return parse_yahoo(payload)


def history_window(bars: list[dict], days: int = 400) -> tuple[date, date]:
    """The date range to ask the currency API for, given the metal bars we have."""
    if not bars:
        today = datetime.now(timezone.utc).date()
        return today - timedelta(days=days), today
    return date.fromisoformat(bars[0]["day"]), date.fromisoformat(bars[-1]["day"])
