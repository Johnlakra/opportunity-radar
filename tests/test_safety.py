from app.safety import check


def test_official_link_ok():
    assert check({"official_site": "https://jup.ag", "action_link": "https://claim.jup.ag/x", "legitimacy": "confirmed"}) == []


def test_lookalike_flagged():
    flags = check({"official_site": "https://jup.ag", "action_link": "https://jup-claim.io"})
    assert any("phishing" in f for f in flags)


def test_seed_phrase_flagged():
    assert check({"official_site": "https://a.io", "what_to_do": "enter your seed phrase to verify"})


def test_no_official_site():
    assert check({"action_link": "https://random.xyz"})
