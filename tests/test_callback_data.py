"""Telegram rejects callback_data over 64 bytes with BUTTON_DATA_INVALID, and the failure only
shows up when a real button is tapped - so every shape the bot builds is checked here."""
import pytest

from app import prefs, topics
from app.ux.tokens import cb

LIMIT = 64
BIG_ID = 2 ** 31            # far more items than this bot will ever hold


def sizes(*values):
    return [(v, len(v.encode())) for v in values]


def check(*values):
    for value, size in sizes(*values):
        assert size <= LIMIT, f"{value!r} is {size} bytes"


def test_every_news_item_button_fits():
    check(*[f"n:{action}:{BIG_ID}" for action in ("save", "done", "drop", "rem", "less", "tell")],
          *[f"n:rem:{BIG_ID}:{code}" for code in ("1h", "3h", "1d", "dl")],
          f"n:mcat:{BIG_ID}:y", f"n:resc:{BIG_ID}")


def test_every_topic_button_fits():
    for entry in topics.channels():
        check(f"n:top:{entry['channel']}:999", f"n:tog:{entry['channel']}",
              f"n:pk:{entry['channel']}", f"n:run:{entry['agent']}",
              f"n:lrn:{entry['channel']}:y", f"n:src:{entry['channel']}:9")
        for level in ("relaxed", "normal", "strict"):
            check(f"n:pk:{entry['channel']}:{level}")


def test_every_settings_button_fits():
    check("n:set", "n:tog", "n:pk", "n:cap", "n:hour", "n:quiet", "n:qday", "n:me", "n:filt",
          "n:metick", "n:tok", "n:tno", "n:tq:9",
          *[f"n:cap:{n}" for n in range(6)], *[f"n:hour:{h}" for h in range(24)],
          *[f"n:quiet:{code}" for code in prefs.QUIET_CHOICES])


def test_every_my_setup_button_fits():
    for field, _ in prefs.ME_FIELDS:
        check(f"n:me:{field}", f"n:mead:{field}", f"n:merm:{field}:99")


def test_a_long_solana_address_never_reaches_a_button(monkeypatch):
    stored = {}
    monkeypatch.setattr("app.ux.tokens.r",
                        type("R", (), {"set": lambda self, k, v, ex=None: stored.setdefault(k, v),
                                       "get": lambda self, k: stored.get(k)})())
    key = "solana:DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
    check(*[cb(action, key) for action in ("chk", "wl", "wx", "jw")])


def test_the_real_item_buttons_fit_too():
    pytest.importorskip("sqlmodel")
    pytest.importorskip("telegram")
    import json
    from types import SimpleNamespace
    from app.agents.news import item_buttons
    row = SimpleNamespace(id=BIG_ID, url="https://x.io", action_link=None, deadline_at=True,
                          researched=True)
    for line in json.loads(item_buttons(row)):
        for button in line:
            if button.get("d"):
                check(button["d"])
