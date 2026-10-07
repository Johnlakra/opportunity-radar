"""Shared HTTP helpers with per-API throttles so free-tier limits are never hit."""
import asyncio
import time
import httpx

UA = {"User-Agent": "opportunity-radar/0.3 (personal, non-commercial)"}
DEFAULT_RETRY_WAIT = 20   # seconds to wait after a first 429 when the server gives no Retry-After
MAX_RETRY_WAIT = 60       # never block an agent longer than this on one retry
COOLDOWN_SECONDS = 600    # after a second 429 in a row, leave that provider alone for 10 minutes


class RateLimited(Exception):
    """The provider keeps answering 429 (or is cooling down); callers skip and try next run."""


def retry_after_seconds(header: str | None) -> int:
    try:
        return min(max(int(header), 1), MAX_RETRY_WAIT)
    except (TypeError, ValueError):
        return DEFAULT_RETRY_WAIT


class Throttle:
    def __init__(self, per_minute: int):
        self.gap = 60.0 / per_minute
        self._last = 0.0
        self._cool_until = 0.0
        self._lock = asyncio.Lock()

    def cool_down(self, seconds: float = COOLDOWN_SECONDS):
        self._cool_until = time.monotonic() + seconds

    def cooling(self) -> bool:
        return time.monotonic() < self._cool_until

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
XAUS = Throttle(20)       # xaus.com spot + daily history, keyless
FX = Throttle(20)         # frankfurter.dev daily USD-INR, keyless
YF = Throttle(10)         # Yahoo chart endpoint: unofficial, used only to bootstrap silver
BINANCE = Throttle(60)    # data-api.binance.vision klines, keyless


async def get_json(client: httpx.AsyncClient, url: str, throttle: Throttle | None = None, **kw):
    host = httpx.URL(url).host
    for attempt in range(2):
        if throttle:
            if throttle.cooling():
                raise RateLimited(f"{host} is rate-limiting us; cooling down")
            await throttle.wait()
        resp = await client.get(url, timeout=25, **kw)
        if resp.status_code == 429:
            if attempt == 0:
                await asyncio.sleep(retry_after_seconds(resp.headers.get("Retry-After")))
                continue
            if throttle:
                throttle.cool_down()
            raise RateLimited(f"{host} answered 429 twice; pausing {COOLDOWN_SECONDS // 60} min")
        resp.raise_for_status()
        return resp.json()


def client() -> httpx.AsyncClient:
    return httpx.AsyncClient(headers=UA, follow_redirects=True)
