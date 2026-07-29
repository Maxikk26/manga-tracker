"""Mecanismo 1 (CD "Mecanismo 1: feed"): the opportunistic, hourly detection
mechanism - one request per run against the latest-releases feed. Lowers
typical latency but guarantees nothing (CD "El feed no garantiza deteccion").
A feed item carries no reliable timestamp - FeedItem.updated_at_hint is raw,
unconverted text - so every feed detection writes
chapter_history.source_published_at as NULL; only a sweep, reading the JSON
endpoint, can ever fill a real UTC value."""

from manga_tracker.discovery.detection import Mapping, apply_detection
from manga_tracker.discovery.runs import RunAlreadyOpen, close_run, open_run, send_and_advance
from manga_tracker.sources.contracts import Chapter

JOB_NAME = "feed_check"
# job_runs.job_name and chapter_history.detected_via are two different CHECK
# constraints with two different value sets - reusing JOB_NAME for both would
# make every chapter_history insert violate its CHECK and get silently
# dropped by INSERT OR IGNORE (SQLite ignores FK/CHECK/UNIQUE alike).
DETECTED_VIA = "feed"


def _mapping_for(conn, site_id: int, source_key: str) -> Mapping | None:
    """Match by (site, source_key) - the schema's own uniqueness boundary."""
    row = conn.execute(
        "SELECT ms.id, ms.manga_id, m.title, b.status, ms.latest_chapter_num, b.last_chapter_read "
        "FROM manga_sites ms JOIN mangas m ON m.id = ms.manga_id "
        "JOIN bookmarks b ON b.manga_id = ms.manga_id "
        "WHERE ms.site_id = ? AND ms.source_key = ?",
        (site_id, source_key),
    ).fetchone()
    return Mapping(*row) if row else None


def feed_check(conn, client, sender, *, site_id: int, now: str, logger) -> None:
    try:
        run_id = open_run(conn, JOB_NAME, now)
    except RunAlreadyOpen as exc:
        logger.warning("feed_check skipped: %s", exc)
        return

    try:
        _check(conn, client, sender, site_id, run_id, now=now, logger=logger)
    except BaseException as exc:
        # Same reasoning as active_sweep's wrapper: close the row so nothing is
        # left with finished_at NULL, then re-raise so the failure still surfaces.
        close_run(conn, run_id, status="error", items_checked=0, updates_found=0,
                  notifications_sent=0, error_summary=f"{type(exc).__name__}: {exc}"[:200])
        raise


def _check(conn, client, sender, site_id: int, run_id, *, now: str, logger) -> None:
    items = client.fetch_latest_feed()
    candidates = []
    for item in items:
        mapping = _mapping_for(conn, site_id, item.source_key)
        if mapping is None:
            continue  # not in the reading list - discarded silently, no per-item log

        # source_published_at MUST stay NULL for a feed detection: the feed's
        # date is unreliable by design, so item.updated_at_hint is never
        # passed as a timestamp - only a sweep can ever fill a real value.
        chapter = Chapter(chapter_num=item.chapter_num, url=item.url, published_at=None)
        candidate = apply_detection(conn, mapping, chapter, detected_via=DETECTED_VIA, now=now, logger=logger)
        if candidate is not None:
            candidates.append(candidate)

    outcome = send_and_advance(conn, candidates, sender, now=now, client=client)
    close_run(
        conn, run_id, status="partial" if outcome.failed else "ok", items_checked=len(items),
        updates_found=len(candidates), notifications_sent=outcome.sent,
    )
