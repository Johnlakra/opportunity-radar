"""Bitcoin market regime from the cheat sheet. Pure logic + a cached fetch.
States: UP_LEG | SECOND_LEG_UP | CORRECTION_WAIT | ACCUMULATE | RANGING
Soft bias only: seasonality and 4-year-cycle patterns are weak evidence."""
import json
from datetime import datetime, timezone

from ..config import settings
from ..redis_client import r
from .http import CG, client, get_json

CGB = "https://api.coingecko.com/api/v3"
DEFAULTS = {"near_high_pct": 0.07, "upleg_30d": 0.10, "min_correction": 0.10, "min_down_legs": 2,
            "leg_drop": 0.08, "leg_bounce": 0.04, "leg_rise": 0.15, "leg_pullback": 0.08,
            "wait_days": 21, "summer_wait_days": 90, "summer_months": [5, 6, 7, 8, 9]}

ADVICE = {
    "UP_LEG": "Profit-taking section (cheat sheet #10, #12): don't add; the rules say take profits in parts.",
    "SECOND_LEG_UP": "Second leg up (cheat sheet #12): the course says go completely flat.",
    "CORRECTION_WAIT": "Correction in progress: the rules say wait for ≥2 large down-legs and time to pass (#4).",
    "ACCUMULATE": "Accumulation conditions met (≥2 down-legs, waited): DCA zone, never >50% at once (#5, #6).",
    "RANGING": "No clear signal: be patient, keep DCA small if at all (#8).",
}


def count_down_legs(prices, drop, bounce):
    legs, peak, trough, in_leg = 0, prices[0], prices[0], False
    for p in prices[1:]:
        if not in_leg:
            peak = max(peak, p)
            if p <= peak * (1 - drop):
                legs, in_leg, trough = legs + 1, True, p
        else:
            trough = min(trough, p)
            if p >= trough * (1 + bounce):
                in_leg, peak = False, p
    return legs


def count_up_legs(prices, rise, pullback):
    legs, trough, peak, in_leg = 0, prices[0], prices[0], False
    for p in prices[1:]:
        if not in_leg:
            trough = min(trough, p)
            if p >= trough * (1 + rise):
                legs, in_leg, peak = legs + 1, True, p
        else:
            peak = max(peak, p)
            if p <= peak * (1 - pullback):
                in_leg, trough = False, p
    return legs


def classify(prices: list[float], month: int, dom_hist: list[float] | None = None, cfg: dict | None = None) -> dict:
    c = {**DEFAULTS, **(cfg or {})}
    w = prices[-180:]
    hi, lo = max(w), min(w)
    hi_i = len(w) - 1 - w[::-1].index(hi)
    lo_i = len(w) - 1 - w[::-1].index(lo)
    last = w[-1]
    dd = last / hi - 1
    days_since_top = len(w) - 1 - hi_i
    down_legs = count_down_legs(w[hi_i:], c["leg_drop"], c["leg_bounce"])
    up_legs = count_up_legs(w[lo_i:], c["leg_rise"], c["leg_pullback"])
    chg30 = last / w[-31] - 1 if len(w) > 31 else 0.0
    chg7 = last / w[-8] - 1 if len(w) > 8 else 0.0
    wait = c["summer_wait_days"] if month in c["summer_months"] else c["wait_days"]
    dom_delta = (dom_hist[-1] - dom_hist[-14]) if dom_hist and len(dom_hist) >= 14 else None

    if dd > -c["near_high_pct"] and chg30 > c["upleg_30d"]:
        state = "SECOND_LEG_UP" if up_legs >= 2 else "UP_LEG"
    elif dd <= -c["min_correction"] and down_legs >= c["min_down_legs"] and days_since_top >= wait:
        state = "ACCUMULATE"
    elif dd <= -c["min_correction"]:
        state = "CORRECTION_WAIT"
    else:
        state = "RANGING"
    return {"state": state, "price": last, "drawdown": dd, "days_since_top": days_since_top,
            "down_legs": down_legs, "up_legs": up_legs, "wait_days": wait, "chg7": chg7, "chg30": chg30,
            "dominance": dom_hist[-1] if dom_hist else None, "dom_delta_14d": dom_delta,
            "altseason": bool(dom_delta is not None and dom_delta < -1.0 and chg30 > 0),
            "advice": ADVICE[state]}


def _headers():
    return {"x-cg-demo-api-key": settings.coingecko_api_key} if settings.coingecko_api_key else {}


async def compute() -> dict:
    async with client() as c:
        chart = await get_json(c, f"{CGB}/coins/bitcoin/market_chart", CG, headers=_headers(),
                               params={"vs_currency": "usd", "days": 365, "interval": "daily"})
        glob = await get_json(c, f"{CGB}/global", CG, headers=_headers())
    prices = [p[1] for p in chart["prices"]]
    dom = float(glob["data"]["market_cap_percentage"]["btc"])
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    r.hset("btc:dominance", today, dom)                     # build our own dominance history
    hist = [float(v) for _, v in sorted(r.hgetall("btc:dominance").items())][-60:]
    reg = classify(prices, datetime.now(timezone.utc).month, hist)
    reg["computed_at"] = datetime.now(timezone.utc).isoformat()
    r.set("btc:regime", json.dumps(reg), ex=12 * 3600)
    return reg


async def current() -> dict:
    cached = r.get("btc:regime")
    return json.loads(cached) if cached else await compute()


def format_regime(reg: dict) -> str:
    dom = f" · BTC dominance {reg['dominance']:.1f}%" if reg.get("dominance") else ""
    alt = " · 🔄 altseason signal (BTC up, dominance falling)" if reg.get("altseason") else ""
    return (f"<b>₿ Regime: {reg['state']}</b>\n"
            f"BTC ${reg['price']:,.0f} · {reg['drawdown']:.0%} from 180d high · "
            f"{reg['days_since_top']}d since top · down-legs {reg['down_legs']} · 30d {reg['chg30']:+.0%}{dom}{alt}\n"
            f"{reg['advice']}\n<i>Rule-based context, not a forecast.</i>")
