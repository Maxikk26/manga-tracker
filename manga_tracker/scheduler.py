"""BlockingScheduler wiring (design D5) - the only module allowed to import
apscheduler (test_architecture.py CONFINEMENT_RULES). Concrete client/sender
objects are built by cli.py (the composition root) and handed in already
constructed, so this file never names sources.manganato or notifier.telegram
and needs no change to the composition-root exemption list."""

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MAX_INSTANCES, EVENT_JOB_MISSED
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
from manga_tracker.discovery.onhold_sweep import JOB_NAME as ONHOLD_SWEEP
from manga_tracker.discovery.onhold_sweep import onhold_sweep
from manga_tracker.storage.db import connect

logger = logging.getLogger(__name__)

# Re-derived worst case (design D5): a feed run waiting behind the sweep is
# correctly dropped; the sweep, the guaranteeing mechanism, is never dropped
# for a mere scheduling delay.
FEED_GRACE_SECONDS = 300
SWEEP_GRACE_SECONDS = 3600
HEARTBEAT_GRACE_SECONDS = 3600  # weekly, informational only - never detection-critical
# The on-hold sweep shares its default hour with the daily one, so it normally
# starts by waiting for it in the single-worker queue. An hour covers the worst
# realistic daily sweep (~35 minutes of timeouts) with margin; a shorter window
# would let the queueing itself misfire the weekly run, and a missed week is a
# week without the only retry a paused mapping gets.
ONHOLD_SWEEP_GRACE_SECONDS = 3600
_JOBS = {FEED_CHECK: feed_check, ACTIVE_SWEEP: active_sweep, HEARTBEAT: heartbeat,
         ONHOLD_SWEEP: onhold_sweep}


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


def _on_job_missed(event) -> None:
    """A scheduled run that never happened - and APScheduler's own answer to that
    is a debug line nobody reads.

    This is the one failure class `job_runs` cannot record. A run that fails
    leaves a row closed `error`; a run that never started leaves nothing at all,
    so the only trace is an absence in a table nobody diffs. For `active_sweep`
    that absence *is* the failure: it is the sole mechanism guaranteeing the ~24h
    detection latency, and the whole design's failure mode is a system that
    reports healthy while detecting nothing.

    A miss means the run fell outside its `misfire_grace_time` (300s for the
    feed, 3600s for either sweep) - typically because the single worker was still
    busy, or the process was down across the window. The scheduled time is logged
    because it names which window was lost.
    """
    logger.error(
        "job %s MISSED its scheduled run at %s and was never executed: the misfire grace "
        "window expired, so this run leaves no job_runs row at all", event.job_id,
        event.scheduled_run_time,
    )


def _on_job_max_instances(event) -> None:
    """A run refused because the previous one is still going (max_instances=1).

    Same consequence as a miss - no row, no execution - from the opposite cause,
    so it is logged rather than left to APScheduler's warning. For `feed_check`
    it is expected and harmless (design D5: an hourly run queued behind the daily
    sweep is correctly dropped). For a sweep it means the previous one has been
    running for over a day, which no realistic population explains.
    """
    logger.error(
        "job %s was NOT executed: its previous run is still in progress and max_instances=1 "
        "refused the overlap (scheduled for %s)", event.job_id, event.scheduled_run_times,
    )


def _scheduler_timezone(timezone_name: str) -> str:
    """The zone the cron hours are expressed in. Not optional, and not cosmetic.

    Left unset, APScheduler resolves its timezone through tzlocal; the container
    sets no TZ, so it resolved to UTC and every cron hour became a UTC hour.
    Observed in production: with ACTIVE_SWEEP_HOUR=3 the daily sweep fired at
    03:00Z, which is 23:00 in America/Caracas - four hours off the schedule the
    spec and both runbooks document, and the "Sunday early morning" heartbeat
    would have arrived on Saturday night. LOCAL_TIMEZONE reached the message
    formatter and nothing else, so the messages said the right local time about
    jobs running at the wrong one.

    An unknown zone name degrades to UTC instead of refusing to boot: a sweep at
    the wrong hour still gives the same ~24h coverage, while a process that will
    not start detects nothing at all. Unlike the old behaviour, it says so.
    """
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        logger.error(
            "LOCAL_TIMEZONE %r is not a known zone; scheduling in UTC. Cron hours "
            "will be UTC hours, not local ones - check tzdata in the image.", timezone_name
        )
        return "UTC"
    return timezone_name


