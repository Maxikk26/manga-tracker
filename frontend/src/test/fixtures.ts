import type { Bookmark } from "../domain/types";

/** Realistic wire-shaped bookmark; override per test.
 *
 * Timestamps use the exact format every backend writer emits
 * (`%Y-%m-%dT%H:%M:%SZ`). They used to be SQLite-style "YYYY-MM-DD HH:MM:SS",
 * which the API never sends — and a fixture that does not match the wire is a
 * hole, not a detail: the tab ordering compares these strings directly, and a
 * space sorts before "T".
 */
export function makeBookmark(overrides: Partial<Bookmark> = {}): Bookmark {
  return {
    id: 1,
    manga_id: 10,
    title: "One Piece",
    status: "reading",
    last_chapter_read: 1100,
    progress_is_approx: false,
    manga_url: "https://example.test/manga/one-piece",
    latest_chapter_num: 1120,
    latest_chapter_url: "https://example.test/one-piece/chapter-1120",
    latest_chapter_at: "2026-08-15T10:00:00Z",
    behind: 20,
    last_read_at: "2026-08-10T03:00:00Z",
    status_changed_at: null,
    my_score: null,
    ...overrides,
  };
}
