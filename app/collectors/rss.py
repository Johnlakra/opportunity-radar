import calendar
import re
from datetime import datetime, timezone
from urllib.parse import quote_plus
import feedparser
import httpx

UA = {"User-Agent": "opportunity-radar/0.2 (personal, non-commercial)"}
_TAG = re.compile(r"<[^>]+>")


def published_at(entry) -> datetime | None:
    """The feed's own date for an entry, in UTC, or None when the feed gives none."""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    try:
        return datetime.fromtimestamp(calendar.timegm(parsed), timezone.utc)
    except (OverflowError, ValueError, TypeError):
        return None


async def fetch_rss(client: httpx.AsyncClient, url: str, source: str, limit: int = 40) -> list[dict]:
    resp = await client.get(url, headers=UA, timeout=20, follow_redirects=True)
    resp.raise_for_status()
    feed = feedparser.parse(resp.content)
    out = []
    for e in feed.entries[:limit]:
        link, title = e.get("link", ""), (e.get("title") or "").strip()
        if not link or not title:
            continue
        summary = _TAG.sub(" ", e.get("summary", "") or "")[:800]
        out.append({"url": link, "title": title, "source": source, "summary": summary,
                    "published": published_at(e)})
    return out


def google_news_url(query: str, hl: str = "en-IN", gl: str = "IN") -> str:
    """Google News RSS search: a free, key-less way to watch ANY topic."""
    return (f"https://news.google.com/rss/search?q={quote_plus(query)}"
            f"&hl={hl}&gl={gl}&ceid={gl}:{hl.split('-')[0]}")
