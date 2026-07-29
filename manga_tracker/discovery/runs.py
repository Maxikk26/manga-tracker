"""job_runs lifecycle: open/close a run row, the overlap guard (CD
"Solapamiento"), and notify-before-update (CD "Orden de operaciones") - a
single digest per run, mappings advance only after a successful send."""

import logging
from datetime import datetime, timezone
from typing import NamedTuple
from manga_tracker.discovery.links import resolve_link
from manga_tracker.notifier.contracts import DigestLine


class RunAlreadyOpen(Exception):
    """No new run while a prior run of the same job_name is still open."""


def open_run(conn, job_name: str, now: str) -> int:
    open_row = conn.execute(
        "SELECT id FROM job_runs WHERE job_name = ? AND finished_at IS NULL", (job_name,)
    ).fetchone()
    if open_row is not None:
        raise RunAlreadyOpen(f"{job_name} run {open_row[0]} is still open")
    run_id = conn.execute(
        "INSERT INTO job_runs (job_name, started_at, status, items_checked, updates_found, notifications_sent) "
        "VALUES (?, ?, 'ok', 0, 0, 0)",
        (job_name, now),
    ).lastrowid
    conn.commit()
    return run_id


def close_run(conn, run_id, *, status, items_checked, updates_found, notifications_sent,
              now=None, error_summary=None):
    """`now` defaults to the real closing instant, and callers should let it.

    A run threads one `now` through everything it writes, which is right for
    detected_at and last_checked_at — one run, one observation timestamp. But
    finished_at means when the run *ended*, and reusing the opening timestamp
    made every run report zero duration. That was observed live: a sweep that
    actually took 166 seconds recorded started_at and finished_at in the same
    second. job_runs is the diagnostic table, and the case it exists for is a
    sweep degrading into timeouts — up to roughly 35 minutes at 16 mappings
    with a 30s timeout plus retries. That is invisible if duration is always
    zero. Passing `now` explicitly stays available so tests can be
    deterministic.
    """
    finished_at = now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        "UPDATE job_runs SET finished_at = ?, status = ?, items_checked = ?, updates_found = ?, "
        "notifications_sent = ?, error_summary = ? WHERE id = ?",
        (finished_at, status, items_checked, updates_found, notifications_sent, error_summary, run_id),
    )
    conn.commit()


class SendOutcome(NamedTuple):
    """`sent` alone cannot express what happened: zero candidates and a failed
    send both send zero. The caller needs the difference, because CD requires a
    failed send to close the run `partial` while silence closes `ok`."""

    sent: int
    failed: bool


def _digest_url(conn, client, candidate) -> str:
    """The link the digest should point at, per BOT's hierarchy.

    Without this the digest always linked to the chapter that was just
    detected, which is the hierarchy's *last* resort. resolve_link existed and
    passed its own tests, but nothing on the production path called it - the
    unit tests exercised the function directly, so the whole feature was dead
    while the suite stayed green. `client` is passed in rather than imported:
    discovery never names a concrete source.
    """
    if client is None:
        return candidate.url
    row = conn.execute(
        "SELECT source_key FROM manga_sites WHERE id = ?", (candidate.manga_site_id,)
    ).fetchone()
    if row is None:
        return candidate.url
    return resolve_link(
        conn, client, manga_site_id=candidate.manga_site_id, source_key=row[0],
        newest_url=candidate.url, last_chapter_read=candidate.last_chapter_read,
    )


def _accumulated_count(conn, candidate) -> int:
    """Chapters registered above the reader's progress, up to and including
    the one just detected (BOT "acumulas N") - the honest number, since it
    only counts what chapter_history actually recorded. NULL progress means
    there is no accumulation to report; the formatter already omits the whole
    progress clause in that case, so the count is never rendered."""
    if candidate.last_chapter_read is None:
        return 1
    row = conn.execute(
        "SELECT COUNT(*) FROM chapter_history WHERE manga_site_id = ? AND chapter_num > ? AND chapter_num <= ?",
        (candidate.manga_site_id, candidate.last_chapter_read, candidate.chapter_num),
    ).fetchone()
    return row[0]


def send_and_advance(conn, candidates: list, sender, *, now: str, client=None) -> SendOutcome:
    """Zero candidates or a failed send: nothing advances. Success: advances
    every candidate's latest_chapter_* and reports the sent count.

    A failure is either a falsy return or a raised exception, and both are
    treated identically. Catching matters: a real Telegram client raises far
    more often than it returns False, and an escaping exception would leave the
    job_runs row open with finished_at NULL — APScheduler swallows job
    exceptions into EVENT_JOB_ERROR, so nothing downstream would close it and
    the `partial` status CD asks for would never be written.
    """
    if not candidates:
        return SendOutcome(0, failed=False)
    lines = [
        DigestLine(
            c.manga_title,
            c.chapter_num,
            _digest_url(conn, client, c),
            c.last_chapter_read,
            _accumulated_count(conn, c),
        )
        for c in candidates
    ]
    try:
        delivered = sender.send_digest(lines, now=now)
    except Exception:
        logging.getLogger(__name__).exception("digest send raised; advancing nothing")
        return SendOutcome(0, failed=True)
    if not delivered:
        return SendOutcome(0, failed=True)
    for c in candidates:
        conn.execute(
            "UPDATE manga_sites SET latest_chapter_num = ?, latest_chapter_url = ?, latest_chapter_at = ? "
            "WHERE id = ?",
            (c.chapter_num, c.url, c.published_at, c.manga_site_id),
        )
    conn.commit()
    return SendOutcome(len(candidates), failed=False)
