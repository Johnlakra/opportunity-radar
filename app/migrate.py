"""Tiny schema back-fill.

SQLModel's create_all() builds missing TABLES but never adds a column to a table that already
exists, so a database created before a feature shipped would break on the new field. Every column
added after the first release is listed here and added on boot. Idempotent by design.
Kept free of SQLModel so it can be tested on its own."""
import re

from sqlalchemy import inspect, text

_SAFE_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")

MIGRATIONS: dict[str, dict[str, str]] = {
    "item": {
        "saved": "BOOLEAN DEFAULT 0",
        "saved_at": "DATETIME",
        "remind_at": "DATETIME",
        "reminded": "BOOLEAN DEFAULT 0",
        "deadline_at": "DATETIME",
        "india_ok": "VARCHAR",
        "cost": "VARCHAR",
    },
    "feedback": {
        "source": "VARCHAR",
    },
    "holding": {
        "entry_price": "REAL",
    },
    "levelsub": {
        "chat_id": "VARCHAR",
    },
}

# Indexes that were right once and are wrong now. levelsub.asset_key was unique while there was
# one subscriber; with a subscription per person the same asset appears once per chat.
STALE_INDEXES = {"levelsub": ["ix_levelsub_asset_key"]}


def ensure_columns(db, table: str, columns: dict[str, str]) -> list[str]:
    """Add the missing columns of one table. Returns the names it actually added."""
    if not _SAFE_NAME.match(table):
        raise ValueError(f"unsafe table name: {table}")
    inspector = inspect(db)
    if table not in inspector.get_table_names():
        return []                                   # create_all() will build it complete
    have = {c["name"] for c in inspector.get_columns(table)}
    added = []
    with db.begin() as conn:
        for name, ddl in columns.items():
            if name in have:
                continue
            if not _SAFE_NAME.match(name):
                raise ValueError(f"unsafe column name: {name}")
            conn.exec_driver_sql(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {ddl}')
            added.append(name)
    return added


def drop_stale_indexes(db) -> list[str]:
    """SQLite cannot alter a constraint, but it can drop an index and let create_all rebuild it."""
    inspector = inspect(db)
    tables = set(inspector.get_table_names())
    dropped = []
    with db.begin() as conn:
        for table, names in STALE_INDEXES.items():
            if table not in tables:
                continue
            have = {i["name"]: i for i in inspector.get_indexes(table)}
            for name in names:
                if have.get(name, {}).get("unique"):
                    conn.exec_driver_sql(f'DROP INDEX IF EXISTS "{name}"')
                    dropped.append(name)
    return dropped


def backfill(db, table: str, column: str, value: str) -> int:
    """Give rows written before a column existed a sensible value. Never touches filled rows."""
    if not _SAFE_NAME.match(table) or not _SAFE_NAME.match(column):
        raise ValueError("unsafe identifier")
    inspector = inspect(db)
    if table not in inspector.get_table_names():
        return 0
    if column not in {c["name"] for c in inspector.get_columns(table)}:
        return 0
    with db.begin() as conn:
        result = conn.execute(   # text() binds :value on SQLite and Postgres alike; ? is SQLite-only
            text(f'UPDATE "{table}" SET "{column}" = :value WHERE "{column}" IS NULL OR "{column}" = \'\''),
            {"value": value})
        return result.rowcount or 0


def run(db, owner_chat_id: str = "") -> dict[str, list[str]]:
    added = {table: ensure_columns(db, table, cols) for table, cols in MIGRATIONS.items()}
    drop_stale_indexes(db)
    if owner_chat_id:
        backfill(db, "levelsub", "chat_id", owner_chat_id)   # your existing alerts stay yours
    return added
