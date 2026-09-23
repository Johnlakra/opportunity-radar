# Opportunity Radar (AI + Crypto)

A personal team of agents that watches AI and crypto (and any topic you add), throws away almost
everything, and sends **only the cream** to one Telegram bot. It is **alert-only**: it never signs up,
trades, swaps, or touches wallet keys. You decide and act.

**Not financial advice.** The crypto parts are scam filters and context, not profit signals.
Most small-cap tokens go to zero; recent academic measurements put pump.fun "graduation" below 1%.

## How it works
```
  news_ai                                            ┌─ instant ping — priority ≥85, up to N a day
  news_crypto                                        │  (you set N, 0–5); quiet hours make it wait
  news_airdrops  ──┐                                 │
  majors           ├─→  cream gate  ──ranks every──  ┤─ holdings protection — priority ≥95, always
  token_scout      │    (app/cream.py)  alert, all   │  delivered: no mute, no quiet hours, no budget
  guardian         │    + app/gate.py   topics       │
  regime           │                                 └─ daily summary at the hour you pick:
  reminders      ──┘                                    top 6 overall, max 2 per topic,
                                                        the rest dropped (🗑 What got filtered)

  the BTC regime state gates what majors and token_scout are allowed to suggest
```
Nothing reaches you except through that gate — there is no side door.

| Agent | What it does |
|---|---|
| **regime** | Bitcoin regime from your cheat sheet: UP_LEG, SECOND_LEG_UP (go flat), CORRECTION_WAIT (≥2 down-legs + 3 weeks, 3 months in summer), ACCUMULATE, RANGING; plus BTC dominance / altseason signal. |
| **guardian** | Watches your journal: take-profit at 2x/3x/5x/10x, "community left" (website/Telegram gone), drawdowns. |
| **news_ai** | Early access, waitlists, free credits, APIs for your stack. |
| **news_crypto** | Only actionable crypto: confirmed listings, hacks, unlocks, migrations, India rules. |
| **news_airdrops** | Only officially confirmed airdrops; claim link must be on the official domain; drainer patterns rejected. |
| **majors** | Discounted top-200 coins (≥70% below ATH, stabilizing, not yet run) — only when the regime allows buying. |
| **token_scout** | DEX tokens through the course checklist, on any chain with a free safety report. **Shadow mode by default.** |
| **curator** | The daily summary, plus a weekly "what I learned from your 👍/👎". |
| **reminders** | Sends the ⏰ reminders you set, once each, never dropped. |

## Setup (≈20 minutes)
1. **Telegram:** message @BotFather → `/newbot` → copy the token. Send your bot a message, then open
   `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `chat.id`.
2. **Gemini key:** aistudio.google.com → Get API key (free tier).
3. **CoinGecko demo key (free, recommended):** coingecko.com → Developer dashboard.
4. `cp .env.example .env` and fill in the keys (add `COINGECKO_API_KEY=` too).
5. Edit `config/me.yaml` (your exchanges, wallets, tickers) — items touching these get ⭐ and a boost.
   You can also edit all of it later from **🎛 Alerts & Topics → 🙋 My setup**, without touching the file.
6. Run: `docker compose up -d --build`   (local test: `pytest -q`)

**Upgrading an existing install:** just pull and rebuild. New columns are added to your existing
`data/radar.db` on boot (`app/migrate.py`), and your journal, watchlist and votes are kept.

**Free hosting:** Oracle Cloud Always Free ARM VM → install Docker → clone → step 6. Uses ~300 MB RAM.

## Using it in Telegram

**The easy way — you never need a contract address.** Send `/menu`, or just type a coin name:

```
you:  bonk
bot:  Found 3 matches for bonk — tap the one you mean.
      [ BONK · $0.000021 · MC $1.9M · 2y old ✓ ]  [ Bonk Inu · $0.00000123 · MC $48k · 21d old ✓ ]
you:  (tap)
bot:  🎯 BONK (Bonk Inu) on solana — 78/100
      💲 One coin costs $0.00000123 right now
      ✅ Market cap $48k — everything added up   ✅ Liquidity $9k — smaller than market cap
      ✅ 21d old — past the risky launch window   ✅ Down 12% today — the course buys weakness
      ✅ Pool money 100% locked — it cannot be pulled   ✅ 2,500 wallets hold it
      [📊 Chart] [🛡 Safety report] [⭐ Watch] [📒 Journal] [🚫 Ignore] [❓ What do these words mean?]
