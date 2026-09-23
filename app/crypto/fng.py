"""Crypto Fear & Greed index (alternative.me, free, no key). Cached for 6h; never fatal."""
import json

from ..redis_client import r
from .http import WEB, get_json

URL = "https://api.alternative.me/fng/"
CACHE_KEY = "fng:latest"
CACHE_TTL = 6 * 3600


def band(value: int) -> str:
    """Plain-English label for a 0-100 reading."""
    if value <= 24:
        return "Extreme Fear"
    if value <= 44:
        return "Fear"
    if value <= 55:
        return "Neutral"
    if value <= 74:
        return "Greed"
    return "Extreme Greed"


def parse(payload: dict) -> dict | None:
    rows = (payload or {}).get("data") or []
    if not rows:
        return None
    try:
        value = int(rows[0]["value"])
    except (KeyError, TypeError, ValueError):
        return None
    return {"value": value, "band": band(value)}


async def current(c) -> dict | None:
    cached = r.get(CACHE_KEY)
    if cached:
        return json.loads(cached)
    try:
        out = parse(await get_json(c, URL, WEB, params={"limit": 1}))
    except Exception:
        return None
    if out:
        r.set(CACHE_KEY, json.dumps(out), ex=CACHE_TTL)
    return out
