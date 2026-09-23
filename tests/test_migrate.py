from sqlalchemy import create_engine, inspect

from app.migrate import MIGRATIONS, ensure_columns, run


def old_database():
    """A database created before any of the new columns existed."""
    db = create_engine("sqlite://")
    with db.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE item (id INTEGER PRIMARY KEY, title VARCHAR)")
        conn.exec_driver_sql("CREATE TABLE feedback (id INTEGER PRIMARY KEY, vote VARCHAR)")
        conn.exec_driver_sql("CREATE TABLE holding (id INTEGER PRIMARY KEY, usd FLOAT)")
    return db


def test_missing_columns_are_added_once():
    db = old_database()
    added = run(db)
    for table, columns in MIGRATIONS.items():
        assert set(added[table]) == set(columns), table
        assert {c["name"] for c in inspect(db).get_columns(table)} >= set(columns), table


def test_running_it_again_changes_nothing():
    db = old_database()
    run(db)
    assert run(db) == {table: [] for table in MIGRATIONS}


def test_existing_rows_survive_the_back_fill():
    db = old_database()
    with db.begin() as conn:
        conn.exec_driver_sql("INSERT INTO item (id, title) VALUES (1, 'hello')")
    run(db)
    with db.begin() as conn:
        assert conn.exec_driver_sql("SELECT title, saved FROM item").fetchone()[0] == "hello"


def test_a_table_that_does_not_exist_yet_is_left_to_create_all():
    db = create_engine("sqlite://")
    assert ensure_columns(db, "item", MIGRATIONS["item"]) == []


def test_unsafe_identifiers_are_refused():
    db = old_database()
    for bad in ("item; something", "Item", "1item"):
        try:
            ensure_columns(db, bad, {})
        except ValueError:
            continue
        raise AssertionError(f"{bad!r} should have been refused")
