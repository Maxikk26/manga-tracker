"""SQLite connection factory and schema bootstrap.

The only file allowed to import sqlite3 (enforced by test_architecture.py).
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the 7 tables/trigger/indexes if missing. No argument beyond the
    connection (design D4/B6) — idempotent, safe to run on every connect."""
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
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

@contextmanager
def transaction(conn: sqlite3.Connection):
    """Wrap a block of writes in one commit, rolling back on any exception."""
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
