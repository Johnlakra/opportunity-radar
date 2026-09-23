"""Tiny schema back-fill.

SQLModel's create_all() builds missing TABLES but never adds a column to a table that already
exists, so a database created before a feature shipped would break on the new field. Every column
added after the first release is listed here and added on boot. Idempotent by design.
Kept free of SQLModel so it can be tested on its own."""
import re

from sqlalchemy import inspect

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
}


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


def run(db) -> dict[str, list[str]]:
    return {table: ensure_columns(db, table, cols) for table, cols in MIGRATIONS.items()}
