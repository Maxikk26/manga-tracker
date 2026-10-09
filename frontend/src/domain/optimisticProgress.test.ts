import { describe, expect, it } from "vitest";
import { applyOptimisticProgress, withOptimisticProgress } from "./optimisticProgress";
import { isCaughtUp } from "./sortBookmarks";
import { makeBookmark } from "../test/fixtures";

describe("withOptimisticProgress", () => {
  it("reaching the latest detected chapter makes the row caught up", () => {
    const row = makeBookmark({ last_chapter_read: 99, latest_chapter_num: 100, behind: 1 });
    const optimistic = withOptimisticProgress(row, 100);
    expect(optimistic.last_chapter_read).toBe(100);
    expect(optimistic.behind).toBe(0);
    expect(isCaughtUp(optimistic)).toBe(true);
  });

  it("reading past the latest detected chapter floors behind at zero, like the API", () => {
    const row = makeBookmark({ last_chapter_read: 99, latest_chapter_num: 100, behind: 1 });
    expect(withOptimisticProgress(row, 105).behind).toBe(0);
  });

  it("stays behind when the new value is still short of the latest chapter", () => {
    const row = makeBookmark({ last_chapter_read: 90, latest_chapter_num: 100, behind: 10 });
    const optimistic = withOptimisticProgress(row, 95);
    expect(optimistic.behind).toBe(5);
    expect(isCaughtUp(optimistic)).toBe(false);
  });

  it("an unknown latest chapter keeps behind unknown -- never guessed as caught up", () => {
    const row = makeBookmark({ last_chapter_read: 5, latest_chapter_num: null, behind: null });
    const optimistic = withOptimisticProgress(row, 500);
    expect(optimistic.behind).toBeNull();
    expect(isCaughtUp(optimistic)).toBe(false);
  });

  it("rounds to two decimals, as the API does for REAL chapter numbers", () => {
    const row = makeBookmark({ last_chapter_read: 1, latest_chapter_num: 32.2, behind: 31.2 });
    expect(withOptimisticProgress(row, 11).behind).toBe(21.2);
  });

  it("never mutates the input row", () => {
    const row = makeBookmark({ last_chapter_read: 99, latest_chapter_num: 100, behind: 1 });
    withOptimisticProgress(row, 100);
    expect(row.last_chapter_read).toBe(99);
    expect(row.behind).toBe(1);
  });
});

describe("applyOptimisticProgress", () => {
  const rows = [
    makeBookmark({ id: 1, last_chapter_read: 99, latest_chapter_num: 100, behind: 1 }),
    makeBookmark({ id: 2, last_chapter_read: 10, latest_chapter_num: 50, behind: 40 }),
  ];

  it("returns the very same array when nothing is pending, so memoized cards do not re-render", () => {
    expect(applyOptimisticProgress(rows, new Map())).toBe(rows);
  });

  it("overrides only the pending rows and keeps every other row's identity", () => {
    const result = applyOptimisticProgress(rows, new Map([[1, 100]]));
    expect(result[0].behind).toBe(0);
    expect(result[1]).toBe(rows[1]);
  });

  it("ignores a pending id that is not in the list", () => {
    const result = applyOptimisticProgress(rows, new Map([[999, 1]]));
    expect(result).toEqual(rows);
  });
});
