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
});
