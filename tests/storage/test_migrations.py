"""Schema migrations, tested against databases on DISK rather than :memory:.

That distinction is the entire point of this file. Every other test in the suite
builds its database from nothing, and `schema.sql` is all CREATE ... IF NOT
EXISTS, so a fresh database always comes out complete and current. A column
added to schema.sql therefore passes the whole suite while doing NOTHING to a
database that already exists - which is the only kind production has. The bug
this file exists to catch is invisible in memory by construction.
"""

import sqlite3

import pytest

from manga_tracker.storage.db import SCHEMA_PATH, SCHEMA_VERSION, connect

SEED_AT = "2026-08-01T00:00:00Z"

# The two columns migration 1 adds. Kept here as literals rather than imported so
# that renaming them in the migration cannot silently rename the assertion too.
ADDED_COLUMNS = ("items_requested", "items_skipped")


def _build_pre_migration_database(path) -> None:
    """A database shaped exactly like production was before migration 1.

    Built by stripping the new columns out of the real schema rather than by
    hand-writing an old CREATE TABLE: a hand-written copy drifts from the real
    one, and then the test migrates a shape that never existed.
    """
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    for column in ADDED_COLUMNS:
        sql = sql.replace(f"    {column} INTEGER,\n", "")
    assert all(f"{c} INTEGER" not in sql for c in ADDED_COLUMNS), "the strip did not take"

    conn = sqlite3.connect(path)
    conn.executescript(sql)
    conn.execute("PRAGMA user_version = 0")  # what every database predating this work reports
    conn.execute(
        "INSERT INTO job_runs (job_name, started_at, finished_at, status, items_checked, updates_found, "
        "notifications_sent) VALUES ('active_sweep', ?, ?, 'ok', 22, 1, 1)",
        (SEED_AT, SEED_AT),
    )
    conn.commit()
    conn.close()


def _columns(conn, table) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def test_an_existing_database_gains_the_new_columns_and_keeps_its_rows(tmp_path):
    """The case that only a file database can express.

    Before this migration machinery existed, `ensure_schema` on this database
    was a no-op: the tables were already there, so IF NOT EXISTS skipped
    everything, and the new columns simply never appeared. Every INSERT naming
    them would then fail in production while the suite stayed green.
    """
    path = tmp_path / "old.db"
    _build_pre_migration_database(path)

    with sqlite3.connect(path) as before:
        assert not (_columns(before, "job_runs") & set(ADDED_COLUMNS)), "fixture is not pre-migration"

    conn = connect(str(path))

    assert set(ADDED_COLUMNS) <= _columns(conn, "job_runs")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    # The row that was already there survives, with its old values and NULL for
    # what the migration could not know.
    row = conn.execute(
        "SELECT job_name, items_checked, updates_found, items_requested, items_skipped FROM job_runs"
    ).fetchone()
    assert row == ("active_sweep", 22, 1, None, None)


def test_a_fresh_database_is_born_current_and_runs_no_migration(tmp_path):
    """A new database must not be migrated - schema.sql already created it whole.

    If it were, migration 1 would ALTER a table that already has both columns.
    That is guarded inside the migration too, but the version stamp is what makes
    the guard unnecessary, and this asserts the stamp.
    """
    conn = connect(str(tmp_path / "new.db"))

    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert set(ADDED_COLUMNS) <= _columns(conn, "job_runs")


def test_connecting_again_changes_nothing(tmp_path):
    """`connect` runs on every job, several times an hour. Migrating twice, or
    re-stamping a version, would be a bug with a very long fuse."""
    path = tmp_path / "old.db"
    _build_pre_migration_database(path)

    connect(str(path)).close()
    conn = connect(str(path))

    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert conn.execute("SELECT COUNT(*) FROM job_runs").fetchone()[0] == 1
    assert len([c for c in _columns(conn, "job_runs") if c == "items_requested"]) == 1


def test_the_migration_is_safe_on_a_database_that_somehow_already_has_the_columns(tmp_path):
    """Belt for the one production database: a row at user_version 0 whose table
    already carries the columns must not blow up with "duplicate column name"."""
    path = tmp_path / "half.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))  # includes both columns
    conn.execute("PRAGMA user_version = 0")  # but claims to predate them
    conn.commit()
    conn.close()

    migrated = connect(str(path))  # must not raise

    assert migrated.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_schema_version_matches_the_migrations_that_exist():
    """A migration added without bumping SCHEMA_VERSION would never run; a bump
    without a migration would stamp a version nothing produced."""
    from manga_tracker.storage.db import MIGRATIONS

    assert sorted(MIGRATIONS) == list(range(1, SCHEMA_VERSION + 1))


@pytest.mark.parametrize("column", ADDED_COLUMNS)
def test_the_new_columns_are_absent_from_the_stripped_fixture(column):
    """Guards the fixture itself: if schema.sql ever stops declaring a column on
    its own line, the strip silently stops working and every test above would
    migrate a database that needed no migration."""
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    assert f"    {column} INTEGER,\n" in sql
