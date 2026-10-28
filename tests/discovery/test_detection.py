"""The shared detection rule (CD Parte B v1.3) - tested directly against a
real DB. The rule takes an already-observed chapter (a source-client concern)
and returns a plain Detection, so no client/sender double is needed."""

import logging
import re

import pytest

from manga_tracker.discovery.detection import (
    NOTHING_DETECTED,
    Candidate,
    Mapping,
    apply_detection,
)
from manga_tracker.sources.contracts import Chapter
from manga_tracker.storage.db import connect

NOW = "2026-07-28T00:00:00Z"
LOGGER = logging.getLogger("test")


def seed_mapping(conn, *, status="reading", latest=None, last_read=None) -> Mapping:
    manga_id = conn.execute(
        "INSERT INTO mangas (title, created_at, updated_at) VALUES ('One Piece', ?, ?)", (NOW, NOW)
    ).lastrowid
    site_id = conn.execute(
        "INSERT INTO sites (name, base_url, created_at, updated_at) VALUES ('manganato', 'https://x', ?, ?)",
        (NOW, NOW),
    ).lastrowid
    ms_id = conn.execute(
        "INSERT INTO manga_sites (manga_id, site_id, source_key, latest_chapter_num, created_at, updated_at) "
        "VALUES (?, ?, 'one-piece', ?, ?, ?)", (manga_id, site_id, latest, NOW, NOW),
    ).lastrowid
    conn.execute(
        "INSERT INTO bookmarks (manga_id, status, last_chapter_read, origin, created_at, updated_at) "
        "VALUES (?, ?, ?, 'seed', ?, ?)",
        (manga_id, status, last_read, NOW, NOW),
    )
    conn.commit()
    return Mapping(ms_id, manga_id, "One Piece", status, latest, last_read)


def _history_count(conn, manga_site_id: int) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM chapter_history WHERE manga_site_id = ?", (manga_site_id,)
    ).fetchone()[0]


@pytest.mark.parametrize("status", ["completed", "dropped"])
def test_terminal_bookmark_writes_no_history_and_no_update(status):
    conn = connect(":memory:")
    mapping = seed_mapping(conn, status=status, latest=100)
    chapter = Chapter(chapter_num=101, url="x", published_at=NOW)

    detection = apply_detection(conn, mapping, chapter, detected_via="feed", now=NOW, logger=LOGGER)

    assert detection == NOTHING_DETECTED  # nothing recorded, so nothing for updates_found to count
    assert _history_count(conn, mapping.id) == 0
    row = conn.execute(
        "SELECT latest_chapter_num, last_checked_at FROM manga_sites WHERE id = ?", (mapping.id,)
    ).fetchone()
    assert row == (100, NOW)  # step 1's seal still happened; nothing else did


def _latest_row(conn, manga_site_id: int):
    return conn.execute(
        "SELECT latest_chapter_num, latest_chapter_url, latest_chapter_at FROM manga_sites WHERE id = ?",
        (manga_site_id,),
    ).fetchone()


def test_the_feed_never_moves_the_stored_value_backward(caplog):
    """One feed row is too weak to overrule the store - a bogus feed row is
    what inflated ms 93 to 373 in the first place (CD v1.12 step 2)."""
    conn = connect(":memory:")
    mapping = seed_mapping(conn, status="reading", latest=100)
    chapter = Chapter(chapter_num=90, url="x", published_at=None)

    with caplog.at_level(logging.WARNING):
        detection = apply_detection(conn, mapping, chapter, detected_via="feed", now=NOW, logger=LOGGER)

    assert detection == NOTHING_DETECTED and "renumbered/deleted" in caplog.text
    stored = conn.execute("SELECT latest_chapter_num FROM manga_sites WHERE id = ?", (mapping.id,)).fetchone()[0]
    assert stored == 100


@pytest.mark.parametrize("detected_via", ["active_sweep", "onhold_sweep"])
@pytest.mark.parametrize("status", ["reading", "want_to_read", "on_hold"])
def test_a_sweep_lowers_an_inflated_stored_value_to_what_the_source_lists(caplog, detected_via, status):
    """The production case (audit 2026-10-28): ms 93 stored 373 while the
    source listed 302, so every real chapter below 373 was dropped with a daily
    warning. A sweep reads the whole list, so its newest chapter being lower
    means the stored value is the wrong one. It is a correction, not a
    publication: no history row and nothing for the digest."""
    conn = connect(":memory:")
    mapping = seed_mapping(conn, status=status, latest=373)
    chapter = Chapter(chapter_num=302, url="https://x/302", published_at="2026-10-27T10:00:00Z")

    with caplog.at_level(logging.WARNING):
        detection = apply_detection(conn, mapping, chapter, detected_via=detected_via, now=NOW, logger=LOGGER)

    assert detection == NOTHING_DETECTED  # not recorded, not a candidate
    assert _latest_row(conn, mapping.id) == (302, "https://x/302", "2026-10-27T10:00:00Z")
    assert _history_count(conn, mapping.id) == 0
    warning = next(r for r in caplog.records if r.levelno == logging.WARNING)
    assert all(str(part) in warning.getMessage() for part in (373, 302, f"manga_sites.id={mapping.id}"))


