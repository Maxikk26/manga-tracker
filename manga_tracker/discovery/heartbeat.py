"""Weekly heartbeat: recorded spec deviation from BOT's onhold_sweep-tied
"Mensaje 2" (docs/spec-bot-telegram.md v1.1) - the deployment had zero on_hold
bookmarks when it was written, so those counts would have rendered 0 forever,
and a message that always reports zeros trains you to ignore it. What did not
come back with the Kitsu import's 72 on-hold titles is the *dependency*: this
beats on its own schedule whether or not that sweep ran, which is the whole
point of decoupling it. Reports what job_runs/bookmarks/manga_sites can actually
say: last successful detection run, tracked/behind counts, degraded runs past
week. Read-only - adds no new state; job_runs already records every run."""

from datetime import datetime, timedelta, timezone

from manga_tracker.discovery import runs
from manga_tracker.notifier.contracts import DegradedRun, HeartbeatReport

JOB_NAME = "heartbeat"
# onhold_sweep is deliberately NOT here, now that it exists. It notifies nothing,
# so a successful weekly run is no evidence that the mechanisms which do notify
# are alive - counting it would let a healthy-looking heartbeat sit on top of six
# days of dead feed and sweep runs, which is precisely the "cron comentado"
# failure this message exists to expose. BOT v1.2 leaves adding its numbers as an
# option ("pueden sumarse"), never as a substitute for these two.
DETECTION_JOBS = ("feed_check", "active_sweep")
# Reported alongside them, never counted among them. See ONHOLD_SWEEP_JOB below.
ONHOLD_SWEEP_JOB = "onhold_sweep"
# Governs both weekly aggregates below: degraded runs and detections.
WEEK_WINDOW_DAYS = 7
# How many degraded runs the message names. A bad week is dominated by one cause
# repeating - four identical DNS failures in production, August 2026 - so the
# newest few identify it, and the count line already carries the true total.
# The cap exists because Telegram truncates at 4096 characters: an unbounded
# list would let a bad week silently cut off the on-hold line under it.
DEGRADED_DETAIL_LIMIT = 5


def _last_successful_run_at(conn) -> str | None:
    row = conn.execute(
        f"SELECT started_at FROM job_runs WHERE job_name IN (?, ?) AND status = 'ok' "
        f"AND {runs.FINISHED_WITH_EVIDENCE} ORDER BY started_at DESC LIMIT 1",
        DETECTION_JOBS,
    ).fetchone()
    return row[0] if row is not None else None


def _tracked_and_behind_counts(conn) -> tuple[int, int]:
    """Tracked = non-terminal bookmarks (completed/dropped consume nothing per
    the shared detection rule, and are excluded here too). Behind = the
    source's latest known chapter is ahead of the reader's own progress."""
    row = conn.execute(
        "SELECT COUNT(*), SUM(CASE WHEN ms.latest_chapter_num IS NOT NULL AND "
        "(b.last_chapter_read IS NULL OR ms.latest_chapter_num > b.last_chapter_read) "
        "THEN 1 ELSE 0 END) FROM bookmarks b JOIN manga_sites ms ON ms.manga_id = b.manga_id "
        "WHERE b.status NOT IN ('completed', 'dropped')"
    ).fetchone()
    return row[0], row[1] or 0


