"""Your personal context: config/me.yaml, plus anything you changed from the ⚙️ buttons.

The YAML file is the baseline you edit by hand; the overlay is what the bot writes when you
tap "My setup". The bot never rewrites the YAML, so your comments and formatting survive."""
from pathlib import Path

import yaml

from . import prefs

ME_PATH = Path("config/me.yaml")
LIST_FIELDS = ("exchanges", "wallets", "chains", "holding_tickers", "interests", "dev_stack")


def base_me() -> dict:
    if not ME_PATH.exists():
        return {}
    return yaml.safe_load(ME_PATH.read_text(encoding="utf-8")) or {}


def merge(base: dict, overlay: dict) -> dict:
    """Overlay wins per field. Lists are replaced, not appended, so removing really removes."""
    merged = dict(base or {})
    for key, value in (overlay or {}).items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = value
    return merged


def load_me() -> dict:
    return merge(base_me(), prefs.me_overlay())


def me_text() -> str:
    """What the scorer sees. Empty string when nothing is set, as before."""
    me = load_me()
    return yaml.safe_dump(me, sort_keys=False, allow_unicode=True).strip() if me else ""


def set_field(field: str, values) -> dict:
    overlay = prefs.me_overlay()
    overlay[field] = values
    prefs.set_me_overlay(overlay)
    return load_me()


def add_to_field(field: str, value: str) -> dict:
    current = list(load_me().get(field) or [])
    value = value.strip()
    if value and value not in current:
        current.append(value)
    return set_field(field, current)


def remove_from_field(field: str, value: str) -> dict:
    current = [x for x in (load_me().get(field) or []) if x != value]
    return set_field(field, current)
