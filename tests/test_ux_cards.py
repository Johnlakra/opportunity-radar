import yaml
from app.crypto.resolve import Candidate
from app.crypto.scout_rules import Snapshot, evaluate
from app.crypto.security import Security
from app.ux import cards, glossary

R = yaml.safe_load(open("topics/token_scout/rules.yaml"))


def snap(**kw):
    base = dict(chain="solana", address="X", symbol="CAT", name="Cat", mcap=150_000, fdv=150_000,
                liquidity=40_000, vol24=8_000, chg24=-12, age_hours=400, price=0.00000123, range_pos=0.15, drawdown=0.85,
                websites=["https://cat.xyz"], website_alive=True, twitter="https://x.com/cat",
                telegram="https://t.me/cat", tg_members=3000,
                sec=Security("rugcheck", holders=2500, top_holder_pct=4, lp_locked_pct=100))
    base.update(kw)
    return Snapshot(**base)


def card(**kw):
    s = snap(**kw)
    return cards.scorecard(s, evaluate(s, R, "ACCUMULATE"), R)


def test_price_keeps_enough_decimals_for_tiny_coins():
    assert cards.price(0.00000123) == "$0.00000123"
    assert cards.price(0.5) == "$0.50" and cards.price(2.3456) == "$2.35"
    assert cards.price(121_345.6) == "$121,346"


def test_price_of_something_unknown_is_a_question_mark():
    assert cards.price(None) == "?" and cards.price(0) == "?" and cards.price("junk") == "?"


def test_money_is_written_the_way_people_say_it():
    assert cards.money(48_000) == "$48k" and cards.money(1_900_000_000) == "$1,900.0M"
    assert cards.money(None) == "?"


def test_age_reads_as_days_not_hours():
    assert cards.age(400) == "17d old" and cards.age(10) == "10h old"


def test_mood_card_is_a_traffic_light_with_advice():
    text = cards.mood_card({"state": "ACCUMULATE", "price": 60000, "drawdown": -0.3,
                            "days_since_top": 40, "down_legs": 2, "dominance": 57.7,
                            "dom_delta_14d": 0.4}, {"value": 30, "band": "Fear"})
    assert "🟢" in text and "Fear &amp; Greed 30" in text and "57.7%" in text
    assert "Not financial advice" in text


def test_mood_card_survives_a_missing_fear_and_greed_reading():
    assert "🔴" in cards.mood_card({"state": "SECOND_LEG_UP", "price": 1, "drawdown": 0,
                                    "days_since_top": 0, "down_legs": 0}, None)


def test_unknown_state_falls_back_to_caution():
    assert "🟡" in cards.mood_card({"state": "???", "price": 1, "drawdown": 0}, None)


def test_scorecard_leads_with_the_price_then_the_market_cap():
    text = card()
    assert "One coin costs $0.00000123 right now" in text
    assert text.index("One coin costs") < text.index("Market cap")
    assert "Market cap $150k — everything added up" in text
    assert "Down 12% today" in text and "buys weakness" in text
    assert "2,500 wallets hold it" in text
    assert "100% locked" in text
    assert "Not financial advice" in text


def test_scorecard_warns_when_the_coin_is_pumping():
    assert "does not chase pumps" in card(chg24=40)


def test_scorecard_calls_a_missing_safety_report_unsafe():
    text = card(sec=Security("rugcheck", available=False))
    assert "No safety report" in text and "⛔" in text


def test_scorecard_names_the_whale():
    assert "could dump on you" in card(sec=Security("rugcheck", holders=2000, top_holder_pct=25,
                                                    lp_locked_pct=100))


def test_scorecard_says_when_nobody_is_home():
    assert "nobody is home" in card(websites=[], twitter=None, telegram=None, tg_members=None)


def test_candidate_label_shows_price_size_age_and_socials():
    label = cards.candidate_label(Candidate(chain="solana", address="X", symbol="BONK", price=0.00000123,
                                            mcap=48_000, age_hours=504, has_socials=True))
    assert label == "BONK · $0.00000123 · MC $48k · 21d old ✓"


def test_candidate_label_drops_the_price_when_there_is_none():
    label = cards.candidate_label(Candidate(chain="solana", address="X", symbol="BONK",
                                            mcap=48_000, age_hours=504, has_socials=False))
    assert label == "BONK · MC $48k · 21d old ⚠️"


def test_empty_search_tells_the_user_what_to_try():
    assert "paste the coin's" in cards.candidates_card("nope", [])


def test_portfolio_shows_price_multiples_and_dollars():
    text = cards.portfolio_card([{"id": 1, "symbol": "CAT", "usd": 100, "entry": 50_000,
                                  "value": 150_000, "price": 0.00015, "unit": "market cap"}])
    assert "3.00x" in text and "+$200" in text and "$0.00015" in text


def test_portfolio_handles_a_coin_with_no_live_price():
    text = cards.portfolio_card([{"id": 2, "symbol": "DOG", "usd": 40, "entry": 0, "value": None,
                                  "unit": "market cap"}])
    assert "live value unavailable" in text


def test_empty_portfolio_points_at_the_add_button():
    assert "Nothing journalled yet" in cards.portfolio_card([])


def test_every_glossary_entry_renders():
    assert all(glossary.lookup(key) for key in glossary.TERMS)
    assert glossary.lookup("nonsense") is None


def ton_candidate(**kw):
    base = dict(chain="ton", address="EQA2", symbol="NOT", name="Notcoin", price=0.0019,
                mcap=190_000_000, liquidity=2_000_000, vol24=900_000, chg24=-4,
                age_hours=9000, has_socials=True)
    base.update(kw)
    return Candidate(**base)


def test_details_card_shows_the_numbers_we_do_have():
    text = cards.details_card(ton_candidate(), "ton")
    assert "$0.0019" in text and "Market cap $190.0M" in text and "Down 4% today" in text


def test_details_card_is_honest_about_what_it_cannot_check():
    text = cards.details_card(ton_candidate(), "ton")
    assert "cannot run the safety checklist on ton yet" in text
    assert "Treat it as unchecked" in text
    assert "Not financial advice" in text


def test_details_card_flags_a_coin_with_no_socials():
    assert "nobody is home" in cards.details_card(ton_candidate(has_socials=False), "ton")