def _week_cutoff(now: str) -> str:
    return (
        datetime.strptime(now, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        - timedelta(days=WEEK_WINDOW_DAYS)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")


def _degraded_run_count(conn, now: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM job_runs WHERE job_name IN (?, ?) AND status IN ('partial', 'error') "
        "AND started_at >= ?",
        (*DETECTION_JOBS, _week_cutoff(now)),
    ).fetchone()
    return row[0]


def _degraded_runs(conn, now: str) -> tuple[DegradedRun, ...]:
    """The newest degraded runs, named and dated, capped at DEGRADED_DETAIL_LIMIT.

    Deliberately a second query rather than a widening of `_degraded_run_count`:
    the count must stay uncapped so the message can say "3 of 12" honestly. A
    single capped query would have silently redefined the number the owner has
    been reading since v1.2.
    """
    rows = conn.execute(
        "SELECT job_name, started_at, status, error_summary FROM job_runs "
        "WHERE job_name IN (?, ?) AND status IN ('partial', 'error') AND started_at >= ? "
        "ORDER BY started_at DESC LIMIT ?",
        (*DETECTION_JOBS, _week_cutoff(now), DEGRADED_DETAIL_LIMIT),
    ).fetchall()
    return tuple(DegradedRun(job_name=r[0], started_at=r[1], status=r[2], error_summary=r[3]) for r in rows)


def _detections_by_job(conn, now: str) -> tuple[tuple[str, int], ...]:
    """Chapters detected per detection job over the window.

    Sums `updates_found`, which every job has written since V1a and which no
    query read until now. That is the hole: every other field in this message
    reports that runs *happened*, never that they *found* anything, so a source
    that changes shape - parsed fine, matched nothing - keeps the heartbeat
    looking healthy while detection is dead.

    Counts `partial` and `error` rows too, not just `ok`. A partial run really
    did detect something (it wrote chapter_history; only the send failed), and
    excluding it would under-report a real detection as zero - the exact
    direction of error this line exists to prevent.

    Returned in DETECTION_JOBS order with an explicit zero for a job that logged
    nothing, so a job that stops running renders `0` instead of vanishing from
    the message.
    """
    rows = dict(
        conn.execute(
            "SELECT job_name, SUM(IFNULL(updates_found, 0)) FROM job_runs "
            "WHERE job_name IN (?, ?) AND started_at >= ? GROUP BY job_name",
            (*DETECTION_JOBS, _week_cutoff(now)),
        ).fetchall()
    )
    return tuple((job, int(rows.get(job) or 0)) for job in DETECTION_JOBS)


def _last_onhold_sweep(conn) -> tuple[str | None, int, int]:
    """The last successful on-hold sweep, as (started_at, examined, silent updates).

    Its own query rather than a branch inside `_last_successful_run_at`, and the
    separation is the point: that function answers "is detection alive?", and
    this sweep cannot answer it. It notifies nothing, so a green run of it says
    only that the slug-liveness check happened.

    Read from the last `ok` run rather than summed over the week because the
    sweep is weekly: one run *is* the week, and a sum would silently double
    after any manual `run-job onhold_sweep`.
    """
    row = conn.execute(
        "SELECT started_at, IFNULL(items_checked, 0), IFNULL(updates_found, 0) FROM job_runs "
        "WHERE job_name = ? AND status = 'ok' AND finished_at IS NOT NULL "
        "ORDER BY started_at DESC LIMIT 1",
        (ONHOLD_SWEEP_JOB,),
    ).fetchone()
    return (None, 0, 0) if row is None else (row[0], row[1], row[2])


def _onhold_sweep_is_degraded(conn) -> bool:
    """Whether the *most recent* on-hold sweep - of any status - closed badly.

    The line above deliberately reports the last `ok` run, so without this the
    message would show healthy numbers from last week while every attempt since
    has failed, and say nothing. Its failures are excluded from
    `_degraded_run_count` for good reason (it notifies nothing, so its health
    proves nothing about detection) - but excluded from that number is not the
    same as reported nowhere, and until now it was reported nowhere at all.

    A separate query rather than a status column on the row above, because the
    two answer different questions: that one is "what did the last good run
    find?", this one is "is it still working?".
    """
    row = conn.execute(
        "SELECT status FROM job_runs WHERE job_name = ? AND finished_at IS NOT NULL "
        "ORDER BY started_at DESC LIMIT 1",
        (ONHOLD_SWEEP_JOB,),
    ).fetchone()
    return row is not None and row[0] != "ok"


def heartbeat(conn, client, sender, *, now: str, logger) -> None:
    """Fired weekly or via `run-job heartbeat`. `client`/`logger` unused -
    matches every other job's signature so the wrapper needs no special case."""
    tracked, behind = _tracked_and_behind_counts(conn)
    onhold_at, onhold_swept, onhold_updates = _last_onhold_sweep(conn)
    report = HeartbeatReport(
        last_successful_run_at=_last_successful_run_at(conn),
        tracked_count=tracked,
        behind_count=behind,
        degraded_run_count=_degraded_run_count(conn, now),
        detections_by_job=_detections_by_job(conn, now),
        degraded_runs=_degraded_runs(conn, now),
        onhold_sweep_at=onhold_at,
        onhold_swept_count=onhold_swept,
        onhold_updates_count=onhold_updates,
        onhold_sweep_degraded=_onhold_sweep_is_degraded(conn),
    )
    sender.send_heartbeat(report, now=now)
