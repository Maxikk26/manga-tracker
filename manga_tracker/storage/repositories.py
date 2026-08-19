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

from manga_tracker.storage.db import transaction

IMPORT_ORIGIN = "kitsu_import"
IMPORT_DETECTED_VIA = "seed_backfill"
PANEL_ORIGIN = "panel"

# The bookmark status enum exactly as the schema CHECK declares it. The panel
# validates a request against this tuple before any SQL runs, so an invalid
# status is a 422 to the caller, never an IntegrityError from the database.
BOOKMARK_STATUSES = ("reading", "want_to_read", "completed", "on_hold", "dropped")

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


# --- panel family (spec-panel-v1b.md fase 1) -----------------------------------

_PANEL_BOOKMARK_SELECT = (
    "SELECT b.id, b.manga_id, m.title, b.status, b.last_chapter_read, b.progress_is_approx, "
    "ms.latest_chapter_num, ms.latest_chapter_url, ms.latest_chapter_at, b.last_read_at, "
    "b.status_changed_at "
    "FROM bookmarks b JOIN mangas m ON m.id = b.manga_id "
    # LEFT, not INNER: a manga can exist without a source mapping (a pending
    # Kitsu entry whose url was never pasted), and its bookmark must still
    # appear in the list — with the source-side columns as NULL.
    "LEFT JOIN manga_sites ms ON ms.manga_id = b.manga_id "
)


def _panel_bookmark_row(row) -> dict:
    (bookmark_id, manga_id, title, status, last_chapter_read, progress_is_approx,
     latest_chapter_num, latest_chapter_url, latest_chapter_at, last_read_at,
     status_changed_at) = row
    # NULL on either side means "behind is unknowable", not zero: a bookmark
    # with no recorded progress is not magically caught up.
    behind = (
        max(latest_chapter_num - last_chapter_read, 0)
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
        "latest_chapter_num": latest_chapter_num,
        "latest_chapter_url": latest_chapter_url,
        "latest_chapter_at": latest_chapter_at,
        "behind": behind,
        "last_read_at": last_read_at,
        "status_changed_at": status_changed_at,
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
    conn: sqlite3.Connection, bookmark_id: int, *, last_chapter_read=UNSET, status=UNSET, now: str
) -> bool:
    """Apply one panel edit: progress and/or status. Returns False when the
    bookmark does not exist. Commits — one edit is one transaction.

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


def set_manga_cover(conn: sqlite3.Connection, manga_id: int, cover_url: str, *, now: str) -> None:
    """Write one cover. Commits — a backfill interrupted halfway must keep the
    covers it already fetched, since each one cost a real request."""
    with transaction(conn):
        conn.execute(
            "UPDATE mangas SET cover_url = ?, updated_at = ? WHERE id = ?",
            (cover_url, now, manga_id),
        )
