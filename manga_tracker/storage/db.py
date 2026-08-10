"""SQLite connection factory and schema bootstrap.

The only file allowed to import sqlite3 (enforced by test_architecture.py).
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# Bump this with every migration added below, and never renumber an existing one:
# the number is recorded in each deployed database's PRAGMA user_version.
SCHEMA_VERSION = 1


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    }


def _user_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def _set_user_version(conn: sqlite3.Connection, version: int) -> None:
    # PRAGMA takes no bound parameters, so the value is interpolated - through
    # int() rather than trusting the caller, since a string here would execute.
    conn.execute(f"PRAGMA user_version = {int(version)}")


def _migration_1_job_runs_prefilter_split(conn: sqlite3.Connection) -> None:
    """job_runs gains items_requested / items_skipped.

    Guarded by table_info rather than assumed: the one production database has
    no second copy, and a migration that raises "duplicate column name" halfway
    would leave the schema version behind the schema itself.
    """
    columns = {row[1] for row in conn.execute("PRAGMA table_info(job_runs)")}
    for column in ("items_requested", "items_skipped"):
        if column not in columns:
            # The name is a literal from the tuple above, never caller input.
            conn.execute(f"ALTER TABLE job_runs ADD COLUMN {column} INTEGER")


MIGRATIONS = {1: _migration_1_job_runs_prefilter_split}


def _migrate(conn: sqlite3.Connection) -> int:
    """Apply every migration the database has not seen, oldest first.

    user_version is written after each one and committed with it, so an
    interruption leaves the number describing what actually ran rather than what
    was intended.
    """
    applied = 0
    for version in range(_user_version(conn) + 1, SCHEMA_VERSION + 1):
        MIGRATIONS[version](conn)
        _set_user_version(conn, version)
        conn.commit()
        applied += 1
    return applied


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the 7 tables/trigger/indexes if missing, then migrate. No argument
    beyond the connection (design D4/B6) — idempotent, safe on every connect.

    The order matters and the emptiness check has to happen FIRST. `schema.sql`
    is all CREATE ... IF NOT EXISTS, which means it creates a fresh database
    complete and correct, and does exactly nothing to one that already has the
    tables — including nothing about a column added to an existing table. That
    is how a schema change could look right in every test and be absent in
    production: the suite builds each database from scratch, where schema.sql
    always applies in full.

    So a database that was born in this call is already current and is stamped
    with SCHEMA_VERSION. One that existed before gets the migrations instead,
    which is the only path that can alter a table SQLite has already created.
    """
    born_empty = not _table_names(conn)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    if born_empty:
        _set_user_version(conn, SCHEMA_VERSION)
    else:
        _migrate(conn)
    conn.commit()


def connect(path: str) -> sqlite3.Connection:
    """Open a connection with FK enforcement on (off by default in SQLite;
    this schema relies on cascade deletes) and the schema bootstrapped."""
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    ensure_schema(conn)
    return conn


def ensure_site(conn: sqlite3.Connection, name: str, base_url: str) -> int:
    """Upsert the single site row, called only from `cli.py` (design D4/B6).

    `ON CONFLICT DO UPDATE`, never `INSERT OR IGNORE`: a source domain change
    must refresh `base_url`, not leave it stale (SRC §9 playbook).
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    row = conn.execute(
        "INSERT INTO sites (name, base_url, created_at, updated_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(name) DO UPDATE SET base_url = excluded.base_url, updated_at = excluded.updated_at "
        "RETURNING id",
        (name, base_url, now, now),
    ).fetchone()
    conn.commit()
    return row[0]

@contextmanager
def transaction(conn: sqlite3.Connection):
    """Wrap a block of writes in one commit, rolling back on any exception."""
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
