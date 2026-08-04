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

from manga_tracker.notifier.contracts import HeartbeatReport

JOB_NAME = "heartbeat"
# onhold_sweep is deliberately NOT here, now that it exists. It notifies nothing,
# so a successful weekly run is no evidence that the mechanisms which do notify
# are alive - counting it would let a healthy-looking heartbeat sit on top of six
# days of dead feed and sweep runs, which is precisely the "cron comentado"
# failure this message exists to expose. BOT v1.2 leaves adding its numbers as an
# option ("pueden sumarse"), never as a substitute for these two.
DETECTION_JOBS = ("feed_check", "active_sweep")
DEGRADED_WINDOW_DAYS = 7


def _last_successful_run_at(conn) -> str | None:
    row = conn.execute(
        "SELECT started_at FROM job_runs WHERE job_name IN (?, ?) AND status = 'ok' "
        "ORDER BY started_at DESC LIMIT 1",
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


def _degraded_run_count(conn, now: str) -> int:
    cutoff = (
        datetime.strptime(now, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        - timedelta(days=DEGRADED_WINDOW_DAYS)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    row = conn.execute(
        "SELECT COUNT(*) FROM job_runs WHERE job_name IN (?, ?) AND status IN ('partial', 'error') "
        "AND started_at >= ?",
        (*DETECTION_JOBS, cutoff),
    ).fetchone()
    return row[0]


def heartbeat(conn, client, sender, *, now: str, logger) -> None:
    """Fired weekly or via `run-job heartbeat`. `client`/`logger` unused -
    matches every other job's signature so the wrapper needs no special case."""
    tracked, behind = _tracked_and_behind_counts(conn)
    report = HeartbeatReport(
        last_successful_run_at=_last_successful_run_at(conn),
        tracked_count=tracked,
        behind_count=behind,
        degraded_run_count=_degraded_run_count(conn, now),
    )
    sender.send_heartbeat(report, now=now)
