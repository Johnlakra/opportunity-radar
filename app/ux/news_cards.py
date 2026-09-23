"""News cards in plain English. Pure formatting - no network, no Redis, no database."""
import json
import re
from datetime import datetime, timedelta, timezone

from ..text import esc

NOT_ADVICE = "<i>I only ever read and report. I never sign up, claim or pay for you.</i>"
TOPIC_ICON = {"ai": "🤖", "crypto_news": "🪙", "airdrops": "🎁"}
INDIA = {"available": "yes", "restricted": "no", "unknown": "not sure"}
_MONTHS = ("jan feb mar apr may jun jul aug sep oct nov dec").split()
_DATE_PATTERNS = [
    (re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"), ("y", "m", "d")),
    (re.compile(r"\b(\d{1,2})[/ ](\d{1,2})[/ ](\d{4})\b"), ("d", "m", "y")),
    (re.compile(r"\b([a-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})?\b", re.I), ("mon", "d", "y")),
    (re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]{3,9})\.?,?\s*(\d{4})?\b", re.I), ("d", "mon", "y")),
]


def icon(topic: str) -> str:
    return TOPIC_ICON.get(topic, "📰")


def parse_deadline(text, now: datetime | None = None) -> datetime | None:
    """Best effort on whatever the research wrote ("Sep 30", "2026-09-30", "30 September 2026").
    A date with no year that already passed is read as next year. Returns None when unsure."""
    if not text or not isinstance(text, str):
        return None
    now = now or datetime.now(timezone.utc)
    for pattern, order in _DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        parts = dict(zip(order, match.groups()))
        month = parts.get("m")
        if parts.get("mon"):
            name = parts["mon"][:3].lower()
            if name not in _MONTHS:
                continue
            month = _MONTHS.index(name) + 1
        try:
            day, month = int(parts["d"]), int(month)
            year = int(parts["y"]) if parts.get("y") else now.year
            found = datetime(year, month, day, tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
        if not parts.get("y") and found < now - timedelta(days=1):
            try:
                found = found.replace(year=year + 1)
            except ValueError:
                return None
        return found
    return None


def _info(row) -> dict:
    try:
        return json.loads(row.research_json) if getattr(row, "research_json", None) else {}
    except json.JSONDecodeError:
        return {}


def when(deadline: datetime | None, now: datetime | None = None) -> str:
    if not deadline:
        return ""
    now = now or datetime.now(timezone.utc)
    days = (deadline - now).days
    if days < 0:
        return "closed"
    if days == 0:
        return "today"
    if days == 1:
        return "tomorrow"
    return f"in {days} days" if days < 30 else deadline.strftime("%b %d")


def news_card(row, label: str, now: datetime | None = None) -> str:
    """One thing worth your attention, and what to do about it."""
    info = _info(row)
    head = f"{icon(row.topic)} {esc(label)}"
    if getattr(row, "personal", False):
        head += " · ⭐ touches your setup"
    if getattr(row, "saved", False):
        head += " · ⭐ saved"
    lines = [head, f"<b>{esc(row.title)}</b>"]
    if row.why:
        lines.append(f"Why it matters to you: {esc(row.why)}")
    step = info.get("what_to_do") or row.action
    if step and str(step).lower() != "none":
        lines.append(f"What to do: {esc(step)}")

    facts = []
    deadline = getattr(row, "deadline_at", None)
    if deadline:
        facts.append(f"⏰ Closes {esc(when(deadline, now))}")
    elif info.get("deadline"):
        facts.append(f"⏰ Deadline: {esc(info['deadline'])}")
    india = getattr(row, "india_ok", None) or info.get("india_availability")
    if india:
        facts.append(f"🇮🇳 Usable from India: {esc(INDIA.get(str(india).lower(), india))}")
    cost = getattr(row, "cost", None) or info.get("cost")
    if cost:
        facts.append(f"💰 Cost: {esc(cost)}")
    if facts:
        lines.append(" · ".join(facts))

    if row.source:
        lines.append(f"Source: {esc(row.source)}")
    legitimacy = str(info.get("legitimacy", "")).lower()
    if legitimacy and legitimacy != "confirmed":
        lines.append(f"⚠️ Not confirmed yet — {esc(info.get('evidence') or 'no official source found')}")
    for flag in info.get("red_flags") or []:
        lines.append(f"⚠️ {esc(flag)}")
    return "\n".join(lines)


def research_addition(info: dict) -> str:
    """What "Tell me more" appends to the card."""
    lines = ["", "<b>🔎 What I found</b>"]
    if info.get("what_to_do"):
        lines.append(esc(info["what_to_do"]))
    if info.get("evidence"):
        lines.append(f"Checked against: {esc(info['evidence'])}")
    for flag in info.get("red_flags") or []:
        lines.append(f"⚠️ {esc(flag)}")
    for url in (info.get("_sources") or [])[:3]:
        lines.append(esc(url))
    if len(lines) == 2:
        lines.append("Nothing solid beyond the headline — treat it as unconfirmed.")
    return "\n".join(lines)


def digest_header(counts: dict[str, str]) -> str:
    """counts: label -> how many. "Good morning - 5 things worth your time (2 AI, 1 Crypto)"."""
    total = sum(counts.values())
    if not total:
        return "<b>☀️ Quiet day</b>\nNothing cleared the bar today. That is the system working."
    breakdown = ", ".join(f"{n} {label}" for label, n in counts.items() if n)
    thing = "thing" if total == 1 else "things"
    return (f"<b>☀️ Good morning</b>\n{total} {thing} worth your time today ({esc(breakdown)}).")


def saved_list(rows, now: datetime | None = None) -> str:
    if not rows:
        return ("<b>🗂 Saved &amp; Deadlines</b>\nNothing saved yet.\n"
                "Tap <b>⭐ Save</b> on anything you want to come back to.")
    lines = ["<b>🗂 Saved &amp; Deadlines</b>"]
    for row in rows:
        due = when(getattr(row, "deadline_at", None), now)
        tail = f" · ⏰ {esc(due)}" if due else ""
        lines.append(f"· {icon(row.topic)} <b>{esc(row.title[:90])}</b>{tail}")
    return "\n".join(lines)


def esc_first_line(html_text: str, limit: int = 120) -> str:
    """The headline of an already-rendered card, with its tags stripped."""
    plain = re.sub(r"<[^>]+>", "", (html_text or "").split("\n")[0])
    return esc(plain.strip()[:limit])
