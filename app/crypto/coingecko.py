from .http import CG, get_json
from .regime import CGB, _headers


async def markets(c, page=1, per_page=250, ids: list[str] | None = None) -> list[dict]:
    params = {"vs_currency": "usd", "order": "market_cap_desc", "per_page": per_page, "page": page,
              "price_change_percentage": "7d,30d"}
    if ids:
        params["ids"] = ",".join(ids)
    return await get_json(c, f"{CGB}/coins/markets", CG, params=params, headers=_headers())
