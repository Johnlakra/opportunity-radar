"""TokenScoutAgent: multi-chain DEX token scout applying the course's objective rules.
Discovery (free): GeckoTerminal trending + top-volume pools per chain, DexScreener latest
profiles / CTO list / boosts, plus your watchlist. Security: RugCheck (Solana) / GoPlus (EVM).
Default shadow_mode=true: verdicts are logged, not pushed, until you have evidence it's useful."""
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from sqlmodel import select

from .. import cream
from ..crypto import dexscreener as dx
from ..crypto import geckoterminal as gt
from ..crypto import regime, security, socials
from ..crypto.chains import CHAINS, GECKO_TO_CHAIN, coin_key, norm
from ..crypto.http import client
from ..crypto.scout_rules import Snapshot, evaluate, prefilter
from ..db import session
from ..models import Coin
from ..notifier import esc
from ..redis_client import r

log = logging.getLogger(__name__)
RULES = Path("topics/token_scout/rules.yaml")


def load_rules() -> dict:
    return yaml.safe_load(RULES.read_text(encoding="utf-8"))


class TokenScoutAgent:
    kind = "token_scout"

    def __init__(self, name, cfg):
        self.name = name
        self.chains = [ch for ch in cfg.get("chains", list(CHAINS)) if ch in CHAINS]
        self.shadow = bool(cfg.get("shadow_mode", True))

    # ---------------- discovery ----------------
    async def discover(self, c, R) -> tuple[dict, set, set]:
        cands: dict[str, set] = {ch: set() for ch in self.chains}
        boosted, ctos = set(), set()
        d = R["discovery"]
        for ch in self.chains:
            net = CHAINS[ch]["gecko"]
            for fetch in (gt.trending_pools, gt.top_volume_pools):
                for page in range(1, d["gecko_pages"] + 1):
                    try:
                        for pool in await fetch(c, net, page):
                            addr = gt.pool_token_address(pool)
                            if addr:
                                cands[ch].add(norm(ch, addr))
                    except Exception as exc:
                        log.warning("gecko %s p%s: %s", net, page, exc)
        for fn, bucket in ((dx.latest_profiles, None), (dx.latest_ctos, ctos), (dx.latest_boosts, boosted)):
            try:
                for ch, addr in await fn(c):
                    if ch in cands:
                        cands[ch].add(addr)
                        if bucket is not None:
                            bucket.add(coin_key(ch, addr))
            except Exception as exc:
                log.warning("dexscreener list: %s", exc)
        with session() as s:
            for coin in s.exec(select(Coin).where(Coin.user_status == "watch")).all():
                if coin.chain in cands:
                    cands[coin.chain].add(coin.address)
        return cands, boosted, ctos

    # ---------------- deep check ----------------
    async def snapshot(self, c, chain, addr, pair, R, boosted=(), ctos=()) -> Snapshot:
        b = dx.basics(pair)
        key = coin_key(chain, addr)
        s = Snapshot(chain=chain, address=addr, symbol=b["symbol"], name=b["name"], pair_url=b["pair_url"],
                     mcap=b["mcap"], fdv=b["fdv"], liquidity=b["liquidity"], vol24=b["vol24"],
                     age_hours=b["age_hours"], websites=b["websites"], twitter=b["twitter"],
                     telegram=b["telegram"], is_cto=key in ctos, boosted=b["boosted"] or key in boosted)
        s.sec = await security.check(c, chain, addr, set(w.lower() if chain != "solana" else w
                                                          for w in R.get("exchange_wallets", [])))
        net = CHAINS[chain]["gecko"]
        try:
            daily = await gt.ohlcv(c, net, b["pool"], "day", 1, 120)
            h4 = await gt.ohlcv(c, net, b["pool"], "hour", 4, 6 * R["price_location"]["range_window_days"])
            loc = gt.price_location(daily, h4)
            s.range_pos, s.drawdown = loc.get("range_pos"), loc.get("drawdown")
        except Exception as exc:
            log.info("ohlcv %s: %s", key, exc)
        if s.websites:
            s.website_alive = await socials.website_alive(c, s.websites[0])
            s.domain_age_days = await socials.domain_age_days(c, s.websites[0])
        s.tg_members = await socials.telegram_members(c, s.telegram)
        return s

    async def run(self):
        R = load_rules()
        reg = await regime.current()
        recheck = timedelta(minutes=R["discovery"]["recheck_minutes"])
        async with client() as c:
            cands, boosted, ctos = await self.discover(c, R)
            queue = []
            for ch, addrs in cands.items():
                fresh = [a for a in addrs if not r.exists(f"scout:seen:{coin_key(ch, a)}")]
                if not fresh:
                    continue
                pairs = dx.best_pairs(ch, await dx.pairs_for(c, ch, fresh))
                for addr, pair in pairs.items():
                    ok, _ = prefilter(dx.basics(pair), R)
                    r.set(f"scout:seen:{coin_key(ch, addr)}", 1, ex=int(recheck.total_seconds()))
                    if ok:
                        queue.append((ch, addr, pair))
            queue.sort(key=lambda x: -((x[2].get("volume") or {}).get("h24") or 0))
            queue = queue[:R["discovery"]["max_deep_checks_per_run"]]
            log.info("[scout] %d candidates -> %d deep checks", sum(map(len, cands.values())), len(queue))
            for ch, addr, pair in queue:
                snap = await self.snapshot(c, ch, addr, pair, R, boosted, ctos)
                verdict = evaluate(snap, R, reg["state"])
                await self.record(snap, verdict)

    async def record(self, snap: Snapshot, v):
        key = coin_key(snap.chain, snap.address)
        with session() as s:
            coin = s.get(Coin, key) or Coin(key=key, chain=snap.chain, address=snap.address)
            prev_stage = coin.stage if coin.last_checked else ""
            coin.symbol, coin.name, coin.pair_url = snap.symbol, snap.name, snap.pair_url
            coin.stage, coin.score, coin.mcap = v.stage, v.score, snap.mcap
            coin.reasons_json = json.dumps({"fails": v.fails, "warns": v.warns})
            coin.last_checked = datetime.now(timezone.utc)
            ignored = coin.user_status == "ignore"
            s.add(coin)
            s.commit()
        if v.stage == "BUY_ZONE" and prev_stage != "BUY_ZONE" and not self.shadow and not ignored:
            pri = min(80, 60 + v.score // 5)          # never urgent: patience is the course's rule
            await cream.submit(f"scout:{key}:{datetime.now(timezone.utc):%Y%W}", "token_scout", pri,
                               format_verdict(snap, v), scout_buttons(snap))

    async def check_one(self, chain: str, address: str) -> tuple[str, str]:
        R = load_rules()
        reg = await regime.current()
        addr = norm(chain, address)
        async with client() as c:
            pair = dx.best_pairs(chain, await dx.pairs_for(c, chain, [addr])).get(addr)
            if not pair:
                return "No DEX pair found for that address on " + esc(chain), "[]"
            snap = await self.snapshot(c, chain, addr, pair, R)
        v = evaluate(snap, R, reg["state"])
        await self.record(snap, v)
        return format_verdict(snap, v), scout_buttons(snap)


def format_verdict(s: Snapshot, v) -> str:
    icon = {"BUY_ZONE": "🎯", "WATCH": "👀", "REJECT": "⛔"}[v.stage]
    sec = s.sec
    lines = [f"<b>{icon} {v.stage}: {esc(s.symbol)}</b> ({esc(s.name)}) · {esc(s.chain)}",
             f"MCap ${s.mcap or 0:,.0f} · Liq ${s.liquidity or 0:,.0f} · Vol24 ${s.vol24 or 0:,.0f} · "
             f"Age {(s.age_hours or 0) / 24:.0f}d"]
    if s.range_pos is not None:
        lines.append(f"Range position {s.range_pos:.0%} · {s.drawdown or 0:.0%} below ATH")
    if sec is not None and sec.available:
        top = f"{sec.top_holder_pct:.1f}%" if sec.top_holder_pct is not None else "?"
        lp = f"{sec.lp_locked_pct:.0f}%" if sec.lp_locked_pct is not None else "?"
        lines.append(f"Holders {sec.holders or '?'} · top private wallet {top} · LP locked {lp} ({sec.source})")
    web = "✅" if s.website_alive else ("❌" if s.websites else "—")
    lines.append(f"🌐 {web} · X {'✅' if s.twitter else '—'} · TG {s.tg_members if s.tg_members is not None else ('✅' if s.telegram else '—')}")
    for f in v.fails[:4]:
        lines.append(f"⛔ {esc(f)}")
    for w in v.warns[:5]:
        lines.append(f"⚠️ {esc(w)}")
    if v.stage != "REJECT":
        lines.append("Manual checks left: X activity/engagement, website quality, then decide yourself.")
    lines.append("<i>Scam filter + location check, not a profit signal. Most such tokens go to zero. Not financial advice.</i>")
    return "\n".join(lines)


def scout_buttons(s: Snapshot) -> str:
    key = coin_key(s.chain, s.address)
    sec_url = (f"https://rugcheck.xyz/tokens/{s.address}" if s.chain == "solana"
               else f"https://gopluslabs.io/token-security/{CHAINS[s.chain]['goplus']}/{s.address}")
    return cream.buttons([("📊 Chart", s.pair_url or None, None), ("🛡 Security", sec_url, None)],
                         [("👀 Watch", None, f"w:{key}"), ("🗑 Ignore", None, f"x:{key}")])
