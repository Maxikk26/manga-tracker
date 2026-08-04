"""active_sweep - the primary detection mechanism - and the dead-slug
counter, tested against a fake SourceClient and a fake DigestSender. No
network, no real sleeping: the 5-15s policy lives in transport.py, so a
fake client's fetch_chapters returns instantly."""

import logging

import pytest

from manga_tracker.discovery.active_sweep import active_sweep
from manga_tracker.sources.contracts import Chapter, NotFound, Transient, Unexpected
from manga_tracker.storage.db import connect

NOW = "2026-07-28T03:00:00Z"
LOGGER = logging.getLogger("test")


class FakeClient:
    """One fixed outcome per slug: a chapters list, or an exception class to raise.

    `update_times` drives the pre-filter. `None` (the default) means the client
    cannot answer at all — the same shape as a real failure — so every existing
    test keeps sweeping the whole population and asserts unchanged behaviour.
    """

    def __init__(self, outcomes: dict, *, update_times: dict | None = None, times_raise: bool = False):
        self._outcomes = outcomes
        self._update_times = update_times
        self._times_raise = times_raise
        self.calls: list[str] = []
        self.times_calls = 0

    def fetch_chapters(self, source_key, *, limit=50):
        self.calls.append(source_key)
        outcome = self._outcomes[source_key]
        if isinstance(outcome, type) and issubclass(outcome, Exception):
            raise outcome(f"{source_key} failed")
        return outcome

    def fetch_slug_update_times(self, *, progress=None):
        self.times_calls += 1
        if self._times_raise:
            raise Unexpected("the source's update-time index is unreadable")
        if self._update_times is None:
            raise Unexpected("this fake was not given update times")
        return self._update_times


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


def _seed(conn, *, status="reading", latest=None, consecutive_failures=0, slug="op", title="OP",
          latest_at=None) -> int:
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
        "latest_chapter_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (manga_id, site_id, slug, latest, consecutive_failures, latest_at, NOW, NOW),
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


# --- the sitemap-backed pre-filter -------------------------------------------
# Costs: the Kitsu import took this sweep's population from 16 mappings to 89,
# so asking the source once which titles moved replaces ~89 requests with ~10.

STORED = "2026-07-20T10:00:00Z"


def _requested(conn, client, sender=None, **kw):
    active_sweep(conn, client, sender or FakeSender(), now=NOW, logger=LOGGER, **kw)
    return client.calls


def test_a_mapping_the_source_reports_unchanged_costs_no_request():
    conn = connect(":memory:")
    _seed(conn, slug="quiet", latest=50, latest_at=STORED)
    # Older than what is stored: nothing new since the last successful check.
    client = FakeClient({}, update_times={"quiet": "2026-07-19T09:00:00Z"})

    assert _requested(conn, client) == []
    assert client.times_calls == 1  # asked once for the whole population, not per title


def test_a_mapping_the_source_reports_newer_is_requested():
    conn = connect(":memory:")
    _seed(conn, slug="moved", latest=50, latest_at=STORED)
    client = FakeClient({"moved": [Chapter(51, "u", None)]},
                        update_times={"moved": "2026-07-21T11:00:00Z"})

    assert _requested(conn, client) == ["moved"]


def test_a_mapping_with_no_stored_timestamp_is_always_requested():
    """Never successfully checked, so there is nothing to compare against."""
    conn = connect(":memory:")
    _seed(conn, slug="fresh", latest=None, latest_at=None)
    client = FakeClient({"fresh": [Chapter(1, "u", None)]},
                        update_times={"fresh": "2026-07-19T09:00:00Z"})

    assert _requested(conn, client) == ["fresh"]


def test_a_slug_the_source_does_not_list_is_requested_not_skipped():
    """Unknown is not unchanged.

    A slug missing from the index, or listed without a timestamp, would
    otherwise be skipped on every future run - silently dropping a title out of
    the only mechanism that guarantees detection.
    """
    conn = connect(":memory:")
    _seed(conn, slug="absent", latest=50, latest_at=STORED)
    _seed(conn, slug="no-stamp", latest=50, latest_at=STORED, title="Other")
    client = FakeClient({"absent": [Chapter(51, "u", None)], "no-stamp": [Chapter(51, "u", None)]},
                        update_times={"no-stamp": None})  # 'absent' not in the map at all

    assert sorted(_requested(conn, client)) == ["absent", "no-stamp"]


def test_items_checked_counts_the_whole_population_not_the_requested_subset():
    """A run that examined 3 mappings and requested 1 examined 3.

    `sweep_is_overdue` filters on `items_checked > 0`, so counting only the
    fetched subset would let a legitimate sweep look like one that swept nothing
    - the exact defect that once let an empty-database sweep satisfy the 24h
    catch-up window.
    """
    conn = connect(":memory:")
    _seed(conn, slug="a", latest=50, latest_at=STORED)
    _seed(conn, slug="b", latest=50, latest_at=STORED, title="B")
    _seed(conn, slug="c", latest=50, latest_at=STORED, title="C")
    client = FakeClient({"b": [Chapter(51, "u", None)]},
                        update_times={"a": "2026-07-19T00:00:00Z",
                                      "b": "2026-07-21T00:00:00Z",
                                      "c": "2026-07-19T00:00:00Z"})

    active_sweep(conn, client, FakeSender(), now=NOW, logger=LOGGER)

    assert client.calls == ["b"]  # only the one that moved
    row = conn.execute(
        "SELECT items_checked, status FROM job_runs WHERE job_name = 'active_sweep'"
    ).fetchone()
    assert row == (3, "ok")


def test_a_failing_update_index_sweeps_everything_rather_than_nothing():
    """The pre-filter is an optimisation; the sweep is the latency guarantee.

    Degrading to a full sweep costs requests. Degrading to no sweep would cost
    detection, silently, which is the failure mode this whole design exists to
    avoid.
    """
    conn = connect(":memory:")
    _seed(conn, slug="a", latest=50, latest_at=STORED)
    _seed(conn, slug="b", latest=50, latest_at=STORED, title="B")
    client = FakeClient({"a": [Chapter(51, "u", None)], "b": [Chapter(51, "u", None)]},
                        times_raise=True)

    active_sweep(conn, client, FakeSender(), now=NOW, logger=LOGGER)

    assert sorted(client.calls) == ["a", "b"]
    assert conn.execute(
        "SELECT items_checked FROM job_runs WHERE job_name = 'active_sweep'"
    ).fetchone()[0] == 2


def test_an_exactly_equal_timestamp_is_unchanged_and_costs_no_request():
    """Equality is the steady state, not an edge case.

    A successful sweep stores the newest chapter's own timestamp, which is
    exactly what the source reports for that title until it publishes again. So
    every unchanged mapping compares *equal*, and treating equal as "moved"
    would request the entire population on every run - the optimisation would
    cost the extra index requests and save nothing.

    Found by mutating `>` to `>=` and watching the suite stay green.
    """
    conn = connect(":memory:")
    _seed(conn, slug="steady", latest=50, latest_at=STORED)
    client = FakeClient({}, update_times={"steady": STORED})  # identical, to the second

    assert _requested(conn, client) == []
