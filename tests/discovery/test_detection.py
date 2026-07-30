"""The shared detection rule (CD Parte B v1.3) - tested directly against a
real DB. The rule takes an already-observed chapter (a source-client concern)
and returns a plain Candidate or None, so no client/sender double is needed."""

import logging

import pytest

from manga_tracker.discovery.detection import Candidate, Mapping, apply_detection
from manga_tracker.sources.contracts import Chapter
from manga_tracker.storage.db import connect

NOW = "2026-07-28T00:00:00Z"
LOGGER = logging.getLogger("test")


def seed_mapping(conn, *, status="reading", latest=None) -> Mapping:
    manga_id = conn.execute(
        "INSERT INTO mangas (title, created_at, updated_at) VALUES ('One Piece', ?, ?)", (NOW, NOW)
    ).lastrowid
    site_id = conn.execute(
        "INSERT INTO sites (name, base_url, created_at, updated_at) VALUES ('manganato', 'https://x', ?, ?)",
        (NOW, NOW),
    ).lastrowid
    ms_id = conn.execute(
        "INSERT INTO manga_sites (manga_id, site_id, source_key, latest_chapter_num, created_at, updated_at) "
        "VALUES (?, ?, 'one-piece', ?, ?, ?)", (manga_id, site_id, latest, NOW, NOW),
    ).lastrowid
    conn.execute(
        "INSERT INTO bookmarks (manga_id, status, origin, created_at, updated_at) VALUES (?, ?, 'seed', ?, ?)",
        (manga_id, status, NOW, NOW),
    )
    conn.commit()
    return Mapping(ms_id, manga_id, "One Piece", status, latest, None)


def _history_count(conn, manga_site_id: int) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM chapter_history WHERE manga_site_id = ?", (manga_site_id,)
    ).fetchone()[0]


@pytest.mark.parametrize("status", ["completed", "dropped"])
def test_terminal_bookmark_writes_no_history_and_no_update(status):
    conn = connect(":memory:")
    mapping = seed_mapping(conn, status=status, latest=100)
    chapter = Chapter(chapter_num=101, url="x", published_at=NOW)

    candidate = apply_detection(conn, mapping, chapter, detected_via="feed", now=NOW, logger=LOGGER)

    assert candidate is None
    assert _history_count(conn, mapping.id) == 0
    row = conn.execute(
        "SELECT latest_chapter_num, last_checked_at FROM manga_sites WHERE id = ?", (mapping.id,)
    ).fetchone()
    assert row == (100, NOW)  # step 1's seal still happened; nothing else did


def test_lower_observed_number_never_moves_stored_value_backward(caplog):
    conn = connect(":memory:")
    mapping = seed_mapping(conn, status="reading", latest=100)
    chapter = Chapter(chapter_num=90, url="x", published_at=None)

    with caplog.at_level(logging.WARNING):
        candidate = apply_detection(conn, mapping, chapter, detected_via="active_sweep", now=NOW, logger=LOGGER)

    assert candidate is None and "renumbered/deleted" in caplog.text
    stored = conn.execute("SELECT latest_chapter_num FROM manga_sites WHERE id = ?", (mapping.id,)).fetchone()[0]
    assert stored == 100


@pytest.mark.parametrize("status", ["reading", "want_to_read"])
def test_active_bookmark_returns_candidate_but_leaves_latest_untouched(status):
    conn = connect(":memory:")
    mapping = seed_mapping(conn, status=status, latest=100)
    chapter = Chapter(chapter_num=101, url="https://x/101", published_at="2026-07-28T01:00:00Z")

    candidate = apply_detection(conn, mapping, chapter, detected_via="feed", now=NOW, logger=LOGGER)

    assert candidate == Candidate(mapping.id, "One Piece", 101, "https://x/101", "2026-07-28T01:00:00Z", None)
    assert _history_count(conn, mapping.id) == 1  # written regardless of the (not yet made) notify decision
    stored = conn.execute("SELECT latest_chapter_num FROM manga_sites WHERE id = ?", (mapping.id,)).fetchone()[0]
    assert stored == 100  # notify-before-update: untouched until the digest succeeds


def test_reprocessing_the_same_chapter_is_idempotent():
    """An active bookmark leaves latest_chapter_num untouched (notify-before-
    update), so a second mechanism observing the same chapter runs the rule
    again - the UNIQUE index must make the second chapter_history write a
    silent no-op rather than an error."""
    conn = connect(":memory:")
    mapping = seed_mapping(conn, status="reading", latest=100)
    chapter = Chapter(chapter_num=101, url="x", published_at=None)

    apply_detection(conn, mapping, chapter, detected_via="feed", now=NOW, logger=LOGGER)
    apply_detection(conn, mapping, chapter, detected_via="feed", now=NOW, logger=LOGGER)

    assert _history_count(conn, mapping.id) == 1


def test_on_hold_updates_silently_without_notifying():
    conn = connect(":memory:")
    mapping = seed_mapping(conn, status="on_hold", latest=100)
    chapter = Chapter(chapter_num=101, url="https://x/101", published_at="2026-07-28T01:00:00Z")

    candidate = apply_detection(conn, mapping, chapter, detected_via="active_sweep", now=NOW, logger=LOGGER)

    assert candidate is None
    row = conn.execute(
        "SELECT latest_chapter_num, latest_chapter_url FROM manga_sites WHERE id = ?", (mapping.id,)
    ).fetchone()
    assert row == (101, "https://x/101")  # applied immediately, not gated behind any digest


def test_invalid_detected_via_fails_loudly_instead_of_dropping_history():
    """INSERT OR IGNORE hides CHECK violations, so the value is guarded here.

    Without this, a bad `detected_via` produces no error and no row: history
    disappears with nothing logged. It is a live trap because a job's own
    job_name is the obvious thing to pass, and for active_sweep that happens to
    be a legal value while for feed_check it is not.
    """
    conn = connect(":memory:")
    mapping = Mapping(1, 1, "T", "reading", 100, 90)
    chapter = Chapter(chapter_num=101, url="u", published_at=None)

    with pytest.raises(ValueError, match="detected_via"):
        apply_detection(conn, mapping, chapter, detected_via="feed_check",
                        now="2026-07-29T06:00:00Z", logger=logging.getLogger("t"))
