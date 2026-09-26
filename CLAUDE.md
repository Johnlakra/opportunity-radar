# Opportunity Radar — CLAUDE.md
A personal multi-agent radar: watches AI + crypto (and any topic you add), filters hard, and sends
only the cream to one Telegram bot. ALERT-ONLY: it never signs up, trades, swaps, or touches keys.

## Runtime agents (app/agents/, scheduled by app/orchestrator.py from config/agents.yaml)
| Agent | Job | Cadence | Uses LLM? |
|---|---|---|---|
| regime | BTC regime from the cheat sheet + dominance; alerts on flips | 4h | no |
| guardian | Your journaled holdings: take-profit levels, community loss, drawdowns | 30m | no |
| news_ai / news_crypto / news_airdrops | collect → dedupe → spam/stale prefilter → cluster same story → batch score (keyword fallback) → research top few → submit (unresearched if research fails) | 15–60m | yes (Gemini) |
| bulletin | Hourly roundup of the best waiting news per topic, active hours only; adaptive bar (app/bulletin_rules.py) | 60m | no |
| majors | Discounted top-200 coins, only when regime allows buying | 12h | no |
| token_scout | DEX tokens through the course checklist, scout-tier chains only (shadow mode by default) | 2h | no |
| curator | Daily summary: top N across ALL agents, max 2/topic, rest dropped; weekly learning on Sundays | 09:00 IST (settable) | no |
| reminders | Sends the ⏰ reminders you set, once each, at priority 95 | 10m | no |
| bot (app/bot.py) | Telegram menu, name search, buttons, commands | always on | no |
All agents submit to app/cream.py (the cream gate): priority ≥85 may ping now (max 3/day; ≥95 =
holding protection, always delivered); queued news above the bulletin bar goes out hourly; the rest
competes for the digest. Gemini calls are budgeted per UTC day in Redis (`score:`/`research:` keys).
Pre-LLM filtering lives in app/story.py (pure). Dedupe is one MGET per run - keep Redis command counts
low (Upstash free tier). On Render, app/health.py self-pings RENDER_EXTERNAL_URL so the service never sleeps.

## Build agents (.claude/agents/) — cheapest capable model per job
| Task | Agent | Model (frontmatter alias → resolves to) |
|---|---|---|
| Add/repair a feed | source-scout | `haiku` → Haiku 4.5 |
| New topic end to end | topic-creator → source-scout | `haiku` → Haiku 4.5 |
| API field drift / broken client | api-watch | `haiku` → Haiku 4.5 |
| Telegram UX: menus, name search, cards, journal flows | telegram-ux-upgrader | `sonnet` → Sonnet 5 |
| News UX: cards, digest, saved/deadlines, settings, health | news-ux-upgrader | `sonnet` → Sonnet 5 |
| Tune a noisy/quiet topic from 👍/👎 | prompt-tuner | `sonnet` → Sonnet 5 |
| Tune token-scout thresholds from shadow data | rule-tuner | `sonnet` → Sonnet 5 |
| Pre-deploy money/wallet safety audit | safety-auditor | `sonnet` → Sonnet 5 |
| Architecture changes / multi-file features | planner → architect | `opus` → Opus 5, then `sonnet` → Sonnet 5 |
| Code review before commit | python-reviewer | `sonnet` → Sonnet 5 |
Each agent's frontmatter carries the tier alias, not a pinned model id, so agents follow the latest
model in their tier. Haiku tier = mechanical edits against a known schema; sonnet tier = judgment over
feedback, thresholds, money safety and review; opus tier = multi-file planning.
Run independent agents in parallel (e.g. source-scout for two topics); run safety-auditor last.

## Telegram UX layer (app/ux/, added on top - old commands still work as hidden aliases)
Shared: `menu.py` is a REGISTRY - each half calls `menu.register(...)`; `glossary.py` is one shared
glossary; `router.py` dispatches buttons (news first, then crypto, then the legacy `v:`/`w:`/`x:`
handler); `dispatch.py` + `text_router.py` turn plain text into an intent (keywords first, one small
Gemini call only as a fallback, menu if both fail).
Crypto half (`m:` + short-id callbacks): `flows.py`, `cards.py`, `tokens.py`, `portfolio.py`,
`topic_wizard.py`; resolution in `app/crypto/resolve.py`, storage in `app/journal.py`.
News half (`n:` callbacks): `news.py` (Today's Best, Saved & Deadlines, Bot Health, item actions),
`settings.py` (Alerts & Topics), `news_cards.py` (pure renderers + deadline parsing),
`news_router.py`; storage in `app/news_store.py`, settings in `app/prefs.py`, channel labels in
`app/topics.py`, weekly learning in `app/learning.py`, new topics via `app/topic_builder.py`.
Gate rules live in `app/gate.py` (pure) and are applied by `app/cream.py`.
Schema: `app/migrate.py` back-fills columns on old databases - create_all() never ALTERs.

## Chains (app/crypto/chains.py - single source of truth, one line per chain)
Two tiers. `security: "rugcheck" | "goplus"` = full checklist; `security: None` = LOOKUP ONLY
(search, price, journal, watchlist, guardian all work; the scout stays away because the checklist
treats a missing safety report as a fail). SCOUT_CHAINS / LOOKUP_ONLY are derived, never hand-listed.
Addresses differ per chain (EVM hex, base58, TON base64url, Move types) - use `chains.find_address`,
`chains.is_address` and `chains.norm`, never a local regex, and never lowercase a non-hex address.

## Rules
- Free tiers only; respect throttles in app/crypto/http.py. Gemini: batch scoring; research capped by RESEARCH_DAILY_CAP.
- Never add auto-trading, auto-signup, wallet signing, or key storage.
- Never loosen security thresholds in topics/token_scout/rules.yaml.
- Never encode "guaranteed profit"/"can't get rugged" claims or multi-wallet (Sybil) farming.
- Settings live in Redis (app/prefs.py). NEVER rewrite config/me.yaml or config/agents.yaml at
  runtime, except the topic wizard appending one validated agent entry.
- Any new Item/Alert/Holding column goes in app/migrate.py too, or old databases break.
- The journal's visible #number is the POSITION (app/journal.holdings_in_order), never the row id -
  the id only travels inside callback_data. Money in a CSV uses text.plain_number, never %g.
- Tests: `pytest -q` must pass before commit. The local interpreter may lack telegram/sqlmodel,
  so keep logic testable in pure modules and guard database tests with `pytest.importorskip`.
