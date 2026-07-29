"""Parameterized query helpers for the seed loader's per-row write — no slug or user value is ever interpolated into SQL."""

import sqlite3


def find_manga_site_by_slug(conn: sqlite3.Connection, site_id: int, slug: str) -> tuple[int, int] | None:
    row = conn.execute(
        "SELECT manga_id, id FROM manga_sites WHERE site_id = ? AND source_key = ?", (site_id, slug)
    ).fetchone()
    return (row[0], row[1]) if row else None


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
