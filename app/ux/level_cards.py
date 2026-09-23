"""How a level break reads in Telegram. Pure formatting - no network, no database, no Redis."""
from ..levels import PERIOD_NAMES, PERIODS, distance_pct, with_premium
from ..text import esc, money, price as fmt_price

NOT_A_SIGNAL = "<i>Level break, not a buy/sell signal. Not financial advice.</i>"
BUILDING = "building history"
# Metals are stored per gram and quoted the Indian way; crypto is quoted as it trades.
UNITS = {
    "metal:XAU": {"icon": "🥇", "scale": 10, "suffix": " /10g", "rupees": True,
                  "note": "intl spot in ₹"},
    "metal:XAG": {"icon": "🥈", "scale": 1000, "suffix": " /kg", "rupees": True,
                  "note": "intl spot in ₹"},
}
CRYPTO_UNIT = {"icon": "🪙", "scale": 1, "suffix": "", "rupees": False, "note": ""}
ARROW = {"up": "ABOVE", "down": "BELOW"}
EDGE = {"up": "high", "down": "low"}


def unit_of(asset_key: str) -> dict:
    return UNITS.get(asset_key, CRYPTO_UNIT)


def icon_for(asset_key: str, source: str = "") -> str:
    if asset_key in UNITS:
        return UNITS[asset_key]["icon"]
    return "📒" if source == "journal" else "🪙"


def fmt_value(asset_key: str, value, premium_pct: float = 0) -> str:
    """One number, in the unit a person would actually quote it in."""
    if value is None:
        return "?"
    unit = unit_of(asset_key)
    shown = with_premium(value * unit["scale"], premium_pct if unit["rupees"] else 0)
    return f"₹{shown:,.0f}{unit['suffix']}" if unit["rupees"] else fmt_price(shown)


def fmt_compact(asset_key: str, value, premium_pct: float = 0) -> str:
    """The same number without its unit, for the one-line summary where the unit is already said."""
    if value is None:
        return "?"
    unit = unit_of(asset_key)
    shown = with_premium(value * unit["scale"], premium_pct if unit["rupees"] else 0)
    return f"{shown:,.0f}" if unit["rupees"] else fmt_price(shown)


def levels_line(asset_key: str, found: dict, premium_pct: float = 0) -> str:
    """"W 73,980/72,410 · M 74,250/71,020 · ..." - every period we actually know, high/low."""
    parts = []
    for period in PERIODS:
        pair = found.get(period)
        if not pair:
            continue
        high, low = pair
        parts.append(f"{period} {fmt_compact(asset_key, high, premium_pct)}"
                     f"/{fmt_compact(asset_key, low, premium_pct)}")
    return "Levels · " + " · ".join(parts) if parts else ""


def break_card(sub_label: str, asset_key: str, period: str, direction: str, price: float,
               level: float, found: dict, source: str = "", premium_pct: float = 0,
               extra: list[str] | None = None, approximate: bool = False) -> str:
    """The message you get when something breaks out."""
    beyond = distance_pct(price, level)
    unit = unit_of(asset_key)
    head = (f"<b>{icon_for(asset_key, source)} {esc(sub_label.upper())} broke {ARROW[direction]} "
            f"last {PERIOD_NAMES[period]}'s {EDGE[direction]}</b>")
    facts = [fmt_value(asset_key, price, premium_pct),
             f"level {fmt_value(asset_key, level, premium_pct)}"]
    if beyond is not None:
        facts.append(f"{beyond:+.2f}% beyond")
    if unit["note"]:
        facts.append(f"({unit['note']})")
    lines = [head, " · ".join(facts)]
    lines += extra or []
    line = levels_line(asset_key, found, premium_pct)
    if line:
        lines.append(line)
    if approximate:
        lines.append("<i>Levels from daily closes only — treat them as approximate.</i>")
    lines.append(NOT_A_SIGNAL)
    return "\n".join(lines)


def holding_line(symbol: str, entry_value: float, current_value: float, unit: str) -> str:
    """"📒 You hold: entry market cap $50k · now 2.30x" - only for coins in your journal."""
    entry_text = money(entry_value) if unit == "market cap" else fmt_price(entry_value)
    if entry_value and current_value:
        return f"📒 You hold: entry {unit} {entry_text} · now {current_value / entry_value:.2f}x"
    return f"📒 You hold: entry {unit} {entry_text}"


def levels_table(label: str, asset_key: str, price, found: dict, missing: list[str],
                 premium_pct: float = 0, source: str = "") -> str:
    """The /levels reply: every level, and how far away it is."""
    lines = [f"<b>{icon_for(asset_key, source)} {esc(label)} — levels</b>",
             f"Now {fmt_value(asset_key, price, premium_pct)}", ""]
    for period in PERIODS:
        pair = found.get(period)
        if not pair:
            if period in missing:
                lines.append(f"<b>{period}</b> · {BUILDING}")
            continue
        high, low = pair
        to_high, to_low = distance_pct(price, high), distance_pct(price, low)
        lines.append(
            f"<b>{period}</b> (last {PERIOD_NAMES[period]}) · high {fmt_value(asset_key, high, premium_pct)}"
            + (f" ({to_high:+.1f}%)" if to_high is not None else "")
            + f" · low {fmt_value(asset_key, low, premium_pct)}"
            + (f" ({to_low:+.1f}%)" if to_low is not None else ""))
    if not found:
        lines.append("No completed period has enough history yet — give it a few days.")
    unit = unit_of(asset_key)
    if unit["note"]:
        lines.append(f"<i>{unit['note']}</i>")
    lines.append(NOT_A_SIGNAL)
    return "\n".join(lines)


def menu_row(sub, on_periods: str) -> str:
    """One line of the /alerts menu."""
    icon = icon_for(sub.asset_key, sub.source)
    if not sub.active:
        return f"{icon} <b>{esc(sub.label)}</b> · off"
    arrows = ("↑" if sub.up else "") + ("↓" if sub.down else "")
    shown = " ".join(on_periods) if on_periods else "no periods"
    return f"{icon} <b>{esc(sub.label)}</b> · {shown} {arrows or '—'}"


def menu_text(rows: list[str], paused: bool) -> str:
    head = ["<b>🔔 Level alerts</b>",
            "<i>W=week M=month Q=quarter Y=year · ↑ breaks the previous high · ↓ breaks the low</i>"]
    if paused:
        head.append("⏸ <b>All alerts are paused.</b>")
    if not rows:
        head.append("\nNothing watched yet. Gold and silver appear after the first run.")
    return "\n".join(head + ([""] + rows if rows else []))


def panel_text(sub, on_periods: str, found: dict, price, premium_pct: float = 0) -> str:
    lines = [f"<b>{icon_for(sub.asset_key, sub.source)} {esc(sub.label)}</b>",
             f"Now {fmt_value(sub.asset_key, price, premium_pct)}" if price else "Price not in yet",
             f"Watching: {' '.join(on_periods) if on_periods else 'no periods'} · "
             + (("↑" if sub.up else "") + ("↓" if sub.down else "") or "neither direction"),
             "Alerts are " + ("on" if sub.active else "<b>off</b>") + " for this one."]
    line = levels_line(sub.asset_key, found, premium_pct)
    if line:
        lines.append(line)
    return "\n".join(lines)
