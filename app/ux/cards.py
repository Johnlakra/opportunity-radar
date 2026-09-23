"""Plain-English cards. Pure formatting - no network, no Redis, so it is easy to test.

Every card ends with a reminder that this is research, not advice."""
from ..text import age, esc, money, plain_number, price

NOT_ADVICE = "<i>Research only, never a promise. Most small coins go to zero. Not financial advice.</i>"

# Market mood: the regime state the cheat sheet computes -> a traffic light a beginner can read.
MOOD = {
    "ACCUMULATE":      ("🟢", "Good conditions to build slowly",
                        "Bitcoin has already fallen in steps and has had time to settle. The course buys "
                        "here in small pieces - never everything at once."),
    "RANGING":         ("🟡", "No clear signal - be patient",
                        "Nothing is obviously cheap and nothing is obviously topping. Keep any buying small."),
    "CORRECTION_WAIT": ("🟡", "Still falling - wait",
                        "Bitcoin is down but hasn't finished. The course waits for at least two big drops "
                        "and for time to pass before buying."),
    "UP_LEG":          ("🔴", "Don't chase - think about taking profits",
                        "Bitcoin is running. The course does not buy into this; it sells in parts."),
    "SECOND_LEG_UP":   ("🔴", "Late in the run - the course goes flat",
                        "This is the part of the cycle where the course takes the rest of its profits."),
}


def mood_card(reg: dict, fng: dict | None = None) -> str:
    """The 🌡 Market Mood card - replaces having to read /regime's jargon."""
    light, headline, why = MOOD.get(reg.get("state", ""), ("🟡", "No clear signal", ""))
    facts = [f"Bitcoin {money(reg.get('price'))}",
             f"{abs(reg.get('drawdown') or 0):.0%} below its 180-day high",
             f"{reg.get('days_since_top', 0)}d since the last top",
             f"{reg.get('down_legs', 0)} big drop(s) so far"]
    if reg.get("dominance"):
        arrow = ""
        if reg.get("dom_delta_14d") is not None:
            arrow = " rising" if reg["dom_delta_14d"] > 0 else " falling"
        facts.append(f"Bitcoin holds {reg['dominance']:.1f}% of the market{arrow}")
    if fng:
        facts.append(f"Fear &amp; Greed {fng['value']} ({esc(fng['band'])})")
    lines = [f"<b>🌡 Market Mood: {light} {esc(headline)}</b>", " · ".join(facts), "", esc(why)]
    if reg.get("altseason"):
        lines.append("Money looks like it is rotating from Bitcoin into smaller coins.")
    lines += ["", NOT_ADVICE]
    return "\n".join(lines)


STAGE_PLAIN = {
    "BUY_ZONE": ("🎯", "Passes every check, and it is priced low in its own range"),
    "WATCH":    ("👀", "Passes the safety checks, but not at a price the course would buy"),
    "REJECT":   ("⛔", "Fails at least one hard rule - the course would skip it"),
}


def _market_lines(s, R) -> list[str]:
    f = R["filters"]
    out = []
    if s.price:
        out.append(f"💲 One coin costs {price(s.price)} right now")
    if s.mcap is not None:
        ok = f["min_mcap"] <= s.mcap <= f["max_mcap"]
        out.append(f"{'✅' if ok else '⚠️'} Market cap {money(s.mcap)} — everything added up"
                   + ("" if ok else f" (outside the {money(f['min_mcap'])}–{money(f['max_mcap'])} window)"))
    if s.liquidity is not None:
        healthy = s.mcap is None or s.liquidity <= s.mcap
        out.append(f"{'✅' if healthy else '⚠️'} Liquidity {money(s.liquidity)}"
                   + (" — smaller than market cap, which is normal" if healthy else " — larger than market cap"))
    if s.vol24 is not None:
        ok = s.vol24 >= f["min_volume_24h"]
        out.append(f"{'✅' if ok else '⚠️'} {money(s.vol24)} traded in 24h"
                   + (" — people are actually trading it" if ok else " — very quiet"))
    if s.age_hours is not None:
        ok = s.age_hours >= f["min_age_hours"]
        out.append(f"{'✅' if ok else '⛔'} {age(s.age_hours)}"
                   + (" — past the risky launch window" if ok else " — too new to touch"))
    if s.chg24 is not None:
        out.append(("✅ " if s.chg24 <= 0 else "⚠️ ")
                   + (f"Down {abs(s.chg24):.0f}% today — the course buys weakness" if s.chg24 <= 0
                      else f"Up {s.chg24:.0f}% today — the course does not chase pumps"))
    return out


