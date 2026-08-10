"""Mecanismo 3 (CD "Mecanismo 3: barrido silencioso de on-hold" + "Slugs
muertos" step 4): the weekly sweep that never notifies, and the only retry path
a mapping paused by the dead-slug counter has.

Same procedure as the daily sweep with `detected_via = onhold_sweep`, and four
differences worth stating, because each one is a decision rather than a detail:

1. **Nothing here can send.** `_sweep` is not given the sender at all, so
   "never notifies" is structural and not a policy anyone has to remember. The
   shared detection rule already updates an `on_hold` mapping silently and
   returns None (detection.py step 5), so there is nothing to accumulate.

2. **The population is on-hold mappings plus every paused mapping.** CD states
   this twice and the two statements only agree when read together: Mecanismo 3
   says "mapeos cuyo manga tiene bookmark en `on_hold`. Incluye los pausados por
   fallos", and Slugs muertos step 4 says a mapping at the threshold "sigue
   entrando al barrido semanal, que actua como reintento de baja frecuencia". A
   paused mapping is `reading` or `want_to_read` - that is the only population
   the daily sweep, and therefore the dead-slug counter, ever touches - so
   reading the population as on-hold *only* would leave every paused mapping
   with no retry at all and make Mensaje 3's promise of a weekly retry false for
   every notice it can send. Terminal bookmarks stay out unconditionally: they
   receive zero requests, ever.

3. **No dead-slug notice comes from here.** The counter behaves as it does
   everywhere - only a not-found increments it, any success resets it - but the
   crossing notice belongs to the daily sweep, where "un solo aviso por manga"
   is guaranteed by that population excluding anything at the threshold. Sending
   it from a sweep whose population *includes* those mappings would re-send the
   same notice every Sunday for as long as the slug stayed dead, which is the
   one thing BOT "Mensaje 3" forbids. The cost is stated rather than hidden: an
   `on_hold` title whose slug dies is never announced, and shows up only in
   `manga_sites.consecutive_failures` and the log.

4. **The heartbeat does not fire from here.** CD's Mecanismo 3 ends "al terminar
   se dispara el heartbeat semanal"; that line is superseded. BOT v1.2 decoupled
   the heartbeat, gave it its own Sunday schedule and its own content, and it is
   registered separately in scheduler.py. More specific and more recent wins,
   which is this project's own conflict rule.
"""

from manga_tracker.discovery.active_sweep import DEAD_SLUG_THRESHOLD
from manga_tracker.discovery.detection import DETECTED_VIA_VALUES, Mapping, apply_detection
from manga_tracker.discovery.prefilter import has_moved, slug_update_times
from manga_tracker.discovery.runs import RunAlreadyOpen, close_run, open_run
from manga_tracker.sources.contracts import NotFound, Transient, Unexpected

JOB_NAME = "onhold_sweep"
# Two different CHECK constraints that happen to share a spelling for this job,
# exactly as for active_sweep - kept as two names because they are two columns.
DETECTED_VIA = "onhold_sweep"
assert DETECTED_VIA in DETECTED_VIA_VALUES
# Imported rather than restated: one threshold, one definition. The dead-slug
# counter is the daily sweep's, and this sweep only reads its boundary.


def _population(conn):
    """On-hold mappings, plus every non-terminal mapping paused by the counter.

    The `NOT IN ('completed', 'dropped')` clause is not defensive padding: only
    a non-terminal mapping is ever requested, and a paused terminal one (a title
    dropped after its slug died) would otherwise be pulled back in by the second
    half of the OR - a request the shared detection rule forbids outright.
    """
    return conn.execute(
        "SELECT ms.id, ms.manga_id, m.title, b.status, ms.source_key, "
        "ms.latest_chapter_num, b.last_chapter_read, ms.latest_chapter_at "
        "FROM manga_sites ms JOIN mangas m ON m.id = ms.manga_id "
        "JOIN bookmarks b ON b.manga_id = ms.manga_id "
        "WHERE b.status NOT IN ('completed', 'dropped') "
        "AND (b.status = 'on_hold' OR ms.consecutive_failures >= ?)",
        (DEAD_SLUG_THRESHOLD,),
    ).fetchall()


