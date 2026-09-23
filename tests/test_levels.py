"""The level logic, with no network and no database anywhere near it."""
from datetime import date

import pytest

from app import levels

# A year of bars is plenty to cover every previous period we ask about.
def bars(start: date, end: date, high=100.0, low=90.0):
    out, day = [], start
    while day <= end:
        out.append({"day": day.isoformat(), "o": 95.0, "h": high, "l": low, "c": 95.0})
        day = date.fromordinal(day.toordinal() + 1)
    return out


# ---------------- naming a period ----------------
@pytest.mark.parametrize("day,period,expected", [
    (date(2026, 9, 23), "W", "2026-W39"),
    (date(2026, 9, 23), "M", "2026-09"),
    (date(2026, 9, 23), "Q", "2026-Q3"),
    (date(2026, 9, 23), "Y", "2026"),
    (date(2026, 1, 1), "Q", "2026-Q1"),
    (date(2026, 12, 31), "Q", "2026-Q4"),
])
def test_periods_are_named_the_obvious_way(day, period, expected):
    assert levels.period_id(day, period) == expected


def test_the_iso_week_can_belong_to_the_next_year():
    # 31 Dec 2025 falls in ISO week 1 of 2026
    assert levels.period_id(date(2025, 12, 31), "W") == "2026-W01"


def test_an_unknown_period_is_refused():
    with pytest.raises(ValueError):
        levels.period_id(date(2026, 1, 1), "X")


# ---------------- the previous period ----------------
@pytest.mark.parametrize("day,period,expected", [
    (date(2026, 9, 23), "W", (date(2026, 9, 14), date(2026, 9, 20))),
    (date(2026, 9, 23), "M", (date(2026, 8, 1), date(2026, 8, 31))),
    (date(2026, 9, 23), "Q", (date(2026, 4, 1), date(2026, 6, 30))),
    (date(2026, 9, 23), "Y", (date(2025, 1, 1), date(2025, 12, 31))),
    (date(2026, 1, 15), "M", (date(2025, 12, 1), date(2025, 12, 31))),
    (date(2026, 1, 15), "Q", (date(2025, 10, 1), date(2025, 12, 31))),
])
def test_the_previous_period_spans_the_right_days(day, period, expected):
    assert levels.prev_period_range(day, period) == expected


def test_the_previous_periods_high_and_low_come_from_its_bars():
    history = bars(date(2026, 7, 1), date(2026, 9, 23))
    history[40] = {**history[40], "h": 130.0}          # a spike inside August
    history[41] = {**history[41], "l": 70.0}
    assert levels.prev_period_hl(history, "M", date(2026, 9, 23)) == (130.0, 70.0)


def test_bars_outside_the_period_are_ignored():
    history = bars(date(2026, 7, 1), date(2026, 9, 23))
    history[-1] = {**history[-1], "h": 999.0}          # today, not last month
    assert levels.prev_period_hl(history, "M", date(2026, 9, 23))[0] == 100.0


def test_history_that_does_not_cover_the_whole_period_answers_nothing():
    """Never guess a level from half a month of data."""
    partial = bars(date(2026, 8, 10), date(2026, 9, 23))     # August starts on the 1st
    assert levels.prev_period_hl(partial, "M", date(2026, 9, 23)) is None


def test_history_that_stops_before_the_period_ends_answers_nothing():
    partial = bars(date(2026, 7, 1), date(2026, 8, 20))      # August is not finished in this data
    assert levels.prev_period_hl(partial, "M", date(2026, 9, 23)) is None


def test_no_bars_at_all_answers_nothing():
    assert levels.prev_period_hl([], "M", date(2026, 9, 23)) is None


def test_a_gap_over_a_weekend_is_still_full_coverage():
    """Markets close; a missing Saturday does not mean the month is unknown."""
    history = [b for b in bars(date(2026, 7, 1), date(2026, 9, 23))
               if date.fromisoformat(b["day"]).weekday() < 5]
    assert levels.prev_period_hl(history, "M", date(2026, 9, 23)) == (100.0, 90.0)


# ---------------- crossing ----------------
UP, DOWN = "up", "down"