def _safety_lines(s) -> list[str]:
    sec = s.sec
    if sec is None or not sec.available:
        return ["⛔ No safety report available — treated as unsafe until there is one"]
    out = []
    if sec.lp_locked_pct is not None:
        ok = sec.lp_locked_pct >= 90
        out.append(f"{'✅' if ok else '⛔'} Pool money {sec.lp_locked_pct:.0f}% locked"
                   + (" — it cannot be pulled" if ok else " — the team could pull it"))
    else:
        out.append("⚠️ Pool lock unknown — check it yourself before buying")
    if sec.holders is not None:
        out.append(f"{'✅' if sec.holders >= 1000 else '⚠️'} {sec.holders:,} wallets hold it")
    if sec.top_holder_pct is not None:
        ok = sec.top_holder_pct <= 10
        out.append(f"{'✅' if ok else '⛔'} Biggest private wallet owns {sec.top_holder_pct:.1f}%"
                   + ("" if ok else " — one person could dump on you"))
    if sec.danger:
        out.append("⛔ " + esc(", ".join(sec.danger[:3])))
    elif not sec.warn:
        out.append("✅ The safety scan found nothing alarming")
    return out


def _community_lines(s) -> list[str]:
    have = [n for n, v in (("X", s.twitter), ("Telegram", s.telegram), ("website", bool(s.websites))) if v]
    if not have:
        return ["⛔ No X, no Telegram, no website — nobody is home"]
    line = "✅ " + " · ".join(have) + " listed"
    if s.websites and s.website_alive is False:
        line = "⛔ The website is down — the team may have walked away"
    out = [line]
    if s.tg_members is not None:
        out.append(f"{'✅' if s.tg_members >= 1000 else '⚠️'} Telegram group: {s.tg_members:,} members")
    return out


def scorecard(s, v, R: dict) -> str:
    """The 🔎 Check a Coin result, in words a beginner can act on."""
    icon, plain = STAGE_PLAIN.get(v.stage, ("👀", ""))
    head = f"<b>{icon} {esc(s.symbol or '?')}</b>"
    if s.name and s.name != s.symbol:
        head += f" ({esc(s.name)})"
    head += f" on {esc(s.chain)} — <b>{v.score}/100</b>"
    lines = [head, esc(plain), ""]
    lines += _market_lines(s, R) + _safety_lines(s) + _community_lines(s)
    if s.range_pos is not None:
        low = s.range_pos <= R["price_location"]["max_range_position"]
        lines.append(f"{'✅' if low else '⚠️'} Sitting {s.range_pos:.0%} up its recent range"
                     + (" — near the bottom" if low else " — closer to the top"))
    if s.drawdown is not None:
        lines.append(f"📉 {s.drawdown:.0%} below its all-time high")
    extra = [f for f in v.fails if not any(f[:18] in ln for ln in lines)]
    for fail in extra[:3]:
        lines.append(f"⛔ {esc(fail)}")
    for warn in v.warns[:3]:
        lines.append(f"⚠️ {esc(warn)}")
    lines += ["", "Still up to you: is the X account active, does the website look real?", NOT_ADVICE]
    return "\n".join(lines)


def details_card(c, chain_label: str = "") -> str:
    """For chains with no free safety API (TON, Sui, Aptos...): the numbers we can honestly
    show, and a straight answer about what we cannot check."""
    head = f"<b>🔎 {esc(c.symbol or '?')}</b>"
    if c.name and c.name != c.symbol:
        head += f" ({esc(c.name)})"
    lines = [head + f" on {esc(chain_label or c.chain)}", ""]
    if c.price:
        lines.append(f"💲 One coin costs {price(c.price)} right now")
    lines.append(f"📊 Market cap {money(c.mcap)} — everything added up")
    lines.append(f"💧 Liquidity {money(c.liquidity)} · {money(c.vol24)} traded in 24h")
    if c.chg24 is not None:
        lines.append(("📉 Down " if c.chg24 <= 0 else "📈 Up ") + f"{abs(c.chg24):.0f}% today"
                     + (" — the course buys weakness" if c.chg24 <= 0 else " — the course does not chase pumps"))
    lines.append(f"🕒 {age(c.age_hours)}")
    lines.append("✅ Has socials listed" if c.has_socials else "⚠️ No socials listed — nobody is home")
    lines += ["",
              f"<b>⚠️ I cannot run the safety checklist on {esc(chain_label or c.chain)} yet.</b>",
              "There is no free safety report for this chain, so I cannot tell you whether the "
              "pool is locked, who the big holders are, or whether you could sell again. "
              "Treat it as unchecked and look for yourself.",
              "", NOT_ADVICE]
    return "\n".join(lines)


