import yaml
from app.crypto.scout_rules import Snapshot, evaluate, prefilter
from app.crypto.security import Security

R = yaml.safe_load(open("topics/token_scout/rules.yaml"))


def good(**kw):
    base = dict(chain="solana", address="X", symbol="CAT", name="Cat", mcap=150_000, fdv=150_000,
                liquidity=40_000, vol24=8_000, age_hours=400, range_pos=0.15, drawdown=0.85,
                websites=["https://cat.xyz"], website_alive=True, twitter="https://x.com/cat",
                telegram="https://t.me/cat", tg_members=3000,
                sec=Security("rugcheck", holders=2500, top_holder_pct=4, lp_locked_pct=100))
    base.update(kw)
    return Snapshot(**base)


def test_buy_zone_when_everything_passes():
    assert evaluate(good(), R, "ACCUMULATE").stage == "BUY_ZONE"


def test_regime_gate_downgrades():
    v = evaluate(good(), R, "UP_LEG")
    assert v.stage == "WATCH" and any("regime" in w for w in v.warns)


def test_whale_rejects():
    assert evaluate(good(sec=Security("goplus", holders=2500, top_holder_pct=25, lp_locked_pct=100)), R).stage == "REJECT"


def test_honeypot_rejects():
    assert evaluate(good(sec=Security("goplus", danger=["Honeypot (can't sell)"], holders=5000,
                                      top_holder_pct=2, lp_locked_pct=100)), R).stage == "REJECT"


def test_no_security_report_is_fail_safe():
    assert evaluate(good(sec=Security("rugcheck", available=False)), R).stage == "REJECT"


def test_new_pair_rejected_and_top_of_range_is_watch():
    assert evaluate(good(age_hours=20), R).stage == "REJECT"
    assert evaluate(good(range_pos=0.9), R, "ACCUMULATE").stage == "WATCH"


def test_dead_website_rejects():
    assert evaluate(good(website_alive=False), R).stage == "REJECT"


def test_prefilter():
    assert prefilter({"mcap": 150_000, "liquidity": 40_000, "vol24": 5000, "age_hours": 300}, R)[0]
    assert not prefilter({"mcap": 150_000, "liquidity": 200_000, "vol24": 5000, "age_hours": 300}, R)[0]
