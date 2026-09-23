from sqlmodel import select
from .db import session
from .models import Feedback, Item


def record_item_vote(item_id: int, vote: str):
    with session() as s:
        item = s.get(Item, item_id)
        if not item:
            return
        s.add(Feedback(topic=item.topic, ref=str(item_id), title=item.title,
                       category=item.category, source=item.source or "", vote=vote))
        s.commit()


def build_fewshot(topic: str, limit: int = 8) -> str:
    with session() as s:
        rows = s.exec(select(Feedback).where(Feedback.topic == topic)
                      .order_by(Feedback.created_at.desc()).limit(limit)).all()
    if not rows:
        return "(no feedback yet)"
    return "\n".join(f'- "{r.title}" ({r.category}) -> {r.vote.upper()}' for r in rows)


def tally(topic: str | None = None, days: int = 7) -> dict:
    """What you liked and disliked lately, grouped by kind and by source."""
    from collections import defaultdict
    from datetime import datetime, timedelta, timezone
    since = datetime.now(timezone.utc) - timedelta(days=days)
    with session() as s:
        query = select(Feedback).where(Feedback.created_at >= since)
        if topic:
            query = query.where(Feedback.topic == topic)
        rows = list(s.exec(query).all())
    by_category, by_source = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    for row in rows:
        slot = 0 if row.vote == "up" else 1
        if row.category:
            by_category[row.category][slot] += 1
        if row.source:
            by_source[row.source][slot] += 1
    return {"total": len(rows), "categories": dict(by_category), "sources": dict(by_source)}
