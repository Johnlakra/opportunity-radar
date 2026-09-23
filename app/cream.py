"""The cream gate. Every topic submits candidate alerts here; only the best get through.

  priority >= URGENT_MIN and daily urgent budget left  -> sent now
  otherwise queued -> the daily digest sends the top N across ALL topics (max per topic)
  everything else is stored (see /more) but never pushed.
Holding-protection alerts (take-profit, exits, regime flips) use priority >= 90."""
import json
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlmodel import select
from sqlalchemy.exc import IntegrityError

from . import gate, prefs
from .config import settings
from .db import session
from .models import Alert
from .notifier import btn, send
from .redis_client import r

log = logging.getLogger(__name__)
URGENT_MIN = gate.URGENT_MIN                 # re-exported: existing callers import it from here
ALWAYS_DELIVER = gate.ALWAYS_DELIVER


def _urgent_key():
    return "urgent:" + datetime.now(ZoneInfo(settings.timezone)).strftime("%Y%m%d")


def _take_urgent_slot(priority: int) -> bool:
    if priority >= ALWAYS_DELIVER:
        return True
    key = _urgent_key()
    used = r.incr(key)
    if used == 1:
        r.expire(key, 2 * 86400)
    return used <= prefs.urgent_cap(settings.urgent_daily_cap)


def _now_hour() -> int:
    return datetime.now(ZoneInfo(settings.timezone)).hour


def _rows(buttons_json: str):
    rows = []
    for row in json.loads(buttons_json or "[]"):
        rows.append([btn(b["t"], url=b.get("u"), data=b.get("d")) for b in row])
    return rows


def buttons(*rows):
    """Helper: buttons(("Open", "https://..", None), ("👍", None, "v:up:1")) -> json."""
    return json.dumps([[{"t": t, "u": u, "d": d} for (t, u, d) in row] for row in rows])


async def submit(key: str, topic: str, priority: int, text: str, buttons_json: str = "[]",
                 category: str | None = None):
    priority = max(0, min(100, int(priority)))
    with session() as s:
        alert = Alert(key=key, topic=topic, priority=priority, text=text, buttons_json=buttons_json)
        s.add(alert)
        try:
            s.commit()
        except IntegrityError:          # already submitted earlier
            s.rollback()
            return
        s.refresh(alert)
    verdict = gate.decide(priority, prefs.is_topic_muted(topic), prefs.is_category_muted(category or ""),
                     prefs.is_quiet_now(_now_hour()))
    if verdict == "dropped":
        _mark(alert.id, "dropped")
        return
    if verdict == "urgent" and _take_urgent_slot(priority):
        await send(text, _rows(buttons_json))
        _mark(alert.id, "urgent")


def _mark(alert_id: int, mode: str):
    with session() as s:
        a = s.get(Alert, alert_id)
        a.sent_mode = mode
        s.add(a)
        s.commit()


def pick_digest(total: int, per_topic: int, min_priority: int = 60) -> list[Alert]:
    since = datetime.now(timezone.utc) - timedelta(hours=36)
    with session() as s:
        queued = s.exec(select(Alert).where(Alert.sent_mode == "", Alert.created_at >= since,
                                            Alert.priority >= min_priority)
                        .order_by(Alert.priority.desc())).all()
    chosen, per = [], {}
    for a in queued:
        if per.get(a.topic, 0) >= per_topic:
            continue
        chosen.append(a)
        per[a.topic] = per.get(a.topic, 0) + 1
        if len(chosen) >= total:
            break
    return chosen


def close_out_queue():
    """After the digest, anything still queued is dropped (kept for /more, never pushed)."""
    with session() as s:
        for a in s.exec(select(Alert).where(Alert.sent_mode == "")).all():
            a.sent_mode = "dropped"
            s.add(a)
        s.commit()
