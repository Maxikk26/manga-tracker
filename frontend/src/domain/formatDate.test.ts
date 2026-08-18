import { describe, expect, it } from "vitest";
import { formatLocalDate, formatLocalDateTime } from "./formatDate";

// These tests assume TZ=America/Caracas (UTC-4), pinned in vite.config.ts.
// Without that pin the day-boundary cases below would assert nothing.

describe("formatLocalDateTime", () => {
  it("renders a null timestamp as an em dash", () => {
    expect(formatLocalDateTime(null)).toBe("—");
  });

  it("renders an unparseable timestamp as an em dash", () => {
    expect(formatLocalDateTime("not a date")).toBe("—");
  });

  it("keeps the clock time", () => {
    expect(formatLocalDateTime("2026-08-17 14:30:00")).toContain(":");
  });

  // es-VE formats on a 12-hour clock and separates the meridiem with a narrow
  // no-break space (U+202F), so these assert on the hour rather than on
  // "a. m." / "p. m." — a literal typed with an ordinary space never matches.

  it("treats a SQLite timestamp with no offset as UTC, not as local time", () => {
    // 14:30 UTC is 10:30 in Caracas. Read as local time it would stay 02:30.
    const formatted = formatLocalDateTime("2026-08-17 14:30:00");
    expect(formatted).toContain("10:30");
    expect(formatted).not.toContain("02:30");
  });

  it("honours an explicit offset instead of forcing UTC", () => {
    // 14:30-04:00 is already Caracas time; it must not shift again, so it
    // stays 02:30 rather than sliding to 10:30.
    const formatted = formatLocalDateTime("2026-08-17T14:30:00-04:00");
    expect(formatted).toContain("02:30");
    expect(formatted).not.toContain("10:30");
  });
});

describe("formatLocalDate", () => {
  it("renders a null timestamp as an em dash", () => {
    expect(formatLocalDate(null)).toBe("—");
  });

  it("drops the clock time", () => {
    expect(formatLocalDate("2026-08-17 14:30:00")).not.toContain(":");
  });

  it("converts to local time before reading the day, not after", () => {
    // 02:00 UTC on the 18th is 22:00 on the 17th in Caracas. Reading the day
    // off the UTC string would report the 18th and put a late-evening read on
    // the wrong calendar day.
    const formatted = formatLocalDate("2026-08-18 02:00:00");
    expect(formatted).toContain("17");
    expect(formatted).not.toContain("18");
  });

  it("keeps the same day when the conversion does not cross midnight", () => {
    expect(formatLocalDate("2026-08-17 14:30:00")).toContain("17");
  });
});