def build_scheduler(*, db_path: str, site_id: int, client, sender, timezone_name: str,
                     feed_check_minutes: int = 30,
                     active_sweep_hour: int = 3, heartbeat_hour: int = 3,
                     onhold_sweep_hour: int = 3) -> BlockingScheduler:
    """max_workers=1 is set explicitly - APScheduler 3.x's ThreadPoolExecutor
    defaults to 10 (verified against the installed package), so zero
    concurrency is a configuration fact here, never an inherited default. It is
    also what makes the Sunday collision safe: three jobs share that hour by
    default and one worker turns the overlap into a queue.

    `timezone_name` has no default on purpose: it decides when everything runs,
    and the bug it fixes was precisely an implicit default nobody passed.

    It is handed to every trigger as well as to the scheduler, and that is not
    belt-and-braces. APScheduler only injects the scheduler's timezone into a
    trigger it builds itself from keyword arguments; a trigger passed in already
    constructed - as all three are here - resolved its own timezone at
    construction time through tzlocal, and keeps it. Setting it on the scheduler
    alone changes nothing at all, which is how the first attempt at this fix
    looked correct and did nothing.
    """
    tz = _scheduler_timezone(timezone_name)
    scheduler = BlockingScheduler(
        timezone=tz, executors={"default": ThreadPoolExecutor(max_workers=1)},
    )
    scheduler.add_job(
        _make_job(feed_check, FEED_CHECK, db_path, client, sender, {"site_id": site_id}),
        # Minutes, not hours: the interval has to stay under the source's feed
        # window (41 min measured) or items age off page 1 before any run sees
        # them. FEED_GRACE_SECONDS stays 300 - it is a misfire allowance, and a
        # feed run more than 5 minutes late is still correctly dropped rather
        # than piled onto the next one.
        trigger=IntervalTrigger(minutes=feed_check_minutes, timezone=tz), id=FEED_CHECK, max_instances=1,
        misfire_grace_time=FEED_GRACE_SECONDS,
    )
    scheduler.add_job(
        _make_job(active_sweep, ACTIVE_SWEEP, db_path, client, sender, {}),
        trigger=CronTrigger(hour=active_sweep_hour, minute=0, timezone=tz), id=ACTIVE_SWEEP,
        max_instances=1, misfire_grace_time=SWEEP_GRACE_SECONDS,
    )
    # Own weekly schedule, decoupled from onhold_sweep (recorded spec deviation,
    # BOT v1.2): it beats whether or not that sweep ran, and it is registered
    # here rather than fired at the end of the sweep as CD's Mecanismo 3 says.
    # day_of_week is read in this zone too: Sunday local, not Sunday UTC.
    scheduler.add_job(
        _make_job(heartbeat, HEARTBEAT, db_path, client, sender, {}),
        trigger=CronTrigger(day_of_week="sun", hour=heartbeat_hour, minute=0, timezone=tz),
        id=HEARTBEAT, max_instances=1, misfire_grace_time=HEARTBEAT_GRACE_SECONDS,
    )
    # Mecanismo 3: weekly, Sunday, same zone - so Sunday local, not Sunday UTC.
    # It never sends anything, so nothing here is detection-critical for the
    # reader's alerts; what it does own is the weekly retry of every mapping the
    # dead-slug counter paused.
    scheduler.add_job(
        _make_job(onhold_sweep, ONHOLD_SWEEP, db_path, client, sender, {}),
        trigger=CronTrigger(day_of_week="sun", hour=onhold_sweep_hour, minute=0, timezone=tz),
        id=ONHOLD_SWEEP, max_instances=1, misfire_grace_time=ONHOLD_SWEEP_GRACE_SECONDS,
    )
    # Three listeners for three ways a run can fail to produce a job_runs row.
    # The constant names are the installed package's own (APScheduler 3.11.3
    # exports EVENT_JOB_ERROR, EVENT_JOB_MISSED and EVENT_JOB_MAX_INSTANCES);
    # they are read off `apscheduler.events` rather than guessed, and the import
    # above failing is what would prove a name wrong.
    scheduler.add_listener(_on_job_error, EVENT_JOB_ERROR)
    scheduler.add_listener(_on_job_missed, EVENT_JOB_MISSED)
    scheduler.add_listener(_on_job_max_instances, EVENT_JOB_MAX_INSTANCES)
    return scheduler


