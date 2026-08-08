"""The shared detection rule (CD Parte B v1.3, six steps) - implemented once,
called by every mechanism. Never writes chapter_history for a terminal
bookmark; never moves latest_chapter_num backward; the history write happens
before, and independently of, any notify decision."""

from dataclasses import dataclass
from typing import NamedTuple


class Mapping(NamedTuple):
    """One manga_sites row joined with its bookmark."""
    id: int
    manga_id: int
    manga_title: str
    bookmark_status: str
    latest_chapter_num: float | None
    last_chapter_read: float | None


@dataclass(frozen=True)
class Candidate:
    """An active-manga novelty pending notification; latest_chapter_num stays
    untouched until this run's digest has been sent (runs.send_and_advance)."""
    manga_site_id: int
    manga_title: str
    chapter_num: float
    url: str
    published_at: str | None
    last_chapter_read: float | None


@dataclass(frozen=True)
class Detection:
    """What the rule did with one mapping's newest chapter: two facts, not one.

    `recorded` is "a new chapter went into chapter_history"; `candidate` is set
    only when a reader has to be told about it. They are not the same fact, and
    the difference is exactly the `on_hold` population, which records and never
    notifies (step 5).

    The rule used to return `Candidate | None` alone, which made those two
    questions share one answer: `None` meant terminal, no-novelty *and* silent
    update indistinguishably. `job_runs.updates_found` is defined by CD as
    "capitulos nuevos detectados (activos + silenciosos)", so every caller
    counting the returned candidates under-reported every silent detection it
    made. `onhold_sweep` had already hit this and worked around it locally by
    re-reading `latest_chapter_num` to see whether the rule had moved it - a
    correct answer to the wrong question, since the rule knew all along and
    simply could not say so. That workaround is gone with this type.
    """
    recorded: bool
    candidate: Candidate | None = None


# The rule looked and there was nothing to record: terminal bookmark, or a
# number that is not newer than the stored one. Named because it is returned
# from three places and "nothing happened" reads better than a bare constructor.
NOTHING_DETECTED = Detection(recorded=False)

DETECTED_VIA_VALUES = frozenset({"feed", "active_sweep", "onhold_sweep", "seed_backfill"})


def apply_detection(conn, mapping: Mapping, chapter, *, detected_via: str, now: str, logger) -> Detection:
    # chapter_history is written with INSERT OR IGNORE, which the spec requires
    # so that reprocessing a feed or repeating a sweep is idempotent. The same
    # clause also swallows CHECK violations: an invalid `detected_via` produces
    # no error and no row, so history would vanish with nothing logged anywhere.
    # This already happened once — a job passed its own job_name ("feed_check")
    # where the column wants "feed". It reads as harmless because for
    # active_sweep the two strings coincide by accident.
    if detected_via not in DETECTED_VIA_VALUES:
        raise ValueError(
            f"detected_via {detected_via!r} is not one of {sorted(DETECTED_VIA_VALUES)}; "
            "INSERT OR IGNORE would drop the history row silently"
        )
    conn.execute("UPDATE manga_sites SET last_checked_at = ? WHERE id = ?", (now, mapping.id))  # step 1: always

    if mapping.bookmark_status in ("completed", "dropped"):
        conn.commit()
        return NOTHING_DETECTED  # step 2 (CD v1.3 step 3): terminal - no history, no update, ever

    latest = mapping.latest_chapter_num
    if latest is not None and chapter.chapter_num <= latest:
        if chapter.chapter_num < latest:
            logger.warning("observed %s < stored %s for manga_sites.id=%s; source renumbered/deleted, "
                            "not moving the stored value backward", chapter.chapter_num, latest, mapping.id)
        conn.commit()
        return NOTHING_DETECTED  # step 3: no novelty either way

    conn.execute(
        "INSERT OR IGNORE INTO chapter_history "
        "(manga_site_id, chapter_num, chapter_url, source_published_at, detected_at, detected_via) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (mapping.id, chapter.chapter_num, chapter.url, chapter.published_at, now, detected_via),
    )  # step 4: before any notify decision, independent of it - a publication is a fact

    if mapping.bookmark_status == "on_hold":
        conn.execute(
            "UPDATE manga_sites SET latest_chapter_num = ?, latest_chapter_url = ?, latest_chapter_at = ? "
            "WHERE id = ?", (chapter.chapter_num, chapter.url, chapter.published_at, mapping.id),
        )
        conn.commit()
        # step 5: silent, immediate - on_hold never notifies. Recorded all the
        # same: the history row above is a fact, and CD counts it in
        # updates_found. No candidate, so nothing reaches the digest.
        return Detection(recorded=True)

    conn.commit()
    return Detection(  # step 5 (active): untouched until step 6 advances it
        recorded=True,
        candidate=Candidate(mapping.id, mapping.manga_title, chapter.chapter_num, chapter.url,
                            chapter.published_at, mapping.last_chapter_read),
    )
