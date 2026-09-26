from datetime import datetime, timezone

import httpx

ALGOLIA = "https://hn.algolia.com/api/v1/search_by_date"


async def fetch_hn(client: httpx.AsyncClient, tags: str = "show_hn", min_points: int = 5) -> list[dict]:
    params = {"tags": tags, "numericFilters": f"points>{min_points}", "hitsPerPage": 50}
    resp = await client.get(ALGOLIA, params=params, timeout=20)
    resp.raise_for_status()
    out = []
    for h in resp.json().get("hits", []):
        url = h.get("url") or f"https://news.ycombinator.com/item?id={h['objectID']}"
        out.append({"url": url, "title": h.get("title") or "", "source": f"HN/{tags}",
                    "summary": (h.get("story_text") or "")[:800],
                    "published": _when(h.get("created_at_i"))})
    return out


def _when(epoch) -> datetime | None:
    return datetime.fromtimestamp(epoch, timezone.utc) if isinstance(epoch, int) else None
