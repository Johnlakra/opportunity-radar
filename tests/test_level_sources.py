"""Parsers for the level feeds, run against real responses saved in tests/fixtures/."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import levels
from app.crypto import binance, metals

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


NOW = datetime(2026, 9, 23, 10, 0, tzinfo=timezone.utc)


# ---------------- live spot ----------------
def test_spot_reads_gold_silver_and_the_rupee_rate():
    payload = fixture("xaus_spot.json")
    fresh_now = datetime.fromisoformat(payload["updated_at"].replace("Z", "+00:00")) + timedelta(minutes=2)
    quote = metals.parse_spot(payload, now=fresh_now)
    assert quote["gold_usd_oz"] == pytest.approx(4314.799805)
    assert quote["silver_usd_oz"] == pytest.approx(65.315002)
    assert quote["usd_inr"] == pytest.approx(95.647843)


def test_a_stale_quote_is_refused():
    payload = fixture("xaus_spot.json")
    old = datetime.fromisoformat(payload["updated_at"].replace("Z", "+00:00")) + timedelta(hours=3)
    assert metals.parse_spot(payload, now=old) is None


def test_a_feed_that_does_not_say_fresh_is_refused():
    payload = {**fixture("xaus_spot.json"), "data_state": {"status": "degraded"}}
    assert metals.parse_spot(payload, now=NOW) is None


@pytest.mark.parametrize("broken", [{}, None, {"data_state": {"status": "fresh"}},
                                    {"data_state": {"status": "fresh"}, "updated_at": "nonsense"}])
def test_a_broken_spot_response_is_refused_rather_than_guessed(broken):
    assert metals.parse_spot(broken, now=NOW) is None


def test_a_missing_exchange_rate_is_refused():
    payload = {**fixture("xaus_spot.json"), "fx_rate": 0}
    fresh = datetime.fromisoformat(payload["updated_at"].replace("Z", "+00:00"))
    assert metals.parse_spot(payload, now=fresh) is None


# ---------------- daily history ----------------
def test_gold_history_parses_into_ordered_bars():
    bars = metals.parse_history(fixture("xaus_history.json"))
    assert len(bars) == 45
    assert bars == sorted(bars, key=lambda b: b["day"])
    assert all(b["h"] >= b["l"] > 0 for b in bars)
    assert bars[-1]["day"] == "2026-09-23"


def test_history_points_missing_a_field_are_skipped_not_faked():
    payload = {"points": [{"d": "2026-09-01", "c": 10, "h": 11, "l": 9},
                          {"d": "2026-09-02", "c": None, "h": 11, "l": 9},
                          {"d": "2026-09-03"}]}
    assert [b["day"] for b in metals.parse_history(payload)] == ["2026-09-01"]


def test_the_rupee_history_parses():
    rates = metals.parse_fx(fixture("frankfurter.json"))
    assert rates["2026-09-01"] == pytest.approx(94.95)
    assert all(rate > 0 for rate in rates.values())


def test_silver_history_parses_from_yahoo():
    bars = metals.parse_yahoo(fixture("yahoo_silver.json"))
    assert bars and all(b["h"] >= b["l"] > 0 for b in bars)
    assert bars == sorted(bars, key=lambda b: b["day"])


def test_a_yahoo_response_of_the_wrong_shape_gives_nothing():
    for broken in ({}, None, {"chart": {}}, {"chart": {"result": []}}):
        assert metals.parse_yahoo(broken) == []


# ---------------- converting a history to rupees ----------------
def test_usd_bars_become_rupee_bars_at_that_days_rate():
    usd = [{"day": "2026-09-01", "o": 4000.0, "h": 4100.0, "l": 3900.0, "c": 4050.0}]
    [bar] = metals.to_inr_bars(usd, {"2026-09-01": 95.0})
    assert bar["h"] == pytest.approx(levels.inr_per_gram(4100.0, 95.0))
    assert bar["currency"] == "INR"


def test_a_weekend_carries_fridays_rate_forward():
    usd = [{"day": "2026-09-04", "o": 1, "h": 1, "l": 1, "c": 1},      # Friday
           {"day": "2026-09-05", "o": 1, "h": 1, "l": 1, "c": 1},      # Saturday, no rate
           {"day": "2026-09-06", "o": 1, "h": 1, "l": 1, "c": 1}]
    out = metals.to_inr_bars(usd, {"2026-09-04": 95.0})
    assert len(out) == 3 and out[1]["h"] == out[0]["h"] == out[2]["h"]


def test_bars_from_before_the_first_known_rate_are_dropped_not_guessed():
    usd = [{"day": "2026-08-01", "o": 1, "h": 1, "l": 1, "c": 1},
           {"day": "2026-09-01", "o": 1, "h": 1, "l": 1, "c": 1}]
    assert [b["day"] for b in metals.to_inr_bars(usd, {"2026-09-01": 95.0})] == ["2026-09-01"]


# ---------------- listed coins ----------------
def test_binance_klines_parse_into_daily_bars():
    bars = binance.parse_klines(fixture("binance_klines.json"))
    assert len(bars) == 3
    assert bars[0]["h"] == pytest.approx(87395.67)
    assert bars[0]["l"] == pytest.approx(80850.22)
    assert bars == sorted(bars, key=lambda b: b["day"])


def test_a_malformed_kline_row_is_skipped():
    assert binance.parse_klines([["x"], [], None, [1789948800000, "1", "2", "3", "4"]])[0]["h"] == 2.0


def test_the_ticker_becomes_a_usdt_symbol():
    assert binance.symbol_for("btc") == "BTCUSDT" and binance.symbol_for("SOL") == "SOLUSDT"
    assert binance.symbol_for("") == "" and binance.symbol_for(None) == ""


def test_dex_candles_parse_into_the_same_bar_shape():
    rows = [[1758499200, "0.001", "0.002", "0.0005", "0.0015", "1000"]]
    [bar] = levels.bars_from_ohlcv(rows)
    assert bar["h"] == 0.002 and bar["l"] == 0.0005 and bar["day"] == "2025-09-22"


def test_rubbish_candles_are_skipped():
    assert levels.bars_from_ohlcv([[], None, ["x", "y"], [1758499200, 0, 0, 0, 0, 0]]) == []
