"""scheduler.py: registration (trigger types, ids, explicit max_workers) and
the job wrapper's error handling. No real scheduler is ever started (design
D5) - `build_scheduler` only constructs and registers, never `.start()`s."""

import logging

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from manga_tracker.discovery.active_sweep import JOB_NAME as ACTIVE_SWEEP
from manga_tracker.discovery.feed_check import JOB_NAME as FEED_CHECK
from manga_tracker.discovery.heartbeat import JOB_NAME as HEARTBEAT
from manga_tracker.discovery.onhold_sweep import JOB_NAME as ONHOLD_SWEEP
from manga_tracker.scheduler import (
    HEARTBEAT_GRACE_SECONDS,
    ONHOLD_SWEEP_GRACE_SECONDS,
    _make_job,
    build_scheduler,
    run_job_once,
)
from manga_tracker.storage.db import connect


def _scheduler(**overrides):
    kwargs = dict(db_path=":memory:", site_id=1, client=object(), sender=object(),
                  timezone_name="America/Caracas")
    return build_scheduler(**{**kwargs, **overrides})


def test_cron_hours_are_local_hours_not_utc():
    """ACTIVE_SWEEP_HOUR=3 means 03:00 in the configured zone, not 03:00 UTC.

    It used to mean 03:00 UTC. build_scheduler constructed BlockingScheduler
    without a timezone, APScheduler resolved one through tzlocal, and the
    container sets no TZ - so every cron hour silently became a UTC hour. In
    production the daily sweep ran at 23:00 local and the Sunday heartbeat would
    have landed Saturday night. LOCAL_TIMEZONE was reaching the message
    formatter and nothing else, so the messages reported the right local time
    about jobs firing at the wrong one.

    The zone asserted here is deliberately NOT the production one. A first pass
    of this test used America/Caracas and passed against a build_scheduler that
    only set the timezone on the scheduler - which does nothing for triggers
    passed in already constructed. It passed because the developer machine's
    tzlocal *is* America/Caracas, so the ambient default happened to match the
    expectation, and it would have failed in the container. Asia/Tokyo cannot be
    supplied by accident, so the assertion measures the plumbing.
    """
    from datetime import datetime
    from datetime import timezone as dt_timezone
    from zoneinfo import ZoneInfo

    tokyo = ZoneInfo("Asia/Tokyo")  # UTC+9: 03:00 local is 18:00 UTC the day before
    noon_utc = datetime(2026, 7, 30, 12, 0, tzinfo=dt_timezone.utc)
    jobs = {job.id: job
            for job in _scheduler(timezone_name="Asia/Tokyo", active_sweep_hour=3, heartbeat_hour=3,
                                  onhold_sweep_hour=3).get_jobs()}

    for job_id in (ACTIVE_SWEEP, HEARTBEAT, ONHOLD_SWEEP):
        trigger = jobs[job_id].trigger
        assert str(trigger.timezone) == "Asia/Tokyo"
        fires_at = trigger.get_next_fire_time(None, noon_utc)
        assert fires_at.astimezone(tokyo).hour == 3
        assert fires_at.astimezone(dt_timezone.utc).hour == 18  # the bug put a 3 here

    # Both weekly jobs read their weekday in that zone too: Sunday local, not Sunday UTC.
    for job_id in (HEARTBEAT, ONHOLD_SWEEP):
        assert jobs[job_id].trigger.get_next_fire_time(None, noon_utc).astimezone(tokyo).weekday() == 6

    # And the production configuration: 03:00 America/Caracas is 07:00 UTC.
    caracas_sweep = {job.id: job for job in _scheduler(active_sweep_hour=3).get_jobs()}[ACTIVE_SWEEP]
    assert caracas_sweep.trigger.get_next_fire_time(None, noon_utc).astimezone(dt_timezone.utc).hour == 7


def test_an_unknown_timezone_degrades_to_utc_instead_of_refusing_to_boot(caplog):
    """A sweep at the wrong hour still covers ~24h; a process that will not start
    covers nothing. Unlike the old implicit UTC, this one is logged."""
    with caplog.at_level(logging.ERROR):
        jobs = {job.id: job for job in _scheduler(timezone_name="Not/AZone").get_jobs()}
    assert str(jobs[ACTIVE_SWEEP].trigger.timezone) == "UTC"
    assert "Not/AZone" in caplog.text


def test_executor_max_workers_is_explicit_not_the_apscheduler_default():
    # APScheduler's own ThreadPoolExecutor defaults to 10 (verified against the
    # installed package's __init__ signature) - this proves the config says 1.
    assert _scheduler()._executors["default"]._pool._max_workers == 1