SWEEP_CATCHUP_AFTER_SECONDS = 24 * 3600
# Long enough that no live run can be mistaken for a corpse. The worst realistic
# sweep is ~16 mappings x (30s timeout, two attempts, plus a 5-15s delay) - about
# 25 minutes - and `run-job` may legitimately be sweeping from a separate
# container, where max_instances is no help because it is process-local. An hour
# clears that with margin.
STALE_RUN_AFTER_SECONDS = 3600


def reap_stale_runs(db_path: str, *, max_age_seconds: int = STALE_RUN_AFTER_SECONDS) -> int:
    """Close job_runs rows left open by a process that died mid-run.

    Without this, one hard kill disables the primary detection mechanism
    permanently and silently. `open_run` refuses to start while a row for the
    same job is open, nothing closes it - SIGKILL raises no Python exception, so
    `_make_job`'s handler never runs - and `sweep_is_overdue` used to read that
    same row as a completed sweep. The result was a system reporting `ok` and
    detecting nothing, which is this project's original failure mode.

    Reproduced during the first deploy: `docker compose restart` allows 10s
    before SIGKILL and a sweep takes about 150s, so any restart during a sweep
    triggered it.

    Closed as `error`, not `partial`: `partial` means the run finished and
    something inside it failed, while these never finished at all. The row also
    fails `sweep_is_overdue`'s items_checked filter, so a reaped run correctly
    leaves the sweep owed.
    """
    now = datetime.now(timezone.utc)
    conn = connect(db_path)
    try:
        open_rows = conn.execute(
            "SELECT id, job_name, started_at FROM job_runs WHERE finished_at IS NULL"
        ).fetchall()
        reaped = 0
        for run_id, job_name, started_at in open_rows:
            started = datetime.strptime(started_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            age = (now - started).total_seconds()
            if age <= max_age_seconds:
                continue  # may still be running, in this process or another container
            conn.execute(
                "UPDATE job_runs SET finished_at = ?, status = 'error', error_summary = ? WHERE id = ?",
                (now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                 f"reaped at startup: left open {age / 3600:.1f}h, process died before closing it", run_id),
            )
            logger.error(
                "reaped stale %s run %s left open since %s (%.1fh) - it would otherwise have blocked "
                "every future run of that job", job_name, run_id, started_at, age / 3600,
            )
            reaped += 1
        conn.commit()
        return reaped
    finally:
        conn.close()


def sweep_is_overdue(conn, *, max_age_seconds: int = SWEEP_CATCHUP_AFTER_SECONDS) -> bool:
    """True when the last active_sweep that actually swept is older than its interval.

    The jobstore is in memory, so a restart forgets any window it missed: a
    container coming back at 04:00 with the sweep scheduled at 03:00 gets no
    sweep until 03:00 the next day, stretching the worst-case detection latency
    from ~24h to ~47h. The documented mitigation was a human remembering to run
    `run-job active_sweep`, which is a poor guarantee for the mechanism the
    whole design leans on.

    No persistent jobstore is needed to fix it: job_runs already records what
    ran and when, which is exactly what that table exists for. Reading it back
    at startup costs one query.

    The two extra conditions are not defensive padding — both were observed
    suppressing a real catch-up on the first server, and `status IN ('ok',
    'partial')` alone matches rows that did not sweep anything:

    - `finished_at IS NOT NULL`. `open_run` inserts the row with status 'ok'
      already set and finished_at NULL, so a run merely *in flight* matched, and
      so did one whose process was killed mid-sweep. That is the worse case: the
      row stays open forever, and every later sweep is then refused by
      open_run's overlap guard while this query keeps reporting the sweep as
      satisfied. Only a finished run is evidence of a sweep.

    - `items_checked > 0`. A sweep over an empty database completes correctly
      and closes 'ok' having examined nothing. It then satisfied this window for
      24h, which is exactly what happened at bring-up: the container came up
      before the seed, swept zero titles in under a second, and the sweep that
      should have followed the seed never ran. Zero items examined is not a
      sweep, whatever its status says.
    """
    row = conn.execute(
        "SELECT started_at FROM job_runs WHERE job_name = ? AND status IN ('ok', 'partial') "
        "AND finished_at IS NOT NULL AND IFNULL(items_checked, 0) > 0 "
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
