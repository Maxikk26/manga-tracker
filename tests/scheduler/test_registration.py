"""scheduler.py: registration (trigger types, ids, explicit max_workers) and
the job wrapper's error handling. No real scheduler is ever started (design
D5) - `build_scheduler` only constructs and registers, never `.start()`s."""

import logging

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from manga_tracker.discovery.active_sweep import JOB_NAME as ACTIVE_SWEEP
from manga_tracker.discovery.feed_check import JOB_NAME as FEED_CHECK
from manga_tracker.scheduler import _make_job, build_scheduler, run_job_once
from manga_tracker.storage.db import connect


def _scheduler():
    return build_scheduler(db_path=":memory:", site_id=1, client=object(), sender=object())


def test_executor_max_workers_is_explicit_not_the_apscheduler_default():
    # APScheduler's own ThreadPoolExecutor defaults to 10 (verified against the
    # installed package's __init__ signature) - this proves the config says 1.
    assert _scheduler()._executors["default"]._pool._max_workers == 1


def test_both_jobs_registered_with_expected_trigger_types_and_grace():
    jobs = {job.id: job for job in _scheduler().get_jobs()}
    assert set(jobs) == {FEED_CHECK, ACTIVE_SWEEP}
    assert isinstance(jobs[FEED_CHECK].trigger, IntervalTrigger)
    assert isinstance(jobs[ACTIVE_SWEEP].trigger, CronTrigger)
    assert jobs[FEED_CHECK].max_instances == 1 and jobs[ACTIVE_SWEEP].max_instances == 1
    assert jobs[FEED_CHECK].misfire_grace_time == 300
    assert jobs[ACTIVE_SWEEP].misfire_grace_time == 3600


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

    conn = connect(":memory:")
    assert sweep_is_overdue(conn) is True  # never swept: nothing is armed yet

    conn.execute(
        "INSERT INTO job_runs (job_name, started_at, status) VALUES (?, ?, 'ok')",
        (SWEEP, stamp(timedelta(hours=-2))),
    )
    conn.commit()
    assert sweep_is_overdue(conn) is False  # swept two hours ago: nothing owed

    conn.execute(
        "INSERT INTO job_runs (job_name, started_at, status) VALUES (?, ?, 'ok')",
        (SWEEP, stamp(timedelta(hours=-30))),
    )
    conn.execute("DELETE FROM job_runs WHERE started_at = ?", (stamp(timedelta(hours=-2)),))
    conn.commit()
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
