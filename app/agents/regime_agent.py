"""RegimeAgent: computes the BTC regime (cheat sheet) and alerts on meaningful flips."""
from datetime import datetime, timezone
from sqlmodel import select

from .. import cream
from ..crypto import regime
from ..db import session
from ..models import Holding
from ..redis_client import r


class RegimeAgent:
    kind = "regime"

    def __init__(self, name, cfg):
        self.name, self.cfg = name, cfg

    async def run(self):
        reg = await regime.compute()
        prev = r.get("btc:regime:last_state")
        r.set("btc:regime:last_state", reg["state"])
        if prev is None or prev == reg["state"]:
            return
        with session() as s:
            has_holdings = bool(s.exec(select(Holding)).first())
        state = reg["state"]
        if state == "SECOND_LEG_UP":
            pri = 97 if has_holdings else 80
        elif state == "UP_LEG":
            pri = 92 if has_holdings else 75
        elif state == "CORRECTION_WAIT" and prev in ("UP_LEG", "SECOND_LEG_UP"):
            pri = 96 if has_holdings else 78   # top likely in: "sell even the coins that didn't pump"
        elif state == "ACCUMULATE":
            pri = 86
        else:
            pri = 65
        text = f"🔁 Regime changed: {prev} → {state}\n\n" + regime.format_regime(reg)
        if state in ("CORRECTION_WAIT",) and prev in ("UP_LEG", "SECOND_LEG_UP") and has_holdings:
            text += "\n\nCheat sheet: when BTC tops, alts fall harder — the course sells even coins that didn't pump."
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        await cream.submit(f"regime:{state}:{day}", "regime", pri, text)
