"""Every feature a chat may use must be reachable from its own menu - not only by typing."""
import pytest

pytest.importorskip("telegram")
pytest.importorskip("sqlmodel")

import app.bot  # noqa: E402,F401  (registers every menu entry)
from app.ux import menu  # noqa: E402


def test_level_alerts_are_in_the_main_menu_and_command_list():
    assert "levels" in [e["key"] for e in menu.entries()]
    assert "alerts" in dict(menu.commands())


def test_menu_buttons_fit_telegram_limits():
    for e in menu.entries():
        assert len(f"m:{e['key']}".encode()) <= 64


def test_a_metals_only_chat_is_offered_only_what_answers_it():
    names = [name for name, _ in menu.METALS_COMMANDS]
    assert names == ["start", "alerts", "levels", "chatid"]
    assert all(len(desc) <= 256 for _, desc in menu.METALS_COMMANDS)
