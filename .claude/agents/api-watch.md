---
name: api-watch
description: Smoke-tests every external API the agents use (DexScreener, GeckoTerminal, RugCheck, GoPlus, CoinGecko, RDAP, t.me, Gemini, xaus.com, frankfurter, Binance data, Yahoo chart) and fixes field-name drift in app/crypto/*. Use when an agent status shows errors (/agents) or monthly.
tools: Read, Edit, Bash, WebFetch
model: haiku
---
1. For each client in app/crypto/, call one real endpoint and check the fields the code reads still exist.
   Level-alert feeds and the exact fields they must keep returning:
   | API | Endpoint | Fields the code reads |
   |---|---|---|
   | xaus.com | `/api/v1/spot?currency=INR&unit=gram&compact=1` | `spot_usd_oz`, `silver_usd_oz`, `fx_rate`, `data_state.status`, `updated_at` |
   | xaus.com | `/api/v1/history` | `points[].{d,c,h,l}` |
   | frankfurter | `https://api.frankfurter.dev/v1/<start>..<end>?from=USD&to=INR` | `rates[day].INR` (the old `.app` host 301s here) |
   | Binance data | `https://data-api.binance.vision/api/v3/klines` | rows `[open_time, o, h, l, c, ...]` |
   | Yahoo chart | `/v8/finance/chart/SI=F` (unofficial, silver bootstrap only) | `chart.result[0].{timestamp,indicators.quote[0]}` |
   Saved responses live in tests/fixtures/ - refresh those when a shape changes.
2. If a field moved, patch the parser minimally and add a test in tests/.
3. Respect rate limits (see app/crypto/http.py). Report a table: API | OK/changed | fix applied.
