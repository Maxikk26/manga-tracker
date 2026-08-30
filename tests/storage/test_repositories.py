"""Direct repository-function tests that don't fit the higher-level suites:
the stored-url cover candidate query (panel-v1b-fase-4 design D5), the
`TERMINAL_STATUSES` parity guard (design D8), `update_panel_bookmark`'s
`my_score` sentinel handling (design D1), and `set_bookmark_score`'s
fill-only-NULL guard (design D6).
"""

from manga_tracker.importer.export import TERMINAL_STATUSES as EXPORT_TERMINAL_STATUSES
from manga_tracker.storage.db import connect
from manga_tracker.storage.repositories import (
    TERMINAL_STATUSES,
    list_stored_url_cover_candidates,
    set_bookmark_score,
    update_panel_bookmark,
)
from manga_tracker.web.app import TERMINAL_STATUSES as APP_TERMINAL_STATUSES

NOW = "2026-08-25T00:00:00Z"


def test_the_three_terminal_statuses_copies_are_equal():
    """`web/app.py`, `importer/export.py` and `storage/repositories.py` each
    carry their own copy (design D8) — kept separate on purpose (pulling
    `storage`, and `sqlite3` with it, into the pure XML parser is the worse
    trade), pinned equal here instead of by convention."""
    assert TERMINAL_STATUSES == APP_TERMINAL_STATUSES == EXPORT_TERMINAL_STATUSES


def test_list_stored_url_cover_candidates_sees_unmapped_rows(tmp_path):
    """`list_cover_candidates`'s INNER JOIN cannot return this row at all —
    this query must, because most of today's terminals have no `manga_sites`
    row (design D5)."""
    path = str(tmp_path / "unmapped.db")
    conn = connect(path)
    conn.execute(
        "INSERT INTO mangas (id, title, cover_url, created_at, updated_at) "
        "VALUES (1, 'Orphan', 'https://media.kitsu.app/x.webp', ?, ?)", (NOW, NOW),
    )
    conn.execute(
        "INSERT INTO bookmarks (manga_id, status, origin, created_at, updated_at) "
        "VALUES (1, 'completed', 'seed', ?, ?)", (NOW, NOW),
    )
    conn.commit()

    rows = list_stored_url_cover_candidates(conn, statuses=("completed", "dropped"))
    conn.close()

    assert rows == [(1, "Orphan", "https://media.kitsu.app/x.webp")]


def test_list_stored_url_cover_candidates_never_carries_a_source_key(tmp_path):
    """Structural, not incidental: the SELECT has no `manga_sites` column at
    all, so even a MAPPED terminal's row carries no `source_key` (design D5
    — "no hay slug con el que hacerlas aunque alguien quisiera", made
    mechanical)."""
    path = str(tmp_path / "mapped.db")
    conn = connect(path)
    conn.execute(
        "INSERT INTO sites (id, name, base_url, created_at, updated_at) "
        "VALUES (1, 'manganato', 'https://manganato.example', ?, ?)", (NOW, NOW),
    )
    conn.execute(
        "INSERT INTO mangas (id, title, cover_url, created_at, updated_at) "
        "VALUES (1, 'Mapped', 'https://media.kitsu.app/x.webp', ?, ?)", (NOW, NOW),
    )
    conn.execute(
        "INSERT INTO manga_sites (manga_id, site_id, source_key, created_at, updated_at) "
        "VALUES (1, 1, 'a-slug', ?, ?)", (NOW, NOW),
    )
    conn.execute(
        "INSERT INTO bookmarks (manga_id, status, origin, created_at, updated_at) "
        "VALUES (1, 'dropped', 'seed', ?, ?)", (NOW, NOW),
    )
    conn.commit()

    row = list_stored_url_cover_candidates(conn, statuses=("completed", "dropped"))[0]
    conn.close()

    assert row == (1, "Mapped", "https://media.kitsu.app/x.webp")
    assert len(row) == 3  # (manga_id, title, cover_url) -- no fourth column for a slug


def test_list_stored_url_cover_candidates_is_not_filtered_on_cover_url(tmp_path):
    """Reports the whole population; the caller decides what a NULL costs."""
    path = str(tmp_path / "nulls.db")
    conn = connect(path)
    conn.execute(
        "INSERT INTO mangas (id, title, cover_url, created_at, updated_at) "
        "VALUES (1, 'No Cover', NULL, ?, ?)", (NOW, NOW),
    )
    conn.execute(
        "INSERT INTO bookmarks (manga_id, status, origin, created_at, updated_at) "
        "VALUES (1, 'dropped', 'seed', ?, ?)", (NOW, NOW),
    )
    conn.commit()

    rows = list_stored_url_cover_candidates(conn, statuses=("completed", "dropped"))
    conn.close()

    assert rows == [(1, "No Cover", None)]


def test_list_stored_url_cover_candidates_excludes_non_terminal_statuses(tmp_path):
    path = str(tmp_path / "mixed.db")
    conn = connect(path)
    conn.execute(
        "INSERT INTO mangas (id, title, cover_url, created_at, updated_at) "
        "VALUES (1, 'Reading', 'https://media.kitsu.app/x.webp', ?, ?)", (NOW, NOW),
    )
    conn.execute(
        "INSERT INTO bookmarks (manga_id, status, origin, created_at, updated_at) "
        "VALUES (1, 'reading', 'seed', ?, ?)", (NOW, NOW),
    )
    conn.commit()

    rows = list_stored_url_cover_candidates(conn, statuses=("completed", "dropped"))
    conn.close()

    assert rows == []


