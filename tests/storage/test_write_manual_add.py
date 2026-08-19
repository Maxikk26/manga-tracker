"""`write_manual_add` and `list_tracked_titles` — the panel add flow's writer
(design D3/D5, spec.md "The manual bookmark write shape", "Zero chapters is a
successful add", "Confirm is atomic; any rejection leaves zero rows").

Real SQLite files on disk, never `:memory:` (design's Testing Strategy), the
same storage layer production uses."""

import re
import sqlite3

import pytest

from manga_tracker.sources.contracts import Chapter
from manga_tracker.storage.db import connect, ensure_site
from manga_tracker.storage.repositories import list_tracked_titles, write_manual_add

NOW = "2026-08-19T12:00:00Z"

_STATUS_CHANGED_AT_RE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

CHAPTERS = [
    Chapter(chapter_num=12.0, url="https://host/manga/x/chapter-12", published_at="2026-08-18T00:00:00Z"),
    Chapter(chapter_num=11.0, url="https://host/manga/x/chapter-11", published_at="2026-08-17T00:00:00Z"),
]


@pytest.fixture()
def db(tmp_path):
    return str(tmp_path / "add.db")


@pytest.fixture()
def conn(db):
    connection = connect(db)
    yield connection
    connection.close()


@pytest.fixture()
def site_id(conn):
    return ensure_site(conn, "manganato", "https://www.manganato.gg")


def _counts(conn) -> tuple[int, int, int, int]:
    return (
        conn.execute("SELECT COUNT(*) FROM mangas").fetchone()[0],
        conn.execute("SELECT COUNT(*) FROM manga_sites").fetchone()[0],
        conn.execute("SELECT COUNT(*) FROM bookmarks").fetchone()[0],
        conn.execute("SELECT COUNT(*) FROM chapter_history").fetchone()[0],
    )


def _write(conn, site_id, *, chapters=CHAPTERS, status="reading", last_chapter_read=0.0,
           cover_url="https://host/cover.webp"):
    return write_manual_add(
        conn,
        title="Some Manga",
        site_id=site_id,
        slug="some-manga",
        url="https://www.manganato.gg/manga/some-manga",
        chapters=chapters,
        status=status,
        last_chapter_read=last_chapter_read,
        cover_url=cover_url,
        now=NOW,
    )


# --- the write shape (spec.md "The manual bookmark write shape") --------------


def test_write_shape_origin_progress_and_status_changed_at(conn, site_id):
    manga_id, bookmark_id = _write(conn, site_id)

    row = conn.execute(
        "SELECT origin, progress_is_approx, status_changed_at, last_read_at FROM bookmarks WHERE id = ?",
        (bookmark_id,),
    ).fetchone()
    assert row[0] == "manual"
    assert row[1] == 0
    assert _STATUS_CHANGED_AT_RE.match(row[2])
    assert row[3] is None  # an initial chapter is progress, not a reading event


def test_chapters_seeded_on_add_reuse_seed_backfill(conn, site_id):
    manga_id, _ = _write(conn, site_id)

    manga_site_id = conn.execute("SELECT id FROM manga_sites WHERE manga_id = ?", (manga_id,)).fetchone()[0]
    detected_via = {
        row[0]
        for row in conn.execute(
            "SELECT detected_via FROM chapter_history WHERE manga_site_id = ?", (manga_site_id,)
        )
    }
    assert detected_via == {"seed_backfill"}


def test_no_reading_history_row_is_generated(conn, site_id):
    """The trigger is UPDATE-only; an INSERT must never fire it (bulk-add
    parity with the seed loader and the Kitsu import)."""
    manga_id, _ = _write(conn, site_id)

    assert conn.execute(
        "SELECT COUNT(*) FROM reading_history WHERE manga_id = ?", (manga_id,)
    ).fetchone()[0] == 0


def test_cover_url_is_written_to_mangas(conn, site_id):
    manga_id, _ = _write(conn, site_id, cover_url="https://host/cover.webp")

    assert conn.execute("SELECT cover_url FROM mangas WHERE id = ?", (manga_id,)).fetchone()[0] == (
        "https://host/cover.webp"
    )


# --- zero chapters (design D5, spec.md "Zero chapters is a successful add") ---


def test_zero_chapters_leaves_latest_chapter_num_null_and_writes_no_history(conn, site_id):
    manga_id, bookmark_id = _write(conn, site_id, chapters=[])

    manga_site = conn.execute(
        "SELECT latest_chapter_num, latest_chapter_url, latest_chapter_at FROM manga_sites WHERE manga_id = ?",
        (manga_id,),
    ).fetchone()
    assert manga_site == (None, None, None)
    assert conn.execute("SELECT COUNT(*) FROM chapter_history").fetchone()[0] == 0
    # The bookmark still exists — this is a successful add, not a rejection.
    assert conn.execute("SELECT status FROM bookmarks WHERE id = ?", (bookmark_id,)).fetchone()[0] == "reading"


def test_zero_chapters_still_stamps_last_checked_at(conn, site_id):
    """The confirm operation really did ask the source (fetch_chapters ran and
    reported an empty list); `last_checked_at` records that fact independently
    of whether a chapter was found."""
    manga_id, _ = _write(conn, site_id, chapters=[])

    assert conn.execute(
        "SELECT last_checked_at FROM manga_sites WHERE manga_id = ?", (manga_id,)
    ).fetchone()[0] == NOW


# --- initial chapter (spec.md "Initial status and chapter validation") -------


def test_initial_chapter_ahead_of_the_source_is_written_as_is(conn, site_id):
    """No cross-validation against latest_chapter_num — reading ahead of what
    the source has detected is legitimate."""
    _, bookmark_id = _write(conn, site_id, chapters=CHAPTERS, last_chapter_read=100.0)

    assert conn.execute(
        "SELECT last_chapter_read FROM bookmarks WHERE id = ?", (bookmark_id,)
    ).fetchone()[0] == 100.0


# --- atomicity (spec.md "Confirm is atomic; any rejection leaves zero rows") --


def test_a_failure_partway_through_the_write_leaves_zero_rows(conn):
    """An FK violation on manga_sites.site_id fires after the mangas INSERT
    already ran inside the same connection — the property under test is that
    the transaction wrapper rolls that first INSERT back too."""
    before = _counts(conn)

    with pytest.raises(sqlite3.IntegrityError):
        _write(conn, site_id=999999)  # no such site

    assert _counts(conn) == before


# --- list_tracked_titles (design D3, duplicate gates 2 and 3) -----------------


def test_list_tracked_titles_returns_title_and_status_per_bookmark(conn, site_id):
    _write(conn, site_id)
    write_manual_add(
        conn, title="Another Manga", site_id=site_id, slug="another-manga",
        url="https://www.manganato.gg/manga/another-manga", chapters=[], status="dropped",
        last_chapter_read=0.0, cover_url=None, now=NOW,
    )

    assert sorted(list_tracked_titles(conn)) == [("Another Manga", "dropped"), ("Some Manga", "reading")]


def test_list_tracked_titles_is_empty_for_a_fresh_database(conn):
    assert list_tracked_titles(conn) == []
