"""active_sweep - the primary detection mechanism - and the dead-slug
counter, tested against a fake SourceClient and a fake DigestSender. No
network, no real sleeping: the 5-15s policy lives in transport.py, so a
fake client's fetch_chapters returns instantly."""

import logging

import pytest

from manga_tracker.discovery.active_sweep import active_sweep
from manga_tracker.sources.contracts import Chapter, NotFound, Transient
from manga_tracker.storage.db import connect

NOW = "2026-07-28T03:00:00Z"
LOGGER = logging.getLogger("test")


class FakeClient:
    """One fixed outcome per slug: a chapters list, or an exception class to raise."""

    def __init__(self, outcomes: dict):
        self._outcomes = outcomes
        self.calls: list[str] = []

    def fetch_chapters(self, source_key, *, limit=50):
        self.calls.append(source_key)
        outcome = self._outcomes[source_key]
        if isinstance(outcome, type) and issubclass(outcome, Exception):
            raise outcome(f"{source_key} failed")
        return outcome


class FakeSender:
    def __init__(self, ok: bool = True):
        self.ok = ok

    def send_digest(self, lines, *, now):
        return self.ok


def _seed(conn, *, status="reading", latest=None, consecutive_failures=0, slug="op") -> int:
    manga_id = conn.execute(
        "INSERT INTO mangas (title, created_at, updated_at) VALUES ('OP', ?, ?)", (NOW, NOW)
    ).lastrowid
    site_id = conn.execute(
        "INSERT INTO sites (name, base_url, created_at, updated_at) VALUES ('manganato', 'x', ?, ?)", (NOW, NOW)
    ).lastrowid
    ms_id = conn.execute(
        "INSERT INTO manga_sites (manga_id, site_id, source_key, latest_chapter_num, consecutive_failures, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (manga_id, site_id, slug, latest, consecutive_failures, NOW, NOW),
    ).lastrowid
    conn.execute(
        "INSERT INTO bookmarks (manga_id, status, origin, created_at, updated_at) VALUES (?, ?, 'seed', ?, ?)",
        (manga_id, status, NOW, NOW),
    )
    conn.commit()
    return ms_id


def _failures(conn, ms_id) -> int:
    return conn.execute("SELECT consecutive_failures FROM manga_sites WHERE id = ?", (ms_id,)).fetchone()[0]


@pytest.mark.parametrize(
    "outcome, before, expected",
    [
        (NotFound, 2, 3),
        (Transient, 2, 2),
        ([Chapter(1, "u", None)], 4, 0),
    ],
    ids=["not-found-increments", "transient-unchanged", "success-resets"],
)
def test_dead_slug_counter(outcome, before, expected):
    conn = connect(":memory:")
    ms_id = _seed(conn, consecutive_failures=before, slug="op")

    active_sweep(conn, FakeClient({"op": outcome}), FakeSender(), now=NOW, logger=LOGGER)

    assert _failures(conn, ms_id) == expected


def test_mapping_at_threshold_is_skipped_and_consumes_no_request():
    conn = connect(":memory:")
    _seed(conn, consecutive_failures=5, slug="dead")
    client = FakeClient({})  # no outcome registered - a call would raise KeyError

    active_sweep(conn, client, FakeSender(), now=NOW, logger=LOGGER)

    assert client.calls == []


def test_failing_send_closes_partial_and_advances_nothing():
    conn = connect(":memory:")
    ms_id = _seed(conn, latest=100, slug="op")
    client = FakeClient({"op": [Chapter(101, "https://x/101", NOW)]})

    active_sweep(conn, client, FakeSender(ok=False), now=NOW, logger=LOGGER)

    stored = conn.execute("SELECT latest_chapter_num FROM manga_sites WHERE id = ?", (ms_id,)).fetchone()[0]
    assert stored == 100
    row = conn.execute(
        "SELECT status, notifications_sent FROM job_runs WHERE job_name = 'active_sweep'"
    ).fetchone()
    assert row == ("partial", 0)


def test_non_newest_chapters_still_land_in_chapter_history():
    conn = connect(":memory:")
    ms_id = _seed(conn, latest=100, slug="op")
    chapters = [Chapter(103, "u3", None), Chapter(102, "u2", None), Chapter(101, "u1", None)]

    active_sweep(conn, FakeClient({"op": chapters}), FakeSender(), now=NOW, logger=LOGGER)

    rows = conn.execute(
        "SELECT chapter_num FROM chapter_history WHERE manga_site_id = ? ORDER BY chapter_num", (ms_id,)
    ).fetchall()
    assert [r[0] for r in rows] == [101, 102, 103]
