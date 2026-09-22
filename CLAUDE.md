# Opportunity Radar — CLAUDE.md
A personal multi-agent radar: watches AI + crypto (and any topic you add), filters hard, and sends
only the cream to one Telegram bot. ALERT-ONLY: it never signs up, trades, swaps, or touches keys.

## Runtime agents (app/agents/, scheduled by app/orchestrator.py from config/agents.yaml)
| Agent | Job | Cadence | Uses LLM? |
|---|---|---|---|
| regime | BTC regime from the cheat sheet + dominance; alerts on flips | 4h | no |
| guardian | Your journaled holdings: take-profit levels, community loss, drawdowns | 30m | no |
| news_ai / news_crypto / news_airdrops | collect → dedupe → batch score → research top few → submit | 45–90m | yes (Gemini) |
| majors | Discounted top-200 coins, only when regime allows buying | 12h | no |
| token_scout | Multi-chain DEX tokens through the course checklist (shadow mode by default) | 2h | no |
| curator | Daily digest: top N across ALL agents, max 2/topic, rest dropped | 09:00 IST | no |
| bot (app/bot.py) | Telegram commands + buttons | always on | no |
All agents submit to app/cream.py (the cream gate): priority ≥85 may ping now (max 3/day; ≥95 =
holding protection, always delivered), everything else competes for the digest.

## Build agents (.claude/agents/) — cheapest capable model per job
| Task | Agent | Model |
|---|---|---|
| Add/repair a feed | source-scout | haiku |
| New topic end to end | topic-creator → source-scout | haiku |
| API field drift / broken client | api-watch | haiku |
| Tune a noisy/quiet topic from 👍/👎 | prompt-tuner | sonnet |
| Tune token-scout thresholds from shadow data | rule-tuner | sonnet |
| Pre-deploy money/wallet safety audit | safety-auditor | sonnet |
| Architecture changes / multi-file features | ECC `planner` + `architect` | opus/sonnet |
| Code review before commit | ECC `python-reviewer` | sonnet |
Run independent agents in parallel (e.g. source-scout for two topics); run safety-auditor last.

## Rules
- Free tiers only; respect throttles in app/crypto/http.py. Gemini: batch scoring; research capped by RESEARCH_DAILY_CAP.
- Never add auto-trading, auto-signup, wallet signing, or key storage.
- Never loosen security thresholds in topics/token_scout/rules.yaml.
- Never encode "guaranteed profit"/"can't get rugged" claims or multi-wallet (Sybil) farming.
- Tests: `pytest -q` must pass before commit.
