"""Your settings, changed from buttons instead of a config file.

Everything lives in Redis so the bot can change it at runtime; config/me.yaml and
config/agents.yaml stay exactly as you wrote them and are never rewritten by the bot.
Each getter falls back to the file/env default, so an empty Redis behaves like today."""
import json

from .redis_client import r

HASH = "prefs"
MUTED_TOPICS = "muted"              # already used by /mute; kept as-is
MUTED_CATEGORIES = "muted:cat"
ME_OVERLAY = "me:overlay"

# "How picky should I be?" -> the score an item must reach to be worth researching.
PICKINESS = {"relaxed": 6, "normal": 7, "strict": 8}
PICKY_WORDS = {"relaxed": "Relaxed — send me more", "normal": "Normal",
               "strict": "Strict — only the best"}
QUIET_CHOICES = {"off": ("Always allowed", None), "23-7": ("11pm – 7am", (23, 7)),
                 "22-8": ("10pm – 8am", (22, 8)), "0-6": ("Midnight – 6am", (0, 6))}
ME_FIELDS = [("exchanges", "Exchanges you use"), ("wallets", "Wallets"), ("chains", "Chains"),
             ("holding_tickers", "Coins you hold"), ("interests", "What you care about")]
DIGEST_HOURS = [6, 7, 8, 9, 10, 12, 18, 21]
DEFAULT_PICKINESS = "normal"
MAX_URGENT_PER_DAY = 5


def get(field: str, default=None):
    value = r.hget(HASH, field)
    return default if value is None else value


def put(field: str, value) -> None:
    r.hset(HASH, field, str(value))


def _int(field: str, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(get(field, default))))
    except (TypeError, ValueError):
        return default


# ---------------- topics ----------------
def is_topic_muted(topic: str) -> bool:
    return bool(r.sismember(MUTED_TOPICS, topic))


def set_topic_muted(topic: str, muted: bool) -> None:
    (r.sadd if muted else r.srem)(MUTED_TOPICS, topic)


def muted_topics() -> set[str]:
    return set(r.smembers(MUTED_TOPICS) or [])


# ---------------- categories ("less of this kind") ----------------
def norm_category(category: str) -> str:
    return (category or "").strip().lower()[:40]


def is_category_muted(category: str) -> bool:
    key = norm_category(category)
    return bool(key) and bool(r.sismember(MUTED_CATEGORIES, key))


def set_category_muted(category: str, muted: bool) -> None:
    key = norm_category(category)
    if key:
        (r.sadd if muted else r.srem)(MUTED_CATEGORIES, key)


def muted_categories() -> set[str]:
    return set(r.smembers(MUTED_CATEGORIES) or [])


# ---------------- how picky ----------------
def pickiness(topic: str) -> str:
    value = get(f"picky:{topic}")
    return value if value in PICKINESS else DEFAULT_PICKINESS


def set_pickiness(topic: str, level: str) -> None:
    if level not in PICKINESS:
        raise ValueError(f"unknown pickiness: {level}")
    put(f"picky:{topic}", level)


def threshold_for(topic: str, fallback: int) -> int:
    """The score an item must reach. Redis wins; otherwise agents.yaml's score_threshold."""
    value = get(f"picky:{topic}")
    return PICKINESS[value] if value in PICKINESS else fallback


# ---------------- pings ----------------
def urgent_cap(fallback: int) -> int:
    return _int("urgent_cap", fallback, 0, MAX_URGENT_PER_DAY)


def digest_hour(fallback: int) -> int:
    return _int("digest_hour", fallback, 0, 23)


def quiet_hours() -> tuple[int, int] | None:
    start, end = get("quiet_start"), get("quiet_end")
    if start is None or end is None:
        return None
    try:
        return int(start) % 24, int(end) % 24
    except (TypeError, ValueError):
        return None


def set_quiet_hours(start: int | None, end: int | None = None) -> None:
    if start is None:
        r.hdel(HASH, "quiet_start", "quiet_end")
        return
    put("quiet_start", int(start) % 24)
    put("quiet_end", int(end) % 24)


def within_quiet_hours(start: int, end: int, hour: int) -> bool:
    """Handles windows that wrap past midnight, e.g. 23:00-07:00."""
    if start == end:
        return False
    return start <= hour < end if start < end else (hour >= start or hour < end)


def is_quiet_now(hour: int) -> bool:
    window = quiet_hours()
    return bool(window) and within_quiet_hours(window[0], window[1], hour)


def tell_me_on_quiet_days() -> bool:
    return get("quiet_day_notice", "1") == "1"


def set_quiet_day_notice(on: bool) -> None:
    put("quiet_day_notice", "1" if on else "0")


# ---------------- "my setup" overlay over config/me.yaml ----------------
def me_overlay() -> dict:
    raw = r.get(ME_OVERLAY)
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def set_me_overlay(data: dict) -> None:
    r.set(ME_OVERLAY, json.dumps(data))


# ---------------- sources you switched off (never deleted from sources.yaml) ----------------
SOURCES_OFF = "sources:off"


def sources_off(topic: str) -> set[str]:
    return {x.split("|", 1)[1] for x in (r.smembers(SOURCES_OFF) or []) if x.startswith(f"{topic}|")}


def set_source_off(topic: str, name: str, off: bool) -> None:
    (r.sadd if off else r.srem)(SOURCES_OFF, f"{topic}|{name}")
