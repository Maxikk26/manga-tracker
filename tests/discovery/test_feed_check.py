"""feed_check - Mecanismo 1, the opportunistic hourly mechanism - tested
against a fake SourceClient and a fake DigestSender. No network."""

import logging

from manga_tracker.discovery.feed_check import feed_check
from manga_tracker.sources.contracts import FeedItem
from manga_tracker.storage.db import connect

NOW = "2026-07-28T04:00:00Z"
LOGGER = logging.getLogger("test")


class FakeClient:
    def __init__(self, items):
        self._items = items

    def fetch_latest_feed(self):
        return self._items


class FakeSender:
    def __init__(self, ok: bool = True):
        self.ok = ok

    def send_digest(self, lines, *, now):
        return self.ok


def _seed(conn, *, status="reading", latest=None, slug="op") -> tuple[int, int]:
    manga_id = conn.execute(
        "INSERT INTO mangas (title, created_at, updated_at) VALUES ('OP', ?, ?)", (NOW, NOW)
    ).lastrowid
    site_id = conn.execute(
        "INSERT INTO sites (name, base_url, created_at, updated_at) VALUES ('manganato', 'x', ?, ?)", (NOW, NOW)
    ).lastrowid
    ms_id = conn.execute(
        "INSERT INTO manga_sites (manga_id, site_id, source_key, latest_chapter_num, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (manga_id, site_id, slug, latest, NOW, NOW),
    ).lastrowid
    conn.execute(
        "INSERT INTO bookmarks (manga_id, status, origin, created_at, updated_at) VALUES (?, ?, 'seed', ?, ?)",
        (manga_id, status, NOW, NOW),
    )
    conn.commit()
    return site_id, ms_id


def test_feed_item_not_in_reading_list_is_ignored_with_no_error():
    conn = connect(":memory:")
    site_id, _ = _seed(conn, slug="op")
    item = FeedItem("someone-else", "Other Manga", 5, "https://x/5", None, None)

    feed_check(conn, FakeClient([item]), FakeSender(), site_id=site_id, now=NOW, logger=LOGGER)

    row = conn.execute("SELECT status, updates_found FROM job_runs WHERE job_name = 'feed_check'").fetchone()
    assert row == ("ok", 0)


def test_a_silent_on_hold_match_still_counts_in_updates_found():
    """The production symptom, as a test: on 2026-08-05 the feed detected two
    chapters on on_hold titles and `job_runs` reported `updates_found = 0`.

    CD defines the column as "capitulos nuevos detectados (activos +
    silenciosos)", and the count was `len(candidates)` - which an on_hold match
    never joins, because it is never notified. Reading that zero back, the run
    looked like it had found nothing at all while `chapter_history` said
    otherwise. `notifications_sent` stays 0 here: silent means silent, and only
    the counting was wrong.
    """
    conn = connect(":memory:")
    site_id, ms_id = _seed(conn, status="on_hold", latest=100, slug="op")
    item = FeedItem("op", "One Piece", 101, "https://x/101", None, "3 hours ago")

    feed_check(conn, FakeClient([item]), FakeSender(), site_id=site_id, now=NOW, logger=LOGGER)

    row = conn.execute(
        "SELECT status, updates_found, notifications_sent FROM job_runs WHERE job_name = 'feed_check'"
    ).fetchone()
    assert row == ("ok", 1, 0)
    history = conn.execute(
        "SELECT COUNT(*) FROM chapter_history WHERE manga_site_id = ?", (ms_id,)
    ).fetchone()[0]
    assert history == 1  # the column now agrees with the table it was contradicting


def test_matching_active_item_produces_a_candidate():
    conn = connect(":memory:")
    site_id, ms_id = _seed(conn, latest=100, slug="op")
    item = FeedItem("op", "One Piece", 101, "https://x/101", None, "3 hours ago")

    feed_check(conn, FakeClient([item]), FakeSender(), site_id=site_id, now=NOW, logger=LOGGER)

    row = conn.execute(
        "SELECT status, updates_found, notifications_sent FROM job_runs WHERE job_name = 'feed_check'"
    ).fetchone()
    assert row == ("ok", 1, 1)
    stored = conn.execute("SELECT latest_chapter_num FROM manga_sites WHERE id = ?", (ms_id,)).fetchone()[0]
    assert stored == 101


def test_feed_detection_writes_source_published_at_as_null():
    conn = connect(":memory:")
    site_id, ms_id = _seed(conn, latest=100, slug="op")
    item = FeedItem("op", "One Piece", 101, "https://x/101", None, "3 hours ago")

    feed_check(conn, FakeClient([item]), FakeSender(), site_id=site_id, now=NOW, logger=LOGGER)

    stored = conn.execute(
        "SELECT source_published_at FROM chapter_history WHERE manga_site_id = ?", (ms_id,)
    ).fetchone()[0]
    assert stored is None