def test_every_job_registered_with_expected_trigger_types_and_grace():
    jobs = {job.id: job for job in _scheduler().get_jobs()}
    assert set(jobs) == {FEED_CHECK, ACTIVE_SWEEP, HEARTBEAT, ONHOLD_SWEEP}
    assert isinstance(jobs[FEED_CHECK].trigger, IntervalTrigger)
    assert isinstance(jobs[ACTIVE_SWEEP].trigger, CronTrigger)
    assert jobs[FEED_CHECK].max_instances == 1 and jobs[ACTIVE_SWEEP].max_instances == 1
    assert jobs[FEED_CHECK].misfire_grace_time == 300
    assert jobs[ACTIVE_SWEEP].misfire_grace_time == 3600


def test_onhold_sweep_registered_weekly_on_its_own_configurable_hour():
    """CD Mecanismo 3: weekly, Sunday, configurable hour.

    The hour is asserted against a value passed in, not against the default: in
    production it arrives from `ONHOLD_SWEEP_HOUR`, which defaults to the daily
    sweep's hour in `config.py` (tested there). The grace window has to outlast
    the queueing that default causes - all three cron jobs then fire in the same
    minute and max_workers=1 makes that a queue - or it would misfire the very
    run it protects.
    """
    jobs = {job.id: job for job in _scheduler(onhold_sweep_hour=22).get_jobs()}
    trigger = jobs[ONHOLD_SWEEP].trigger
    assert isinstance(trigger, CronTrigger)
    assert str(next(f for f in trigger.fields if f.name == "day_of_week")) == "sun"
    assert str(next(f for f in trigger.fields if f.name == "hour")) == "22"
    assert jobs[ONHOLD_SWEEP].max_instances == 1
    assert jobs[ONHOLD_SWEEP].misfire_grace_time == ONHOLD_SWEEP_GRACE_SECONDS
    assert ONHOLD_SWEEP_GRACE_SECONDS >= 3600  # the worst realistic daily sweep is ~35 minutes


def test_run_job_once_dispatches_the_onhold_sweep(tmp_path):
    """`run-job onhold_sweep`: waiting until Sunday to see a weekly job work is
    not workable, and it is also how a paused mapping gets retried on demand."""
    db_path = str(tmp_path / "onhold.db")

    class FakeClient:
        def fetch_slug_update_times(self, *, progress=None):
            raise AssertionError("an empty population must not cost even the index request")

    run_job_once(ONHOLD_SWEEP, db_path=db_path, site_id=1, client=FakeClient(), sender=object())

    rows = connect(db_path).execute("SELECT job_name, status FROM job_runs").fetchall()
    assert rows == [(ONHOLD_SWEEP, "ok")]


def test_heartbeat_registered_weekly_with_expected_id():
    """Own weekly schedule, decoupled from onhold_sweep (recorded spec
    deviation): Sunday, id 'heartbeat', its own grace window."""
    jobs = {job.id: job for job in _scheduler().get_jobs()}
    trigger = jobs[HEARTBEAT].trigger
    assert isinstance(trigger, CronTrigger)
    assert str(next(f for f in trigger.fields if f.name == "day_of_week")) == "sun"
    assert jobs[HEARTBEAT].max_instances == 1
    assert jobs[HEARTBEAT].misfire_grace_time == HEARTBEAT_GRACE_SECONDS


def test_run_job_once_dispatches_heartbeat(tmp_path):
    """`run-job heartbeat`: fired on demand, same dispatch path as the
    detection jobs - waiting a week to see the message render is not workable."""

    class FakeSender:
        def __init__(self):
            self.called = False

        def send_heartbeat(self, report, *, now):
            self.called = True
            return True

    sender = FakeSender()
    run_job_once(HEARTBEAT, db_path=str(tmp_path / "heartbeat.db"), site_id=1, client=None, sender=sender)
    assert sender.called is True


def test_run_job_once_dispatches_exactly_one_job(tmp_path):
    db_path = str(tmp_path / "run_job.db")

    class FakeClient:
        def fetch_latest_feed(self):
            return []

    class FakeSender:
        def send_digest(self, lines, *, now):
            return True

    run_job_once(FEED_CHECK, db_path=db_path, site_id=1, client=FakeClient(), sender=FakeSender())

    rows = connect(db_path).execute("SELECT job_name FROM job_runs").fetchall()
    assert [row[0] for row in rows] == [FEED_CHECK]  # only the requested job ran, never both


