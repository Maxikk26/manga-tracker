import type { Bookmark, BookmarkStatus } from "./types";

/**
 * Per-tab ordering.
 *
 * The API returns the whole list ordered by title (repositories.py), which is
 * the right default for the tabs you browse. "Leyendo" is not browsed, it is
 * worked: the manga you touched last is the one you are most likely to touch
 * again, so it goes on top.
 *
 * Sorting lives here rather than in SQL because the list is fetched whole and
 * filtered client-side, so the ordering is a property of the tab, not of the
 * request.
 */

/**
 * Most recently read first, never-read last.
 *
 * A null `last_read_at` is not "old", it is unknown, so it cannot be folded
 * into the date comparison as a zero — that would claim the manga was read at
 * the epoch. Unknowns sink as a group and are ordered by title among
 * themselves.
 */
function byLastReadDesc(a: Bookmark, b: Bookmark): number {
  if (a.last_read_at === null && b.last_read_at === null) {
    return a.title.localeCompare(b.title, "es");
  }
  if (a.last_read_at === null) return 1;
  if (b.last_read_at === null) return -1;
  // Compared as plain strings, not parsed as dates. That is safe only because
  // every writer in the backend emits the same fixed-width UTC format
  // (`%Y-%m-%dT%H:%M:%SZ` — web/app.py, scheduler.py, db.py, the schema
  // trigger, the importer), so lexicographic order is chronological order.
  // Mix a SQLite-style "YYYY-MM-DD HH:MM:SS" into the column and this breaks
  // silently, because a space sorts before "T".
  return b.last_read_at.localeCompare(a.last_read_at);
}

export function sortBookmarksForTab(
  bookmarks: readonly Bookmark[],
  status: BookmarkStatus,
): Bookmark[] {
  if (status === "reading") {
    return [...bookmarks].sort(byLastReadDesc);
  }
  // Every other tab keeps the API's title ordering. Copied anyway so callers
  // never receive the input array back and cannot mutate it by accident.
  return [...bookmarks];
}
