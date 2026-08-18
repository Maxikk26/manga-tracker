import { describe, expect, it } from "vitest";
import { sortBookmarksForTab } from "./sortBookmarks";
import type { Bookmark, BookmarkStatus } from "./types";

function bookmark(
  id: number,
  title: string,
  last_read_at: string | null,
  status: BookmarkStatus = "reading",
): Bookmark {
  return {
    id,
    manga_id: id,
    title,
    status,
    last_chapter_read: 1,
    progress_is_approx: false,
    latest_chapter_num: 1,
    latest_chapter_url: null,
    latest_chapter_at: null,
    behind: null,
    last_read_at,
  };
}

const titlesOf = (list: readonly Bookmark[]) => list.map((b) => b.title);

describe("sortBookmarksForTab: reading", () => {
  it("puts the most recently read first", () => {
    const sorted = sortBookmarksForTab(
      [
        bookmark(1, "Vieja", "2026-08-01T10:00:00Z"),
        bookmark(2, "Reciente", "2026-08-17T10:00:00Z"),
        bookmark(3, "Media", "2026-08-10T10:00:00Z"),
      ],
      "reading",
    );
    expect(titlesOf(sorted)).toEqual(["Reciente", "Media", "Vieja"]);
  });

  it("sinks never-read bookmarks to the bottom", () => {
    const sorted = sortBookmarksForTab(
      [
        bookmark(1, "Sin fecha", null),
        bookmark(2, "Con fecha", "2026-08-01T10:00:00Z"),
      ],
      "reading",
    );
    expect(titlesOf(sorted)).toEqual(["Con fecha", "Sin fecha"]);
  });

  it("does not treat a null date as the epoch", () => {
    // The failure this guards: folding null into the comparison as 0 or ""
    // would sort the never-read one as the oldest read, which is the same
    // position by luck here — so assert the whole order with a date old
    // enough that only correct null handling produces it.
    const sorted = sortBookmarksForTab(
      [
        bookmark(1, "Nunca leido", null),
        bookmark(2, "Leido en 1970", "1970-01-01T00:00:00Z"),
        bookmark(3, "Leido ayer", "2026-08-17T10:00:00Z"),
      ],
      "reading",
    );
    expect(titlesOf(sorted)).toEqual(["Leido ayer", "Leido en 1970", "Nunca leido"]);
  });

  it("orders never-read bookmarks among themselves by title", () => {
    const sorted = sortBookmarksForTab(
      [bookmark(1, "Zorro", null), bookmark(2, "Alfa", null), bookmark(3, "Medio", null)],
      "reading",
    );
    expect(titlesOf(sorted)).toEqual(["Alfa", "Medio", "Zorro"]);
  });

  it("keeps the whole tab stable when nothing has been read yet", () => {
    // Production state on day one: last_read_at is null for every reading
    // bookmark, so the tab must fall back to title order rather than to the
    // arbitrary order the rows arrived in.
    const sorted = sortBookmarksForTab(
      [bookmark(1, "Charlie", null), bookmark(2, "Alfa", null), bookmark(3, "Bravo", null)],
      "reading",
    );
    expect(titlesOf(sorted)).toEqual(["Alfa", "Bravo", "Charlie"]);
  });
});

describe("sortBookmarksForTab: other tabs", () => {
  it("keeps the API's title ordering untouched", () => {
    const input = [
      bookmark(1, "Alfa", "2026-08-01T10:00:00Z", "on_hold"),
      bookmark(2, "Bravo", "2026-08-17T10:00:00Z", "on_hold"),
    ];
    expect(titlesOf(sortBookmarksForTab(input, "on_hold"))).toEqual(["Alfa", "Bravo"]);
  });

  it("never returns the caller's array", () => {
    const input = [bookmark(1, "Alfa", null, "completed")];
    expect(sortBookmarksForTab(input, "completed")).not.toBe(input);
  });

  it("does not mutate the input", () => {
    const input = [
      bookmark(1, "Vieja", "2026-08-01T10:00:00Z"),
      bookmark(2, "Reciente", "2026-08-17T10:00:00Z"),
    ];
    sortBookmarksForTab(input, "reading");
    expect(titlesOf(input)).toEqual(["Vieja", "Reciente"]);
  });
});