def onhold_sweep(conn, client, sender, *, now: str, logger) -> None:
    """`sender` is accepted and never used, so the scheduler's job wrapper needs
    no special case - the same reason heartbeat ignores `client`. It is not
    forwarded to `_sweep`: this job has no way to send anything."""
    try:
        run_id = open_run(conn, JOB_NAME, now)
    except RunAlreadyOpen as exc:
        logger.warning("onhold_sweep skipped: %s", exc)
        return

    try:
        _sweep(conn, client, run_id, now=now, logger=logger)
    except BaseException as exc:
        # Same reasoning as active_sweep's wrapper: `error` is CD's status for a
        # run that aborted, the row is closed so nothing is left with
        # finished_at NULL, and the exception is re-raised so it still surfaces.
        close_run(conn, run_id, status="error", items_checked=0, updates_found=0,
                  notifications_sent=0, error_summary=f"{type(exc).__name__}: {exc}"[:200])
        raise


def _sweep(conn, client, run_id, *, now: str, logger) -> None:
    items_checked = 0
    skipped = 0
    updates_found = 0
    population = _population(conn)
    times = slug_update_times(client, logger) if population else None
    for ms_id, manga_id, title, status, source_key, latest, last_read, stored_at in population:
        # Counted before the skip decision, same as the daily sweep: a run that
        # examined 72 mappings and requested 3 examined 72.
        items_checked += 1
        if times is not None and not has_moved(times, source_key, stored_at):
            skipped += 1
            continue
        try:
            chapters = client.fetch_chapters(source_key)
        except NotFound:
            # A plain increment, with no threshold branch: the notice is the
            # daily sweep's and cannot be repeated (see the module docstring).
            # The counter is allowed past the threshold - a mapping at 9 is as
            # excluded from the daily sweep as one at 5, and the number is
            # honest about how long the slug has been gone.
            conn.execute(
                "UPDATE manga_sites SET consecutive_failures = consecutive_failures + 1 WHERE id = ?", (ms_id,)
            )
            conn.commit()
            continue
        except Transient:
            continue  # a timeout says nothing about the slug's validity - counter untouched
        except Unexpected:
            logger.exception("onhold_sweep: unexpected response shape for manga_sites.id=%s", ms_id)
            continue

        # Any success resets it, and for this sweep that reset is the point: it
        # is what lets a title whose slug came back re-enter the daily sweep on
        # its own, with no manual repair (CD "Slugs muertos" step 4).
        conn.execute("UPDATE manga_sites SET consecutive_failures = 0 WHERE id = ?", (ms_id,))
        conn.commit()
        if not chapters:
            continue  # a well-formed empty response is a success; nothing else to do

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
        # Any candidate is deliberately dropped rather than sent. For the on-hold
        # majority there is never one, and for a paused `reading` mapping that
        # answered again it is a candidate whose notification belongs to the
        # daily sweep: nothing advanced `latest_chapter_num` here, so
        # notify-before-update means tomorrow's sweep re-detects it and sends the
        # digest. That is the correct division - this sweep answers "is the slug
        # alive?", the daily one owns the reader's alerts.
        #
        # `recorded` is what updates_found wants, and it now comes from the rule
        # itself. This used to re-read latest_chapter_num to infer whether the
        # rule had moved it, because a bare `Candidate | None` could not say
        # "recorded but silent" - the right answer to the wrong question, and one
        # extra query per requested mapping. The other two mechanisms had the
        # same problem and no workaround at all.
        updates_found += detection.recorded

    if times is not None:
        logger.info(
            "onhold_sweep examined %s mapping(s), requested %s, skipped %s the source reports unchanged",
            items_checked, items_checked - skipped, skipped,
        )
    # Always `ok` or `error`, never `partial`: `partial` is CD's status for a run
    # that completed with a failed send, and this run has no send to fail. Item
    # failures do not make the daily sweep partial either, so the two agree.
    close_run(conn, run_id, status="ok", items_checked=items_checked,
              updates_found=updates_found, notifications_sent=0,
              # Same split as the daily sweep, and it matters more here: this is
              # the population the prefilter saves the most on - 141 mappings
              # against a handful actually requested - and this sweep sends
              # nothing, so job_runs is the only place its work is ever visible.
              items_requested=(items_checked - skipped) if times is not None else None,
              items_skipped=skipped if times is not None else None)