def decide(stored, price, level=100.0, direction=UP, buffer_pct=0.5, pid="2026-09"):
    return levels.decide(stored, pid, price, level, direction, buffer_pct)


def test_the_first_time_we_look_we_only_remember_where_we_are():
    alert, state = decide(None, price=150.0)
    assert alert is False and state == "2026-09:above"


def test_breaking_above_the_high_alerts_once():
    alert, state = decide("2026-09:below", price=101.0)
    assert alert is True and state == "2026-09:above"


def test_staying_above_does_not_alert_again():
    assert decide("2026-09:above", price=120.0)[0] is False


def test_a_move_inside_the_buffer_is_not_a_break():
    alert, state = decide("2026-09:below", price=100.4)      # 0.4% < 0.5% buffer
    assert alert is False and state == "2026-09:below"


def test_the_buffer_does_not_strand_a_price_that_later_breaks_through():
    """Sitting just above the level must not count as 'above' and swallow the real break."""
    _, state = decide("2026-09:below", price=100.4)
    assert decide(state, price=101.0)[0] is True


def test_breaking_below_the_low_alerts_once():
    alert, state = decide("2026-09:above", price=98.0, level=100.0, direction=DOWN)
    assert alert is True and state == "2026-09:below"
    assert decide(state, price=97.0, direction=DOWN)[0] is False


def test_a_new_period_never_alerts_on_its_own():
    """The level itself moved, so a 'break' against the old one means nothing."""
    alert, state = decide("2026-08:below", price=150.0)
    assert alert is False and state == "2026-09:above"


def test_a_corrupt_stored_value_is_treated_as_a_fresh_start():
    for junk in ("", "nonsense", "2026-09", ":", "a:b:c"):
        assert levels.decide(junk, "2026-09", 150.0, 100.0, UP, 0.5)[0] is False


def test_a_level_of_zero_or_nothing_never_alerts():
    assert levels.decide("2026-09:below", "2026-09", 150.0, 0.0, UP, 0.5) == (False, "2026-09:below")


# ---------------- the money conversions ----------------
def test_the_indian_way_of_quoting_gold_and_silver():
    # $4314.80/oz at 95.65 INR/USD
    per_gram = levels.inr_per_gram(4314.799805, 95.647843)
    assert round(per_gram, 2) == 13268.65                     # matches the API's own number
    assert round(levels.gold_per_10g(per_gram)) == 132687     # gold is quoted per 10 grams
    silver_gram = levels.inr_per_gram(65.315002, 95.647843)
    assert round(levels.silver_per_kg(silver_gram)) == 200853  # silver is quoted per kilo


def test_a_premium_moves_the_price_and_the_level_by_the_same_amount():
    assert levels.with_premium(100.0, 9) == pytest.approx(109.0)
    assert levels.with_premium(100.0, 0) == 100.0


def test_a_premium_can_never_change_whether_something_broke():
    for premium in (0, 5, 9, 25):
        price, level = levels.with_premium(101.0, premium), levels.with_premium(100.0, premium)
        assert levels.decide("2026-09:below", "2026-09", price, level, UP, 0.5)[0] is True
        near, level = levels.with_premium(100.4, premium), levels.with_premium(100.0, premium)
        assert levels.decide("2026-09:below", "2026-09", near, level, UP, 0.5)[0] is False


def test_how_far_away_a_level_is():
    assert levels.distance_pct(110.0, 100.0) == pytest.approx(10.0)
    assert levels.distance_pct(90.0, 100.0) == pytest.approx(-10.0)
    assert levels.distance_pct(110.0, 0) is None


# ---------------- which periods are switched on ----------------
def test_reading_the_enabled_periods():
    assert levels.enabled_periods("WMQY") == ["W", "M", "Q", "Y"]
    assert levels.enabled_periods("MQY") == ["M", "Q", "Y"]
    assert levels.enabled_periods("mq") == ["M", "Q"]
    assert levels.enabled_periods("") == []
    assert levels.enabled_periods("WXZ") == ["W"]


def test_toggling_a_period_keeps_the_canonical_order():
    assert levels.toggle_period("MQY", "W") == "WMQY"
    assert levels.toggle_period("WMQY", "M") == "WQY"
    assert levels.toggle_period("", "Y") == "Y"
