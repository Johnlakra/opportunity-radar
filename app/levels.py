"""Previous week / month / quarter / year highs and lows, and whether price just broke one.

Pure: no network, no database, no Redis. Everything here is arithmetic and calendars, which is
exactly the part that must not be wrong, so it is the part that is tested hardest.

The rule the whole feature rests on: a level only counts once it belongs to a COMPLETED period.
A level that moved because the calendar rolled over is not a break, it is a new yardstick."""
from datetime import date, timedelta

PERIODS = ("W", "M", "Q", "Y")
PERIOD_NAMES = {"W": "week", "M": "month", "Q": "quarter", "Y": "year"}
TROY_OUNCE_G = 31.1034768
GRAMS_PER_KG = 1000
GOLD_UNIT_G = 10                     # India quotes gold per 10 grams, silver per kilo
ABOVE, BELOW = "above", "below"


# ---------------- naming a period ----------------
def period_id(day: date, period: str) -> str:
    """"2026-W39" · "2026-09" · "2026-Q3" · "2026". The caller passes a local date."""
    if period == "W":
        iso = day.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    if period == "M":
        return f"{day.year}-{day.month:02d}"
    if period == "Q":
        return f"{day.year}-Q{(day.month - 1) // 3 + 1}"
    if period == "Y":
        return str(day.year)
    raise ValueError(f"unknown period: {period}")


def period_range(day: date, period: str) -> tuple[date, date]:
    """First and last day of the period `day` falls in."""
    if period == "W":
        start = day - timedelta(days=day.weekday())
        return start, start + timedelta(days=6)
    if period == "M":
        start = day.replace(day=1)
        return start, _month_end(start)
    if period == "Q":
        first_month = 3 * ((day.month - 1) // 3) + 1
        start = day.replace(month=first_month, day=1)
        return start, _month_end(start.replace(month=first_month + 2))
    if period == "Y":
        return date(day.year, 1, 1), date(day.year, 12, 31)
    raise ValueError(f"unknown period: {period}")


def prev_period_range(day: date, period: str) -> tuple[date, date]:
    start, _ = period_range(day, period)
    return period_range(start - timedelta(days=1), period)


def _month_end(first_of_month: date) -> date:
    if first_of_month.month == 12:
        return first_of_month.replace(day=31)
    return first_of_month.replace(month=first_of_month.month + 1, day=1) - timedelta(days=1)


# ---------------- the level itself ----------------
def prev_period_hl(bars: list[dict], period: str, day: date) -> tuple[float, float] | None:
    """(high, low) of the last completed period, or None when the bars do not cover all of it.

    Coverage means the history starts on or before the period's first day and runs to or past its
    last day. Missing weekends inside are fine - a closed market is not missing data - but a
    history that begins mid-period would invent a high that never existed."""
    if not bars:
        return None
    start, end = prev_period_range(day, period)
    days = [date.fromisoformat(b["day"]) for b in bars]
    if min(days) > start or max(days) < end:
        return None
    inside = [b for b, d in zip(bars, days) if start <= d <= end]
    if not inside:
        return None
    return max(b["h"] for b in inside), min(b["l"] for b in inside)


# ---------------- crossing ----------------
def side_for(price: float, level: float, direction: str, buffer_pct: float) -> str:
    """Which side of the level we are on, with the buffer built in.

    The buffer belongs in the side, not only in the alert test: if "just above the level" counted
    as above, the state would flip early and swallow the real break that followed."""
    if direction == "up":
        return ABOVE if price > level * (1 + buffer_pct / 100) else BELOW
    return BELOW if price < level * (1 - buffer_pct / 100) else ABOVE


def decide(stored: str | None, current_period: str, price: float, level: float,
           direction: str, buffer_pct: float) -> tuple[bool, str]:
    """(should_alert, new_state). `stored` is "<period_id>:<above|below>" from the last run.

    No alert when: we have never looked before, the period just rolled over (the level moved),
    or we were already on this side. A level of zero or None can never break."""
    if not level or price is None:
        return False, stored or f"{current_period}:{BELOW}"
    side = side_for(price, level, direction, buffer_pct)
    new_state = f"{current_period}:{side}"
    was_period, _, was_side = (stored or "").partition(":")
    if was_side not in (ABOVE, BELOW) or was_period != current_period:
        return False, new_state                    # first look, or a fresh period: just remember
    crossed = (direction == "up" and was_side == BELOW and side == ABOVE) or \
              (direction == "down" and was_side == ABOVE and side == BELOW)
    return crossed, new_state


def state_field(asset_key: str, period: str, direction: str) -> str:
    """The Redis hash field one asset's one level lives in."""
    return f"{asset_key}|{period}|{'hi' if direction == 'up' else 'lo'}"


def alert_key(asset_key: str, period: str, pid: str, direction: str) -> str:
    """The cream gate's unique key: at most one alert per asset, period and direction."""
    return f"lvl:{asset_key}:{period}:{pid}:{direction}"


def bars_from_ohlcv(rows) -> list[dict]:
    """GeckoTerminal's [ts, o, h, l, c, v] rows -> daily bars, oldest first."""
    from datetime import datetime, timezone
    bars = []
    for row in rows or []:
        try:
            day = datetime.fromtimestamp(row[0], timezone.utc).date().isoformat()
            bar = {"day": day, "o": float(row[1]), "h": float(row[2]),
                   "l": float(row[3]), "c": float(row[4])}
        except (IndexError, TypeError, ValueError, OSError):
            continue
        if bar["h"] > 0 and bar["l"] > 0:
            bars.append(bar)
    bars.sort(key=lambda b: b["day"])
    return bars


# ---------------- money ----------------
def inr_per_gram(usd_per_ounce: float, usd_inr: float) -> float:
    return usd_per_ounce * usd_inr / TROY_OUNCE_G


def gold_per_10g(per_gram: float) -> float:
    return per_gram * GOLD_UNIT_G


def silver_per_kg(per_gram: float) -> float:
    return per_gram * GRAMS_PER_KG


def with_premium(value: float, premium_pct: float) -> float:
    """Display only. It scales the price and every level by the same factor, so it can never
    change whether something broke - it only brings the numbers nearer to what a jeweller quotes."""
    return value * (1 + (premium_pct or 0) / 100)


def distance_pct(price: float, level: float) -> float | None:
    return None if not level else (price / level - 1) * 100


# ---------------- which periods are switched on ----------------
def enabled_periods(spec: str) -> list[str]:
    wanted = set((spec or "").upper())
    return [p for p in PERIODS if p in wanted]


def toggle_period(spec: str, period: str) -> str:
    current = set(enabled_periods(spec))
    current.symmetric_difference_update({period.upper()})
    return "".join(p for p in PERIODS if p in current)
