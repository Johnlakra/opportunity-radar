"""Reads and writes for the news side: saved items, reminders, search, rescued items."""
from datetime import datetime, timedelta, timezone

from sqlmodel import or_, select

from .db import session
from .models import Alert, Item

RECENT_HOURS = 36
SEARCH_LIMIT = 8


def now() -> datetime:
    return datetime.now(timezone.utc)


def get_item(item_id: int) -> Item | None:
    with session() as s:
        return s.get(Item, item_id)


def set_saved(item_id: int, saved: bool) -> Item | None:
    with session() as s:
        row = s.get(Item, item_id)
        if not row:
            return None
        row.saved = saved
        row.saved_at = now() if saved else None
        s.add(row); s.commit(); s.refresh(row)
        return row


def set_reminder(item_id: int, when: datetime | None) -> Item | None:
    with session() as s:
        row = s.get(Item, item_id)
        if not row:
            return None
        row.remind_at = when
        row.reminded = False
        s.add(row); s.commit(); s.refresh(row)
        return row


def saved_and_deadlines(limit: int = 15) -> list[Item]:
    """Saved items and anything with a deadline still ahead, soonest first."""
    with session() as s:
        rows = s.exec(select(Item)
                      .where(or_(Item.saved == True,                       # noqa: E712
                                 Item.deadline_at != None))                # noqa: E711
                      .order_by(Item.deadline_at.asc()).limit(limit * 2)).all()
    fresh = [r for r in rows if not r.deadline_at or r.deadline_at >= now() - timedelta(days=1)]
    fresh.sort(key=lambda r: (r.deadline_at is None, r.deadline_at or now()))
    return fresh[:limit]


def due_reminders(limit: int = 20) -> list[Item]:
    with session() as s:
        return list(s.exec(select(Item)
                           .where(Item.remind_at != None,                   # noqa: E711
                                  Item.remind_at <= now(),
                                  Item.reminded == False)                   # noqa: E712
                           .order_by(Item.remind_at.asc()).limit(limit)).all())


def mark_reminded(item_id: int) -> None:
    with session() as s:
        row = s.get(Item, item_id)
        if row:
            row.reminded = True
            s.add(row); s.commit()


def search(query: str, limit: int = SEARCH_LIMIT) -> list[Item]:
    """Plain substring search over what has already come through."""
    term = f"%{(query or '').strip()[:60]}%"
    if len(term) <= 4:
        return []
    with session() as s:
        return list(s.exec(select(Item)
                           .where(or_(Item.title.like(term), Item.summary.like(term)))
                           .order_by(Item.fetched_at.desc()).limit(limit)).all())


def top_recent(limit: int = 3, channel: str | None = None, offset: int = 0,
               min_priority: int = 50) -> list[Alert]:
    """Best of the last day and a half. Read-only: it never consumes the digest queue."""
    since = now() - timedelta(hours=RECENT_HOURS)
    with session() as s:
        query = select(Alert).where(Alert.created_at >= since, Alert.priority >= min_priority,
                                    Alert.sent_mode != "dropped")
        if channel:
            query = query.where(Alert.topic == channel)
        return list(s.exec(query.order_by(Alert.priority.desc()).offset(offset).limit(limit)).all())


def dropped(limit: int = 10) -> list[Alert]:
    with session() as s:
        return list(s.exec(select(Alert).where(Alert.sent_mode == "dropped")
                           .order_by(Alert.created_at.desc()).limit(limit)).all())


def get_alert(alert_id: int) -> Alert | None:
    with session() as s:
        return s.get(Alert, alert_id)
