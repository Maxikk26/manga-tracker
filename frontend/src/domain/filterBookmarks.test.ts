import { describe, expect, it } from "vitest";
import { filterBookmarks } from "./filterBookmarks";
import type { Bookmark } from "./types";

function bookmark(id: number, title: string): Bookmark {
  return {
    id,
    manga_id: id,
    title,
    status: "reading",
    last_chapter_read: 1,
    progress_is_approx: false,
    manga_url: null,
    latest_chapter_num: 1,
    latest_chapter_url: null,
    latest_chapter_at: null,
    behind: null,
    last_read_at: null,
    status_changed_at: null,
    my_score: null,
  };
}

const titlesOf = (rows: readonly Bookmark[]) => rows.map((r) => r.title);

describe("filterBookmarks", () => {
  it("matches a query with accents against a title without them", () => {
    const rows = [bookmark(1, "Solo Leveling"), bookmark(2, "Kimetsu no Yaiba")];
    expect(titlesOf(filterBookmarks(rows, "leveling"))).toEqual(["Solo Leveling"]);
  });

  it("matches a query without accents against a title that carries them", () => {
    const rows = [bookmark(1, "Berserk"), bookmark(2, "Águila Roja")];
    expect(titlesOf(filterBookmarks(rows, "aguila"))).toEqual(["Águila Roja"]);
  });

  it("matches a query with accents against a title that carries different ones too", () => {
    // Both directions of the same accent-insensitivity rule, in one call:
    // the needle and the haystack each carry a diacritic the other lacks.
    const rows = [bookmark(1, "Águila Roja")];
    expect(titlesOf(filterBookmarks(rows, "águíla"))).toEqual(["Águila Roja"]);
  });

  it("is case-insensitive", () => {
    const rows = [bookmark(1, "One Piece")];
    expect(titlesOf(filterBookmarks(rows, "ONE piece"))).toEqual(["One Piece"]);
  });

  it("matches as a substring, not only a prefix", () => {
    const rows = [bookmark(1, "The Regressed Mercenary")];
    expect(titlesOf(filterBookmarks(rows, "regressed"))).toEqual(["The Regressed Mercenary"]);
  });

  it("returns every row for an empty query", () => {
    const rows = [bookmark(1, "Alfa"), bookmark(2, "Bravo")];
    expect(filterBookmarks(rows, "")).toEqual(rows);
  });

  it("returns every row for a whitespace-only query", () => {
    const rows = [bookmark(1, "Alfa"), bookmark(2, "Bravo")];
    expect(filterBookmarks(rows, "   ")).toEqual(rows);
  });

  it("returns an empty array when nothing matches", () => {
    const rows = [bookmark(1, "Alfa"), bookmark(2, "Bravo")];
    expect(filterBookmarks(rows, "zzz")).toEqual([]);
  });

  it("never returns the caller's own array, even for an empty query", () => {
    const rows = [bookmark(1, "Alfa")];
    expect(filterBookmarks(rows, "")).not.toBe(rows);
  });

  it("does not mutate the input array", () => {
    const rows = [bookmark(1, "Alfa"), bookmark(2, "Bravo")];
    const copy = [...rows];
    filterBookmarks(rows, "alfa");
    expect(rows).toEqual(copy);
  });
});
