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


def chat_warnings(chat_ids: dict[str, str], ask) -> list[str]:
    """chat_ids: {id: role}. ask(id) -> Telegram's getChat reply as a dict.
    A chat the bot cannot see is a chat every alert silently misses - say so at boot."""
    out = []
    for chat_id, role in chat_ids.items():
        try:
            reply = ask(chat_id)
        except Exception as exc:
            out.append(f"could not check {role} chat {chat_id}: {type(exc).__name__}")
            continue
        if not reply.get("ok"):
            out.append(f"{role} chat {chat_id} is unreachable ({reply.get('description', 'no reason given')}). "
                       "That person must open the bot and press Start, or add the bot to the group; "
                       "sending /chatid to the bot from that chat shows its real id.")
    return out


def check_chats(settings) -> None:
    """Warn, never stop: the rest of the bot works even if one recipient is misconfigured."""
    if not settings.telegram_bot_token:
        return
    import httpx
    api = f"https://api.telegram.org/bot{settings.telegram_bot_token}/getChat"

    def ask(chat_id):
        return httpx.get(api, params={"chat_id": chat_id}, timeout=10).json()

    roles = {**{c: "metals" for c in settings.metals_chat_ids}, **{c: "main" for c in settings.chat_ids}}
    for warning in chat_warnings(roles, ask):
        print(f"WARNING: {warning}", file=sys.stderr)


def main() -> int:
    quiet_http_logs()
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
    check_chats(settings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
