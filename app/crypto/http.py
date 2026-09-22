"""Shared HTTP helpers with per-API throttles so free-tier limits are never hit."""
import asyncio
import time
import httpx

UA = {"User-Agent": "opportunity-radar/0.3 (personal, non-commercial)"}


class Throttle:
    def __init__(self, per_minute: int):
        self.gap = 60.0 / per_minute
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def wait(self):
        async with self._lock:
            delta = time.monotonic() - self._last
            if delta < self.gap:
                await asyncio.sleep(self.gap - delta)
            self._last = time.monotonic()


# Conservative: below each provider's documented free limit.
DEX = Throttle(50)        # DexScreener profile/boost/CTO endpoints: 60 rpm
DEX_PAIRS = Throttle(200) # DexScreener tokens/pairs: 300 rpm
GECKO = Throttle(25)      # GeckoTerminal: 30 rpm, keyless
RUG = Throttle(8)         # RugCheck anonymous: ~10 rpm
GOPLUS = Throttle(20)
CG = Throttle(25)         # CoinGecko demo key: 30 rpm
WEB = Throttle(60)


async def get_json(client: httpx.AsyncClient, url: str, throttle: Throttle | None = None, **kw):
    for attempt in range(2):
        if throttle:
            await throttle.wait()
        resp = await client.get(url, timeout=25, **kw)
        if resp.status_code == 429 and attempt == 0:
            await asyncio.sleep(20)
            continue
        resp.raise_for_status()
        return resp.json()


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(headers=UA, follow_redirects=True)
