"""Mecanismo 2 (CD "Mecanismo 2: barrido de activos" + "Slugs muertos"): the
primary detection mechanism, run once daily against every active mapping -
the only guarantor of the ~24h worst-case latency once the feed is saturated.
Also owns the dead-slug counter: only a not-found classification increments
it, any success resets it, and a mapping at the threshold consumes zero
requests."""

import logging

from manga_tracker.discovery.detection import DETECTED_VIA_VALUES, Mapping, apply_detection
from manga_tracker.discovery.runs import RunAlreadyOpen, close_run, open_run, send_and_advance
from manga_tracker.notifier.contracts import DeadSlugNotice
from manga_tracker.sources.contracts import NotFound, Transient, Unexpected

JOB_NAME = "active_sweep"
# job_runs.job_name and chapter_history.detected_via happen to share a spelling
# for this job. They do not for feed_check, so they are kept as separate names.
DETECTED_VIA = "active_sweep"
assert DETECTED_VIA in DETECTED_VIA_VALUES
DEAD_SLUG_THRESHOLD = 5
# `onhold_sweep` is phase 2, so a mapping paused at the threshold has no
# automatic recovery yet (one-pager, accepted risk). The notice says so instead
# of promising the weekly retry the bot spec's illustration describes; flip this
# when that sweep lands and every message corrects itself.
DEAD_SLUG_RETRIES_WEEKLY = False


def _report_dead_slugs(conn, pending: list, sender, *, now: str, logger) -> bool:
    """Send the notice, and only then let the counters reach the threshold.

    This is CD's "Orden de operaciones" - notify before advancing - applied to
    Mensaje 3, and here it is load-bearing rather than stylistic. A mapping at
    the threshold is excluded from the population, so it never issues another
    request and never increments again: the crossing happens exactly once in the
    life of a dead slug. Advancing the counter first would mean a failed send
    loses the only notice that mapping will ever generate, and the title would
    drop out of the daily sweep in the silence this whole message exists to
    break. Holding the increment back costs one extra request next run and turns
    a lost notice into a re-detected one.

    Returns True when the notice failed, matching send_and_advance's convention
    so the caller can close the run `partial`.
    """
    if not pending:
        return False
    notices = [
        DeadSlugNotice(title, source_key, DEAD_SLUG_THRESHOLD, retries_weekly=DEAD_SLUG_RETRIES_WEEKLY)
        for _, title, source_key in pending
    ]
    try:
        delivered = sender.send_dead_slug_notice(notices, now=now)
    except Exception:
        logging.getLogger(__name__).exception("dead-slug notice raised; counters left below the threshold")
        return True
    if not delivered:
        logger.warning("dead-slug notice not delivered; counters left below the threshold")
        return True
    for ms_id, _, _ in pending:
        conn.execute(
            "UPDATE manga_sites SET consecutive_failures = ? WHERE id = ?", (DEAD_SLUG_THRESHOLD, ms_id)
        )
    conn.commit()
    return False


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
                  notifications_sent=0, error_summary=f"{type(exc).__name__}: {exc}"[:200])
        raise


def _sweep(conn, client, sender, run_id, *, now: str, logger) -> None:
    candidates = []
    pending_dead: list[tuple[int, str, str]] = []
    items_checked = 0
    for ms_id, manga_id, title, status, source_key, latest, last_read in _population(conn):
        items_checked += 1
        try:
            chapters = client.fetch_chapters(source_key)
        except NotFound:
            failures = conn.execute(
                "SELECT consecutive_failures FROM manga_sites WHERE id = ?", (ms_id,)
            ).fetchone()[0]
            if failures + 1 >= DEAD_SLUG_THRESHOLD:
                # The counter is deliberately NOT advanced here - see
                # _report_dead_slugs. It moves only once the notice is out.
                pending_dead.append((ms_id, title, source_key))
            else:
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
    dead_failed = _report_dead_slugs(conn, pending_dead, sender, now=now, logger=logger)
    close_run(
        conn, run_id, status="partial" if (outcome.failed or dead_failed) else "ok",
        items_checked=items_checked, updates_found=len(candidates),
        # The dead-slug notice counts: it is a message that went out, and
        # under-reporting it would make job_runs a worse diagnostic than it is.
        notifications_sent=outcome.sent + (1 if pending_dead and not dead_failed else 0),
    )
