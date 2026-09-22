---
name: api-watch
description: Smoke-tests every external API the agents use (DexScreener, GeckoTerminal, RugCheck, GoPlus, CoinGecko, RDAP, t.me, Gemini) and fixes field-name drift in app/crypto/*. Use when an agent status shows errors (/agents) or monthly.
tools: Read, Edit, Bash, WebFetch
model: haiku
---
1. For each client in app/crypto/, call one real endpoint and check the fields the code reads still exist.
2. If a field moved, patch the parser minimally and add a test in tests/.
3. Respect rate limits (see app/crypto/http.py). Report a table: API | OK/changed | fix applied.
