"""BlockingScheduler wiring (design D5) - the only module allowed to import
apscheduler (test_architecture.py CONFINEMENT_RULES). Concrete client/sender
objects are built by cli.py (the composition root) and handed in already
constructed, so this file never names sources.manganato or notifier.telegram
and needs no change to the composition-root exemption list."""

import logging
from datetime import datetime, timezone

from apscheduler.events import EVENT_JOB_ERROR
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from manga_tracker.discovery.active_sweep import JOB_NAME as ACTIVE_SWEEP
from manga_tracker.discovery.active_sweep import active_sweep
from manga_tracker.discovery.feed_check import JOB_NAME as FEED_CHECK
from manga_tracker.discovery.feed_check import feed_check
from manga_tracker.discovery.heartbeat import JOB_NAME as HEARTBEAT
from manga_tracker.discovery.heartbeat import heartbeat
from manga_tracker.storage.db import connect

logger = logging.getLogger(__name__)

# Re-derived worst case (design D5): a feed run waiting behind the sweep is
# correctly dropped; the sweep, the guaranteeing mechanism, is never dropped
# for a mere scheduling delay.
FEED_GRACE_SECONDS = 300
SWEEP_GRACE_SECONDS = 3600
HEARTBEAT_GRACE_SECONDS = 3600  # weekly, informational only - never detection-critical
_JOBS = {FEED_CHECK: feed_check, ACTIVE_SWEEP: active_sweep, HEARTBEAT: heartbeat}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _close_if_still_open(conn, job_name: str, now: str, error_summary: str) -> None:
    """Safety net only: feed_check/active_sweep already close their own
    job_runs row on an internal exception. This covers a failure the job body
    never got a chance to handle itself, e.g. a bug before its own try/except."""
    row = conn.execute(
        "SELECT id FROM job_runs WHERE job_name = ? AND finished_at IS NULL", (job_name,)
    ).fetchone()
    if row is not None:
        conn.execute(
            "UPDATE job_runs SET finished_at = ?, status = 'error', error_summary = ? WHERE id = ?",
            (now, error_summary[:200], row[0]),
        )
        conn.commit()


def _make_job(job_fn, job_name: str, db_path: str, client, sender, extra: dict):
    """One sqlite3 connection per run, opened here on the worker thread the
    executor actually runs jobs on: sqlite3 defaults to check_same_thread=True
    and BlockingScheduler holds the main thread, so a connection built anywhere
    else would be used from the wrong thread. APScheduler swallows an escaping
    job exception into EVENT_JOB_ERROR before it reaches BlockingScheduler -
    the 2025 attempt's exact cause of death - so this always logs first and
    never lets the exception vanish silently."""

    def _run() -> None:
        now = _utc_now()
        conn = connect(db_path)
        try:
            job_fn(conn, client, sender, now=now, logger=logger, **extra)
        except Exception as exc:
            logger.exception("%s failed", job_name)
            _close_if_still_open(conn, job_name, now, f"{type(exc).__name__}: {exc}")
        finally:
            conn.close()

    return _run


def _on_job_error(event) -> None:
    """Backstop only: fires if something escaped _make_job's own try/except
    (e.g. connect() itself raising, before any job_runs row could exist)."""
    logger.error("unhandled scheduler error for job %s", event.job_id)


def build_scheduler(*, db_path: str, site_id: int, client, sender, active_sweep_hour: int = 3,
                     heartbeat_hour: int = 3) -> BlockingScheduler:
    """max_workers=1 is set explicitly - APScheduler 3.x's ThreadPoolExecutor
    defaults to 10 (verified against the installed package), so zero
    concurrency is a configuration fact here, never an inherited default."""
    scheduler = BlockingScheduler(executors={"default": ThreadPoolExecutor(max_workers=1)})
    scheduler.add_job(
        _make_job(feed_check, FEED_CHECK, db_path, client, sender, {"site_id": site_id}),
        trigger=IntervalTrigger(hours=1), id=FEED_CHECK, max_instances=1,
        misfire_grace_time=FEED_GRACE_SECONDS,
    )
    scheduler.add_job(
        _make_job(active_sweep, ACTIVE_SWEEP, db_path, client, sender, {}),
        trigger=CronTrigger(hour=active_sweep_hour, minute=0), id=ACTIVE_SWEEP, max_instances=1,
        misfire_grace_time=SWEEP_GRACE_SECONDS,
    )
    # Own weekly schedule, decoupled from onhold_sweep (recorded spec deviation).
    scheduler.add_job(
        _make_job(heartbeat, HEARTBEAT, db_path, client, sender, {}),
        trigger=CronTrigger(day_of_week="sun", hour=heartbeat_hour, minute=0), id=HEARTBEAT, max_instances=1,
        misfire_grace_time=HEARTBEAT_GRACE_SECONDS,
    )
    scheduler.add_listener(_on_job_error, EVENT_JOB_ERROR)
    return scheduler


SWEEP_CATCHUP_AFTER_SECONDS = 24 * 3600


def sweep_is_overdue(conn, *, max_age_seconds: int = SWEEP_CATCHUP_AFTER_SECONDS) -> bool:
    """True when the last successful active_sweep is older than its interval.

    The jobstore is in memory, so a restart forgets any window it missed: a
    container coming back at 04:00 with the sweep scheduled at 03:00 gets no
    sweep until 03:00 the next day, stretching the worst-case detection latency
    from ~24h to ~47h. The documented mitigation was a human remembering to run
    `run-job active_sweep`, which is a poor guarantee for the mechanism the
    whole design leans on.

    No persistent jobstore is needed to fix it: job_runs already records what
    ran and when, which is exactly what that table exists for. Reading it back
    at startup costs one query.
    """
    row = conn.execute(
        "SELECT started_at FROM job_runs WHERE job_name = ? AND status IN ('ok', 'partial') "
        "ORDER BY started_at DESC LIMIT 1",
        (ACTIVE_SWEEP,),
    ).fetchone()
    if row is None:
        return True  # never swept: the seed alone leaves nothing armed
    last = datetime.strptime(row[0], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - last).total_seconds() > max_age_seconds


def catch_up_sweep_if_overdue(*, db_path: str, client, sender) -> bool:
    """Run one active_sweep at startup when the last one is overdue.

    This is not the startup message the bot spec forbids — that rule is about a
    greeting or liveness ping. A sweep that finds real chapters and reports them
    is the product working, and staying silent when there is nothing new is the
    normal outcome either way.
    """
    conn = connect(db_path)
    try:
        overdue = sweep_is_overdue(conn)
    finally:
        conn.close()
    if not overdue:
        return False
    logger.info("active_sweep is overdue; running one now before scheduling")
    _make_job(active_sweep, ACTIVE_SWEEP, db_path, client, sender, {})()
    return True


def run_job_once(job_name: str, *, db_path: str, site_id: int, client, sender) -> None:
    """`run-job`: run one job body directly, no scheduler involved - covers
    bring-up, where waiting an hour for a real feed tick is not workable.

    Unguarded against a concurrently scheduled sweep: max_instances=1 is
    process-local, so `run-job active_sweep` against an already-running
    scheduler process can overlap it and issue concurrent requests. Accepted
    at one operator - a database-level guard would deadlock the job
    permanently after any crash that leaves a job_runs row open (design D5)."""
    if job_name not in _JOBS:
        raise ValueError(f"unknown job {job_name!r}; choose one of {sorted(_JOBS)}")
    extra = {"site_id": site_id} if job_name == FEED_CHECK else {}
    _make_job(_JOBS[job_name], job_name, db_path, client, sender, extra)()