@pytest.mark.parametrize("status", ["completed", "dropped"])
def test_a_sweep_never_lowers_a_terminal_mapping(status):
    """Terminal is absolute (step 3): not even a correction touches it."""
    conn = connect(":memory:")
    mapping = seed_mapping(conn, status=status, latest=373)
    chapter = Chapter(chapter_num=302, url="https://x/302", published_at=NOW)

    apply_detection(conn, mapping, chapter, detected_via="active_sweep", now=NOW, logger=LOGGER)

    assert _latest_row(conn, mapping.id) == (373, None, None)


def test_after_lowering_the_next_real_chapter_is_a_normal_candidate():
    """The point of lowering: the title speaks again from the next chapter on."""
    conn = connect(":memory:")
    mapping = seed_mapping(conn, status="reading", latest=373)
    apply_detection(conn, mapping, Chapter(302, "https://x/302", None), detected_via="active_sweep",
                    now=NOW, logger=LOGGER)

    lowered = mapping._replace(latest_chapter_num=302)
    detection = apply_detection(conn, lowered, Chapter(303, "https://x/303", None), detected_via="feed",
                                now=NOW, logger=LOGGER)

    assert detection.candidate is not None and detection.candidate.chapter_num == 303


@pytest.mark.parametrize("status", ["reading", "want_to_read"])
def test_active_bookmark_returns_candidate_but_leaves_latest_untouched(status):
    conn = connect(":memory:")
    mapping = seed_mapping(conn, status=status, latest=100)
    chapter = Chapter(chapter_num=101, url="https://x/101", published_at="2026-07-28T01:00:00Z")

    detection = apply_detection(conn, mapping, chapter, detected_via="feed", now=NOW, logger=LOGGER)

    assert detection.candidate == Candidate(
        mapping.id, "One Piece", 101, "https://x/101", "2026-07-28T01:00:00Z", None
    )
    assert detection.recorded is True  # an active detection counts in updates_found too, not just silent ones
    assert _history_count(conn, mapping.id) == 1  # written regardless of the (not yet made) notify decision
    stored = conn.execute("SELECT latest_chapter_num FROM manga_sites WHERE id = ?", (mapping.id,)).fetchone()[0]
    assert stored == 100  # notify-before-update: untouched until the digest succeeds


def test_reprocessing_the_same_chapter_is_idempotent():
    """An active bookmark leaves latest_chapter_num untouched (notify-before-
    update), so a second mechanism observing the same chapter runs the rule
    again - the UNIQUE index must make the second chapter_history write a
    silent no-op rather than an error."""
    conn = connect(":memory:")
    mapping = seed_mapping(conn, status="reading", latest=100)
    chapter = Chapter(chapter_num=101, url="x", published_at=None)

    apply_detection(conn, mapping, chapter, detected_via="feed", now=NOW, logger=LOGGER)
    apply_detection(conn, mapping, chapter, detected_via="feed", now=NOW, logger=LOGGER)

    assert _history_count(conn, mapping.id) == 1


def test_on_hold_updates_silently_without_notifying():
    """Silent, and *recorded* - the two are separate answers.

    `recorded is True` with `candidate is None` is the whole reason the rule
    returns a Detection instead of a bare candidate. CD defines
    `job_runs.updates_found` as "capitulos nuevos detectados (activos +
    silenciosos)", and while the rule could only answer with a candidate, every
    caller counting candidates reported zero for this case. It is not a corner:
    141 of the 229 tracked mangas are on_hold, so it is most of what the feed
    finds.
    """
    conn = connect(":memory:")
    mapping = seed_mapping(conn, status="on_hold", latest=100)
    chapter = Chapter(chapter_num=101, url="https://x/101", published_at="2026-07-28T01:00:00Z")

    detection = apply_detection(conn, mapping, chapter, detected_via="active_sweep", now=NOW, logger=LOGGER)

    assert detection.candidate is None  # never notified
    assert detection.recorded is True   # but it happened, and it counts
    assert _history_count(conn, mapping.id) == 1
    row = conn.execute(
        "SELECT latest_chapter_num, latest_chapter_url FROM manga_sites WHERE id = ?", (mapping.id,)
    ).fetchone()
    assert row == (101, "https://x/101")  # applied immediately, not gated behind any digest


