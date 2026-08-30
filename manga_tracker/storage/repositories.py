"""Parameterized query helpers for the seed loader's, the Kitsu importer's
and the web panel's reads and writes — no slug or user value is ever
interpolated into SQL.

Three families live here and they are deliberately separate. The seed
family (`write_seed_backfill`) owns `origin='seed'`, `progress_is_approx=0`
and commits for itself. The Kitsu family writes `origin='kitsu_import'`,
`progress_is_approx=1`, refuses to touch a bookmark it does not own, and
**never commits**: the importer wraps one whole entry in a single transaction
so a match rejected by verification leaves zero rows (design D5). The panel
family (spec-panel-v1b.md fase 1) reads the bookmark list and applies one
edit per transaction, correcting the trigger-captured row to
`origin='panel'`; it commits for itself, one edit being one transaction.
"""

import json
import sqlite3
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from manga_tracker.storage.db import transaction

# Re-exported so a caller outside `storage` (e.g. `intake.pasted_url`, which
# must catch a unique-index race on `write_manual_add`) can recognize the
# error without importing `sqlite3` itself — that import is confined to this
# package (test_architecture.py's CONFINEMENT_RULES).
IntegrityError = sqlite3.IntegrityError

IMPORT_ORIGIN = "kitsu_import"
IMPORT_DETECTED_VIA = "seed_backfill"
PANEL_ORIGIN = "panel"
MANUAL_ORIGIN = "manual"

# The bookmark status enum exactly as the schema CHECK declares it. The panel
# validates a request against this tuple before any SQL runs, so an invalid
# status is a 422 to the caller, never an IntegrityError from the database.
BOOKMARK_STATUSES = ("reading", "want_to_read", "completed", "on_hold", "dropped")

# The two statuses that receive zero source requests, ever (CLAUDE.md). Also
# lives, by construction, as `web/app.py:TERMINAL_STATUSES` and
# `importer/export.py:TERMINAL_STATUSES` — those two copies predate this one
# and stay where they are (pulling `storage`, and `sqlite3` with it, into the
# XML parser is the worse trade); this copy is what `cli.py` and
# `discovery/covers.py` import, and a parity test keeps all three equal
# (design D8, panel-v1b-fase-4).
TERMINAL_STATUSES = frozenset({"completed", "dropped"})

# "The PATCH did not carry this field". None cannot play that role because it
# is a real value for last_chapter_read, so absence gets its own marker.
UNSET = object()

# What write_kitsu_bookmark did, so the caller can report it.
BOOKMARK_INSERTED = "inserted"
BOOKMARK_UPDATED = "updated"
BOOKMARK_PROTECTED = "protected"

# The seed loader's cap, kept identical: fetch_chapters already returns at most
# this many, so the slice only matters if a client ever returns more.
CHAPTER_HISTORY_LIMIT = 50


def find_manga_site_by_slug(conn: sqlite3.Connection, site_id: int, slug: str) -> tuple[int, int] | None:
    row = conn.execute(
        "SELECT manga_id, id FROM manga_sites WHERE site_id = ? AND source_key = ?", (site_id, slug)
    ).fetchone()
    return (row[0], row[1]) if row else None


def find_slug_owner(conn: sqlite3.Connection, site_id: int, slug: str) -> tuple[str, str | None] | None:
    """`(title, kitsu_id)` of the manga this slug is already mapped to, if any.

    `manga_sites(site_id, source_key)` is UNIQUE, so a slug points at exactly one
    manga. The seed reuses that mapping by slug on purpose (SEED
    "Re-ejecucion"), and this exists to tell legitimate reuse apart from SEED
    "Validacion"'s error "slug que en la base ya apunta a otro manga": a mapping
    whose manga the file calls something else entirely is a mis-pasted URL, not a
    re-run.

    `kitsu_id` travels with the title because it decides whether the comparison
    is meaningful at all - see the loader's `_slug_owner_error`.
    """
    row = conn.execute(
        "SELECT m.title, m.kitsu_id FROM manga_sites ms JOIN mangas m ON m.id = ms.manga_id "
        "WHERE ms.site_id = ? AND ms.source_key = ?",
        (site_id, slug),
    ).fetchone()
    return (row[0], row[1]) if row else None


