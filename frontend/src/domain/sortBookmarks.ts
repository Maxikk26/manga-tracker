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

/**
 * Nothing left to read.
 *
 * `behind === 0` and only that. A null `behind` means the source side is
 * unknown — no mapping, or nothing detected yet — and "I cannot tell" is not
 * "I am up to date", so an unknown stays with the actionable ones rather than
 * being filed away as done.
 *
 * Exported (fase 5 slice 2a, design D9) so the card's fade, its "Al día"
 * chip and this sorter share one definition instead of three copies of
 * `behind === 0` drifting independently.
 */
export function isCaughtUp(bookmark: Bookmark): boolean {
  return bookmark.behind === 0;
}

export function sortBookmarksForTab(
  bookmarks: readonly Bookmark[],
  status: BookmarkStatus,
): Bookmark[] {
  const field = TAB_DATE[status];
  // Copied even when unsorted, so callers never receive the input array back
  // and cannot mutate it by accident.
  const copy = [...bookmarks];
  if (!field) return copy;

  const byDate = byDateDesc(field);

  if (status !== "reading") return copy.sort(byDate);

  // "Leyendo" asks one question before any other: what do I still have to
  // read. A manga you are caught up on is not an item on that list, so it
  // sinks below every manga with chapters pending, whatever the dates say.
  // Inside each group the date ordering still decides.
  return copy.sort((a, b) => {
    const caughtUp = Number(isCaughtUp(a)) - Number(isCaughtUp(b));
    return caughtUp !== 0 ? caughtUp : byDate(a, b);
  });
}

/**
 * Re-sequences `rows` to match a previously-captured `ids` order (fase 5
 * slice 2a, design D4) -- the ordering freeze while a popover is open.
 *
 * Ids, never row objects: freezing the objects would freeze their *values*
 * too, so an open chapter panel would sit over a card still showing the old
 * number -- the card must keep repainting from fresh props while only its
 * *position* stays put. A row whose id is not in `ids` is appended after the
 * frozen sequence (a fresh row from a refetch, e.g. one just added); a
 * frozen id no longer present in `rows` is silently dropped (e.g. removed
 * upstream). Never throws, never mutates either input.
 */
export function applyFrozenOrder(
  rows: readonly Bookmark[],
  ids: readonly number[],
): Bookmark[] {
  const byId = new Map(rows.map((row) => [row.id, row] as const));
  const ordered: Bookmark[] = [];
  for (const id of ids) {
    const row = byId.get(id);
    if (row) {
      ordered.push(row);
      byId.delete(id);
    }
  }
  // Whatever is left in `byId` was never in the frozen sequence -- append it
  // in the order it arrived in `rows`.
  for (const row of rows) {
    if (byId.has(row.id)) ordered.push(row);
  }
  return ordered;
}
