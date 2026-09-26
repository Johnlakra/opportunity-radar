"""BulletinAgent: once an hour, while you are awake, the best waiting news per topic in one message.

It sits between the instant pings (priority >= 85, max 3/day) and the 09:00 digest, so a good
story reaches you within the hour instead of the next morning - without a ping per story.
The bar adapts to the day's pace (app/bulletin_rules.py) to keep volume near target_per_day."""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlmodel import select

from .. import bulletin_rules, cream, prefs, topics
from ..config import settings
from ..db import session
from ..models import Item
from ..notifier import btn, send
from ..redis_client import r
from ..ux import news_cards

log = logging.getLogger(__name__)
NEWS_KEY_PREFIX = "news:"
LOOKBACK_HOURS = 18
COUNTER_TTL_SECONDS = 2 * 86400


def sent_today_key(now: datetime) -> str:
    return "bulletin:" + now.strftime("%Y%m%d")


def sent_today(now: datetime) -> int:
    return int(r.get(sent_today_key(now)) or 0)


def current_bar(cfg: dict, now: datetime) -> int:
    start, end = cfg.get("active_hours", [7, 23])
    fraction = bulletin_rules.day_fraction(now.hour, now.minute, start, end)
    return bulletin_rules.bar(int(cfg.get("min_priority", bulletin_rules.DEFAULT_BAR)),
                              sent_today(now), int(cfg.get("target_per_day", 30)), fraction)


def _item_id(alert) -> int | None:
    tail = alert.key.removeprefix(NEWS_KEY_PREFIX)
    return int(tail) if alert.key.startswith(NEWS_KEY_PREFIX) and tail.isdigit() else None


def _items(alerts: list) -> list[tuple]:
    """(alert, item) pairs, in the alerts' order; alerts whose item is gone are skipped."""
    ids = [i for i in (_item_id(a) for a in alerts) if i is not None]
    with session() as s:
        by_id = {row.id: row for row in s.exec(select(Item).where(Item.id.in_(ids))).all()}
    return [(a, by_id[_item_id(a)]) for a in alerts if _item_id(a) in by_id]


def _buttons(rows: list) -> list[list]:
    return [[btn(f"👍 {n}", data=f"v:up:{row.id}"), btn(f"👎 {n}", data=f"v:dn:{row.id}"),
             btn(f"🔎 {n}", data=f"n:tell:{row.id}")] for n, row in enumerate(rows, 1)]


class BulletinAgent:
    kind = "bulletin"

    def __init__(self, name: str, cfg: dict):
        self.name = name
        self.cfg = cfg
        self.per_topic = int(cfg.get("per_topic", 5))

    async def run(self):
        now = datetime.now(ZoneInfo(settings.timezone))
        start, end = self.cfg.get("active_hours", [7, 23])
        if not bulletin_rules.is_active(now.hour, start, end) or prefs.is_quiet_now(now.hour):
            return
        news = {c["channel"] for c in topics.news_channels() if not prefs.is_topic_muted(c["channel"])}
        if not news:
            return
        bar = current_bar(self.cfg, now)
        picks = bulletin_rules.pick(cream.queued(news, LOOKBACK_HOURS), self.per_topic, bar)
        sent = 0
        for topic, alerts in picks.items():
            pairs = _items(alerts)
            if not pairs:
                continue
            rows = [item for _, item in pairs]
            text = news_cards.bulletin(topics.label_for_channel(topic), topic, rows, bar)
            await send(text, _buttons(rows))
            for alert, _ in pairs:
                cream._mark(alert.id, "bulletin")
            sent += len(pairs)
        if sent:
            key = sent_today_key(now)
            r.incrby(key, sent)
            r.expire(key, COUNTER_TTL_SECONDS)
        log.info("bulletin: bar %d, sent %d item(s) across %d topic(s)", bar, sent, len(picks))