```

A pasted DexScreener / pump.fun / Solscan / Etherscan link, or an address in a forwarded message,
works the same way — the address is resolved and stored for you, and never shown in a button.

| Menu button | Does |
|---|---|
| 🌡 **Market Mood** | One traffic-light card: Bitcoin's state, dominance, Fear & Greed, and what the course does about it |
| 🔎 **Check a Coin** | Search by name or paste anything → the scorecard above |
| 📰 **Today's Best** | The best of everything right now, filterable by topic, without consuming the daily summary |
| 🧭 **Daily Picks** | Sends today's summary now |
| ⭐ **Watchlist** | Coins you follow; the scout re-checks them every run |
| 📒 **Journal** | What you paid → what it costs now, multiple, $ profit, add by tapping, CSV export |
| 🗂 **Saved & Deadlines** | What you starred, and anything closing soon, soonest first |
| 🎛 **Alerts & Topics** | Topics on/off, how picky to be, pings per day, summary time, quiet hours, your setup, what got filtered |
| 🩺 **Bot Health** | 🟢/🟡/🔴 per agent, which feeds are failing, and a Run now button |
| ❓ **Help** | Plain-English glossary for every word on a card |

### The journal

```
📒 Journal
#1 UTYA  · $0.02973 → $0.02973 · $210 in · 1.00x · flat
#2 BRETT · $0.005883 → $0.005881 · $458 in · 1.00x · flat
#3 TROLL · $0.05574 → $0.05854 · $486 in · 1.05x · +$24.29

Total $1,154 in → $1,178 (+$24.17)
```

The number is the position in the list, so removing one never leaves a gap — the database id
travels inside the buttons instead, where it cannot be mistyped. Removing always asks first and
names the coin. `/sell <n>` takes the number you can see.

**⬇️ Export CSV** gives you a spreadsheet, not a data dump: plain decimals throughout (a market cap
is `29732700`, not `2.97327E+07`; a memecoin price is `0.00000000123`, not `1.23E-09`), one line per
holding, and a TOTAL line at the end.

| Column | |
|---|---|
| `#` · `journal_id` · `symbol` · `chain` | which line, and which coin |
| `tracked_on` | `market cap` for DEX tokens, `price` for listed coins — the course tracks market cap |
| `date_added` · `days_held` · `amount_invested_usd` | when and how much |
| `entry_price_usd` · `entry_price_source` | what one coin cost you. `recorded` when the journal saved it; `estimated from market cap` for rows added before it did, worked back from the market-cap ratio |
| `entry_market_cap_usd` · `current_price_usd` · `current_market_cap_usd` | then and now |
| `multiple_x` · `value_now_usd` · `profit_usd` · `profit_pct` · `link` | where you stand |

### News cards you can act on

```
🤖 AI · ⭐ touches your setup
Anthropic opens free Claude credits for devs
Why it matters to you: You build on FastAPI and Next.js
What to do: Sign up with your Google account
⏰ Closes in 5 days · 🇮🇳 Usable from India: yes · 💰 Cost: free
Source: Anthropic
[🔗 Open] [⭐ Save] [⏰ Remind me]
[👍 More like this] [👎 Not useful]
[🙈 Less of this kind] [🔎 Tell me more]
```

**⏰ Remind me** picks an hour, three hours, tomorrow, or the day before it closes — reminders come
through at priority 95, so a mute or quiet hours can never swallow one. **🙈 Less of this kind**
records a 👎 and offers to mute that whole category. **🔎 Tell me more** runs one grounded lookup
on demand and says so politely when the free daily research budget is gone.

### Or just say what you want

```
anything new on AI?          → 📰 Today's Best, filtered to AI
mute airdrops                → turns that topic off
turn airdrops back on        → and on again
find gemini credits          → searches everything that already came through
be stricter with crypto news → raises that topic's bar
remind me about the last one tomorrow
watch hackathons             → sets up a whole new topic, with suggested feeds to approve
bonk                         → still goes to the coin search
```

A keyword router handles all of these for free. Only if it finds nothing does one small Gemini call
get a say, and if that fails too you get the menu — never an error.

### Settings, all on buttons

Topics on/off · how picky per topic (relaxed / normal / strict) · instant pings per day (0–5) ·
daily summary time · quiet hours (pings wait; holdings alerts still come through) · "tell me on
quiet days" · your setup (exchanges, wallets, chains, tickers, interests — including "use the coins
in my journal") · what got filtered, with a 👍 Rescue button.

Everything is stored in Redis. `config/me.yaml` and `config/agents.yaml` are **never rewritten**, so
your comments and formatting stay exactly as you wrote them.

