import asyncio

import yaml

from app.crypto.scout_rules import Snapshot, evaluate
from app.crypto.security import _result_for, check, goplus_summary, rugcheck_summary


def test_goplus_excludes_lp_and_locks():
    g = {"is_honeypot": "0", "is_open_source": "1", "buy_tax": "0", "sell_tax": "0.02", "holder_count": "3200",
         "holders": [{"address": "0xpool", "percent": "0.40", "is_contract": "1", "is_locked": "0"},
                     {"address": "0xwhale", "percent": "0.06", "is_contract": "0", "is_locked": "0"}],
         "lp_holders": [{"address": "0x000000000000000000000000000000000000dead", "percent": "0.95", "is_locked": "0"}]}
    s = goplus_summary(g, set())
    assert s.holders == 3200 and round(s.top_holder_pct) == 6 and round(s.lp_locked_pct) == 95 and not s.danger


def test_goplus_honeypot():
    assert "Honeypot (can't sell)" in goplus_summary({"is_honeypot": "1"}, set()).danger


def test_rugcheck_excludes_pool_accounts():
    rep = {"risks": [{"name": "Low liquidity", "level": "warn"}], "totalHolders": 1500,
           "markets": [{"pubkey": "POOL", "liquidityA": "VAULT", "lp": {"lpLockedPct": 100}}],
           "topHolders": [{"address": "VAULT", "owner": "POOL", "pct": 30}, {"address": "W1", "owner": "O1", "pct": 5}]}
    s = rugcheck_summary(rep, set())
    assert s.top_holder_pct == 5 and s.lp_locked_pct == 100 and s.warn == ["Low liquidity"]


def test_goplus_result_is_found_whatever_case_the_key_uses():
    tron = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"          # Tron keys come back exactly as sent
    assert _result_for({"result": {tron: {"is_honeypot": "0"}}}, tron) == {"is_honeypot": "0"}
    evm = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"   # EVM keys come back lowercased
    assert _result_for({"result": {evm.lower(): {"x": 1}}}, evm) == {"x": 1}


def test_missing_result_reads_as_nothing():
    assert _result_for({}, "0xabc") is None


def test_a_chain_with_no_safety_api_is_fail_safe():
    """TON, Sui, Aptos and friends: no report means the scout must never pass the token."""
    sec = asyncio.run(check(None, "ton", "EQA2kCVNwVsil2EM2mB0SkXytxCqQjS4mttjDpnXmwG9T6bO", set()))
    assert sec.available is False and sec.source == "none"
    rules = yaml.safe_load(open("topics/token_scout/rules.yaml"))
    snap = Snapshot(chain="ton", address="EQA2", mcap=150_000, liquidity=40_000, age_hours=400, sec=sec)
    assert evaluate(snap, rules).stage == "REJECT"
