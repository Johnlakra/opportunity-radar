"""Free social-signal checks: website liveness, domain age (RDAP), Telegram public member count.
X/Twitter has no free API in 2026 -> presence only; follower/activity check stays manual."""
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from ..redis_client import r
from .http import WEB, get_json

TG_RE = re.compile(r'tgme_page_extra">\s*([\d\s,.]+)\s*(members|subscribers)', re.I)


async def website_alive(c, url: str) -> bool:
    try:
        await WEB.wait()
        resp = await c.get(url, timeout=15)
        return resp.status_code < 400
    except Exception:
        return False


async def domain_age_days(c, url: str) -> int | None:
    host = (urlparse(url).hostname or "").lower()
    domain = ".".join(host.split(".")[-2:])
    if not domain:
        return None
    cached = r.get(f"rdap:{domain}")
    if cached:
        return int(cached)
    try:
        d = await get_json(c, f"https://rdap.org/domain/{domain}", WEB)
        for ev in d.get("events", []):
            if ev.get("eventAction") == "registration":
                born = datetime.fromisoformat(ev["eventDate"].replace("Z", "+00:00"))
                days = (datetime.now(timezone.utc) - born).days
                r.set(f"rdap:{domain}", days, ex=7 * 86400)
                return days
    except Exception:
        return None
    return None


async def telegram_members(c, url: str) -> int | None:
    if not url or "t.me/" not in url:
        return None
    try:
        await WEB.wait()
        resp = await c.get(url, timeout=15)
        m = TG_RE.search(resp.text)
        return int(re.sub(r"[^\d]", "", m.group(1))) if m else None
    except Exception:
        return None