**Every original command still works:**
`/digest` `/regime` `/check <chain> <address>` `/watch <chain> <address>`
`/hold cg <coingecko-id> <usd>` (e.g. `/hold cg solana 100`) · `/hold <chain> <address> <usd>`
`/holdings` `/sell <n>` (the number shown in the journal) `/mute <topic>` `/unmute <topic>` `/more` (what got filtered) `/agents` `/run <agent>`
Buttons: 👍/👎 teach the scorer · 👀 Watch / 🗑 Ignore on tokens.

## Chains

38 chains, in two tiers. Search by name works on all of them, and so do the
journal, watchlist and guardian alerts — `app/crypto/chains.py` is the single source of truth.

| Tier | Chains | What you get |
|---|---|---|
| **Full checklist** (free safety report: RugCheck on Solana, GoPlus elsewhere) | solana, ethereum, base, bsc, arbitrum, polygon, avalanche, optimism, tron, blast, linea, scroll, zksync, mantle, cronos, opbnb, sonic, berachain, unichain, worldchain, abstract, soneium, monad, manta | Everything: the scout crawls them, and 🔎 Check a Coin returns the full scorecard |
| **Lookup only** (no free safety API yet) | ton, sui, aptos, near, sei, hyperevm, starknet, injective, xrpl, celo, pulsechain, ink, hedera, algorand | Name search, price, market cap, liquidity, volume, age, socials, journal, watchlist and take-profit alerts — plus a plain statement that the safety checks could not run |

The scout never crawls the lookup-only tier: the checklist treats "no safety report" as a
fail, so crawling them would only produce ⛔ verdicts that say nothing about the coin. The
moment a free safety API covers one, it is one line in `chains.py` to promote it.

Add a chain to the scout's crawl in `config/agents.yaml` under `token_scout: chains:` —
each extra chain costs a couple of GeckoTerminal calls per run, so keep the list short.

## Add any topic

**From chat:** type `watch hackathons`. The bot suggests 3–5 news searches, you tap the ones to keep,
and it writes `topics/hackathons/` plus the `config/agents.yaml` entry for you. It only ever writes a
validated name and quoted strings, re-parses the config before saving, and changes nothing if that fails.
Restart the worker to pick up the new schedule.

**By hand:** copy `topics/ai/` to `topics/<new>/`, edit `profile.md` + `sources.yaml` (RSS or Google
News queries), add an entry in `config/agents.yaml` with `type: news`. Or ask Claude Code:
*"use topic-creator to add grants"*.

## Where things live
| Path | What is in it |
|---|---|
| `app/agents/` | one file per runtime agent, scheduled from `config/agents.yaml` |
| `app/cream.py` + `app/gate.py` | the single gate every pushed message goes through |
| `app/ux/` | everything you see in Telegram: `menu.py` (shared button registry), `flows.py` + `cards.py` (coins), `news.py` + `settings.py` + `news_cards.py` (news), `text_router.py` + `dispatch.py` (plain English), `glossary.py` |
| `app/crypto/` | chains, resolution by name, price data, safety reports, the checklist |
| `app/prefs.py` | every setting you change from a button (Redis; your YAML is never rewritten) |
| `app/migrate.py` | back-fills new columns on an existing database |
| `topics/<name>/` | `profile.md` (how to score it) + `sources.yaml` (where to look) |

## Free-tier budget
| Service | Use | Limit respected by |
|---|---|---|
| Gemini Flash-Lite | batched scoring (15 items/call) | ~100 calls/day of 500 |
| Gemini + Google Search | research on top items, and 🔎 Tell me more on demand | `RESEARCH_DAILY_CAP=40`, shared by both |
| Gemini Flash-Lite | understanding a typed sentence the keyword router missed | one short call, only as a fallback |
| GeckoTerminal / DexScreener / RugCheck / GoPlus / CoinGecko | crypto data, name search | per-API throttles in `app/crypto/http.py` |
| alternative.me | Fear & Greed for Market Mood | cached 6h in Redis |

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
- Keep `token_scout` in shadow mode until the rule-tuner agent shows (from 🗑 What got filtered and
  the Coin table) that it beats random selection in the same market-cap band.
- TON, Sui, Aptos and the rest of the lookup-only tier have no free safety API, so those coins are
  shown with their numbers and an explicit "I could not check this" — never a pass.
- Deadlines are parsed from whatever the research wrote, so "rolling" or an odd format simply means
  no reminder offer, not a wrong date.
- Searching past items is a plain substring match over what already came through the filter.
