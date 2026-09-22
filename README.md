# Opportunity Radar (AI + Crypto)

A personal team of agents that watches AI and crypto (and any topic you add), throws away almost
everything, and sends **only the cream** to one Telegram bot. It is **alert-only**: it never signs up,
trades, swaps, or touches wallet keys. You decide and act.

**Not financial advice.** The crypto parts are scam filters and context, not profit signals.
Most small-cap tokens go to zero; recent academic measurements put pump.fun "graduation" below 1%.

## How it works
```
 news_ai ─┐                                                   ┌─ urgent ping (priority ≥85, max 3/day;
 news_crypto ─┤                                                │   holding protection ≥95 always)
 news_airdrops ─┤→  cream gate (app/cream.py) ── ranks all ──┤
 majors ─┤          every alert from every agent              └─ daily digest 09:00 IST: top 6 overall,
 token_scout ─┤                                                    max 2 per topic, rest dropped (/more)
 guardian ─┤   ← regime (BTC cheat-sheet state) gates majors + token_scout
```
| Agent | What it does |
|---|---|
| **regime** | Bitcoin regime from your cheat sheet: UP_LEG, SECOND_LEG_UP (go flat), CORRECTION_WAIT (≥2 down-legs + 3 weeks, 3 months in summer), ACCUMULATE, RANGING; plus BTC dominance / altseason signal. |
| **guardian** | Watches your journal: take-profit at 2x/3x/5x/10x, "community left" (website/Telegram gone), drawdowns. |
| **news_ai** | Early access, waitlists, free credits, APIs for your stack. |
| **news_crypto** | Only actionable crypto: confirmed listings, hacks, unlocks, migrations, India rules. |
| **news_airdrops** | Only officially confirmed airdrops; claim link must be on the official domain; drainer patterns rejected. |
| **majors** | Discounted top-200 coins (≥70% below ATH, stabilizing, not yet run) — only when the regime allows buying. |
| **token_scout** | Multi-chain DEX tokens (Solana, Base, Ethereum, BSC, Arbitrum) through the course checklist. **Shadow mode by default.** |
| **curator** | The daily digest. |

## Setup (≈20 minutes)
1. **Telegram:** message @BotFather → `/newbot` → copy the token. Send your bot a message, then open
   `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `chat.id`.
2. **Gemini key:** aistudio.google.com → Get API key (free tier).
3. **CoinGecko demo key (free, recommended):** coingecko.com → Developer dashboard.
4. `cp .env.example .env` and fill in the keys (add `COINGECKO_API_KEY=` too).
5. Edit `config/me.yaml` (your exchanges, wallets, tickers) — items touching these get ⭐ and a boost.
6. Run: `docker compose up -d --build`   (local test: `pytest -q`)

**Free hosting:** Oracle Cloud Always Free ARM VM → install Docker → clone → step 6. Uses ~300 MB RAM.

## Telegram commands
`/digest` `/regime` `/check <chain> <address>` `/watch <chain> <address>`
`/hold cg <coingecko-id> <usd>` (e.g. `/hold cg solana 100`) · `/hold <chain> <address> <usd>`
`/holdings` `/sell <id>` `/mute <topic>` `/unmute <topic>` `/more` (what got filtered) `/agents` `/run <agent>`
Buttons: 👍/👎 teach the scorer · 👀 Watch / 🗑 Ignore on tokens.

## Add any topic (no code)
Copy `topics/ai/` to `topics/<new>/`, edit `profile.md` + `sources.yaml` (RSS or Google News queries),
add an entry in `config/agents.yaml` with `type: news`. Or ask Claude Code: *"use topic-creator to add grants"*.

## Free-tier budget
| Service | Use | Limit respected by |
|---|---|---|
| Gemini Flash-Lite | batched scoring (15 items/call) | ~100 calls/day of 500 |
| Gemini + Google Search | research on top items only | `RESEARCH_DAILY_CAP=40` |
| GeckoTerminal / DexScreener / RugCheck / GoPlus / CoinGecko | crypto data | per-API throttles in `app/crypto/http.py` |

## What came from the course, and what was deliberately left out
**Encoded:** market-cap range, no fresh launches (≥100h), volume, liquidity ≤ mcap, FDV ≈ mcap, holders ≥1000,
no private wallet >10% (LP/locks/CEX excluded), LP locked ≥90%, RugCheck/GoPlus pass, socials alive,
CTO/boosted/seasonal-theme penalties, bottom-of-range + deep below the launch pump, BTC-regime gating,
take profits in parts, exit when the community leaves, journaling, all 15 cheat-sheet regime rules that are measurable.
**Left out:** "guaranteed life-changing money" and "you'll never get rugged" (contradicted by data);
multi-wallet airdrop farming (violates most airdrop terms); following influencer calls; any auto-trading.
**Manual by design:** X/Twitter activity (no free API in 2026), trendline judgment, position sizing.

## Honest limitations
- Token discovery sees trending/top-volume pools and DexScreener's curated lists, not every token.
- Security APIs can miss new scam patterns; LP detection can fail on unusual pools (flagged as "verify").
- The regime detector is rule-based context; seasonality and halving cycles are weak evidence.
- Keep `token_scout` in shadow mode until the rule-tuner agent shows (from /more and the Coin table)
  that it beats random selection in the same market-cap band.
