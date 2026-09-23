"""Text helpers shared by every formatter - cards, agent alerts, buttons.
Deliberately dependency-free so the pure formatting layer stays easy to test."""
import html
import math

MAX_PRICE_DECIMALS = 12


def esc(s) -> str:
    """HTML-escape anything before it goes into a Telegram message."""
    return html.escape(str(s)) if s not in (None, "") else ""


def money(x) -> str:
    """$48k, $1.9M - the way a person would say a market cap."""
    if x is None:
        return "?"
    if x >= 1_000_000:
        return f"${x / 1_000_000:,.1f}M"
    if x >= 1_000:
        return f"${x / 1_000:,.0f}k"
    return f"${x:,.0f}"


def price(x) -> str:
    """A coin price at any size: $121,345 · $2.34 · $0.50 · $0.00000123.
    Small-cap tokens live far below a cent, so keep enough decimals to tell them apart."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "?"
    if x <= 0:
        return "?"
    if x >= 1_000:
        return f"${x:,.0f}"
    if x >= 1:
        return f"${x:,.2f}"
    decimals = min(MAX_PRICE_DECIMALS, -math.floor(math.log10(x)) + 3)
    digits = f"{x:.{decimals}f}".rstrip("0")
    whole, _, fraction = digits.partition(".")
    return f"${whole}.{fraction.ljust(2, '0')}"


def age(hours) -> str:
    """Hours since the pair opened, said in days or months."""
    if hours is None:
        return "age unknown"
    days = hours / 24
    return f"{hours:.0f}h old" if days < 2 else (f"{days:.0f}d old" if days < 90 else f"{days / 30:.0f}mo old")


def as_data(text, limit: int = 500) -> str:
    """Remote text (titles, summaries, coin names) is DATA, never instructions.
    Strip control characters and cap the length before it can reach a prompt."""
    cleaned = "".join(ch for ch in str(text or "") if ch == "\n" or ch >= " ")
    return cleaned[:limit]


def plain_number(value, decimals: int = 12) -> str:
    """Decimal notation for a spreadsheet cell, never 2.97327E+07 or 1.23e-09.
    Trailing zeros are trimmed, so 29732700.0 -> "29732700" and 1.23e-9 -> "0.00000000123"."""
    if value in (None, ""):
        return ""
    try:
        text = f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return ""
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"
