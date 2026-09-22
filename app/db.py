import os
from sqlmodel import SQLModel, Session, create_engine
from .config import settings

os.makedirs("data", exist_ok=True)
_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=_args)


def init_db():
    from . import models  # noqa: F401  (register tables)
    SQLModel.metadata.create_all(engine)


def session() -> Session:
    return Session(engine)
