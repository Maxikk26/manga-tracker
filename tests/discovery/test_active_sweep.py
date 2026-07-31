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
    def __init__(self, ok: bool = True, dead_slug_ok: bool = True):
        self.ok = ok
        self.dead_slug_ok = dead_slug_ok
        self.dead_slug_calls: list[list] = []

    def send_digest(self, lines, *, now):
        return self.ok

    def send_dead_slug_notice(self, notices, *, now):
        self.dead_slug_calls.append(list(notices))
        return self.dead_slug_ok


def _seed(conn, *, status="reading", latest=None, consecutive_failures=0, slug="op", title="OP") -> int:
    """Get-or-create the site row: `sites.name` is UNIQUE, so a second call in
    the same test used to fail on the insert rather than on anything meaningful."""
    manga_id = conn.execute(
        "INSERT INTO mangas (title, created_at, updated_at) VALUES (?, ?, ?)", (title, NOW, NOW)
    ).lastrowid
    site = conn.execute("SELECT id FROM sites WHERE name = 'manganato'").fetchone()
    site_id = site[0] if site else conn.execute(
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


def _status(conn):
    return conn.execute("SELECT status, notifications_sent FROM job_runs ORDER BY id DESC LIMIT 1").fetchone()


def test_crossing_the_threshold_notifies_and_only_then_advances_the_counter():
    """BOT "Mensaje 3". The counter moves after the notice, never before.

    A mapping at the threshold is excluded from the population, so it issues no
    further requests and never increments again: the crossing happens exactly
    once in the life of a dead slug. Advancing first would let a failed send
    destroy the only notice that mapping will ever produce.
    """
    conn = connect(":memory:")
    ms_id = _seed(conn, consecutive_failures=4, slug="gone")
    sender = FakeSender()

    active_sweep(conn, FakeClient({"gone": NotFound}), sender, now=NOW, logger=LOGGER)

    assert len(sender.dead_slug_calls) == 1
    notice = sender.dead_slug_calls[0][0]
    assert (notice.manga_title, notice.source_key, notice.failure_count) == ("OP", "gone", 5)
    assert notice.retries_weekly is False  # onhold_sweep does not exist yet
    assert _failures(conn, ms_id) == 5
    assert _status(conn) == ("ok", 1)


def test_a_failed_dead_slug_notice_loses_nothing_and_the_next_run_retries():
    """The whole point of the ordering: a lost notice would drop the title out of
    the daily sweep in exactly the silence the message exists to break."""
    conn = connect(":memory:")
    ms_id = _seed(conn, consecutive_failures=4, slug="gone")

    failing = FakeSender(dead_slug_ok=False)
    active_sweep(conn, FakeClient({"gone": NotFound}), failing, now=NOW, logger=LOGGER)

    assert len(failing.dead_slug_calls) == 1
    assert _failures(conn, ms_id) == 4  # held back, so the crossing can happen again
    assert _status(conn) == ("partial", 0)

    # Still in the population, so the next run re-detects and re-notifies.
    working = FakeSender()
    active_sweep(conn, FakeClient({"gone": NotFound}), working, now=NOW, logger=LOGGER)

    assert len(working.dead_slug_calls) == 1
    assert _failures(conn, ms_id) == 5
    assert _status(conn) == ("ok", 1)


def test_several_slugs_crossing_in_one_run_share_a_single_notice():
    conn = connect(":memory:")
    first = _seed(conn, consecutive_failures=4, slug="gone-a", title="Zeta")
    second = _seed(conn, consecutive_failures=4, slug="gone-b", title="Alpha")
    sender = FakeSender()

    active_sweep(conn, FakeClient({"gone-a": NotFound, "gone-b": NotFound}), sender, now=NOW, logger=LOGGER)

    assert len(sender.dead_slug_calls) == 1  # one message, not one per manga
    assert {n.source_key for n in sender.dead_slug_calls[0]} == {"gone-a", "gone-b"}
    assert _failures(conn, first) == 5 and _failures(conn, second) == 5
    assert _status(conn) == ("ok", 1)


def test_a_mapping_already_at_the_threshold_is_silent_and_costs_no_request():
    """"Un solo aviso por manga": the notice is not repeated while the counter
    stays high, and that falls out of the population filter rather than needing
    a `notified` flag - a mapping at the threshold is never fetched again."""
    conn = connect(":memory:")
    _seed(conn, consecutive_failures=5, slug="already-dead")
    client = FakeClient({})  # any fetch would raise KeyError
    sender = FakeSender()

    active_sweep(conn, client, sender, now=NOW, logger=LOGGER)

    assert client.calls == []
    assert sender.dead_slug_calls == []
    assert _status(conn) == ("ok", 0)
