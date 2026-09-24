from sqlalchemy import create_engine, inspect

from app.migrate import MIGRATIONS, backfill, drop_stale_indexes, ensure_columns, run


def run_drop(db):
    return drop_stale_indexes(db)


def old_database():
    """A database created before any of the new columns existed."""
    db = create_engine("sqlite://")
    with db.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE item (id INTEGER PRIMARY KEY, title VARCHAR)")
        conn.exec_driver_sql("CREATE TABLE feedback (id INTEGER PRIMARY KEY, vote VARCHAR)")
        conn.exec_driver_sql("CREATE TABLE holding (id INTEGER PRIMARY KEY, usd FLOAT)")
        conn.exec_driver_sql("CREATE TABLE levelsub (id INTEGER PRIMARY KEY, asset_key VARCHAR)")
        # how it was created when there was only ever one subscriber
        conn.exec_driver_sql("CREATE UNIQUE INDEX ix_levelsub_asset_key ON levelsub (asset_key)")
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


def test_the_unique_index_on_a_subscription_is_dropped():
    """One subscriber per asset was right until two people watched the same metal."""
    db = old_database()
    assert "ix_levelsub_asset_key" in run_drop(db)
    assert not any(i["unique"] for i in inspect(db).get_indexes("levelsub"))


def test_dropping_it_twice_is_harmless():
    db = old_database()
    run_drop(db)
    assert run_drop(db) == []


def test_existing_subscriptions_are_handed_to_the_owner():
    db = old_database()
    with db.begin() as conn:
        conn.exec_driver_sql("INSERT INTO levelsub (id, asset_key) VALUES (1, 'metal:XAU')")
    run(db, "999")
    with db.begin() as conn:
        assert conn.exec_driver_sql("SELECT chat_id FROM levelsub").fetchone()[0] == "999"


def test_a_row_that_already_belongs_to_someone_is_left_alone():
    db = old_database()
    run(db, "999")
    with db.begin() as conn:
        conn.exec_driver_sql("INSERT INTO levelsub (id, asset_key, chat_id) VALUES (2, 'x', '111')")
    run(db, "999")
    with db.begin() as conn:
        assert conn.exec_driver_sql("SELECT chat_id FROM levelsub WHERE id = 2").fetchone()[0] == "111"


def test_backfilling_a_table_that_is_not_there_yet_is_a_no_op():
    assert backfill(create_engine("sqlite://"), "levelsub", "chat_id", "1") == 0


def test_every_column_type_also_works_on_postgres():
    """Render runs on Postgres: it rejects BOOLEAN DEFAULT 0 and has no DATETIME type."""
    for table, columns in MIGRATIONS.items():
        for name, ddl in columns.items():
            upper = ddl.upper()
            assert "DATETIME" not in upper, f"{table}.{name}"
            if upper.startswith("BOOLEAN") and "DEFAULT" in upper:
                assert upper.split("DEFAULT")[1].strip() in ("TRUE", "FALSE"), f"{table}.{name}"


def test_an_added_flag_starts_false_on_old_rows():
    db = old_database()
    with db.begin() as conn:
        conn.exec_driver_sql("INSERT INTO item (id, title) VALUES (1, 'hello')")
    run(db)
    with db.begin() as conn:
        assert not conn.exec_driver_sql("SELECT saved, reminded FROM item").fetchone()[0]
