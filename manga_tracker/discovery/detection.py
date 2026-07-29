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


def apply_detection(conn, mapping: Mapping, chapter, *, detected_via: str, now: str, logger) -> Candidate | None:
    conn.execute("UPDATE manga_sites SET last_checked_at = ? WHERE id = ?", (now, mapping.id))  # step 1: always

    if mapping.bookmark_status in ("completed", "dropped"):
        conn.commit()
        return None  # step 2 (CD v1.3 step 3): terminal - no history, no update, ever

    latest = mapping.latest_chapter_num
    if latest is not None and chapter.chapter_num <= latest:
        if chapter.chapter_num < latest:
            logger.warning("observed %s < stored %s for manga_sites.id=%s; source renumbered/deleted, "
                            "not moving the stored value backward", chapter.chapter_num, latest, mapping.id)
        conn.commit()
        return None  # step 3: no novelty either way

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
        return None  # step 5: silent, immediate - on_hold never notifies

    conn.commit()
    return Candidate(mapping.id, mapping.manga_title, chapter.chapter_num, chapter.url, chapter.published_at,
                      mapping.last_chapter_read)  # step 5 (active): untouched until step 6 advances it
