import type { Bookmark } from "./types";

/**
 * The combining-marks block, U+0300 to U+036F -- written with numeric
 * escapes, never pasted as the raw marks themselves. PROTO spells this
 * literally (its own comment: "looks empty in an editor because every
 * character in it is a mark that renders on top of the one before"), and an
 * invisible character class is exactly what a future formatter mangles
 * without a readable diff (design D10).
 */
const COMBINING_MARKS = /[\u0300-\u036f]/g;

function normalize(value: string): string {
  return value.normalize("NFD").replace(COMBINING_MARKS, "").toLowerCase();
}

/**
 * Pure, accent-insensitive substring match on `title` only (design D10).
 *
 * The "Todo" (global) search calls this identical function over the full
 * concatenated row set -- never a separate implementation (Requirement
 * "Search is a pure function over the full list"). An empty or
 * whitespace-only query returns every row, mirroring `sortBookmarks`' own
 * defensive copy so callers never receive the input array back.
 */
export function filterBookmarks(rows: readonly Bookmark[], query: string): Bookmark[] {
  const needle = normalize(query.trim());
  if (!needle) return [...rows];
  return rows.filter((row) => normalize(row.title).includes(needle));
}
