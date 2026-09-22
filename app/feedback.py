from sqlmodel import select
from .db import session
from .models import Feedback, Item


def record_item_vote(item_id: int, vote: str):
    with session() as s:
        item = s.get(Item, item_id)
        if not item:
            return
        s.add(Feedback(topic=item.topic, ref=str(item_id), title=item.title,
                       category=item.category, vote=vote))
        s.commit()


def build_fewshot(topic: str, limit: int = 8) -> str:
    with session() as s:
        rows = s.exec(select(Feedback).where(Feedback.topic == topic)
                      .order_by(Feedback.created_at.desc()).limit(limit)).all()
    if not rows:
        return "(no feedback yet)"
    return "\n".join(f'- "{r.title}" ({r.category}) -> {r.vote.upper()}' for r in rows)
