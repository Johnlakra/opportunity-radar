from pathlib import Path
import yaml

ME_PATH = Path("config/me.yaml")


def load_me() -> dict:
    return yaml.safe_load(ME_PATH.read_text(encoding="utf-8")) if ME_PATH.exists() else {}


def me_text() -> str:
    return ME_PATH.read_text(encoding="utf-8") if ME_PATH.exists() else ""
