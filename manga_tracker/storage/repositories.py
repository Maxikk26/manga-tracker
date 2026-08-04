"""Parameterized query helpers for the seed loader's and the Kitsu importer's
writes — no slug or user value is ever interpolated into SQL.

Two write families live here and they are deliberately separate. The seed
family (`write_seed_backfill`) owns `origin='seed'`, `progress_is_approx=0`
and commits for itself. The Kitsu family below writes
`origin='kitsu_import'`, `progress_is_approx=1`, refuses to touch a bookmark
it does not own, and **never commits**: the importer wraps one whole entry in
a single transaction so a match rejected by verification leaves zero rows
(design D5).
"""

import json
import sqlite3

IMPORT_ORIGIN = "kitsu_import"
IMPORT_DETECTED_VIA = "seed_backfill"

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
