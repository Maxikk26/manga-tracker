import type { Bookmark } from "../domain/types";

/** Realistic wire-shaped bookmark; override per test. */
export function makeBookmark(overrides: Partial<Bookmark> = {}): Bookmark {
  return {
    id: 1,
    manga_id: 10,
    title: "One Piece",
    status: "reading",
    last_chapter_read: 1100,
    progress_is_approx: false,
    latest_chapter_num: 1120,
    latest_chapter_url: "https://example.test/one-piece/chapter-1120",
    latest_chapter_at: "2026-08-15 10:00:00",
    behind: 20,
    last_read_at: "2026-08-10 03:00:00",
    ...overrides,
  };
}
