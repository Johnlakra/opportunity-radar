from app.crypto.regime import classify, count_down_legs, count_up_legs


def test_down_legs_counts_two_crashes():
    prices = [100, 90, 88, 95, 96, 85, 80, 82]      # -12%, bounce, -17% from 96
    assert count_down_legs(prices, 0.08, 0.04) == 2


def test_up_legs():
    prices = [50, 60, 55, 50, 65, 70]                # +20%, pullback, +40%
    assert count_up_legs(prices, 0.15, 0.08) == 2


def test_accumulate_after_two_legs_and_wait():
    prices = [100] * 100 + [100 - i * 0.2 for i in range(20)] + [88] * 5 + [92] * 5 + [80 - i * 0.1 for i in range(50)]
    reg = classify(prices, month=1)
    assert reg["down_legs"] >= 2 and reg["state"] == "ACCUMULATE"


def test_summer_waits_longer():
    prices = [100] * 100 + [90, 80, 85, 88, 75, 70] + [70] * 30
    assert classify(prices, month=1)["state"] == "ACCUMULATE"
    assert classify(prices, month=7)["state"] == "CORRECTION_WAIT"   # 90-day summer wait


def test_up_leg():
    prices = [60] * 150 + [60 + i for i in range(40)]
    assert classify(prices, month=1)["state"] in ("UP_LEG", "SECOND_LEG_UP")