def find_manga_by_kitsu_id(conn: sqlite3.Connection, kitsu_id: str) -> int | None:
    """Reconciliation key 1. The column is UNIQUE, so this is at most one row."""
    row = conn.execute("SELECT id FROM mangas WHERE kitsu_id = ?", (kitsu_id,)).fetchone()
    return row[0] if row else None


def find_manga_site_for_manga(conn: sqlite3.Connection, manga_id: int, site_id: int) -> tuple[int, str] | None:
    """The mapping this manga already has at this site, as `(id, source_key)`.

    Needed because `(manga_id, site_id)` is UNIQUE: a manga reconciled by
    `kitsu_id` may already be mapped to a *different* slug, and inserting a
    second mapping would abort the run with an integrity error instead of
    reporting one entry.
    """
    row = conn.execute(
        "SELECT id, source_key FROM manga_sites WHERE manga_id = ? AND site_id = ?", (manga_id, site_id)
    ).fetchone()
    return (row[0], row[1]) if row else None


def list_manga_titles(conn: sqlite3.Connection) -> list[tuple[int, str]]:
    """Every `(id, title)`, for reconciliation key 3.

    The comparison cannot run in SQL: the key is an NFKD-normalized title and
    SQLite has no NFKD, so the folding happens in Python with the same
    normalizer the slug candidates use (design D3).
    """
    return [(row[0], row[1]) for row in conn.execute("SELECT id, title FROM mangas")]


def write_manga_from_catalogue(
    conn,
    manga_id,
    *,
    title,
    kitsu_id,
    alt_titles,
    synopsis,
    genres,
    cover_url,
    total_chapters,
    publication_status,
    now,
) -> int:
    """Insert the `mangas` row, or enrich the one reconciliation found.

    Every catalogue field is written **only when the catalogue supplied it** —
    `COALESCE(?, column)` — because a missing value is NULL and NULL is honest:
    `total_chapters` is present for 48 of 153 and writing 0 for the rest would
    claim those works have no chapters (KIT). Nothing already stored is ever
    replaced by an absence.

    `kitsu_id` is COALESCEd the other way round: it is backfilled when missing
    and never overwritten, so a second run cannot repoint an existing row.

    Does not commit.
    """
    supplied = (
        _json_array(alt_titles),
        synopsis or None,
        _json_array(genres),
        cover_url or None,
        total_chapters or None,
        publication_status or None,
    )
    if manga_id is None:
        return conn.execute(
            "INSERT INTO mangas (title, kitsu_id, alt_titles, synopsis, genres, cover_url, "
            "total_chapters, publication_status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE(?, 'ongoing'), ?, ?)",
            (title, kitsu_id, *supplied, now, now),
        ).lastrowid

    conn.execute(
        "UPDATE mangas SET title = ?, kitsu_id = COALESCE(kitsu_id, ?), "
        "alt_titles = COALESCE(?, alt_titles), synopsis = COALESCE(?, synopsis), "
        "genres = COALESCE(?, genres), cover_url = COALESCE(?, cover_url), "
        "total_chapters = COALESCE(?, total_chapters), "
        "publication_status = COALESCE(?, publication_status), updated_at = ? WHERE id = ?",
        (title, kitsu_id, *supplied, now, manga_id),
    )
    return manga_id


def write_source_mapping(conn, manga_site_id, manga_id, *, site_id, slug, url, chapters, now) -> int:
    """Create or reuse the mapping, seal the newest chapter, dump the chapters.

    `INSERT OR IGNORE` against the `(manga_site_id, chapter_num)` unique index
    is what makes re-running the import free of duplicates — by constraint, not
    by the operator remembering (KIT Seccion "Re-ejecucion").

    Does not commit.
    """
    if manga_site_id is None:
        manga_site_id = conn.execute(
            "INSERT INTO manga_sites (manga_id, site_id, source_key, url, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (manga_id, site_id, slug, url, now, now),
        ).lastrowid

    newest = chapters[0]  # fetch_chapters returns newest-first
    conn.execute(
        "UPDATE manga_sites SET latest_chapter_num = ?, latest_chapter_url = ?, latest_chapter_at = ?, "
        "last_checked_at = ?, updated_at = ? WHERE id = ?",
        (newest.chapter_num, newest.url, newest.published_at, now, now, manga_site_id),
    )
    for chapter in chapters[:CHAPTER_HISTORY_LIMIT]:
        conn.execute(
            "INSERT OR IGNORE INTO chapter_history "
            "(manga_site_id, chapter_num, chapter_url, source_published_at, detected_at, detected_via) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (manga_site_id, chapter.chapter_num, chapter.url, chapter.published_at, now, IMPORT_DETECTED_VIA),
        )
    return manga_site_id