def candidate_label(c) -> str:
    """One search result as a button label - name, price, size, age, socials tick.
    Price and market cap together are what tell two same-named coins apart."""
    bits = [c.symbol or c.name or "?"]
    if c.price:
        bits.append(price(c.price))
    bits += [f"MC {money(c.mcap)}", age(c.age_hours)]
    return " · ".join(bits) + (" ✓" if c.has_socials else " ⚠️")


def candidates_card(query: str, found: list) -> str:
    if not found:
        return (f"Couldn't find <b>{esc(query)}</b> on any chain I watch.\n"
                "Try the exact name, or paste the coin's DexScreener / Solscan link.")
    return (f"Found {len(found)} match(es) for <b>{esc(query)}</b> — tap the one you mean.\n"
            "<i>Price · MC is the whole coin&#39;s value · age · ✓ means it has socials.</i>")


FLAT_BELOW_USD = 0.5          # under half a dollar, "+$0" reads like a bug - say flat instead
CENTS_BELOW_USD = 100


def profit_text(amount: float) -> str:
    if abs(amount) < FLAT_BELOW_USD:
        return "flat"
    sign = "+" if amount > 0 else "-"
    size = abs(amount)
    return f"{sign}${size:,.2f}" if size < CENTS_BELOW_USD else f"{sign}${size:,.0f}"


def enrich(row: dict) -> dict:
    """Everything derived from one journal line, worked out once for the card and the export.

    Market cap drives the multiple (that is what the course tracks); the entry price is what you
    actually paid. Rows saved before the journal stored an entry price get one worked back from
    the market-cap ratio, which holds while the supply does, and is marked as an estimate."""
    entry, value = row.get("entry"), row.get("value")
    out = dict(row)
    out["multiple"] = (value / entry) if (value and entry) else None
    out["value_now"] = (row["usd"] * out["multiple"]) if out["multiple"] else None
    out["profit"] = (out["value_now"] - row["usd"]) if out["value_now"] is not None else None
    out["profit_pct"] = ((out["multiple"] - 1) * 100) if out["multiple"] else None

    entry_price, estimated = row.get("entry_price"), False
    if not entry_price and row.get("unit") == "price":
        entry_price = entry                                   # listed coins: entry IS the price
    elif not entry_price and row.get("price") and value and entry:
        entry_price, estimated = row["price"] * entry / value, True
    out["entry_price"] = entry_price
    out["entry_price_estimated"] = estimated
    return out


def portfolio_card(rows: list[dict]) -> str:
    """One line per holding: what it costs now, what you paid, and where you stand."""
    if not rows:
        return ("<b>📒 Journal</b>\nNothing journalled yet.\n"
                "Tap ➕ Add, type a coin name, and I will store the rest for you.")
    lines, invested, worth = ["<b>📒 Journal</b>"], 0.0, 0.0
    for position, raw in enumerate(rows, start=1):
        row = enrich(raw)
        invested += row["usd"]
        worth += row["value_now"] if row["value_now"] is not None else row["usd"]
        head = f"#{raw.get('n', position)} <b>{esc(row['symbol'])}</b>"
        if row["multiple"] is None:
            lines.append(f"{head} · ${row['usd']:,.0f} in · live value unavailable")
            continue
        entry_price = row["entry_price"]
        moved = (f"{price(entry_price)} → {price(row['price'])}"
                 if entry_price and row.get("price") else price(row.get("price")))
        lines.append(f"{head} · {moved} · ${row['usd']:,.0f} in · "
                     f"{row['multiple']:.2f}x · {profit_text(row['profit'])}")
    total = worth - invested
    lines.append(f"\n<b>Total</b> ${invested:,.0f} in → ${worth:,.0f} ({profit_text(total)})")
    lines.append(NOT_ADVICE)
    return "\n".join(lines)
