"""onhold_sweep - the weekly silent sweep - against a fake SourceClient and a
sender that cannot be called without failing the test. Same fake shapes as
test_active_sweep.py, deliberately: the two sweeps share a procedure and a
pre-filter, so a difference between the suites should mean a real difference in
behaviour."""

import logging

import pytest

from manga_tracker.discovery.active_sweep import DEAD_SLUG_THRESHOLD, active_sweep
from manga_tracker.discovery.onhold_sweep import onhold_sweep
from manga_tracker.sources.contracts import Chapter, NotFound, Transient, Unexpected
from manga_tracker.storage.db import connect

NOW = "2026-08-02T02:00:00Z"  # a Sunday, in UTC, as every stored timestamp is
LOGGER = logging.getLogger("test")
STORED = "2026-07-20T10:00:00Z"


class FakeClient:
    """One fixed outcome per slug: a chapters list, or an exception class to raise.

    `update_times` drives the pre-filter. `None` (the default) means the client
    cannot answer at all - the same shape as a real failure - so a test that
    says nothing about the pre-filter sweeps the whole population.
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


class ExplodingSender:
    """Every method records itself and then raises, and both halves matter.

    Raising alone would not be enough: `send_and_advance` and
    `_report_dead_slugs` both catch `Exception` around their send, so a sweep
    that started notifying would swallow the AssertionError and merely close
    `partial` - a green test for a broken guarantee. The recorded list is what
    the assertions read.
    """

    def __init__(self):
        self.calls: list[str] = []

    def send_digest(self, lines, *, now):
        self.calls.append("digest")
        raise AssertionError("onhold_sweep must never send a digest")

    def send_dead_slug_notice(self, notices, *, now):
        self.calls.append("dead_slug")
        raise AssertionError("onhold_sweep must never send a dead-slug notice")

    def send_heartbeat(self, report, *, now):
        self.calls.append("heartbeat")
        raise AssertionError("onhold_sweep must never fire the heartbeat")


class RecordingSender:
    """For the handful of assertions about the DAILY sweep in this file."""

    def __init__(self):
        self.digests: list[list] = []
        self.dead_slug_calls: list[list] = []

    def send_digest(self, lines, *, now):
        self.digests.append(list(lines))
        return True

    def send_dead_slug_notice(self, notices, *, now):
        self.dead_slug_calls.append(list(notices))
        return True


def _seed(conn, *, status="on_hold", latest=None, consecutive_failures=0, slug="op", title="OP",
          latest_at=None, last_read=None) -> int:
    """Get-or-create the site row: `sites.name` is UNIQUE, so a second call in
    the same test would otherwise fail on the insert rather than on anything
    meaningful."""
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
        "INSERT INTO bookmarks (manga_id, status, last_chapter_read, origin, created_at, updated_at) "
        "VALUES (?, ?, ?, 'seed', ?, ?)",
        (manga_id, status, last_read, NOW, NOW),
    )
    conn.commit()
    return ms_id


def _failures(conn, ms_id) -> int:
    return conn.execute("SELECT consecutive_failures FROM manga_sites WHERE id = ?", (ms_id,)).fetchone()[0]


def _latest(conn, ms_id):
    return conn.execute("SELECT latest_chapter_num FROM manga_sites WHERE id = ?", (ms_id,)).fetchone()[0]


def _run(conn, job_name="onhold_sweep"):
    return conn.execute(
        "SELECT status, items_checked, updates_found, notifications_sent FROM job_runs "
        "WHERE job_name = ? ORDER BY id DESC LIMIT 1",
        (job_name,),
    ).fetchone()


def _sweep(conn, client, sender=None):
    onhold_sweep(conn, client, sender or ExplodingSender(), now=NOW, logger=LOGGER)
    return client.calls


# --- the mechanism itself -----------------------------------------------------


def test_an_on_hold_mapping_is_swept_and_its_latest_chapter_advances_silently():
    """CD Mecanismo 3: "todas las actualizaciones son silenciosas e inmediatas".

    Immediately, not at the end of the run: unlike an active mapping there is no
    digest to succeed first, so nothing is held back.
    """
    conn = connect(":memory:")
    ms_id = _seed(conn, latest=100, slug="op", last_read=90)
    sender = ExplodingSender()

    onhold_sweep(conn, FakeClient({"op": [Chapter(101, "https://x/101", NOW)]}), sender, now=NOW, logger=LOGGER)

    assert _latest(conn, ms_id) == 101
    assert sender.calls == []
    assert _run(conn) == ("ok", 1, 1, 0)


def test_the_sender_is_never_called_even_when_there_is_something_to_report():
    """The one guarantee that separates this sweep from the daily one.

    Both mappings are four chapters behind with the reader's progress recorded,
    which is exactly the shape the digest exists to announce, and one of them is
    a paused `reading` title. That second mapping is not decoration: the shared
    rule returns None for `on_hold`, so an on-hold-only run has no candidate to
    send and would stay green even if this sweep grew a `send_and_advance` call.
    Found by injecting that call and watching this test pass - only the paused
    active mapping produces something a digest could carry.
    """
    conn = connect(":memory:")
    _seed(conn, latest=100, slug="op", last_read=97)
    _seed(conn, status="reading", latest=100, slug="paused", last_read=97, title="Paused",
          consecutive_failures=DEAD_SLUG_THRESHOLD)
    sender = ExplodingSender()
    four_more = [Chapter(104, "u4", None), Chapter(103, "u3", None), Chapter(102, "u2", None),
                 Chapter(101, "u1", None)]

    onhold_sweep(conn, FakeClient({"op": four_more, "paused": four_more}), sender, now=NOW, logger=LOGGER)

    assert sender.calls == []
    assert _run(conn)[0] == "ok"  # and not `partial`, which a swallowed send failure would give


def test_chapter_history_rows_carry_onhold_sweep():
    """Both write paths: the newest chapter goes through the shared detection
    rule, the rest are inserted by the sweep's own loop. A wrong value in either
    is dropped silently by INSERT OR IGNORE against the CHECK constraint."""
    conn = connect(":memory:")
    ms_id = _seed(conn, latest=100, slug="op")
    chapters = [Chapter(103, "u3", None), Chapter(102, "u2", None), Chapter(101, "u1", None)]

    onhold_sweep(conn, FakeClient({"op": chapters}), ExplodingSender(), now=NOW, logger=LOGGER)

    rows = conn.execute(
        "SELECT chapter_num, detected_via FROM chapter_history WHERE manga_site_id = ? ORDER BY chapter_num",
        (ms_id,),
    ).fetchall()
    assert rows == [(101, "onhold_sweep"), (102, "onhold_sweep"), (103, "onhold_sweep")]


def test_a_run_with_no_novelty_reports_zero_updates_found():
    """`updates_found` cannot be read off the return value here - the shared rule
    returns None for a silent update *and* for no novelty at all."""
    conn = connect(":memory:")
    _seed(conn, latest=100, slug="op")

    onhold_sweep(conn, FakeClient({"op": [Chapter(100, "u", None)]}), ExplodingSender(), now=NOW, logger=LOGGER)

    assert _run(conn) == ("ok", 1, 0, 0)


# --- the population ----------------------------------------------------------


def test_a_reading_mapping_is_not_in_this_population():
    conn = connect(":memory:")
    _seed(conn, status="reading", slug="active", latest=50)
    client = FakeClient({})  # no outcome registered - a request would raise KeyError

    assert _sweep(conn, client) == []
    assert _run(conn)[1] == 0  # not even examined


@pytest.mark.parametrize("failures", [DEAD_SLUG_THRESHOLD, DEAD_SLUG_THRESHOLD + 4], ids=["at", "past"])
def test_a_mapping_at_or_past_the_threshold_is_swept_here_unlike_the_daily_sweep(failures):
    """CD "Slugs muertos" step 4: paused for the daily sweep, still in the weekly
    one, which "actua como reintento de baja frecuencia".

    `reading` on purpose. A paused mapping is always `reading` or
    `want_to_read`, because those are the only states the daily sweep - and so
    the counter - ever touches. Reading the population as on-hold *only* would
    leave every paused mapping with no retry whatsoever, and would make the
    dead-slug notice's promise of a weekly retry false for every notice it can
    send.
    """
    conn = connect(":memory:")
    ms_id = _seed(conn, status="reading", slug="paused", consecutive_failures=failures)
    daily = RecordingSender()

    active_sweep(conn, FakeClient({}), daily, now=NOW, logger=LOGGER)  # would KeyError on a request
    assert _run(conn, "active_sweep")[1] == 0  # excluded from the daily sweep, as before

    assert _sweep(conn, FakeClient({"paused": [Chapter(7, "u", None)]})) == ["paused"]
    assert _failures(conn, ms_id) == 0  # answered again, so the counter resets and the daily sweep resumes


def test_a_paused_active_mapping_that_answers_again_notifies_from_the_daily_sweep_not_here():
    """The division of labour, end to end.

    This sweep asks "is the slug alive?" and nothing else: the chapter is
    recorded, the counter resets, and `latest_chapter_num` does NOT move -
    notify-before-update, so the alert is still owed. The daily sweep, which the
    reset just let the mapping back into, is the one that sends it.
    """
    conn = connect(":memory:")
    ms_id = _seed(conn, status="reading", slug="back", latest=100, last_read=100,
                  consecutive_failures=DEAD_SLUG_THRESHOLD)
    silent = ExplodingSender()

    onhold_sweep(conn, FakeClient({"back": [Chapter(101, "https://x/101", None)]}), silent, now=NOW, logger=LOGGER)

    assert silent.calls == []
    assert _failures(conn, ms_id) == 0
    assert _latest(conn, ms_id) == 100  # nothing advanced, so nothing was lost
    assert _run(conn) == ("ok", 1, 1, 0)  # counted as an update even though it was not announced

    daily = RecordingSender()
    active_sweep(conn, FakeClient({"back": [Chapter(101, "https://x/101", None)]}), daily, now=NOW, logger=LOGGER)

    assert [line.chapter_num for line in daily.digests[0]] == [101]
    assert _latest(conn, ms_id) == 101


@pytest.mark.parametrize("status", ["completed", "dropped"])
def test_a_terminal_mapping_costs_no_request_even_when_it_is_paused(status):
    """"Los terminales no consumen nada, nunca" is absolute, and the paused
    clause of this population is exactly where it could be broken by accident: a
    title dropped *because* its slug died carries a counter above the threshold
    and would otherwise be pulled straight back in."""
    conn = connect(":memory:")
    _seed(conn, status=status, slug="gone", consecutive_failures=DEAD_SLUG_THRESHOLD + 1)
    client = FakeClient({})

    assert _sweep(conn, client) == []
    assert _run(conn)[1] == 0


def test_the_population_is_the_union_and_not_either_half():
    conn = connect(":memory:")
    _seed(conn, status="on_hold", slug="paused-hold", consecutive_failures=DEAD_SLUG_THRESHOLD, title="A")
    _seed(conn, status="on_hold", slug="fresh-hold", title="B")
    _seed(conn, status="reading", slug="paused-active", consecutive_failures=DEAD_SLUG_THRESHOLD, title="C")
    _seed(conn, status="want_to_read", slug="fresh-active", title="D")
    _seed(conn, status="completed", slug="done", title="E")
    client = FakeClient({key: [Chapter(1, "u", None)]
                         for key in ("paused-hold", "fresh-hold", "paused-active")})

    assert sorted(_sweep(conn, client)) == ["fresh-hold", "paused-active", "paused-hold"]


# --- the dead-slug counter ---------------------------------------------------


@pytest.mark.parametrize(
    "outcome, before, expected",
    [
        (NotFound, 2, 3),
        (NotFound, DEAD_SLUG_THRESHOLD, DEAD_SLUG_THRESHOLD + 1),
        (Transient, 2, 2),
        (Unexpected, 2, 2),
        ([Chapter(1, "u", None)], 7, 0),
    ],
    ids=["not-found-increments", "not-found-increments-past-the-threshold",
         "transient-unchanged", "unexpected-unchanged", "success-resets"],
)
def test_the_counter_behaves_here_exactly_as_it_does_in_the_daily_sweep(outcome, before, expected):
    """Only a not-found increments, any success resets, and this sweep adds no
    threshold branch of its own: a counter is allowed past 5, because a mapping
    at 9 is as excluded from the daily sweep as one at 5 and the number is
    honest about how long the slug has been gone."""
    conn = connect(":memory:")
    ms_id = _seed(conn, consecutive_failures=before, slug="op")

    onhold_sweep(conn, FakeClient({"op": outcome}), ExplodingSender(), now=NOW, logger=LOGGER)

    assert _failures(conn, ms_id) == expected


def test_crossing_the_threshold_here_sends_no_notice_and_never_will():
    """BOT "Mensaje 3": "un solo aviso por manga". The daily sweep can guarantee
    that because its population excludes anything at the threshold; this one
    cannot, because its population deliberately *includes* them - a notice from
    here would repeat every Sunday for as long as the slug stayed dead.

    The stated cost: an `on_hold` title whose slug dies is never announced. It is
    visible in `consecutive_failures` and the log, nowhere else.
    """
    conn = connect(":memory:")
    ms_id = _seed(conn, consecutive_failures=DEAD_SLUG_THRESHOLD - 1, slug="dying")
    sender = ExplodingSender()

    onhold_sweep(conn, FakeClient({"dying": NotFound}), sender, now=NOW, logger=LOGGER)

    assert sender.calls == []
    assert _failures(conn, ms_id) == DEAD_SLUG_THRESHOLD  # advanced with no notice to wait for
    assert _run(conn) == ("ok", 1, 0, 0)


def test_an_unexpected_response_is_logged_with_the_mapping_id(caplog):
    conn = connect(":memory:")
    ms_id = _seed(conn, slug="changed")

    with caplog.at_level(logging.ERROR):
        onhold_sweep(conn, FakeClient({"changed": Unexpected}), ExplodingSender(), now=NOW, logger=LOGGER)

    assert f"manga_sites.id={ms_id}" in caplog.text


# --- the shared pre-filter, in front of this population ----------------------


def test_a_mapping_the_source_reports_unchanged_costs_no_request():
    conn = connect(":memory:")
    _seed(conn, slug="quiet", latest=50, latest_at=STORED)
    client = FakeClient({}, update_times={"quiet": "2026-07-19T09:00:00Z"})

    assert _sweep(conn, client) == []
    assert client.times_calls == 1  # asked once for the whole population, not per title


def test_a_paused_slug_the_source_no_longer_lists_is_still_requested():
    """The interaction that makes the pre-filter safe in front of THIS sweep.

    A dead slug is one the source stopped publishing, so it is absent from the
    update-time index too, and "unknown is not unchanged" then requests it. If
    that rule ever became "absent means unchanged", the weekly retry would
    silently disappear for exactly the mappings whose only retry path this is -
    and the dead-slug notice would start promising a retry that no longer
    happened.
    """
    conn = connect(":memory:")
    ms_id = _seed(conn, status="reading", slug="deleted", latest=50, latest_at=STORED,
                  consecutive_failures=DEAD_SLUG_THRESHOLD)
    # The index lists a live title and says nothing about the dead one.
    client = FakeClient({"deleted": [Chapter(51, "u", None)]},
                        update_times={"someone-else": "2026-07-19T09:00:00Z"})

    assert _sweep(conn, client) == ["deleted"]
    assert _failures(conn, ms_id) == 0


def test_an_exactly_equal_timestamp_is_unchanged_and_costs_no_request():
    """Equality is the steady state, not an edge case: a successful sweep stores
    the newest chapter's own timestamp, which is what the source keeps reporting
    until the title publishes again. Treating equal as "moved" would request the
    whole population every week and save nothing."""
    conn = connect(":memory:")
    _seed(conn, slug="steady", latest=50, latest_at=STORED)
    client = FakeClient({}, update_times={"steady": STORED})  # identical, to the second

    assert _sweep(conn, client) == []


def test_items_checked_counts_the_whole_population_not_the_requested_subset():
    conn = connect(":memory:")
    _seed(conn, slug="a", latest=50, latest_at=STORED)
    _seed(conn, slug="b", latest=50, latest_at=STORED, title="B")
    _seed(conn, slug="c", latest=50, latest_at=STORED, title="C")
    client = FakeClient({"b": [Chapter(51, "u", None)]},
                        update_times={"a": "2026-07-19T00:00:00Z",
                                      "b": "2026-07-21T00:00:00Z",
                                      "c": "2026-07-19T00:00:00Z"})

    assert _sweep(conn, client) == ["b"]
    assert _run(conn) == ("ok", 3, 1, 0)


def test_a_failing_update_index_sweeps_everything_rather_than_nothing():
    """Degrading to a full sweep costs requests; degrading to no sweep would
    cost a paused mapping its only retry, silently."""
    conn = connect(":memory:")
    _seed(conn, slug="a", latest=50, latest_at=STORED)
    _seed(conn, slug="b", latest=50, latest_at=STORED, title="B")
    client = FakeClient({"a": [Chapter(51, "u", None)], "b": [Chapter(51, "u", None)]}, times_raise=True)

    assert sorted(_sweep(conn, client)) == ["a", "b"]
    assert _run(conn)[1] == 2


def test_an_empty_population_asks_the_source_nothing_at_all():
    """Not just no chapter requests - not even the index request, which is one
    HTTP round trip against a catalogue of ~91k slugs."""
    conn = connect(":memory:")
    client = FakeClient({})

    assert _sweep(conn, client) == []
    assert client.times_calls == 0
    assert _run(conn) == ("ok", 0, 0, 0)


# --- the run row -------------------------------------------------------------


def test_a_second_run_is_refused_while_one_is_still_open(caplog):
    conn = connect(":memory:")
    _seed(conn, slug="op")
    conn.execute(
        "INSERT INTO job_runs (job_name, started_at, status, items_checked, updates_found, notifications_sent) "
        "VALUES ('onhold_sweep', ?, 'ok', 0, 0, 0)",
        (NOW,),
    )
    conn.commit()
    client = FakeClient({})  # a request would raise KeyError

    with caplog.at_level(logging.WARNING):
        onhold_sweep(conn, client, ExplodingSender(), now=NOW, logger=LOGGER)

    assert client.calls == []
    assert "onhold_sweep skipped" in caplog.text
    assert conn.execute("SELECT COUNT(*) FROM job_runs").fetchone()[0] == 1


def test_an_uncontrolled_exception_closes_the_row_as_error_and_still_surfaces():
    """A job that swallowed the bug would report `ok` having done nothing, which
    is this project's original failure mode; a job that let it escape would
    leave finished_at NULL and block every future run through the overlap
    guard."""

    class Exploding:
        def fetch_slug_update_times(self, *, progress=None):
            raise KeyboardInterrupt("killed mid-run")

    conn = connect(":memory:")
    _seed(conn, slug="op")

    with pytest.raises(KeyboardInterrupt):
        onhold_sweep(conn, Exploding(), ExplodingSender(), now=NOW, logger=LOGGER)

    row = conn.execute(
        "SELECT status, finished_at, error_summary FROM job_runs WHERE job_name = 'onhold_sweep'"
    ).fetchone()
    assert row[0] == "error"
    assert row[1] is not None
    assert "KeyboardInterrupt" in row[2]