def test_job_wrapper_closes_the_run_row_and_logs_when_the_job_body_raises(tmp_path, caplog):
    db_path = str(tmp_path / "wrapper.db")

    def _raising_job(conn, client, sender, *, now, logger, **extra):
        # Mirrors what feed_check/active_sweep do before their own try/except
        # would normally close this row - proves the wrapper is a real safety
        # net, not just trusting the job body.
        conn.execute(
            "INSERT INTO job_runs (job_name, started_at, status, items_checked, updates_found, "
            "notifications_sent) VALUES (?, ?, 'ok', 0, 0, 0)",
            (FEED_CHECK, now),
        )
        conn.commit()
        raise RuntimeError("boom")

    job = _make_job(_raising_job, FEED_CHECK, db_path, client=None, sender=None, extra={})
    with caplog.at_level(logging.ERROR):
        job()  # must not raise - APScheduler must never see this exception escape

    row = connect(db_path).execute(
        "SELECT status, finished_at FROM job_runs WHERE job_name = ?", (FEED_CHECK,)
    ).fetchone()
    assert row[0] == "error"
    assert row[1] is not None  # finished_at is set - never left NULL
    assert "feed_check failed" in caplog.text


def test_sweep_is_overdue_reads_job_runs_rather_than_a_persistent_jobstore():
    """The in-memory jobstore forgets a missed window; job_runs does not.

    A restart outside the scheduled hour used to mean no sweep until the next
    day, stretching worst-case latency from ~24h to ~47h, mitigated only by a
    human remembering a command. These assertions pin the replacement.
    """
    from datetime import datetime, timedelta, timezone

    from manga_tracker.discovery.active_sweep import JOB_NAME as SWEEP
    from manga_tracker.scheduler import sweep_is_overdue
    from manga_tracker.storage.db import connect

    def stamp(delta):
        return (datetime.now(timezone.utc) + delta).strftime("%Y-%m-%dT%H:%M:%SZ")

    def insert_completed_sweep(hours_ago, items=16):
        """A row that looks like what close_run actually writes.

        The earlier version of this test inserted only (job_name, started_at,
        status), leaving finished_at NULL and items_checked NULL - a shape no
        completed sweep ever has. It passed, and in doing so hid two ways the
        query matched runs that swept nothing. Build rows the real code builds.
        """
        conn.execute(
            "INSERT INTO job_runs (job_name, started_at, finished_at, status, items_checked, "
            "updates_found, notifications_sent) VALUES (?, ?, ?, 'ok', ?, 0, 0)",
            (SWEEP, stamp(timedelta(hours=-hours_ago)), stamp(timedelta(hours=-hours_ago, minutes=3)), items),
        )
        conn.commit()

    conn = connect(":memory:")
    assert sweep_is_overdue(conn) is True  # never swept: nothing is armed yet

    insert_completed_sweep(hours_ago=2)
    assert sweep_is_overdue(conn) is False  # swept two hours ago: nothing owed

    conn.execute("DELETE FROM job_runs")
    insert_completed_sweep(hours_ago=30)
    assert sweep_is_overdue(conn) is True  # last success is older than a day


