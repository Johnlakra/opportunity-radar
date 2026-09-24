"""Storage for level alerts: which assets you watch, and the daily history behind the levels."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from .config import settings
from .db import session
from .levels import PERIODS, enabled_periods, prev_period_hl
from .models import DailyBar, Holding, LevelSub


def local_today() -> date:
    """Periods are week/month/quarter/year in YOUR timezone, not UTC."""
    return datetime.now(ZoneInfo(settings.timezone)).date()

METALS = {"metal:XAU": "Gold", "metal:XAG": "Silver"}
JOURNAL_PREFIX = {"cg": "cg:", "dex": "dex:"}


# ---------------- what each person watches ----------------
# Every subscription belongs to one chat id. Two people watching gold have two rows, so their
# periods, directions and on/off switches never touch each other.
def all_subs(chat_id: str | None = None, active_only: bool = False) -> list[LevelSub]:
    with session() as s:
        query = select(LevelSub).order_by(LevelSub.id)
        if chat_id is not None:
            query = query.where(LevelSub.chat_id == str(chat_id))
        if active_only:
            query = query.where(LevelSub.active == True)          # noqa: E712
        return list(s.exec(query).all())


def get_sub(sub_id: int, chat_id: str | None = None) -> LevelSub | None:
    """With a chat_id, a row belonging to someone else is simply not found."""
    with session() as s:
        row = s.get(LevelSub, sub_id)
        if row and chat_id is not None and row.chat_id != str(chat_id):
            return None
        return row


def by_key(chat_id: str, asset_key: str) -> LevelSub | None:
    with session() as s:
        return s.exec(select(LevelSub).where(LevelSub.chat_id == str(chat_id),
                                             LevelSub.asset_key == asset_key)).first()


def upsert(chat_id: str, asset_key: str, label: str, periods: str,
           source: str = "manual") -> LevelSub:
    """Create it for this person, or wake their deactivated one back up.
    Never overwrites settings they changed by hand."""
    chat_id = str(chat_id)
    with session() as s:
        row = s.exec(select(LevelSub).where(LevelSub.chat_id == chat_id,
                                            LevelSub.asset_key == asset_key)).first()
        if row is None:
            row = LevelSub(chat_id=chat_id, asset_key=asset_key, label=label,
                           periods=periods, source=source)
        else:
            row.label = row.label or label
            row.active = True
            if row.source != "manual":
                row.periods = row.periods or periods
        s.add(row); s.commit(); s.refresh(row)
        return row


def update(sub_id: int, **fields) -> LevelSub | None:
    """Any change made by hand marks the row manual, so the journal sync leaves it alone."""
    with session() as s:
        row = s.get(LevelSub, sub_id)
        if not row:
            return None
        for key, value in fields.items():
            setattr(row, key, value)
        row.source = "manual"
        s.add(row); s.commit(); s.refresh(row)
        return row


def set_active(chat_id: str, asset_key: str, active: bool) -> None:
    with session() as s:
        row = s.exec(select(LevelSub).where(LevelSub.chat_id == str(chat_id),
                                            LevelSub.asset_key == asset_key)).first()
        if row:
            row.active = active
            s.add(row); s.commit()


def remove(sub_id: int) -> bool:
    with session() as s:
        row = s.get(LevelSub, sub_id)
        if not row:
            return False
        s.delete(row); s.commit()
        return True


def seed_metals(periods: str, chat_ids: list[str]) -> int:
    """Everyone who is allowed metal alerts gets their own gold and silver row."""
    made = 0
    for chat_id in chat_ids:
        for asset_key, label in METALS.items():
            if by_key(chat_id, asset_key) is None:
                upsert(chat_id, asset_key, label, periods, source="default")
                made += 1
    return made


def holding_key(holding: Holding) -> str:
    return f"cg:{holding.ref}" if holding.kind == "cg" else f"dex:{holding.ref}"


def sync_journal(periods: str, owner_chat_ids: list[str]) -> tuple[int, int]:
    """Journal coins get alerts automatically, for the people who own the journal.
    Sold ones go quiet. Rows edited by hand are untouched. Returns (added, deactivated)."""
    with session() as s:
        holdings = list(s.exec(select(Holding)).all())
    wanted = {holding_key(h): (h.symbol or h.ref) for h in holdings}
    added = gone = 0
    for chat_id in owner_chat_ids:
        for asset_key, label in wanted.items():
            if by_key(chat_id, asset_key) is None:
                upsert(chat_id, asset_key, label, periods, source="journal")
                added += 1
        for row in all_subs(chat_id):
            if row.source == "journal" and row.active and row.asset_key not in wanted:
                set_active(chat_id, row.asset_key, False)
                gone += 1
    return added, gone


def periods_of(sub: LevelSub) -> list[str]:
    return enabled_periods(sub.periods)


def directions_of(sub: LevelSub) -> list[str]:
    return [d for d, on in (("up", sub.up), ("down", sub.down)) if on]


def wants(sub: LevelSub, period: str, direction: str) -> bool:
    """Does this person want to hear about this exact break?"""
    return bool(sub.active) and period in periods_of(sub) and direction in directions_of(sub)


# ---------------- daily history (metals only) ----------------
def load_bars(asset_key: str) -> list[dict]:
    with session() as s:
        rows = s.exec(select(DailyBar).where(DailyBar.asset_key == asset_key)
                      .order_by(DailyBar.day)).all()
    return [{"day": b.day, "o": b.o, "h": b.h, "l": b.l, "c": b.c, "currency": b.currency}
            for b in rows]


def save_bars(asset_key: str, bars: list[dict], currency: str = "INR", own: bool = False) -> int:
    """Bootstrapped bars never overwrite a day we recorded ourselves - ours saw every tick.

    The bot and the level agent run in separate processes and can bootstrap the same metal at
    the same moment. If the other one commits first, its rows exist now, so a second pass
    updates them instead of inserting duplicates."""
    try:
        return _write_bars(asset_key, bars, currency, own)
    except IntegrityError:
        return _write_bars(asset_key, bars, currency, own)


def _write_bars(asset_key: str, bars: list[dict], currency: str, own: bool) -> int:
    written = 0
    with session() as s:
        for bar in bars:
            existing = s.get(DailyBar, (asset_key, bar["day"]))
            if existing and existing.own and not own:
                continue
            row = existing or DailyBar(asset_key=asset_key, day=bar["day"], o=0, h=0, l=0, c=0)
            row.o, row.h, row.l, row.c = bar["o"], bar["h"], bar["l"], bar["c"]
            row.currency, row.own = currency, own or (existing.own if existing else False)
            s.add(row); written += 1
        s.commit()
    return written


def record_live(asset_key: str, day: str, price: float, currency: str = "INR") -> None:
    """Fold one live poll into today's bar, so tomorrow's levels come from what we actually saw."""
    with session() as s:
        row = s.get(DailyBar, (asset_key, day))
        if row is None:
            row = DailyBar(asset_key=asset_key, day=day, o=price, h=price, l=price, c=price,
                           currency=currency, own=True)
        else:
            row.h, row.l, row.c = max(row.h, price), min(row.l, price), price
            row.own = True
        s.add(row); s.commit()


def has_bootstrap(asset_key: str) -> bool:
    """True once a real history has been loaded. Bars we recorded ourselves do not count:
    on day one there is exactly one of them, which is not enough to know any level."""
    with session() as s:
        rows = s.exec(select(DailyBar).where(DailyBar.asset_key == asset_key,
                                             DailyBar.own == False)).all()      # noqa: E712
        return bool(rows)


def bar_count(asset_key: str) -> int:
    with session() as s:
        return len(s.exec(select(DailyBar).where(DailyBar.asset_key == asset_key)).all())


def known_periods(bars: list[dict], today: date | None = None) -> list[str]:
    """Which periods we actually have enough history for - the rest say "building history"."""
    if not bars:
        return []
    today = today or local_today()
    return [p for p in PERIODS if prev_period_hl(bars, p, today) is not None]
