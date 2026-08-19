import type { Bookmark, BookmarkStatus } from "./types";

/**
 * Per-tab ordering.
 *
 * The API returns the whole list ordered by title (repositories.py), which is
 * the right default for the tabs you browse. Two tabs are not browsed, they are
 * worked, and each has a date that answers "which of these did I touch last":
 * "Leyendo" has `last_read_at`, "En pausa" has `status_changed_at`.
 *
 * Sorting lives here rather than in SQL because the list is fetched whole and
 * filtered client-side, so the ordering is a property of the tab, not of the
 * request.
 */

/** Which date each tab is ordered by. Absent means "keep the API's title order". */
const TAB_DATE: Partial<Record<BookmarkStatus, keyof Bookmark>> = {
  reading: "last_read_at",
  on_hold: "status_changed_at",
};

/**
 * Most recent first, unknown last.
 *
 * A null date is not "old", it is unknown, so it cannot be folded into the
 * comparison as a zero — that would claim the manga was read, or paused, at the
 * epoch. Unknowns sink as a group and are ordered by title among themselves,
 * which is what keeps a tab where nothing is known yet looking deliberate
 * rather than shuffled.
 */
function byDateDesc(field: keyof Bookmark) {
  return (a: Bookmark, b: Bookmark): number => {
    const left = a[field] as string | null;
    const right = b[field] as string | null;
    if (left === null && right === null) {
      return a.title.localeCompare(b.title, "es");
    }
    if (left === null) return 1;
    if (right === null) return -1;
    // Compared as plain strings, not parsed as dates. That is safe only because
    // every writer in the backend emits the same fixed-width UTC format
    // (`%Y-%m-%dT%H:%M:%SZ` — web/app.py, scheduler.py, db.py, the schema
    // trigger, the importer), so lexicographic order is chronological order.
    // Mix a SQLite-style "YYYY-MM-DD HH:MM:SS" into a column and this breaks
    // silently, because a space sorts before "T".
    return right.localeCompare(left);
  };
}

export function sortBookmarksForTab(
  bookmarks: readonly Bookmark[],
  status: BookmarkStatus,
): Bookmark[] {
  const field = TAB_DATE[status];
  // Copied even when unsorted, so callers never receive the input array back
  // and cannot mutate it by accident.
  const copy = [...bookmarks];
  return field ? copy.sort(byDateDesc(field)) : copy;
}
