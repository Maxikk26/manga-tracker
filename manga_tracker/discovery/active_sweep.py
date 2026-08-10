"""Mecanismo 2 (CD "Mecanismo 2: barrido de activos" + "Slugs muertos"): the
primary detection mechanism, run once daily against every active mapping -
the only guarantor of the ~24h worst-case latency once the feed is saturated.
Also owns the dead-slug counter: only a not-found classification increments
it, any success resets it, and a mapping at the threshold consumes zero
requests."""

import logging

from manga_tracker.discovery.detection import DETECTED_VIA_VALUES, Mapping, apply_detection
from manga_tracker.discovery.prefilter import has_moved, slug_update_times
from manga_tracker.discovery.runs import RunAlreadyOpen, close_run, open_run, send_and_advance
from manga_tracker.notifier.contracts import DeadSlugNotice
from manga_tracker.sources.contracts import NotFound, Transient, Unexpected

JOB_NAME = "active_sweep"
# job_runs.job_name and chapter_history.detected_via happen to share a spelling
# for this job. They do not for feed_check, so they are kept as separate names.
DETECTED_VIA = "active_sweep"
assert DETECTED_VIA in DETECTED_VIA_VALUES
DEAD_SLUG_THRESHOLD = 5
# True since `onhold_sweep` landed, and that is the whole reason the wording was
# made conditional rather than fixed: the notice promised no weekly retry while
# nothing performed one, and it now promises the retry that does happen. The
# weekly sweep's population includes every mapping paused at this threshold, so
# the promise holds for exactly the mappings this notice can be sent about -
# which are all `reading`/`want_to_read`, since only this sweep sends it.
DEAD_SLUG_RETRIES_WEEKLY = True


def _report_dead_slugs(conn, pending: list, sender, *, now: str, logger) -> bool:
    """Send the notice, and only then let the counters reach the threshold.

    This is CD's "Orden de operaciones" - notify before advancing - applied to
    Mensaje 3, and here it is load-bearing rather than stylistic. A mapping at
    the threshold is excluded from *this* population, so it never crosses twice:
    the crossing happens exactly once in the life of a dead slug. (`onhold_sweep`
    does keep requesting it weekly and does keep counting its failures, which is
    why the exclusion is written as `< THRESHOLD` rather than `== THRESHOLD` -
    a counter at 6 or 9 stays out of the daily sweep and produces no second
    notice.) Advancing the counter first would mean a failed send loses the only
    notice that mapping will ever generate, and the title would drop out of the
    daily sweep in the silence this whole message exists to break. Holding the
    increment back costs one extra request next run and turns a lost notice into
    a re-detected one.

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
        "ms.latest_chapter_num, b.last_chapter_read, ms.latest_chapter_at "
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
    skipped = 0
    # Not len(candidates): CD defines updates_found as "activos + silenciosos",
    # and a silent detection produces no candidate. This sweep's population is
    # reading/want_to_read, so a silent one only happens when a bookmark moves to
    # on_hold between the query and the request - rare, and precisely the case
    # where an unexplained zero would send someone hunting for a bug.
    recorded = 0
    population = _population(conn)
    times = slug_update_times(client, logger) if population else None
    for ms_id, manga_id, title, status, source_key, latest, last_read, stored_at in population:
        # Counted before the skip decision, and that is load-bearing: a run that
        # examined 89 mappings and requested 3 examined 89. `sweep_is_overdue`
        # filters on items_checked > 0, so under-reporting here would let a
        # legitimate sweep look like one that swept nothing.
        items_checked += 1
        if times is not None and not has_moved(times, source_key, stored_at):
            skipped += 1
            continue
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
        detection = apply_detection(conn, mapping, chapters[0], detected_via=DETECTED_VIA, now=now, logger=logger)
        recorded += detection.recorded
        if detection.candidate is not None:
            candidates.append(detection.candidate)

    if times is not None:
        logger.info(
            "active_sweep examined %s mapping(s), requested %s, skipped %s the source reports unchanged",
            items_checked, items_checked - skipped, skipped,
        )
    outcome = send_and_advance(conn, candidates, sender, now=now, client=client)
    dead_failed = _report_dead_slugs(conn, pending_dead, sender, now=now, logger=logger)
    close_run(
        conn, run_id, status="partial" if (outcome.failed or dead_failed) else "ok",
        items_checked=items_checked, updates_found=recorded,
        # The same split the log line above reports, now in the table. It lived
        # only in the container log, which meant "did the prefilter skip these or
        # did the sweep never look?" could not be answered from job_runs at all -
        # and last_checked_at cannot answer it either, since a skipped mapping is
        # never sealed. When the prefilter did not run, both stay None rather
        # than claiming a split that did not happen.
        items_requested=(items_checked - skipped) if times is not None else None,
        items_skipped=skipped if times is not None else None,
        # The dead-slug notice counts: it is a message that went out, and
        # under-reporting it would make job_runs a worse diagnostic than it is.
        notifications_sent=outcome.sent + (1 if pending_dead and not dead_failed else 0),
    )
