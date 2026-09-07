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
# Above this share of *requested* mappings failing with Transient/Unexpected, the
# run closes `partial` instead of `ok`. Closes the contradiction CD already
# described and this module did not implement: CD defines `partial` as "fallos
# individuales (items con error, o digest fallido)" and only the second half
# existed, so a sweep in which every single mapping failed still closed `ok`.
#
# The two swallowed classes have no escalation of their own - `NotFound` feeds
# the dead-slug counter and is deliberately excluded here, because that path
# already ends in a notice. Transient and Unexpected end nowhere.
#
# 25% rather than "any failure" or "all of them": one broken title is ordinary
# noise, and degrading the run on it would leave the heartbeat red every week
# until it was fixed - retraining the owner to ignore it, which is the failure
# this whole line of work exists to undo. "All of them" is the opposite mistake:
# a source that changes shape for part of its catalogue would never be reported.
SWALLOWED_FAILURE_RATIO = 0.25


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


def _failure_summary(swallowed: int, requested: int, send_failed: bool) -> str:
    """What `partial` means for this run, in the row itself.

    Until now `partial` never stored a reason - the status was only ever set on
    a send failure, and that failure went to the log. The weekly heartbeat reads
    this column, so a threshold breach that stored nothing would render as the
    same bare "envío fallido" as a Telegram outage, pointing the owner at the
    wrong system entirely.
    """
    threshold = f"{int(SWALLOWED_FAILURE_RATIO * 100)}%"
    summary = (f"{swallowed}/{requested} mappings failed with transient/unexpected errors, "
               f"over the {threshold} threshold: the source may have changed shape")
    return f"send failed; {summary}" if send_failed else summary


def _sweep(conn, client, sender, run_id, *, now: str, logger) -> None:
    candidates = []
    pending_dead: list[tuple[int, str, str]] = []
    items_checked = 0
    skipped = 0
    # Transient/Unexpected failures this run discarded. Not an error counter:
    # discarding them per item is still correct, and the run still finishes. What
    # was missing is that nothing anywhere recorded how many were discarded.
    swallowed = 0
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
            swallowed += 1  # counted, not escalated - see SWALLOWED_FAILURE_RATIO
            continue  # a timeout says nothing about the slug's validity - counter untouched
        except Unexpected:
            # Third and last category of CD's taxonomy: the response arrived but
            # has the wrong shape, so the source probably changed. Log and move
            # on; the counter stays put because the slug may be perfectly valid.
            # Counted too: on its own this is one odd mapping, but enough of them
            # in one run is the signature of the source changing shape, and until
            # v1.8 that produced a green run reporting zero updates.
            swallowed += 1
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
    if swallowed:
        # WARNING, not INFO: individually these are ordinary, but the count is
        # the first place a shape change shows up before the ratio trips.
        logger.warning(
            "active_sweep discarded %s of %s requested mapping(s) to transient/unexpected errors",
            swallowed, items_checked - skipped,
        )
    outcome = send_and_advance(conn, candidates, sender, now=now, client=client)
    dead_failed = _report_dead_slugs(conn, pending_dead, sender, now=now, logger=logger)
    # Against what was actually requested, never against items_checked: the
    # prefilter routinely skips most of the population, and a mapping nobody
    # asked about cannot have failed. Using the wider denominator would dilute
    # the ratio exactly when the prefilter is working hardest.
    requested = items_checked - skipped
    too_many_failed = requested > 0 and swallowed / requested > SWALLOWED_FAILURE_RATIO
    send_failed = outcome.failed or dead_failed
    close_run(
        conn, run_id, status="partial" if (send_failed or too_many_failed) else "ok",
        # English, like every other error_summary: this field is a diagnostic the
        # developer reads, and the heartbeat quoting it verbatim is quoting a
        # diagnostic. Its own Spanish copy for a send failure lives in the
        # notifier, where product copy belongs.
        error_summary=_failure_summary(swallowed, requested, send_failed) if too_many_failed else None,
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
