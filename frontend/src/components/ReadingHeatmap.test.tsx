import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ReadingHeatmap } from "./ReadingHeatmap";
import type { ReadingHistoryResponse } from "../domain/types";

const data: ReadingHistoryResponse = {
  timezone: "America/Caracas",
  from: "2026-08-01",
  to: "2026-08-21",
  days: [
    { date: "2026-08-19", chapters: 2, edits: 1 },
    { date: "2026-08-20", chapters: 0.5, edits: 1 },
  ],
};

describe("ReadingHeatmap", () => {
  it("renders one cell per active day, with the right local date and chapter count in its accessible label", () => {
    render(<ReadingHeatmap data={data} />);

    // The API already resolved the local calendar day (2026-08-20T03:30:00Z
    // groups under 2026-08-19 Caracas) — the component only echoes it, so
    // this pins that no client-side reformatting sneaks a re-derivation in.
    expect(screen.getByLabelText("2026-08-19: 2 capítulos leídos")).toBeInTheDocument();
    expect(screen.getByLabelText("2026-08-20: 0.5 capítulos leídos")).toBeInTheDocument();
  });

  it("shows the Spanish empty state when there are no active days", () => {
    render(<ReadingHeatmap data={{ ...data, days: [] }} />);

    expect(screen.getByText("Todavía no hay lecturas registradas.")).toBeInTheDocument();
  });

  it("keeps a cell for a day with no reading instead of collapsing the gap", () => {
    // The whole point of the calendar direction the owner chose over a short
    // recent window: an empty stretch has to stay visible as an absence. The
    // previous render only emitted active days, so two readings a fortnight
    // apart drew as two adjacent squares.
    render(<ReadingHeatmap data={data} />);

    expect(screen.getByTitle("2026-08-10: sin lecturas")).toBeInTheDocument();
  });

  it("spans exactly from `from` to `to`, inclusive on both ends", () => {
    // Boundary coverage only. It does NOT prove the date arithmetic is
    // timezone-safe, and the original version of this comment claimed it did.
    // Verified by breaking it on purpose: swapping the UTC parse for
    // `new Date(from)` or `new Date(`${from}T00:00:00`)` leaves all of these
    // green. Two reasons, both worth knowing before trusting this file:
    //   1. A date-only string is parsed as UTC by spec, so dropping the `Z`
    //      changes nothing at all.
    //   2. The TZ=America/Caracas pin in vite.config.ts is UTC-4, so local
    //      midnight is 04:00 the SAME UTC day. The shift never crosses the
    //      date boundary here. It would in any UTC+X zone.
    // So the defence against that off-by-one is the explicit `Z` and the
    // getUTC* accessors in the component, not this test. Do not delete them
    // on the evidence of a green suite.
    render(<ReadingHeatmap data={data} />);

    expect(screen.getByTitle("2026-08-01: sin lecturas")).toBeInTheDocument();
    expect(screen.getByTitle("2026-08-21: sin lecturas")).toBeInTheDocument();
    expect(screen.queryByTitle(/^2026-07-31/)).not.toBeInTheDocument();
    expect(screen.queryByTitle(/^2026-08-22/)).not.toBeInTheDocument();
  });

  it("keeps quiet days out of the accessibility tree", () => {
    // 300-odd "sin lecturas" announcements would bury the handful of days
    // that actually say something.
    render(<ReadingHeatmap data={data} />);

    expect(screen.queryByLabelText("2026-08-10: 0 capítulos leídos")).not.toBeInTheDocument();
    expect(screen.getByLabelText("2026-08-19: 2 capítulos leídos")).toBeInTheDocument();
  });
});