# --- update_panel_bookmark: my_score (panel-v1b-fase-4 design D1) -----------------


def _seed_scored_bookmark(tmp_path, name, *, my_score=None, last_chapter_read=None):
    conn = connect(str(tmp_path / f"{name}.db"))
    manga_id = conn.execute(
        "INSERT INTO mangas (title, created_at, updated_at) VALUES (?, ?, ?)",
        ("Scored Manga", NOW, NOW),
    ).lastrowid
    bookmark_id = conn.execute(
        "INSERT INTO bookmarks (manga_id, status, last_chapter_read, my_score, origin, "
        "created_at, updated_at) VALUES (?, 'reading', ?, ?, 'seed', ?, ?)",
        (manga_id, last_chapter_read, my_score, NOW, NOW),
    ).lastrowid
    conn.commit()
    return conn, manga_id, bookmark_id


def _my_score(conn, bookmark_id):
    return conn.execute("SELECT my_score FROM bookmarks WHERE id = ?", (bookmark_id,)).fetchone()[0]


def _reading_history_count(conn, manga_id):
    return conn.execute(
        "SELECT COUNT(*) FROM reading_history WHERE manga_id = ?", (manga_id,)
    ).fetchone()[0]


def test_update_panel_bookmark_my_score_none_writes_sql_null(tmp_path):
    conn, _manga_id, bookmark_id = _seed_scored_bookmark(tmp_path, "clear", my_score=7)

    assert update_panel_bookmark(conn, bookmark_id, my_score=None, now=NOW) is True

    assert _my_score(conn, bookmark_id) is None


def test_update_panel_bookmark_leaves_my_score_untouched_when_the_argument_is_omitted(tmp_path):
    """`my_score` defaults to `UNSET`, a sentinel distinct from `None`. If the
    repository's guard is ever weakened from `is not UNSET` to `is not None`,
    this default (`UNSET`, which very much `is not None`) would be bound
    straight into the SQL parameter list — and `sqlite3` refuses to bind a
    bare `object()`, so the swap fails loudly here rather than silently
    dropping every un-nulled score (design D1)."""
    conn, _manga_id, bookmark_id = _seed_scored_bookmark(tmp_path, "untouched", my_score=5)

    assert update_panel_bookmark(conn, bookmark_id, now=NOW) is True

    assert _my_score(conn, bookmark_id) == 5


def test_update_panel_bookmark_my_score_only_edit_writes_no_reading_history(tmp_path):
    conn, manga_id, bookmark_id = _seed_scored_bookmark(
        tmp_path, "no-history", my_score=None, last_chapter_read=10.0
    )

    update_panel_bookmark(conn, bookmark_id, my_score=8, now=NOW)

    assert _my_score(conn, bookmark_id) == 8
    assert _reading_history_count(conn, manga_id) == 0


# --- set_bookmark_score (panel-v1b-fase-4 design D6, TOCTOU) -----------------


class _CountingConnection:
    """Proxies every attribute to a real `sqlite3.Connection` except
    `execute`, which it also counts. `sqlite3.Connection` is an immutable C
    type -- neither the class nor an instance accepts a patched `execute` --
    so counting calls means wrapping one instead of monkeypatching it."""

    def __init__(self, real):
        self._real = real
        self.execute_calls: list = []

    def execute(self, *args, **kwargs):
        self.execute_calls.append(args)
        return self._real.execute(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)


def test_set_bookmark_score_fills_an_unscored_bookmark_in_one_statement(tmp_path):
    """The fill-only-NULL rule MUST be one statement -- the guard lives in the
    WHERE clause, never in a Python read-then-write (design D6): the latter is
    a real TOCTOU against a concurrent panel edit on the same SQLite file, not
    a theoretical one.

    Asserted mechanically, not just by outcome, and on THIS scenario
    specifically: a read-then-write rewrite needs two `execute()` calls to
    fill a NULL score (a SELECT to check it is still unscored, then the
    UPDATE), while the one-statement `UPDATE ... WHERE my_score IS NULL`
    needs exactly one. (The rejected-row scenario below can't tell the two
    shapes apart -- a read-then-write's SELECT alone is enough to bail out
    early there, so it also costs one call. This is the scenario where the
    call count actually diverges.) Pinning it to 1 here fails loudly the
    moment the guard moves into Python, even though the *outcome* would look
    identical from a single-threaded caller either way.
    """
    conn, manga_id, bookmark_id = _seed_scored_bookmark(tmp_path, "fill", my_score=None)
    counting = _CountingConnection(conn)

    assert set_bookmark_score(counting, manga_id, 9, now=NOW) is True

    assert len(counting.execute_calls) == 1, (
        f"expected exactly one execute() call, got {len(counting.execute_calls)}: "
        f"{counting.execute_calls}"
    )
    assert _my_score(conn, bookmark_id) == 9


def test_set_bookmark_score_returns_false_and_changes_nothing_on_an_already_scored_row(tmp_path):
    conn, manga_id, bookmark_id = _seed_scored_bookmark(tmp_path, "already-scored", my_score=7)

    assert set_bookmark_score(conn, manga_id, 9, now=NOW) is False

    assert _my_score(conn, bookmark_id) == 7  # untouched -- the hand-typed score survives