def test_a_failed_sweep_does_not_count_as_having_run():
    """`error` means the run aborted, so it leaves the sweep still owed."""
    from datetime import datetime, timedelta, timezone

    from manga_tracker.discovery.active_sweep import JOB_NAME as SWEEP
    from manga_tracker.scheduler import sweep_is_overdue
    from manga_tracker.storage.db import connect

    conn = connect(":memory:")
    conn.execute(
        "INSERT INTO job_runs (job_name, started_at, status) VALUES (?, ?, 'error')",
        (SWEEP, (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")),
    )
    conn.commit()
    assert sweep_is_overdue(conn) is True


def test_a_sweep_that_examined_nothing_does_not_satisfy_the_catch_up_window():
    """Observed on the first server, and it silenced the mechanism for a day.

    The container came up before the seed had run. Its catch-up swept an empty
    database, examined zero titles, finished in under a second and closed 'ok'.
    Sixteen titles were then loaded - and because that empty run looked like a
    successful sweep, neither the following restart nor a recreate ran one. The
    16 titles sat unswept until the next 03:00 cron.
    """
    from datetime import datetime, timedelta, timezone

    from manga_tracker.discovery.active_sweep import JOB_NAME as SWEEP
    from manga_tracker.scheduler import sweep_is_overdue
    from manga_tracker.storage.db import connect

    now = datetime.now(timezone.utc)

    def stamp(minutes):
        return (now + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")

    conn = connect(":memory:")
    conn.execute(
        "INSERT INTO job_runs (job_name, started_at, finished_at, status, items_checked, "
        "updates_found, notifications_sent) VALUES (?, ?, ?, 'ok', 0, 0, 0)",
        (SWEEP, stamp(-40), stamp(-40)),
    )
    conn.commit()
    assert sweep_is_overdue(conn) is True

    # One real sweep, and the window is genuinely satisfied.
    conn.execute(
        "INSERT INTO job_runs (job_name, started_at, finished_at, status, items_checked, "
        "updates_found, notifications_sent) VALUES (?, ?, ?, 'ok', 16, 0, 0)",
        (SWEEP, stamp(-10), stamp(-7)),
    )
    conn.commit()
    assert sweep_is_overdue(conn) is False


def test_an_unfinished_sweep_does_not_satisfy_the_catch_up_window():
    """open_run writes status 'ok' up front, so an OPEN row already reads as a
    success to any query that does not check finished_at.

    Two consequences, and the second is the dangerous one. A run merely in
    flight suppressed the catch-up - harmless, it is running. But a run whose
    process was killed mid-sweep leaves that row open permanently: open_run's
    overlap guard then refuses every future active_sweep with RunAlreadyOpen
    while this query keeps reporting the sweep as satisfied, so the primary
    detection mechanism dies silently and nothing ever says so. Reproduced by
    killing a `run-job active_sweep` container mid-run on the real server.
    """
    from datetime import datetime, timedelta, timezone

    from manga_tracker.discovery.active_sweep import JOB_NAME as SWEEP
    from manga_tracker.discovery.runs import RunAlreadyOpen, open_run
    from manga_tracker.scheduler import sweep_is_overdue
    from manga_tracker.storage.db import connect

    started = (datetime.now(timezone.utc) - timedelta(minutes=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = connect(":memory:")
    run_id = open_run(conn, SWEEP, started)

    row = conn.execute("SELECT status, finished_at FROM job_runs WHERE id = ?", (run_id,)).fetchone()
    assert row == ("ok", None)  # the shape that used to read as a completed sweep

    assert sweep_is_overdue(conn) is True

    # And this is why it matters: while that row is open, no sweep can start.
    try:
        open_run(conn, SWEEP, started)
    except RunAlreadyOpen:
        pass
    else:
        raise AssertionError("expected the overlap guard to refuse a second run")


def test_reaping_releases_a_run_row_left_open_by_a_dead_process(tmp_path, caplog):
    """One hard kill used to disable active_sweep permanently and silently.

    `open_run` refuses to start while a row for the same job is open, and nothing
    closed it: SIGKILL raises no Python exception, so `_make_job`'s handler never
    runs. The result was a system reporting `ok` and detecting nothing. Observed
    for real - `docker compose restart` allows 10s before SIGKILL and a sweep
    takes about 150s.
    """
    from datetime import datetime, timedelta, timezone

    from manga_tracker.discovery.active_sweep import JOB_NAME as SWEEP
    from manga_tracker.discovery.runs import RunAlreadyOpen, open_run
    from manga_tracker.scheduler import reap_stale_runs
    from manga_tracker.storage.db import connect

    db_path = str(tmp_path / "reap.db")
    conn = connect(db_path)

    def stamp(hours):
        return (datetime.now(timezone.utc) + timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")

    orphan = open_run(conn, SWEEP, stamp(-3))
    conn.close()

    with caplog.at_level(logging.ERROR):
        assert reap_stale_runs(db_path) == 1
    assert "would otherwise have blocked" in caplog.text

    conn = connect(db_path)
    row = conn.execute("SELECT status, finished_at, error_summary FROM job_runs WHERE id = ?", (orphan,)).fetchone()
    assert row[0] == "error"          # never finished, so not `partial`
    assert row[1] is not None
    assert "reaped at startup" in row[2]

    # The point of reaping: the job can run again.
    open_run(conn, SWEEP, stamp(0))

    # And a reaped run leaves the sweep owed, rather than counting as one.
    from manga_tracker.scheduler import sweep_is_overdue
    assert sweep_is_overdue(conn) is True

    # A second open row exists now; prove the guard is still doing its job.
    try:
        open_run(conn, SWEEP, stamp(0))
    except RunAlreadyOpen:
        pass
    else:
        raise AssertionError("expected the overlap guard to still refuse a concurrent run")


def test_reaping_leaves_a_run_that_may_still_be_alive_alone(tmp_path):
    """The threshold is not arbitrary. `run-job` can be sweeping from a separate
    container, where max_instances is no help because it is process-local, and a
    real sweep takes minutes. Reaping a live run would close the row underneath
    it and let a second one start concurrently - the opposite of the guard."""
    from datetime import datetime, timedelta, timezone

    from manga_tracker.discovery.active_sweep import JOB_NAME as SWEEP
    from manga_tracker.discovery.runs import open_run
    from manga_tracker.scheduler import reap_stale_runs
    from manga_tracker.storage.db import connect

    db_path = str(tmp_path / "alive.db")
    conn = connect(db_path)
    open_run(conn, SWEEP, (datetime.now(timezone.utc) - timedelta(minutes=4)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    conn.close()

    assert reap_stale_runs(db_path) == 0
    assert connect(db_path).execute(
        "SELECT finished_at FROM job_runs WHERE id = 1"
    ).fetchone()[0] is None
