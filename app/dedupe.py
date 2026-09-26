import hashlib
from .redis_client import r


def _norm_url(url: str) -> str:
    u = url.split("#")[0].split("?")[0].rstrip("/").lower()
    for p in ("https://", "http://", "www."):
        u = u.replace(p, "")
    return u


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:32]


def _keys(topic: str, url: str, title: str) -> tuple[str, str]:
    return (f"seen:{topic}:u:{_h(_norm_url(url))}", f"seen:{topic}:t:{_h(title.strip().lower())}")


def filter_new(topic: str, items: list[dict], ttl_days: int = 30) -> list[dict]:
    """is_new() for a whole run in one MGET + one pipeline, instead of 3 Redis commands per item.
    Hosted Redis free tiers count commands; fetching every 15 minutes would otherwise burn them."""
    if not items:
        return []
    keys = [_keys(topic, it["url"], it["title"]) for it in items]
    flat = [k for pair in keys for k in pair]
    seen = r.mget(flat)
    fresh, claimed = [], set()
    for i, (it, pair) in enumerate(zip(items, keys)):
        if seen[2 * i] or seen[2 * i + 1] or claimed & set(pair):
            continue                          # stored before, or a repeat inside this same run
        claimed.update(pair)
        fresh.append(it)
    if claimed:
        pipe = r.pipeline()
        for k in claimed:
            pipe.set(k, 1, ex=ttl_days * 86400)
        pipe.execute()
    return fresh
