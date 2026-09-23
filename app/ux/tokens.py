"""Short callback tokens.

Telegram limits callback_data to 64 bytes and a Solana address alone is 44, so the
payload lives in Redis and the button carries only a 10-character id. A side effect
is that no contract address is ever visible in the chat unless the user asks."""
import hashlib

from ..redis_client import r

PREFIX = "cb:"
TTL = 7 * 86400
ID_LEN = 10


def short_id(payload: str) -> str:
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:ID_LEN]


def put(payload: str) -> str:
    sid = short_id(payload)
    r.set(PREFIX + sid, payload, ex=TTL)
    return sid


def get(sid: str) -> str | None:
    return r.get(PREFIX + sid) if sid else None


def cb(action: str, payload: str) -> str:
    """Build callback_data for a button: `<action>:<short id>`, always well under 64 bytes."""
    return f"{action}:{put(payload)}"


def split(data: str) -> tuple[str, str]:
    action, _, sid = (data or "").partition(":")
    return action, sid
