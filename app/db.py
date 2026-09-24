import os

from sqlmodel import SQLModel, Session, create_engine

from . import migrate as _migrate
from .config import settings

os.makedirs("data", exist_ok=True)
_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
# pre_ping: hosted Postgres (Neon) drops idle connections; test each one before use
engine = create_engine(settings.database_url, connect_args=_args, pool_pre_ping=True)


def init_db():
    from . import models  # noqa: F401  (register tables)
    owner = settings.chat_ids[0] if settings.chat_ids else ""
    _migrate.run(engine, owner)             # old database -> columns added since it was created
    SQLModel.metadata.create_all(engine)


def session() -> Session:
    return Session(engine)
