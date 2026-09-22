"""MajorsAgent: the non-meme part of the cheat sheet (rule #7: layer-1s, narrative coins, BTC).
Finds established top-N coins that are deeply discounted, stabilizing, and haven't run yet -
but ONLY when the regime allows buying (ACCUMULATE / RANGING / altseason). Research candidates."""
from datetime import datetime, timezone

from .. import cream
from ..crypto import coingecko, regime
from ..crypto.http import client
from ..notifier import esc

STABLE_WORDS = ("usd", "eur", "wrapped", "staked", "bridged", "restaked", "liquid staking", "tether", "gold")


def is_stable_or_wrapper(c: dict) -> bool:
    name = f"{c.get('name', '')} {c.get('symbol', '')}".lower()
    if any(w in name for w in STABLE_WORDS):
        return True
    price, ath = c.get("current_price") or 0, c.get("ath") or 0
    return 0.95 <= price <= 1.05 and ath and ath < 1.5


class MajorsAgent:
    kind = "majors"

    def __init__(self, name, cfg):
        self.name = name
        self.rank_max = cfg.get("rank_max", 200)
        self.min_ath_drawdown = cfg.get("min_ath_drawdown_pct", 70)
        self.max_per_run = cfg.get("max_per_run", 3)

    async def run(self):
        reg = await regime.current()
        if reg["state"] not in ("ACCUMULATE", "RANGING") and not reg.get("altseason"):
            return                                   # cheat sheet: don't buy in up-legs / fresh corrections
        async with client() as c:
            coins = await coingecko.markets(c, 1) + await coingecko.markets(c, 2)
        btc30 = reg["chg30"] * 100
        picks = []
        for x in coins:
            rank = x.get("market_cap_rank") or 9999
            if rank > self.rank_max or is_stable_or_wrapper(x):
                continue
            ath_chg = x.get("ath_change_percentage") or 0
            c30 = x.get("price_change_percentage_30d_in_currency")
            vol, mcap = x.get("total_volume") or 0, x.get("market_cap") or 0
            if c30 is None or not mcap:
                continue
            if (ath_chg <= -self.min_ath_drawdown          # deep discount
                    and -15 <= c30 <= 40                   # stabilizing, not a falling knife, not already pumped
                    and c30 <= btc30 + 10                  # hasn't outrun BTC ("hasn't done its move yet")
                    and vol / mcap >= 0.02):               # still actively traded
                picks.append(x)
        picks.sort(key=lambda x: -(x["total_volume"] / x["market_cap"]))
        week = datetime.now(timezone.utc).strftime("%G%V")
        for x in picks[:self.max_per_run]:
            text = (f"<b>🏛 Discounted major: {esc(x['name'])} ({esc(x['symbol'].upper())})</b> · rank #{x['market_cap_rank']}\n"
                    f"{x['ath_change_percentage']:.0f}% from ATH · 30d {x['price_change_percentage_30d_in_currency']:+.0f}% "
                    f"(BTC {btc30:+.0f}%) · vol/mcap {x['total_volume'] / x['market_cap']:.1%}\n"
                    f"Regime: {reg['state']}{' · altseason signal' if reg.get('altseason') else ''}\n"
                    "Research first: is the project alive (dev activity, users, unlocks ahead)? "
                    "Cheat sheet: DCA, never all at once, keep allocation balanced (#6, #7).\n"
                    "<i>Candidate for research, not a recommendation.</i>")
            url = f"https://www.coingecko.com/en/coins/{x['id']}"
            await cream.submit(f"major:{x['id']}:{week}", "majors", 66, text,
                               cream.buttons([("📊 CoinGecko", url, None)]))
