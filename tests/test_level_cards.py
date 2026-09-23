"""How a level break reads. Pure formatting, so it is cheap to pin down exactly."""
from types import SimpleNamespace

import pytest

from app.ux import level_cards as lc

GOLD, SILVER, COIN = "metal:XAU", "metal:XAG", "cg:bonk"
FOUND = {"W": (13686.2, 13183.9), "M": (14588.7, 12487.8), "Y": (13241.6, 7224.0)}


def sub(**kw):
    base = dict(id=1, asset_key=GOLD, label="Gold", periods="WMQY", up=True, down=True,
                active=True, source="default")
    base.update(kw)
    return SimpleNamespace(**base)


# ---------------- units people actually use ----------------
def test_gold_is_quoted_per_ten_grams_and_silver_per_kilo():
    assert lc.fmt_value(GOLD, 13279.1) == "₹132,791 /10g"
    assert lc.fmt_value(SILVER, 200.85) == "₹200,850 /kg"


def test_a_coin_is_quoted_as_it_trades():
    assert lc.fmt_value(COIN, 0.0000123) == "$0.0000123"
    assert lc.fmt_value(COIN, 61234.0) == "$61,234"


def test_an_unknown_price_says_so():
    assert lc.fmt_value(GOLD, None) == "?" and lc.fmt_compact(GOLD, None) == "?"


def test_the_premium_applies_to_rupees_only():
    assert lc.fmt_value(GOLD, 13279.1, 9) == "₹144,742 /10g"
    assert lc.fmt_value(COIN, 100.0, 9) == "$100.00"       # a coin price is not an Indian import


# ---------------- the summary line ----------------
def test_the_levels_line_says_the_unit_once_not_eight_times():
    line = lc.levels_line(GOLD, FOUND)
    assert line == "Levels · W 136,862/131,839 · M 145,887/124,878 · Y 132,416/72,240"
    assert "/10g" not in line


def test_periods_we_do_not_know_are_simply_absent():
    assert "Q" not in lc.levels_line(GOLD, FOUND)
    assert lc.levels_line(GOLD, {}) == ""


# ---------------- the alert ----------------
def test_a_break_above_reads_like_a_sentence():
    text = lc.break_card("Gold", GOLD, "M", "up", 13279.1, 12487.8, FOUND, "default")
    assert "🥇 GOLD broke ABOVE last month's high" in text
    assert "₹132,791 /10g · level ₹124,878 /10g" in text
    assert "+6.34% beyond" in text
    assert "intl spot in ₹" in text                        # never mistakable for an MCX quote
    assert text.endswith(lc.NOT_A_SIGNAL)


def test_a_break_below_reads_the_other_way():
    text = lc.break_card("BONK", COIN, "W", "down", 0.0000123, 0.0000131, {}, "journal")
    assert "broke BELOW last week's low" in text and text.startswith("<b>📒")


def test_a_coin_you_hold_says_so():
    text = lc.break_card("BONK", COIN, "W", "down", 1.0, 2.0, {}, "journal",
                         extra=[lc.holding_line("BONK", 50_000, 150_000, "market cap")])
    assert "📒 You hold: entry market cap $50k · now 3.00x" in text


def test_levels_built_from_closes_admit_it():
    text = lc.break_card("XYZ", COIN, "M", "up", 2.0, 1.0, {}, approximate=True)
    assert "approximate" in text


def test_the_asset_name_is_escaped_not_rendered():
    head = lc.break_card("<b>x</b>", COIN, "M", "up", 2.0, 1.0, {}).split("\n")[0]
    assert "&lt;B&gt;X&lt;/B&gt;" in head and "<b>x</b>" not in head


# ---------------- the /levels table ----------------
def test_the_table_shows_every_level_and_how_far_away_it_is():
    text = lc.levels_table("Gold", GOLD, 13279.1, FOUND, ["Q"])
    assert "Now ₹132,791 /10g" in text
    assert "high ₹145,887 /10g (-9.0%)" in text and "low ₹124,878 /10g (+6.3%)" in text
    assert "<b>Q</b> · building history" in text


def test_a_brand_new_asset_says_to_wait():
    text = lc.levels_table("New", COIN, 1.0, {}, ["W", "M", "Q", "Y"])
    assert "No completed period has enough history yet" in text


# ---------------- the menu ----------------
def test_the_menu_row_shows_what_is_switched_on():
    assert lc.menu_row(sub(), "WMQY") == "🥇 <b>Gold</b> · W M Q Y ↑↓"
    assert lc.menu_row(sub(up=False), "MQY") == "🥇 <b>Gold</b> · M Q Y ↓"
    assert lc.menu_row(sub(active=False), "WMQY") == "🥇 <b>Gold</b> · off"


def test_a_journal_coin_is_marked_as_one():
    assert lc.icon_for("cg:solana", "journal") == "📒"
    assert lc.icon_for("cg:solana", "manual") == "🪙"
    assert lc.icon_for(GOLD, "journal") == "🥇"


def test_the_menu_says_when_everything_is_paused():
    assert "paused" in lc.menu_text(["a"], paused=True)
    assert "Nothing watched yet" in lc.menu_text([], paused=False)


@pytest.mark.parametrize("period,word", [("W", "week"), ("M", "month"), ("Q", "quarter"), ("Y", "year")])
def test_every_period_has_a_plain_english_name(period, word):
    assert word in lc.break_card("X", COIN, period, "up", 2.0, 1.0, {})


# ---------------- callback data must fit Telegram's 64 bytes ----------------
def test_every_level_button_fits_in_a_callback():
    big = 2 ** 31
    shapes = ["lv:m", "lv:p", "lv:j", f"lv:a:{big}", f"lv:s:{big}", f"lv:r:{big}",
              *[f"lv:t:{big}:{code}" for code in ("W", "M", "Q", "Y", "U", "D", "A")],
              "lv:n:" + "a" * 40]
    for data in shapes:
        assert len(data.encode()) <= 64, data


def test_a_coin_id_is_the_only_thing_that_could_grow():
    """An address never goes in a button; only a CoinGecko id, which is short."""
    assert len(("lv:n:" + "wrapped-staked-ether-liquid-restaking").encode()) <= 64
