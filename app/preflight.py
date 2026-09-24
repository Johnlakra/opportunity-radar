"""Boot checks for the one-container host (start.sh): stop early with a plain-English reason
instead of a 60-line traceback, then build the tables once before the bot and scheduler start."""
import logging
import os
import sys
from urllib.parse import urlparse

# Hosts that only exist on your PC or inside docker compose - never reachable from a cloud host.
LOCAL_ONLY_HOSTS = {"redis", "localhost", "127.0.0.1"}


def quiet_http_logs():
    """httpx logs every request URL at INFO, and Telegram's URL carries the bot token."""
    logging.getLogger("httpx").setLevel(logging.WARNING)


def redis_problem(url: str) -> str | None:
    host = urlparse(url or "").hostname or ""
    if host in LOCAL_ONLY_HOSTS:
        return (f"REDIS_URL points at '{host}', which only exists on your PC. "
                "Set REDIS_URL to your Upstash address (starts with rediss://).")
    return None


def database_problem(url: str) -> str | None:
    if os.environ.get("RENDER") and (url or "").startswith("sqlite"):
        return ("DATABASE_URL is SQLite, and Render wipes the disk on every restart - your "
                "journal would vanish. Set DATABASE_URL to your Neon postgresql+psycopg:// string.")
    return None


def main() -> int:
    from .config import settings
    for problem in (redis_problem(settings.redis_url), database_problem(settings.database_url)):
        if problem:
            print(f"STARTUP STOPPED: {problem}", file=sys.stderr)
            return 1
    from .redis_client import r
    try:
        r.ping()
    except Exception as exc:                # any failure here means the settings are wrong
        print(f"STARTUP STOPPED: cannot reach Redis ({type(exc).__name__}: {exc}). "
              "Check REDIS_URL.", file=sys.stderr)
        return 1
    from .db import init_db
    init_db()
    return 0


if __name__ == "__main__":
    sys.exit(main())
