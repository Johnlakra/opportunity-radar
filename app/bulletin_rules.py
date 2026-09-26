"""The hourly bulletin's rules - pure, so they can be read and tested on their own.

Between "ping me now" (priority >= 85) and "tell me tomorrow at 9" (the digest) sits the bulletin:
once an hour, during your waking hours, the best queued news per topic in one short message.
The bar moves with the day's pace so volume stays near the daily target:
ahead of target -> stricter, behind -> a little looser, never below the digest's floor."""
DEFAULT_BAR = 65                # priority 0-100; a score-7 story is ~63, score-8 ~72
FLOOR = 61                      # just above the digest's min_priority (60)
MAX_RAISE = 15
LOOSEN_BY = 5
AHEAD_PACE = 1.2
BEHIND_PACE = 0.6
MIN_DAY_FRACTION = 0.05


def is_active(hour: int, start: int, end: int) -> bool:
    return start <= hour < end


def day_fraction(hour: int, minute: int, start: int, end: int) -> float:
    """How far through today's active window we are, 0.05..1."""
    span = max(1, end - start)
    return min(1.0, max(MIN_DAY_FRACTION, (hour + minute / 60 - start) / span))


def bar(base: int, sent_today: int, target_per_day: int, fraction: float) -> int:
    expected = max(1.0, target_per_day * fraction)
    pace = sent_today / expected
    if pace > AHEAD_PACE:
        return base + min(MAX_RAISE, round((pace - 1) * 10))
    if pace < BEHIND_PACE:
        return max(FLOOR, base - LOOSEN_BY)
    return base


def pick(alerts: list, per_topic: int, min_priority: int) -> dict[str, list]:
    """alerts sorted best-first -> {topic: [up to per_topic alerts at or above the bar]}."""
    out: dict[str, list] = {}
    for a in alerts:
        if a.priority < min_priority:
            continue
        chosen = out.setdefault(a.topic, [])
        if len(chosen) < per_topic:
            chosen.append(a)
    return {topic: chosen for topic, chosen in out.items() if chosen}
