"""/stats: what the news side did today, and how much free Gemini budget is left."""
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlmodel import select

from .config import settings
from .db import session
from .models import Alert
from .redis_client import r
from .ux.news_cards import stats_card


def _counts_since(since: datetime) -> dict[str, int]:
    with session() as s:
        rows = s.exec(select(Alert.sent_mode, func.count()).where(Alert.created_at >= since)
                      .group_by(Alert.sent_mode)).all()
    return {mode: n for mode, n in rows}


def _used(kind: str) -> int:
    return int(r.get(f"{kind}:" + datetime.now(timezone.utc).strftime("%Y%m%d")) or 0)


def today_text() -> str:
    from .agents import bulletin
    from .orchestrator import load_config
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz)
    midnight = datetime.combine(now.date(), time.min, tz).astimezone(timezone.utc)
    cfg = next((c for c in load_config().values() if c.get("type") == "bulletin"), None)
    bar = bulletin.current_bar(cfg, now) if cfg else None
    budgets = {"scoring": (_used("score"), settings.score_daily_cap),
               "research": (_used("research"), settings.research_daily_cap)}
    return stats_card(_counts_since(midnight), bar, (cfg or {}).get("target_per_day", 30), budgets)
