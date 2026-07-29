"""Mecanismo 2 (CD "Mecanismo 2: barrido de activos" + "Slugs muertos"): the
primary detection mechanism, run once daily against every active mapping -
the only guarantor of the ~24h worst-case latency once the feed is saturated.
Also owns the dead-slug counter: only a not-found classification increments
it, any success resets it, and a mapping at the threshold consumes zero
requests."""

from manga_tracker.discovery.detection import DETECTED_VIA_VALUES, Mapping, apply_detection
from manga_tracker.discovery.runs import RunAlreadyOpen, close_run, open_run, send_and_advance
from manga_tracker.sources.contracts import NotFound, Transient, Unexpected

JOB_NAME = "active_sweep"
# job_runs.job_name and chapter_history.detected_via happen to share a spelling
# for this job. They do not for feed_check, so they are kept as separate names.
DETECTED_VIA = "active_sweep"
assert DETECTED_VIA in DETECTED_VIA_VALUES
DEAD_SLUG_THRESHOLD = 5


def _population(conn):
    """reading/want_to_read mappings, excluding those paused by the dead-slug
    counter (CD "Poblacion" + "Slugs muertos" step 4) - a paused mapping never
    reaches fetch_chapters, so it consumes no request."""
    return conn.execute(
        "SELECT ms.id, ms.manga_id, m.title, b.status, ms.source_key, "
        "ms.latest_chapter_num, b.last_chapter_read "
        "FROM manga_sites ms JOIN mangas m ON m.id = ms.manga_id "
        "JOIN bookmarks b ON b.manga_id = ms.manga_id "
        "WHERE b.status IN ('reading', 'want_to_read') AND ms.consecutive_failures < ?",
        (DEAD_SLUG_THRESHOLD,),
    ).fetchall()


def active_sweep(conn, client, sender, *, now: str, logger) -> None:
    """The 5-15s delay between consecutive requests is the transport's job
    (already injectable there); `client` here is the `SourceClient` Protocol,
    so a fake in tests never sleeps at all."""
    try:
        run_id = open_run(conn, JOB_NAME, now)
    except RunAlreadyOpen as exc:
        logger.warning("active_sweep skipped: %s", exc)
        return

    try:
        _sweep(conn, client, sender, run_id, now=now, logger=logger)
    except BaseException as exc:
        # CD reserves job_runs.status `error` for "la corrida abortó (excepción
        # no controlada)". Swallowing per item instead would turn a real bug
        # into an `ok` run with zero updates - a job that reports success and
        # does nothing, which is this project's original failure mode. The row
        # is closed here so nothing is left with finished_at NULL, then the
        # exception is re-raised so it still surfaces.
        close_run(conn, run_id, status="error", items_checked=0, updates_found=0,
                  notifications_sent=0, now=now, error_summary=f"{type(exc).__name__}: {exc}"[:200])
        raise


def _sweep(conn, client, sender, run_id, *, now: str, logger) -> None:
    candidates = []
    items_checked = 0
    for ms_id, manga_id, title, status, source_key, latest, last_read in _population(conn):
        items_checked += 1
        try:
            chapters = client.fetch_chapters(source_key)
        except NotFound:
            conn.execute(
                "UPDATE manga_sites SET consecutive_failures = consecutive_failures + 1 WHERE id = ?", (ms_id,)
            )
            conn.commit()
            continue
        except Transient:
            continue  # a timeout says nothing about the slug's validity - counter untouched
        except Unexpected:
            # Third and last category of CD's taxonomy: the response arrived but
            # has the wrong shape, so the source probably changed. Log and move
            # on; the counter stays put because the slug may be perfectly valid.
            logger.exception("active_sweep: unexpected response shape for manga_sites.id=%s", ms_id)
            continue

        conn.execute("UPDATE manga_sites SET consecutive_failures = 0 WHERE id = ?", (ms_id,))
        conn.commit()
        if not chapters:
            continue  # D14: a well-formed empty response is a success; nothing else to do

        for chapter in chapters[1:]:  # only the newest is compared; the rest are free data
            conn.execute(
                "INSERT OR IGNORE INTO chapter_history "
                "(manga_site_id, chapter_num, chapter_url, source_published_at, detected_at, detected_via) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (ms_id, chapter.chapter_num, chapter.url, chapter.published_at, now, DETECTED_VIA),
            )
        conn.commit()

        mapping = Mapping(ms_id, manga_id, title, status, latest, last_read)
        candidate = apply_detection(conn, mapping, chapters[0], detected_via=DETECTED_VIA, now=now, logger=logger)
        if candidate is not None:
            candidates.append(candidate)

    outcome = send_and_advance(conn, candidates, sender, now=now, client=client)
    close_run(
        conn, run_id, status="partial" if outcome.failed else "ok", items_checked=items_checked,
        updates_found=len(candidates), notifications_sent=outcome.sent, now=now,
    )
