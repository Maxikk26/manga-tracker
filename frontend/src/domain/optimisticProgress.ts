import type { Bookmark } from "./types";

/**
 * The row as it will look once a chapter save lands, shown while the PATCH
 * and its refetch are still in flight -- so the caught-up fade and the
 * "Al día" chip appear on commit instead of a couple of seconds later.
 *
 * `behind` mirrors the API's own formula (`_panel_bookmark_row` in
 * storage/repositories.py): `latest - read`, floored at zero, rounded to two
 * decimals because chapter numbers are REAL. An unknown latest chapter keeps
 * `behind` unknown -- "I cannot tell" is never guessed as caught up.
 *
 * This is a preview, not a second source of truth: the container drops it
 * the moment the server answers, whatever the server says.
 */
export function withOptimisticProgress(bookmark: Bookmark, lastChapterRead: number): Bookmark {
  const behind =
    bookmark.latest_chapter_num === null
      ? null
      : Math.round(Math.max(bookmark.latest_chapter_num - lastChapterRead, 0) * 100) / 100;
  return { ...bookmark, last_chapter_read: lastChapterRead, behind };
}

/**
 * Applies every pending chapter save to the fetched list. Rows without a
 * pending save keep their identity, and an empty `pending` returns `rows`
 * itself, so the memoized cards only re-render for the row being edited.
 */
export function applyOptimisticProgress(
  rows: Bookmark[],
  pending: ReadonlyMap<number, number>,
): Bookmark[] {
  if (pending.size === 0) return rows;
  return rows.map((row) => {
    const value = pending.get(row.id);
    return value === undefined ? row : withOptimisticProgress(row, value);
  });
}
