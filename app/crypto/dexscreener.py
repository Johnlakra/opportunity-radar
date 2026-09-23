"""DexScreener public API (no key). Used for multi-chain enrichment + curated discovery lists.
Note: it has NO filter endpoint - filtering happens in scout_rules.prefilter()."""
import time
from .chains import CHAINS, DEX_TO_CHAIN, norm
from .http import DEX, DEX_PAIRS, get_json

BASE = "https://api.dexscreener.com"


def _list(d):
    if isinstance(d, list):
        return d
    return (d or {}).get("pairs") or (d or {}).get("data") or []


async def _token_list(c, path):
    out = []
    for t in _list(await get_json(c, BASE + path, DEX)):
        chain = DEX_TO_CHAIN.get(t.get("chainId"))
        if chain and t.get("tokenAddress"):
            out.append((chain, norm(chain, t["tokenAddress"])))
    return out


async def latest_profiles(c):
    return await _token_list(c, "/token-profiles/latest/v1")


async def latest_boosts(c):
    return await _token_list(c, "/token-boosts/latest/v1")


async def latest_ctos(c):
    return await _token_list(c, "/community-takeovers/latest/v1")


async def pairs_for(c, chain: str, addresses: list[str]) -> list[dict]:
    pairs = []
    for i in range(0, len(addresses), 30):
        chunk = ",".join(addresses[i:i + 30])
        pairs += _list(await get_json(c, f"{BASE}/tokens/v1/{CHAINS[chain]['dex']}/{chunk}", DEX_PAIRS))
    return pairs


async def search(c, query: str) -> list[dict]:
    """Free-text search across every chain: name, symbol, token address or pair address."""
    d = await get_json(c, f"{BASE}/latest/dex/search", DEX_PAIRS, params={"q": query})
    return _list(d)


async def pair(c, chain: str, pair_address: str) -> dict | None:
    """One pair by its POOL address (what a DexScreener URL contains)."""
    pairs = _list(await get_json(c, f"{BASE}/latest/dex/pairs/{CHAINS[chain]['dex']}/{pair_address}", DEX_PAIRS))
    return pairs[0] if pairs else None


def best_pairs(chain: str, pairs: list[dict]) -> dict[str, dict]:
    """Highest-liquidity pair per base token."""
    best = {}
    for p in pairs:
        addr = norm(chain, (p.get("baseToken") or {}).get("address", ""))
        liq = ((p.get("liquidity") or {}).get("usd") or 0)
        if addr and (addr not in best or liq > ((best[addr].get("liquidity") or {}).get("usd") or 0)):
            best[addr] = p
    return best


def basics(p: dict) -> dict:
    info = p.get("info") or {}
    socials = {}
    for s in info.get("socials") or []:
        typ = (s.get("type") or s.get("platform") or "").lower()
        socials[typ] = s.get("url") or s.get("handle")
    created = p.get("pairCreatedAt")
    base = p.get("baseToken") or {}
    try:
        price = float(p["priceUsd"]) if p.get("priceUsd") not in (None, "") else None
    except (TypeError, ValueError):
        price = None
    return {
        "symbol": base.get("symbol", ""), "name": base.get("name", ""),
        "price": price,
        "mcap": p.get("marketCap") or p.get("fdv"), "fdv": p.get("fdv"),
        "liquidity": (p.get("liquidity") or {}).get("usd"),
        "vol24": (p.get("volume") or {}).get("h24"),
        "chg24": (p.get("priceChange") or {}).get("h24"),
        "age_hours": (time.time() * 1000 - created) / 3.6e6 if created else None,
        "pair_url": p.get("url", ""), "pool": p.get("pairAddress", ""),
        "websites": [w.get("url") for w in info.get("websites") or [] if w.get("url")],
        "twitter": socials.get("twitter") or socials.get("x"),
        "telegram": socials.get("telegram"),
        "boosted": bool((p.get("boosts") or {}).get("active")),
    }
