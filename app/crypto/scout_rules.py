"""The course's objective coin-selection rules as a pure, testable function.
REJECT = fails a safety/quality rule | WATCH = passes, wrong price location or wrong regime
BUY_ZONE = passes everything AND sits near the bottom of its range AND BTC regime allows it.
BUY_ZONE is a scam filter + location check, NOT a prediction of profit."""
from dataclasses import dataclass, field


@dataclass
class Snapshot:
    chain: str
    address: str
    symbol: str = ""
    name: str = ""
    pair_url: str = ""
    price: float | None = None
    mcap: float | None = None
    fdv: float | None = None
    liquidity: float | None = None
    vol24: float | None = None
    chg24: float | None = None
    age_hours: float | None = None
    range_pos: float | None = None
    drawdown: float | None = None
    websites: list = field(default_factory=list)
    website_alive: bool | None = None
    domain_age_days: int | None = None
    twitter: str | None = None
    telegram: str | None = None
    tg_members: int | None = None
    is_cto: bool = False
    boosted: bool = False
    sec: object = None          # crypto.security.Security


@dataclass
class Verdict:
    stage: str
    score: int
    fails: list
    warns: list


def prefilter(b: dict, R: dict) -> tuple[bool, str]:
    """Cheap filter on DexScreener fields before spending security/OHLCV calls."""
    f = R["filters"]
    mcap, liq, vol, age = b.get("mcap"), b.get("liquidity"), b.get("vol24"), b.get("age_hours")
    if not mcap or not (f["min_mcap"] <= mcap <= f["max_mcap"]):
        return False, "mcap out of range"
    if age is None or not (f["min_age_hours"] <= age <= f["max_age_hours"]):
        return False, "age out of range"
    if (vol or 0) < f["min_volume_24h"]:
        return False, "low volume"
    if not liq or liq > mcap:
        return False, "liquidity missing or > mcap"
    return True, ""


def evaluate(s: Snapshot, R: dict, regime_state: str | None = None) -> Verdict:
    f, h, so, loc = R["filters"], R["holders"], R["socials"], R["price_location"]
    fails, warns = [], []
    sec = s.sec

    # --- security (hard) ---
    if sec is None or not sec.available:
        fails.append("No security report — fail-safe reject")
    else:
        if sec.rugged:
            fails.append("Flagged as rugged")
        if sec.danger:
            fails.append("Security danger: " + ", ".join(sec.danger[:3]))
        warns += [f"Security: {w}" for w in sec.warn[:2]]
        if sec.lp_locked_pct is None:
            warns.append("LP lock unknown — check manually")
        elif sec.lp_locked_pct < R["security"]["min_lp_locked_pct"]:
            fails.append(f"LP locked only {sec.lp_locked_pct:.0f}%")

    # --- market structure (hard) ---
    if s.mcap is None:
        fails.append("No market cap")
    elif not (f["min_mcap"] <= s.mcap <= f["max_mcap"]):
        fails.append(f"Market cap ${s.mcap:,.0f} outside range")
    if s.fdv and s.mcap and s.fdv / s.mcap > f["max_fdv_to_mcap"]:
        fails.append("FDV much larger than market cap (supply overhang)")
    if s.liquidity and s.mcap and s.liquidity > s.mcap:
        fails.append("Liquidity higher than market cap")
    if s.age_hours is not None and s.age_hours < f["min_age_hours"]:
        fails.append(f"Too new ({s.age_hours:.0f}h) — course never trades fresh launches")

    # --- holders ---
    if sec is not None and sec.available:
        if sec.holders is None:
            warns.append("Holder count unknown")
        elif sec.holders < h["hard_min"]:
            fails.append(f"Only {sec.holders} holders")
        elif sec.holders < h["min"]:
            warns.append(f"{sec.holders} holders (< {h['min']})")
        if sec.top_holder_pct is not None:
            if sec.top_holder_pct > h["max_single_wallet_pct"]:
                if not sec.lp_identified:
                    warns.append(f"A wallet holds {sec.top_holder_pct:.1f}% (LP not identified — verify)")
                else:
                    fails.append(f"A private wallet holds {sec.top_holder_pct:.1f}%")
            elif sec.top_holder_pct > h["warn_single_wallet_pct"]:
                warns.append(f"Top private wallet {sec.top_holder_pct:.1f}%")

    # --- community ---
    if not (s.websites or s.twitter or s.telegram):
        fails.append("No socials at all")
    else:
        if not s.twitter:
            warns.append("No X account listed")
        if not s.telegram:
            warns.append("No Telegram listed")
        if not s.websites:
            warns.append("No website listed")
        if s.websites and s.website_alive is False:
            fails.append("Website down — community may have left")
        if s.domain_age_days is not None and s.domain_age_days < so["min_domain_age_days"]:
            warns.append(f"Website domain only {s.domain_age_days} days old")
        if s.tg_members is not None and s.tg_members < so["min_telegram_members"]:
            warns.append(f"Telegram {s.tg_members} members")
    if s.is_cto:
        warns.append("Community takeover (CTO) — lower priority")
    if s.boosted:
        warns.append("Paid DexScreener boost — an ad, not an endorsement")
    text = f"{s.name} {s.symbol}".lower()
    if any(k in text for k in R.get("avoid_name_keywords", [])):
        warns.append("Seasonal/football/country theme — course avoids these")

    # --- stage ---
    at_bottom = s.range_pos is not None and s.range_pos <= loc["max_range_position"]
    deep = s.drawdown is not None and s.drawdown >= loc["min_drawdown_from_ath"]
    if fails:
        stage = "REJECT"
    elif at_bottom and deep:
        stage = "BUY_ZONE"
    else:
        stage = "WATCH"
        if s.range_pos is not None and s.range_pos > 0.7:
            warns.append("Near top of its recent range — don't chase")
    if stage == "BUY_ZONE" and regime_state in R["regime_gate"]["block_buyzone_in"]:
        stage = "WATCH"
        warns.append(f"BTC regime {regime_state} — cheat sheet says wait")

    # --- ranking score (only orders candidates; not a quality guarantee) ---
    score = 50
    if sec is not None and sec.holders:
        score += min(15, sec.holders // 400)
    if s.tg_members:
        score += min(10, s.tg_members // 500)
    if at_bottom:
        score += 10
    if deep:
        score += 5
    score -= 4 * len(warns)
    return Verdict(stage, max(0, min(100, score)), fails, warns)
