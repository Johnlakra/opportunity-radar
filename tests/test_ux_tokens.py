import pytest
from app.ux import tokens


class FakeRedis:
    """Enough of redis for the callback-token map."""
    def __init__(self):
        self.store = {}

    def set(self, key, value, ex=None):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)


@pytest.fixture
def fake(monkeypatch):
    stub = FakeRedis()
    monkeypatch.setattr(tokens, "r", stub)
    return stub


SOL_KEY = "solana:DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"


def test_callback_data_stays_inside_telegrams_64_byte_limit(fake):
    for action in ("chk", "wl", "wx", "jw"):
        assert len(tokens.cb(action, SOL_KEY).encode()) <= 64


def test_the_address_never_appears_in_the_button(fake):
    assert "DezXAZ" not in tokens.cb("chk", SOL_KEY)


def test_round_trip_returns_the_original_key(fake):
    action, sid = tokens.split(tokens.cb("chk", SOL_KEY))
    assert action == "chk" and tokens.get(sid) == SOL_KEY


def test_the_same_coin_always_gets_the_same_id(fake):
    assert tokens.cb("chk", SOL_KEY) == tokens.cb("chk", SOL_KEY)


def test_an_expired_id_reads_back_as_nothing(fake):
    assert tokens.get("deadbeef00") is None and tokens.get("") is None


def test_split_copes_with_junk():
    assert tokens.split("") == ("", "") and tokens.split("m:mood") == ("m", "mood")
