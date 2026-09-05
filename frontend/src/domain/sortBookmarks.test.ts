import { describe, expect, it } from "vitest";
import { applyFrozenOrder, sortBookmarksForAll, sortBookmarksForTab } from "./sortBookmarks";
import { BOOKMARK_STATUSES, type Bookmark, type BookmarkStatus } from "./types";

function bookmark(
  id: number,
  title: string,
  last_read_at: string | null,
  status: BookmarkStatus = "reading",
  status_changed_at: string | null = null,
): Bookmark {
  return {
    id,
    manga_id: id,
    title,
    status,
    last_chapter_read: 1,
    progress_is_approx: false,
    manga_url: null,
    latest_chapter_num: 1,
    latest_chapter_url: null,
    latest_chapter_at: null,
    behind: null,
    last_read_at,
    status_changed_at,
    my_score: null,
  };
}

function paused(id: number, title: string, status_changed_at: string | null): Bookmark {
  return bookmark(id, title, null, "on_hold", status_changed_at);
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

describe("sortBookmarksForTab: on_hold", () => {
  it("puts the most recently paused first", () => {
    const sorted = sortBookmarksForTab(
      [
        paused(1, "Pausada hace tiempo", "2026-08-01T10:00:00Z"),
        paused(2, "Pausada ayer", "2026-08-17T10:00:00Z"),
      ],
      "on_hold",
    );
    expect(titlesOf(sorted)).toEqual(["Pausada ayer", "Pausada hace tiempo"]);
  });

  it("sinks the rows whose pause date is unknown", () => {
    // Production state: all 141 historical on_hold rows carry NULL, because
    // migration 2 refused to invent a date for them.
    const sorted = sortBookmarksForTab(
      [paused(1, "Historica", null), paused(2, "Pausada hoy", "2026-08-17T10:00:00Z")],
      "on_hold",
    );
    expect(titlesOf(sorted)).toEqual(["Pausada hoy", "Historica"]);
  });

  it("falls back to title order while every pause date is unknown", () => {
    const sorted = sortBookmarksForTab(
      [paused(1, "Charlie", null), paused(2, "Alfa", null), paused(3, "Bravo", null)],
      "on_hold",
    );
    expect(titlesOf(sorted)).toEqual(["Alfa", "Bravo", "Charlie"]);
  });

  it("ignores last_read_at, which answers a different question", () => {
    // A paused manga can have been read recently and paused long ago. The tab
    // must order by the pause, not by the reading.
    const sorted = sortBookmarksForTab(
      [
        bookmark(1, "Leida ayer, pausada hace meses", "2026-08-17T10:00:00Z", "on_hold", "2026-06-01T10:00:00Z"),
        bookmark(2, "Leida hace meses, pausada ayer", "2026-06-01T10:00:00Z", "on_hold", "2026-08-17T10:00:00Z"),
      ],
      "on_hold",
    );
    expect(titlesOf(sorted)).toEqual([
      "Leida hace meses, pausada ayer",
      "Leida ayer, pausada hace meses",
    ]);
  });
});

describe("sortBookmarksForTab: browsed tabs", () => {
  it("keeps the API's title ordering untouched", () => {
    const input = [
      bookmark(1, "Alfa", "2026-08-01T10:00:00Z", "completed"),
      bookmark(2, "Bravo", "2026-08-17T10:00:00Z", "completed"),
    ];
    expect(titlesOf(sortBookmarksForTab(input, "completed"))).toEqual(["Alfa", "Bravo"]);
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

describe("sortBookmarksForTab: reading puts what you owe first", () => {
  const withBehind = (
    id: number,
    title: string,
    behind: number | null,
    last_read_at: string | null = null,
  ): Bookmark => ({ ...bookmark(id, title, last_read_at), behind });

  it("sinks the caught-up ones below everything pending", () => {
    // The tab answers "what do I still have to read". A manga with nothing
    // pending is not on that list, however recently it was read.
    const sorted = sortBookmarksForTab(
      [
        withBehind(1, "Al dia, leido hoy", 0, "2026-08-19T10:00:00Z"),
        withBehind(2, "Pendiente, leido hace meses", 5, "2026-06-01T10:00:00Z"),
      ],
      "reading",
    );
    expect(titlesOf(sorted)).toEqual(["Pendiente, leido hace meses", "Al dia, leido hoy"]);
  });

  it("keeps the date ordering inside each group", () => {
    const sorted = sortBookmarksForTab(
      [
        withBehind(1, "Al dia viejo", 0, "2026-06-01T10:00:00Z"),
        withBehind(2, "Pendiente viejo", 3, "2026-06-01T10:00:00Z"),
        withBehind(3, "Al dia reciente", 0, "2026-08-18T10:00:00Z"),
        withBehind(4, "Pendiente reciente", 3, "2026-08-18T10:00:00Z"),
      ],
      "reading",
    );
    expect(titlesOf(sorted)).toEqual([
      "Pendiente reciente",
      "Pendiente viejo",
      "Al dia reciente",
      "Al dia viejo",
    ]);
  });

  it("does not file an unknown behind away as caught up", () => {
    // No mapping or nothing detected yet. "I cannot tell" is not "I am up to
    // date", so it stays with the actionable ones.
    const sorted = sortBookmarksForTab(
      [withBehind(1, "Al dia", 0), withBehind(2, "Desconocido", null)],
      "reading",
    );
    expect(titlesOf(sorted)).toEqual(["Desconocido", "Al dia"]);
  });

  it("leaves the paused tab ordered by its own date, not by what is pending", () => {
    // Being behind is not what "En pausa" is asking about.
    const sorted = sortBookmarksForTab(
      [
        bookmark(1, "Pausada ayer", null, "on_hold", "2026-08-18T10:00:00Z"),
        bookmark(2, "Pausada en junio", null, "on_hold", "2026-06-01T10:00:00Z"),
      ].map((b, i) => ({ ...b, behind: i === 0 ? 0 : 9 })),
      "on_hold",
    );
    expect(titlesOf(sorted)).toEqual(["Pausada ayer", "Pausada en junio"]);
  });
});

describe("sortBookmarksForAll", () => {
  // One bookmark per status, each carrying data that would make a global
  // (non-contiguous) sort visibly reorder them across tabs -- caught-up
  // "reading" rows sink within "reading", `on_hold` orders by its own
  // pause date, etc.
  const rows: Bookmark[] = [
    { ...bookmark(1, "Reading caught up", "2026-08-18T10:00:00Z"), behind: 0 },
    { ...bookmark(2, "Reading behind", "2026-08-01T10:00:00Z"), behind: 5 },
    bookmark(3, "Want to read", null, "want_to_read"),
    bookmark(4, "Completed", null, "completed"),
    paused(5, "On hold recent", "2026-08-17T10:00:00Z"),
    paused(6, "On hold old", "2026-06-01T10:00:00Z"),
    bookmark(7, "Dropped", null, "dropped"),
  ];

  it("groups the output contiguously by BOOKMARK_STATUSES order", () => {
    const result = sortBookmarksForAll(rows);
    const statusesSeen = result.map((row) => row.status);
    // Contiguous: once a status' block ends, it never reappears later.
    const firstSeenAt = new Map<BookmarkStatus, number>();
    statusesSeen.forEach((status, index) => {
      if (!firstSeenAt.has(status)) firstSeenAt.set(status, index);
    });
    const order = [...firstSeenAt.entries()].sort((a, b) => a[1] - b[1]).map(([s]) => s);
    expect(order).toEqual(
      BOOKMARK_STATUSES.filter((status) => statusesSeen.includes(status)),
    );
    let lastIndexOfPreviousBlock = -1;
    for (const status of order) {
      const indices = statusesSeen
        .map((s, i) => (s === status ? i : -1))
        .filter((i) => i !== -1);
      expect(Math.min(...indices)).toBeGreaterThan(lastIndexOfPreviousBlock);
      lastIndexOfPreviousBlock = Math.max(...indices);
    }
  });

  it("matches, per status, the output of that status' own sortBookmarksForTab -- the property " +
    "that guards against PROTO's global-partition bug ever creeping back in", () => {
    const result = sortBookmarksForAll(rows);
    for (const status of BOOKMARK_STATUSES) {
      const fromAll = result.filter((row) => row.status === status);
      const fromTab = sortBookmarksForTab(
        rows.filter((row) => row.status === status),
        status,
      );
      expect(fromAll).toEqual(fromTab);
    }
  });

  it("never returns the caller's array", () => {
    expect(sortBookmarksForAll(rows)).not.toBe(rows);
  });
});

describe("applyFrozenOrder", () => {
  const rowsAbc = [
    bookmark(1, "Alfa", null),
    bookmark(2, "Bravo", null),
    bookmark(3, "Charlie", null),
  ];

  it("reorders rows to match the frozen id sequence", () => {
    const result = applyFrozenOrder(rowsAbc, [3, 1, 2]);
    expect(titlesOf(result)).toEqual(["Charlie", "Alfa", "Bravo"]);
  });

  it("appends a row whose id is absent from the frozen sequence, in its input order", () => {
    // A refetch can add a row (a new bookmark, or one leaving another tab)
    // that the freeze never saw -- it must not vanish, and it must not
    // jump ahead of the frozen sequence either.
    const result = applyFrozenOrder(rowsAbc, [2, 1]);
    expect(titlesOf(result)).toEqual(["Bravo", "Alfa", "Charlie"]);
  });

  it("silently drops a frozen id no longer present in rows", () => {
    // Id 9 was frozen (a row that has since been removed upstream) and must
    // not throw or leave a gap; Bravo was never frozen, so it still gets
    // appended after the frozen sequence like any other unlisted row.
    const result = applyFrozenOrder(rowsAbc, [9, 3, 1]);
    expect(titlesOf(result)).toEqual(["Charlie", "Alfa", "Bravo"]);
  });

  it("returns the input order unchanged for an empty id list", () => {
    const result = applyFrozenOrder(rowsAbc, []);
    expect(titlesOf(result)).toEqual(["Alfa", "Bravo", "Charlie"]);
  });

  it("never mutates the input array", () => {
    const copy = [...rowsAbc];
    applyFrozenOrder(rowsAbc, [3, 2, 1]);
    expect(rowsAbc).toEqual(copy);
  });
});
