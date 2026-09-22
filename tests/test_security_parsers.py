from app.crypto.security import goplus_summary, rugcheck_summary


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
