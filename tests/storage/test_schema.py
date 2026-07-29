"""Schema creation, FK enforcement, the reading_history trigger, and the closed
index set — tested against a real SQLite database (docs/spec-modelo-de-datos.md v1.6)."""

import sqlite3

import pytest

from manga_tracker.storage.db import connect, ensure_schema

NOW = "2026-07-23T18:30:00Z"

def _seeded_mapping(conn):
    """Insert one manga + site + manga_sites + bookmarks row, return their ids."""
    manga_id = conn.execute(
        "INSERT INTO mangas (title, created_at, updated_at) VALUES (?, ?, ?)", ("One Piece", NOW, NOW)
    ).lastrowid
    site_id = conn.execute(
        "INSERT INTO sites (name, base_url, created_at, updated_at) VALUES (?, ?, ?, ?)",
        ("manganato", "https://www.manganato.gg", NOW, NOW)).lastrowid
    manga_site_id = conn.execute(
        "INSERT INTO manga_sites (manga_id, site_id, source_key, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (manga_id, site_id, "one-piece", NOW, NOW)).lastrowid
    conn.execute("INSERT INTO bookmarks (manga_id, status, origin, created_at, updated_at) "
                 "VALUES (?, 'reading', 'seed', ?, ?)", (manga_id, NOW, NOW))
    conn.commit()
    return manga_id, site_id, manga_site_id

def test_ensure_schema_is_idempotent():
    conn = connect(":memory:")
    ensure_schema(conn)  # second call on an already-bootstrapped DB must not raise
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"mangas", "sites", "manga_sites", "bookmarks", "reading_history", "chapter_history", "job_runs"} <= tables

def test_foreign_keys_enforced_and_cascade_delete_works():
    conn = connect(":memory:")
    manga_id, site_id, manga_site_id = _seeded_mapping(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO manga_sites (manga_id, site_id, source_key, created_at, updated_at) "
                     "VALUES (9999, ?, 'ghost', ?, ?)", (site_id, NOW, NOW))
    conn.execute("DELETE FROM mangas WHERE id = ?", (manga_id,))
    conn.commit()
    remaining = conn.execute("SELECT COUNT(*) FROM manga_sites WHERE id = ?", (manga_site_id,)).fetchone()[0]
    assert remaining == 0

def test_trigger_fires_on_update_not_on_insert():
    conn = connect(":memory:")
    manga_id, _, _ = _seeded_mapping(conn)
    assert conn.execute("SELECT COUNT(*) FROM reading_history").fetchone()[0] == 0  # INSERT above: zero events
    conn.execute("UPDATE bookmarks SET last_chapter_read = 10 WHERE manga_id = ?", (manga_id,))
    conn.commit()
    row = conn.execute(
        "SELECT chapter_num, previous_chapter_num FROM reading_history WHERE manga_id = ?", (manga_id,)).fetchone()
    assert row == (10, None)

def test_downward_correction_is_captured_as_negative_delta_event():
    conn = connect(":memory:")
    manga_id, _, _ = _seeded_mapping(conn)
    conn.execute("UPDATE bookmarks SET last_chapter_read = 50 WHERE manga_id = ?", (manga_id,))
    conn.execute("UPDATE bookmarks SET last_chapter_read = 40 WHERE manga_id = ?", (manga_id,))
    conn.commit()
    rows = conn.execute(
        "SELECT chapter_num, previous_chapter_num FROM reading_history WHERE manga_id = ? ORDER BY id", (manga_id,)).fetchall()
    assert rows == [(50, None), (40, 50)]  # second event's delta (40 - 50) is negative, kept as-is

def test_check_constraint_rejects_unknown_status():
    conn = connect(":memory:")
    manga_id, _, _ = _seeded_mapping(conn)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE bookmarks SET status = 'binged' WHERE manga_id = ?", (manga_id,))

EXPECTED_INDEXES = {
    "idx_sites_name", "idx_mangas_kitsu_id", "idx_manga_sites_manga_site", "idx_manga_sites_site_source_key",
    "idx_bookmarks_manga_id", "idx_chapter_history_manga_site_chapter", "idx_bookmarks_status",
    "idx_job_runs_job_name_started_at", "idx_reading_history_manga_id_read_at", "idx_reading_history_read_at",
}

def test_every_declared_index_exists():
    conn = connect(":memory:")
    names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
    assert EXPECTED_INDEXES <= names