def test_invalid_detected_via_fails_loudly_instead_of_dropping_history():
    """INSERT OR IGNORE hides CHECK violations, so the value is guarded here.

    Without this, a bad `detected_via` produces no error and no row: history
    disappears with nothing logged. It is a live trap because a job's own
    job_name is the obvious thing to pass, and for active_sweep that happens to
    be a legal value while for feed_check it is not.
    """
    conn = connect(":memory:")
    mapping = Mapping(1, 1, "T", "reading", 100, 90)
    chapter = Chapter(chapter_num=101, url="u", published_at=None)

    with pytest.raises(ValueError, match="detected_via"):
        apply_detection(conn, mapping, chapter, detected_via="feed_check",
                        now="2026-07-29T06:00:00Z", logger=logging.getLogger("t"))


# --- what I already read (CD v1.12 step 5) -------------------------------------


@pytest.mark.parametrize("status", ["reading", "want_to_read"])
@pytest.mark.parametrize("observed", [805, 912], ids=["below-progress", "at-progress"])
def test_a_chapter_already_read_is_recorded_and_advances_silently(status, observed):
    """The Steward in production: read to 912 elsewhere, the source at 804. Every
    chapter the source publishes up to 912 is one I have read, and the digest
    used to announce each of them. Now it behaves like on_hold: recorded, the
    stored value moves at once, and no candidate ever reaches the digest."""
    conn = connect(":memory:")
    mapping = seed_mapping(conn, status=status, latest=804, last_read=912)
    chapter = Chapter(chapter_num=observed, url=f"https://x/{observed}", published_at="2026-10-28T01:00:00Z")

    detection = apply_detection(conn, mapping, chapter, detected_via="active_sweep", now=NOW, logger=LOGGER)

    assert detection.candidate is None  # never notified
    assert detection.recorded is True   # but it happened, and updates_found counts it
    assert _history_count(conn, mapping.id) == 1
    assert _latest_row(conn, mapping.id) == (observed, f"https://x/{observed}", "2026-10-28T01:00:00Z")


def test_a_chapter_above_progress_is_still_a_candidate():
    conn = connect(":memory:")
    mapping = seed_mapping(conn, status="reading", latest=912, last_read=912)

    detection = apply_detection(conn, mapping, Chapter(913, "https://x/913", None), detected_via="feed",
                                now=NOW, logger=LOGGER)

    assert detection.candidate is not None and detection.candidate.chapter_num == 913
    assert _latest_row(conn, mapping.id)[0] == 912  # notify-before-update still holds for these


_WRITES_BOOKMARKS = re.compile(r"\b(UPDATE|INSERT\s+(OR\s+\w+\s+)?INTO|REPLACE\s+INTO|DELETE\s+FROM)\s+bookmarks\b",
                               re.IGNORECASE)


@pytest.mark.parametrize(
    "status, latest, last_read, observed, detected_via",
    [
        ("reading", 912, 912, 804, "active_sweep"),   # the source far below my progress: lowered, progress kept
        ("reading", 804, 912, 805, "active_sweep"),   # already read: silent advance
        ("reading", 100, 90, 101, "feed"),            # ordinary candidate
        ("on_hold", 100, 90, 101, "onhold_sweep"),    # ordinary silent update
        ("reading", 912, 912, 804, "feed"),           # the feed's warning-only path
    ],
    ids=["lowered-below-progress", "already-read", "candidate", "on-hold", "feed-regression"],
)
def test_detection_never_writes_the_bookmark(status, latest, last_read, observed, detected_via):
    """last_chapter_read is my progress, not a fact about the source. Reading
    912 against a source at 804 means I read it elsewhere (V2 multi-source),
    and "correcting" it down would also fire the reading_history trigger and
    log a fake downward reading event. So the rule must not issue a single
    write against bookmarks - checked on the SQL itself, not only on the row,
    so that rewriting the same value back would fail here too."""
    conn = connect(":memory:")
    mapping = seed_mapping(conn, status=status, latest=latest, last_read=last_read)
    before = conn.execute("SELECT * FROM bookmarks").fetchall()
    statements: list[str] = []
    conn.set_trace_callback(statements.append)

    apply_detection(conn, mapping, Chapter(observed, f"https://x/{observed}", None), detected_via=detected_via,
                    now=NOW, logger=LOGGER)

    conn.set_trace_callback(None)
    assert [s for s in statements if _WRITES_BOOKMARKS.search(s)] == []
    assert conn.execute("SELECT * FROM bookmarks").fetchall() == before
    assert conn.execute("SELECT COUNT(*) FROM reading_history").fetchone()[0] == 0