def write_kitsu_bookmark(conn, manga_id, *, status, last_chapter_read, last_read_at, now) -> tuple[str, str]:
    """Insert the bookmark, update it, or leave someone else's alone.

    Returns `(action, origin)`. The rule is `bookmarks.origin` (KIT Seccion
    "Que bookmark puede tocar el import"): `seed` is mine, typed by hand, and
    worth more than the catalogue; `manual` is a deliberate correction of mine
    and worth more still. Only `kitsu_import` rows belong to this importer, and
    for those the export is the source of truth.

    Updating one of its own rows is what fires the `reading_history` trigger —
    deliberately: chapters really were read between two exports, and the
    trigger is UPDATE-only precisely so the bulk insert stays silent.

    Does not commit.
    """
    row = conn.execute("SELECT id, origin FROM bookmarks WHERE manga_id = ?", (manga_id,)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO bookmarks (manga_id, status, last_chapter_read, progress_is_approx, origin, "
            "last_read_at, created_at, updated_at) VALUES (?, ?, ?, 1, ?, ?, ?, ?)",
            (manga_id, status, last_chapter_read, IMPORT_ORIGIN, last_read_at, now, now),
        )
        return (BOOKMARK_INSERTED, IMPORT_ORIGIN)

    bookmark_id, origin = row
    if origin != IMPORT_ORIGIN:
        return (BOOKMARK_PROTECTED, origin)

    conn.execute(
        "UPDATE bookmarks SET status = ?, last_chapter_read = ?, last_read_at = ?, updated_at = ? WHERE id = ?",
        (status, last_chapter_read, last_read_at, now, bookmark_id),
    )
    return (BOOKMARK_UPDATED, origin)


def _json_array(values) -> str | None:
    """A list column is stored as a JSON array; an empty list is stored as
    nothing at all, so "the catalogue knows no alternative titles" reads as
    NULL rather than as an empty array a consumer has to special-case."""
    items = [value for value in (values or []) if value]
    return json.dumps(items, ensure_ascii=False) if items else None


def write_seed_backfill(conn, existing, title, site_id, slug, url, chapters, status, last_chapter_read, now):
    """Create or reuse (`existing`) the manga + mapping, set the newest chapter, dump chapters, upsert the bookmark."""
    if existing is None:
        manga_id = conn.execute(
            "INSERT INTO mangas (title, created_at, updated_at) VALUES (?, ?, ?)", (title, now, now)
        ).lastrowid
        manga_site_id = conn.execute(
            "INSERT INTO manga_sites (manga_id, site_id, source_key, url, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (manga_id, site_id, slug, url, now, now),
        ).lastrowid
    else:
        manga_id, manga_site_id = existing

    newest = chapters[0]  # fetch_chapters returns newest-first
    conn.execute(
        "UPDATE manga_sites SET latest_chapter_num = ?, latest_chapter_url = ?, latest_chapter_at = ?, "
        "last_checked_at = ?, updated_at = ? WHERE id = ?",
        (newest.chapter_num, newest.url, newest.published_at, now, now, manga_site_id),
    )
    for chapter in chapters[:50]:
        conn.execute(
            "INSERT OR IGNORE INTO chapter_history "
            "(manga_site_id, chapter_num, chapter_url, source_published_at, detected_at, detected_via) "
            "VALUES (?, ?, ?, ?, ?, 'seed_backfill')",
            (manga_site_id, chapter.chapter_num, chapter.url, chapter.published_at, now),
        )

    existing_bm = conn.execute("SELECT id FROM bookmarks WHERE manga_id = ?", (manga_id,)).fetchone()
    if existing_bm is None:
        conn.execute(
            "INSERT INTO bookmarks (manga_id, status, last_chapter_read, progress_is_approx, origin, "
            "created_at, updated_at) VALUES (?, ?, ?, 0, 'seed', ?, ?)",
            (manga_id, status, last_chapter_read, now, now),
        )
    else:
        conn.execute(
            "UPDATE bookmarks SET status = ?, last_chapter_read = ?, updated_at = ? WHERE id = ?",
            (status, last_chapter_read, now, existing_bm[0]),
        )
    conn.commit()


# --- intake family (spec-panel-v1b.md fase 3, add-a-manga) --------------------


def list_tracked_titles(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """`(title, status)` for every bookmarked manga — duplicate gates 2 and 3
    (design D3). A manga always has exactly one bookmark by construction, so
    this is one row per tracked title, not per manga_sites mapping."""
    return [
        tuple(row)
        for row in conn.execute(
            "SELECT m.title, b.status FROM bookmarks b JOIN mangas m ON m.id = b.manga_id"
        )
    ]


def write_manual_add(
    conn: sqlite3.Connection,
    *,
    title: str,
    site_id: int,
    slug: str,
    url: str,
    chapters,
    status: str,
    last_chapter_read: float,
    cover_url: str | None,
    now: str,
) -> tuple[int, int]:
    """`mangas` + `manga_sites` + `bookmarks` (+ `chapter_history`) in ONE
    transaction (spec.md "Confirm is atomic; any rejection leaves zero rows").

    `origin='manual'`, `progress_is_approx=0`, `status_changed_at=now` — a
    fresh bookmark's status just changed, by definition, at the moment it was
    created. `chapters` may be empty: `latest_chapter_num`/`_url`/`_at` stay
    NULL and no `chapter_history` row is written — a legitimate state the next
    `active_sweep` will seal once a chapter appears (design D5), not a dead
    row. `detected_via` reuses `seed_backfill`: the CHECK constraint admits no
    `'manual'`/`'panel'` value, so the existing value is reused, not invented.
    `last_read_at` stays NULL: an initial chapter is progress, not a reading
    event, and the `reading_history` trigger is UPDATE-only, so this INSERT
    fires it not at all.

    Returns `(manga_id, bookmark_id)`.
    """
    with transaction(conn):
        manga_id = conn.execute(
            "INSERT INTO mangas (title, cover_url, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (title, cover_url, now, now),
        ).lastrowid
        manga_site_id = conn.execute(
            "INSERT INTO manga_sites (manga_id, site_id, source_key, url, last_checked_at, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (manga_id, site_id, slug, url, now, now, now),
        ).lastrowid

        if chapters:
            newest = chapters[0]  # fetch_chapters returns newest-first
            conn.execute(
                "UPDATE manga_sites SET latest_chapter_num = ?, latest_chapter_url = ?, "
                "latest_chapter_at = ? WHERE id = ?",
                (newest.chapter_num, newest.url, newest.published_at, manga_site_id),
            )
            for chapter in chapters[:CHAPTER_HISTORY_LIMIT]:
                conn.execute(
                    "INSERT OR IGNORE INTO chapter_history "
                    "(manga_site_id, chapter_num, chapter_url, source_published_at, detected_at, detected_via) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (manga_site_id, chapter.chapter_num, chapter.url, chapter.published_at, now, IMPORT_DETECTED_VIA),
                )
        # else: latest_chapter_num/_url/_at stay NULL and no chapter_history
        # row is written (D5) — the row is indistinguishable from any other
        # NULL-latest mapping the sweep already knows how to handle.

        bookmark_id = conn.execute(
            "INSERT INTO bookmarks (manga_id, status, last_chapter_read, progress_is_approx, origin, "
            "last_read_at, status_changed_at, created_at, updated_at) "
            "VALUES (?, ?, ?, 0, ?, NULL, ?, ?, ?)",
            (manga_id, status, last_chapter_read, MANUAL_ORIGIN, now, now, now),
        ).lastrowid
    return manga_id, bookmark_id


# --- panel family (spec-panel-v1b.md fase 1) -----------------------------------

_PANEL_BOOKMARK_SELECT = (
    "SELECT b.id, b.manga_id, m.title, b.status, b.last_chapter_read, b.progress_is_approx, "
    "ms.url, ms.latest_chapter_num, ms.latest_chapter_url, ms.latest_chapter_at, b.last_read_at, "
    "b.status_changed_at, b.my_score "
    "FROM bookmarks b JOIN mangas m ON m.id = b.manga_id "
    # LEFT, not INNER: a manga can exist without a source mapping (a pending
    # Kitsu entry whose url was never pasted), and its bookmark must still
    # appear in the list — with the source-side columns as NULL.
    "LEFT JOIN manga_sites ms ON ms.manga_id = b.manga_id "
)


def _panel_bookmark_row(row) -> dict:
    (bookmark_id, manga_id, title, status, last_chapter_read, progress_is_approx,
     manga_url, latest_chapter_num, latest_chapter_url, latest_chapter_at, last_read_at,
     status_changed_at, my_score) = row
    # NULL on either side means "behind is unknowable", not zero: a bookmark
    # with no recorded progress is not magically caught up.
    #
    # Rounded to two decimals because chapter numbers are REAL — the source
    # publishes 32.2 and 45.5 — and IEEE 754 subtraction turns 32.2 - 11.0 into
    # 21.200000000000003, which reached the panel verbatim. Two decimals keep a
    # genuine half chapter honest while the artifact disappears.
    behind = (
        round(max(latest_chapter_num - last_chapter_read, 0), 2)
        if latest_chapter_num is not None and last_chapter_read is not None
        else None
    )
    return {
        "id": bookmark_id,
        "manga_id": manga_id,
        "title": title,
        "status": status,
        "last_chapter_read": last_chapter_read,
        "progress_is_approx": bool(progress_is_approx),
        # The manga's own page at the source, stored at insert time. Serialized
        # rather than derived: stripping the trailing segment off
        # `latest_chapter_url` would put the source's URL shape inside the
        # panel, and assembling source URLs is client knowledge (CLAUDE.md,
        # "the structural boundary"). Null for a bookmark with no manga_sites
        # row -- 66 of 236 in production, measured 2026-08-25. Today that
        # population is exactly the 66 terminal bookmarks (no sweep ever
        # visits one to learn a slug), but that is how these rows got here,
        # not a property of the terminal states themselves (panel-v1b-fase-4
        # design D5) -- a mapped `reading` manga marked `completed` from the
        # panel keeps its manga_sites row and this column stays non-null.
        "manga_url": manga_url,
        "latest_chapter_num": latest_chapter_num,
        "latest_chapter_url": latest_chapter_url,
        "latest_chapter_at": latest_chapter_at,
        "behind": behind,
        "last_read_at": last_read_at,
        "status_changed_at": status_changed_at,
        # NULL means unscored, an ordinary state for a title never rated on
        # Kitsu or in the panel -- not "zero" (panel-v1b-fase-4 design D1).
        "my_score": my_score,
    }


def list_panel_bookmarks(conn: sqlite3.Connection, status: str | None = None) -> list[dict]:
    """Every bookmark joined with its manga title and source-side chapter state,
    ordered by title so the list is stable across requests."""
    sql, params = _PANEL_BOOKMARK_SELECT, ()
    if status is not None:
        sql += "WHERE b.status = ? "
        params = (status,)
    return [_panel_bookmark_row(row) for row in conn.execute(sql + "ORDER BY m.title, b.id", params)]


def get_panel_bookmark(conn: sqlite3.Connection, bookmark_id: int) -> dict | None:
    row = conn.execute(_PANEL_BOOKMARK_SELECT + "WHERE b.id = ?", (bookmark_id,)).fetchone()
    return _panel_bookmark_row(row) if row else None


def update_panel_bookmark(
    conn: sqlite3.Connection, bookmark_id: int, *,
    last_chapter_read=UNSET, status=UNSET, my_score=UNSET, now: str
) -> bool:
    """Apply one panel edit: progress, status and/or score. Returns False when
    the bookmark does not exist. Commits — one edit is one transaction.

    `my_score`: `UNSET` = absent (leave the stored score alone), `None` = clear
    it to unscored, an `int` = set it. `None` is a legal *value* here, never a
    signal of absence -- that is what `UNSET` is for -- so the guard below
    MUST read `is not UNSET`, never `is not None`; the latter would make
    un-scoring silently unreachable (panel-v1b-fase-4 design D1).

    An edited progress is exact by definition, so `progress_is_approx` drops to
    0 and `last_read_at` is sealed with the edit's timestamp. Downward edits
    are legal and recorded as-is: the trigger keeps `previous_chapter_num` and
    the consumer treats a negative delta as a correction, not reading.

    The UPDATE fires `reading_history_capture_progress`, which hardcodes
    `origin='manual'` (direct SQLite edits must keep registering that), so the
    captured row is corrected to 'panel' here, inside the same transaction.
    The spec says `last_insert_rowid()` names that row, but it does not:
    SQLite reverts the value when a trigger program ends (verified against
    3.49), so trusting it would rewrite whatever unrelated row the connection
    inserted last — or nothing. Instead the correction targets ids above the
    pre-UPDATE ceiling, which inside this write transaction can only be the
    trigger's own INSERT. And only when the trigger actually fired: it skips
    an unchanged value, a NULL, and a status-only edit, and correcting on
    those would hit a row some earlier edit legitimately captured.
    """
    with transaction(conn):
        row = conn.execute(
            "SELECT manga_id, last_chapter_read, status FROM bookmarks WHERE id = ?",
            (bookmark_id,),
        ).fetchone()
        if row is None:
            return False
        manga_id, current_progress, current_status = row

        assignments, params = ["updated_at = ?"], [now]
        if last_chapter_read is not UNSET:
            assignments += ["last_chapter_read = ?", "progress_is_approx = 0", "last_read_at = ?"]
            params += [last_chapter_read, now]
        if status is not UNSET:
            assignments.append("status = ?")
            params.append(status)
            # Only a real transition is a transition. Re-picking the current
            # status in the dropdown must not reset the date, or "paused on"
            # would silently become "last time the select was touched".
            if status != current_status:
                assignments.append("status_changed_at = ?")
                params.append(now)
        if my_score is not UNSET:
            # `None` binds as SQL NULL and is never tested for here -- it is
            # the un-scoring value, not "nothing to do" (design D1).
            assignments.append("my_score = ?")
            params.append(my_score)

        # Mirrors the trigger's WHEN clause exactly: NEW IS NOT OLD AND NEW IS
        # NOT NULL. Any mismatch corrupts: correcting when the trigger stayed
        # silent rewrites an unrelated captured row's origin.
        trigger_fired = (
            last_chapter_read is not UNSET
            and last_chapter_read is not None
            and last_chapter_read != current_progress
        )
        ceiling = (
            conn.execute("SELECT COALESCE(MAX(id), 0) FROM reading_history").fetchone()[0]
            if trigger_fired
            else None
        )
        # Column names come from the literal lists above, never caller input.
        conn.execute(
            f"UPDATE bookmarks SET {', '.join(assignments)} WHERE id = ?", (*params, bookmark_id)
        )
        if trigger_fired:
            conn.execute(
                "UPDATE reading_history SET origin = ? WHERE id > ? AND manga_id = ?",
                (PANEL_ORIGIN, ceiling, manga_id),
            )
    return True


def set_bookmark_score(conn: sqlite3.Connection, manga_id: int, my_score: int, *, now: str) -> bool:
    """Fill an unscored bookmark from `import-scores`. Returns False, changing
    nothing, when it already had one.

    One statement, and that is the whole point (panel-v1b-fase-4 design D6):
    the fill-only-NULL guard lives in the WHERE clause, never in a Python
    read-then-write. The panel container serves the same SQLite file this
    importer writes to, so a read-then-write would be a real TOCTOU -- the
    owner could be typing a score in the browser while the import runs -- not
    a theoretical one. WAL plus `busy_timeout=5000` (db.py) handles the lock;
    this one conditional UPDATE is what closes the race itself.

    Commits -- each fill is its own transaction, safe to interleave with a
    concurrent panel edit.
    """
    with transaction(conn):
        cursor = conn.execute(
            "UPDATE bookmarks SET my_score = ?, updated_at = ? WHERE manga_id = ? AND my_score IS NULL",
            (my_score, now, manga_id),
        )
        return cursor.rowcount > 0


# --- history family (spec-panel-v1b.md fase 2) --------------------------------

# The fixed width `read_at`/`detected_at`/`source_published_at` are always
# stored in (`%Y-%m-%dT%H:%M:%SZ`, e.g. `_utc_now()` in web/app.py). Text
# comparison against a string in this same shape is exact and uses the
# `read_at` index — no SQL date function is trusted (CLAUDE.md: the
# production SQLite build lacks `chr()`, so its function set is untrusted).
_UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _parse_utc(value: str) -> datetime:
    return datetime.strptime(value, _UTC_FORMAT).replace(tzinfo=timezone.utc)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime(_UTC_FORMAT)


def reading_days(conn: sqlite3.Connection, *, days: int, timezone_name: str, now: str) -> dict:
    """Aggregate `reading_history` by LOCAL calendar day over the trailing
    `days` days ending today (design D2/D3).

    The window boundary and the grouping key both go through the same
    `ZoneInfo(timezone_name)` shift, applied to the row's UTC `read_at`
    BEFORE any grouping happens (spec "Local-Day Grouping Happens In The
    Backend, Before Aggregation, Via zoneinfo") — never a SQL date function.

    A day's `chapters` value sums only the POSITIVE deltas
    (`chapter_num - previous_chapter_num`); a downward correction
    (`chapter_num <= previous_chapter_num`) contributes zero to `chapters`
    but the row still counts toward that day's `edits` (design D5/D6) — the
    correction happened, it is just not "reading". A NULL
    `previous_chapter_num` (progress was unknown before this edit) is the
    same: `chapters` gets 0, `edits` still gets 1 (design D5) — a bookmark
    whose progress became known is bookkeeping, not a reading marathon.

    Rounded to two decimals for the same reason `_panel_bookmark_row`
    rounds `behind`: chapter numbers are REAL and IEEE 754 subtraction
    produces artifacts like `21.200000000000003`.

    Sparse output (design D8): only days with at least one row appear.
    """
    tz = ZoneInfo(timezone_name)
    now_utc = _parse_utc(now)
    local_today = now_utc.astimezone(tz).date()
    window_start_local_date = local_today - timedelta(days=days - 1)
    window_start_utc = _format_utc(datetime.combine(window_start_local_date, time.min, tzinfo=tz))

    rows = conn.execute(
        "SELECT chapter_num, previous_chapter_num, read_at FROM reading_history WHERE read_at >= ?",
        (window_start_utc,),
    ).fetchall()

    buckets: dict[str, list] = {}
    for chapter_num, previous_chapter_num, read_at in rows:
        local_date = _parse_utc(read_at).astimezone(tz).date().isoformat()
        bucket = buckets.setdefault(local_date, [0.0, 0])
        bucket[1] += 1
        if previous_chapter_num is not None and chapter_num > previous_chapter_num:
            bucket[0] += chapter_num - previous_chapter_num

    return {
        "timezone": timezone_name,
        "from": window_start_local_date.isoformat(),
        "to": local_today.isoformat(),
        "days": [
            {"date": local_date, "chapters": round(chapters, 2), "edits": edits}
            for local_date, (chapters, edits) in sorted(buckets.items())
        ],
    }


def manga_history(conn: sqlite3.Connection, manga_id: int) -> dict | None:
    """Interleave `reading_history` with `chapter_history` publications for one
    manga, chronological descending, tagged by `kind`. Returns `None` when the
    manga row itself does not exist — the caller turns that into a 404,
    distinguishing "no such manga" from "manga exists, nothing happened yet"
    (spec.md "404 for absent manga vs 200 + events: [] for a manga with
    none").

    A downward correction stays VISIBLE here with a negative `delta`
    (design D6) — the heatmap measures reading and excludes it, but this is
    history, and hiding a correction would misrepresent what happened.

    `publications_since` is the earliest `detected_at` across this manga's
    `chapter_history` rows, or `None` when there are none yet (design D9):
    `CHAPTER_HISTORY_LIMIT` only caps the one-time backfill, so completeness
    is bounded by when the mapping was learned, and a timestamp states that
    where a constant `is_partial` flag would carry no information.
    """
    row = conn.execute("SELECT title FROM mangas WHERE id = ?", (manga_id,)).fetchone()
    if row is None:
        return None
    title = row[0]

    events = []
    for chapter_num, previous_chapter_num, read_at, origin in conn.execute(
        "SELECT chapter_num, previous_chapter_num, read_at, origin "
        "FROM reading_history WHERE manga_id = ?",
        (manga_id,),
    ):
        delta = round(chapter_num - previous_chapter_num, 2) if previous_chapter_num is not None else None
        events.append(
            {
                "kind": "reading",
                "at": read_at,
                "chapter_num": chapter_num,
                "previous_chapter_num": previous_chapter_num,
                "delta": delta,
                "origin": origin,
            }
        )

    for chapter_num, chapter_url, source_published_at, detected_at, detected_via in conn.execute(
        "SELECT ch.chapter_num, ch.chapter_url, ch.source_published_at, ch.detected_at, ch.detected_via "
        "FROM chapter_history ch JOIN manga_sites ms ON ms.id = ch.manga_site_id WHERE ms.manga_id = ?",
        (manga_id,),
    ):
        events.append(
            {
                "kind": "publication",
                "at": source_published_at or detected_at,
                "chapter_num": chapter_num,
                "chapter_url": chapter_url,
                "source_published_at": source_published_at,
                "detected_via": detected_via,
            }
        )

    events.sort(key=lambda event: event["at"], reverse=True)

    publications_since = conn.execute(
        "SELECT MIN(ch.detected_at) FROM chapter_history ch JOIN manga_sites ms ON ms.id = ch.manga_site_id "
        "WHERE ms.manga_id = ?",
        (manga_id,),
    ).fetchone()[0]

    return {
        "manga_id": manga_id,
        "title": title,
        "publications_since": publications_since,
        "events": events,
    }


# --- cover family (one-off maintenance) ----------------------------------------


def list_cover_candidates(
    conn: sqlite3.Connection, *, statuses: tuple[str, ...] | None = None
) -> list[tuple[int, str, str, str | None]]:
    """(manga_id, title, source_key, cover_url) for every mapped manga in these
    statuses — including the ones that already have a cover_url.

    Deliberately not filtered to "cover_url IS NULL". Knowing the address of an
    image is not the same as having it: manganato's image hosts answer 403
    without a manganato Referer, so a stored URL can be a cover the panel can
    never render. Whether work is needed is decided by the caller, which is the
    only side that can see the local cache.

    INNER JOIN on manga_sites, not LEFT: a manga with no source mapping has no
    slug, so there is nowhere to ask and listing it would only produce a row the
    caller must skip. Terminal bookmarks are excluded by the caller's
    `statuses`, never here — this helper does not own that policy.
    """
    sql = (
        "SELECT m.id, m.title, ms.source_key, m.cover_url "
        "FROM mangas m "
        "JOIN manga_sites ms ON ms.manga_id = m.id "
        "JOIN bookmarks b ON b.manga_id = m.id "
    )
    params: tuple = ()
    if statuses:
        # Placeholders are generated from the tuple's length, never from its
        # contents; the values themselves stay bound.
        sql += f"WHERE b.status IN ({', '.join('?' * len(statuses))}) "
        params = statuses
    return [tuple(row) for row in conn.execute(sql + "ORDER BY m.title", params)]


def list_stored_url_cover_candidates(
    conn: sqlite3.Connection, *, statuses: tuple[str, ...]
) -> list[tuple[int, str, str | None]]:
    """(manga_id, title, cover_url) for every bookmark in these statuses.

    No `manga_sites` join, structurally: this route (panel-v1b-fase-4 design
    D5) may never ask the source anything, so it must never even hold a
    `source_key` in scope, not as a defensive check but because the query
    cannot produce one. Selects by `bookmarks.status` alone -- never by
    whether a mapping exists, so a bookmark that is both terminal and mapped
    (D5's "not an invariant" case) is still returned here, exactly once.

    Not filtered on `cover_url`: knowing whether a row is downloadable is a
    cost decision the caller makes per row, this helper only reports the
    population (mirrors `list_cover_candidates`'s same choice above).
    """
    sql = (
        "SELECT m.id, m.title, m.cover_url "
        "FROM mangas m "
        "JOIN bookmarks b ON b.manga_id = m.id "
        f"WHERE b.status IN ({', '.join('?' * len(statuses))}) "
        "ORDER BY m.title"
    )
    return [tuple(row) for row in conn.execute(sql, statuses)]


def set_manga_cover(conn: sqlite3.Connection, manga_id: int, cover_url: str, *, now: str) -> None:
    """Write one cover. Commits — a backfill interrupted halfway must keep the
    covers it already fetched, since each one cost a real request."""
    with transaction(conn):
        conn.execute(
            "UPDATE mangas SET cover_url = ?, updated_at = ? WHERE id = ?",
            (cover_url, now, manga_id),
        )
