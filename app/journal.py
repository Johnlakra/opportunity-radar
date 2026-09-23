"""Journal and watchlist storage. Same two tables the bot has always used (Holding, Coin) -
this module just gives the button flows one place to read and write them."""
from sqlmodel import select

from .db import session
from .models import Coin, Holding

STATUSES = ("", "watch", "ignore")


def set_status(key: str, status: str) -> None:
    """Mark a coin watched or ignored. `key` is "<chain>:<address>"."""
    if status not in STATUSES:
        raise ValueError(f"unknown status: {status}")
    chain, _, addr = key.partition(":")
    with session() as s:
        coin = s.get(Coin, key) or Coin(key=key, chain=chain, address=addr)
        coin.user_status = status
        s.add(coin)
        s.commit()


def watchlist() -> list[Coin]:
    with session() as s:
        return list(s.exec(select(Coin).where(Coin.user_status == "watch")
                           .order_by(Coin.score.desc())).all())


def add_dex_holding(key: str, symbol: str, entry_mcap: float, usd: float,
                    entry_price: float | None = None) -> Holding:
    """Journal a DEX token at its CURRENT market cap - the course tracks market cap, not price -
    and keep the price you paid alongside it."""
    holding = Holding(kind="dex", ref=key, symbol=symbol or key, entry_value=entry_mcap or 0,
                      entry_price=entry_price, usd=usd)
    with session() as s:
        s.add(holding)
        s.commit()
        s.refresh(holding)
    return holding


def remove_holding(holding_id: int) -> bool:
    with session() as s:
        holding = s.get(Holding, holding_id)
        if not holding:
            return False
        s.delete(holding)
        s.commit()
    return True


def holdings_symbols() -> list[str]:
    """Tickers you have journalled, for the scorer's "my setup"."""
    with session() as s:
        rows = s.exec(select(Holding)).all()
    seen = []
    for holding in rows:
        symbol = (holding.symbol or "").upper().strip()
        if symbol and symbol not in seen:
            seen.append(symbol)
    return seen


def holdings_in_order() -> list[Holding]:
    """Oldest first. Position in this list is the #number you see; it always starts at 1,
    so removing one never leaves a gap."""
    with session() as s:
        return list(s.exec(select(Holding).order_by(Holding.added_at, Holding.id)).all())


def get_holding(holding_id: int) -> Holding | None:
    with session() as s:
        return s.get(Holding, holding_id)


def holding_at(position: int) -> Holding | None:
    """The holding shown as #position, or None if there is no such line."""
    rows = holdings_in_order()
    return rows[position - 1] if 1 <= position <= len(rows) else None
