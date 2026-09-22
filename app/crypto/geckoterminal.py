"""GeckoTerminal public API (no key, 30 rpm): multi-chain discovery + OHLCV for price location."""
from .http import GECKO, get_json

BASE = "https://api.geckoterminal.com/api/v2"
H = {"Accept": "application/json"}


def pool_token_address(pool: dict) -> str | None:
    try:
        tid = pool["relationships"]["base_token"]["data"]["id"]   # "<network>_<address>"
        return tid.split("_", 1)[1]
    except (KeyError, IndexError, TypeError):
        return None


async def trending_pools(c, network: str, page: int = 1) -> list[dict]:
    d = await get_json(c, f"{BASE}/networks/{network}/trending_pools", GECKO, params={"page": page}, headers=H)
    return d.get("data", [])


async def top_volume_pools(c, network: str, page: int = 1) -> list[dict]:
    d = await get_json(c, f"{BASE}/networks/{network}/pools", GECKO,
                       params={"page": page, "sort": "h24_volume_usd_desc"}, headers=H)
    return d.get("data", [])


async def ohlcv(c, network: str, pool: str, timeframe: str = "day", aggregate: int = 1, limit: int = 120):
    d = await get_json(c, f"{BASE}/networks/{network}/pools/{pool}/ohlcv/{timeframe}", GECKO,
                       params={"aggregate": aggregate, "limit": limit, "currency": "usd"}, headers=H)
    rows = d["data"]["attributes"]["ohlcv_list"]           # [ts, o, h, l, c, v]
    return sorted(rows, key=lambda x: x[0])


def price_location(daily: list, h4: list) -> dict:
    """Course rule: buy near the BOTTOM of a consolidating range, deep below the launch pump.
    Prices are proportional to market cap (fixed supply), so ratios work on either."""
    if not daily:
        return {}
    ath = max(row[2] for row in daily)
    recent = h4 or daily[-15:]
    cur = recent[-1][4]
    lo, hi = min(row[3] for row in recent), max(row[2] for row in recent)
    pos = (cur - lo) / (hi - lo) if hi > lo else 0.5
    return {"drawdown": 1 - cur / ath if ath else None, "range_pos": pos}
