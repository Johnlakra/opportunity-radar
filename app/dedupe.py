import hashlib
from .redis_client import r


def _norm_url(url: str) -> str:
    u = url.split("#")[0].split("?")[0].rstrip("/").lower()
    for p in ("https://", "http://", "www."):
        u = u.replace(p, "")
    return u


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:32]


def is_new(topic: str, url: str, title: str, ttl_days: int = 30) -> bool:
    """Exact dedupe per topic on normalized URL and title."""
    keys = [f"seen:{topic}:u:{_h(_norm_url(url))}",
            f"seen:{topic}:t:{_h(title.strip().lower())}"]
    if r.exists(*keys):
        return False
    pipe = r.pipeline()
    for k in keys:
        pipe.set(k, 1, ex=ttl_days * 86400)
    pipe.execute()
    return True
