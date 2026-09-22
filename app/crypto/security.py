"""Token security, normalized across chains:
   Solana -> RugCheck (free, no key)   |   EVM chains -> GoPlus (free, no key)."""
from dataclasses import dataclass, field
from .chains import CHAINS
from .http import GOPLUS, RUG, get_json

BURN = {"0x000000000000000000000000000000000000dead", "0x0000000000000000000000000000000000000000"}


@dataclass
class Security:
    source: str
    danger: list = field(default_factory=list)
    warn: list = field(default_factory=list)
    holders: int | None = None
    top_holder_pct: float | None = None      # largest PRIVATE wallet, LP/locks/CEX excluded
    lp_locked_pct: float | None = None
    lp_identified: bool = True
    rugged: bool = False
    available: bool = True                   # False = no report -> treated as a reject (fail-safe)


async def check(c, chain: str, address: str, exchange_wallets: set[str]) -> Security:
    try:
        if chain == "solana":
            rep = await get_json(c, f"https://api.rugcheck.xyz/v1/tokens/{address}/report", RUG)
            return rugcheck_summary(rep, exchange_wallets)
        d = await get_json(c, f"https://api.gopluslabs.io/api/v1/token_security/{CHAINS[chain]['goplus']}",
                           GOPLUS, params={"contract_addresses": address})
        g = (d.get("result") or {}).get(address.lower())
        return goplus_summary(g, exchange_wallets) if g else Security("goplus", available=False)
    except Exception as exc:
        return Security("rugcheck" if chain == "solana" else "goplus", warn=[f"security API error: {exc}"],
                        available=False)


def rugcheck_summary(rep: dict, exchange_wallets: set[str]) -> Security:
    risks = rep.get("risks") or []
    sec = Security("rugcheck",
                   danger=[x.get("name", "?") for x in risks if (x.get("level") or "").lower() == "danger"],
                   warn=[x.get("name", "?") for x in risks if (x.get("level") or "").lower() == "warn"],
                   holders=rep.get("totalHolders"), rugged=bool(rep.get("rugged")))
    markets = rep.get("markets") or []
    locked = [(m.get("lp") or {}).get("lpLockedPct") for m in markets if m.get("lp")]
    locked = [x for x in locked if x is not None]
    sec.lp_locked_pct = max(locked) if locked else None
    pool_addrs = set()
    for m in markets:
        for k in ("pubkey", "liquidityA", "liquidityB", "liquidityAAccount", "liquidityBAccount", "mintLP"):
            if isinstance(m.get(k), str):
                pool_addrs.add(m[k])
    known = set((rep.get("knownAccounts") or {}).keys())
    raw = rep.get("topHolders") or []
    scale = 100.0 if raw and max(float(h.get("pct") or 0) for h in raw) <= 1.0 else 1.0
    private = []
    for h in raw:
        a, o = h.get("address"), h.get("owner")
        if {a, o} & (pool_addrs | known | exchange_wallets):
            continue
        private.append(float(h.get("pct") or 0) * scale)
    sec.top_holder_pct = max(private) if private else None
    sec.lp_identified = bool(pool_addrs or known)
    return sec


def goplus_summary(g: dict, exchange_wallets: set[str]) -> Security:
    flag = lambda k: str(g.get(k, "0")) == "1"          # noqa: E731
    sec = Security("goplus")
    for key, label in [("is_honeypot", "Honeypot (can't sell)"), ("cannot_sell_all", "Cannot sell all"),
                       ("owner_change_balance", "Owner can change balances"), ("hidden_owner", "Hidden owner"),
                       ("can_take_back_ownership", "Ownership can be reclaimed"), ("selfdestruct", "Self-destruct"),
                       ("transfer_pausable", "Transfers can be paused"), ("is_blacklisted", "Blacklist function")]:
        if flag(key):
            sec.danger.append(label)
    if str(g.get("is_open_source", "1")) == "0":
        sec.danger.append("Contract source not verified")
    try:
        tax = max(float(g.get("buy_tax") or 0), float(g.get("sell_tax") or 0))
        if tax > 0.10:
            sec.danger.append(f"Tax {tax:.0%}")
        elif tax > 0.05:
            sec.warn.append(f"Tax {tax:.0%}")
    except ValueError:
        pass
    if flag("is_mintable"):
        sec.warn.append("Mintable supply")
    try:
        sec.holders = int(g.get("holder_count")) if g.get("holder_count") else None
    except ValueError:
        pass
    private = [float(h.get("percent") or 0) * 100 for h in g.get("holders") or []
               if str(h.get("is_locked")) != "1" and str(h.get("is_contract")) != "1" and not h.get("tag")
               and (h.get("address") or "").lower() not in exchange_wallets | BURN]
    sec.top_holder_pct = max(private) if private else None
    lp = g.get("lp_holders") or []
    sec.lp_identified = bool(lp)
    if lp:
        sec.lp_locked_pct = 100 * sum(float(h.get("percent") or 0) for h in lp
                                      if str(h.get("is_locked")) == "1" or (h.get("address") or "").lower() in BURN)
    return sec
