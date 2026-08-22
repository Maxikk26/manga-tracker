import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { HistoryContainer } from "./HistoryContainer";
import type { ReadingHistoryResponse } from "../domain/types";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const readingBody: ReadingHistoryResponse = {
  timezone: "America/Caracas",
  from: "2025-08-22",
  to: "2026-08-21",
  days: [
    { date: "2026-08-19", chapters: 2, edits: 1 },
    { date: "2026-08-20", chapters: 0.5, edits: 1 },
  ],
};

function stubFetch() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.startsWith("/api/history/reading")) return jsonResponse(readingBody);
    throw new Error(`unexpected fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("HistoryContainer", () => {
  it("renders the heatmap under a heading and a summary line", async () => {
    stubFetch();

    render(<HistoryContainer />);

    expect(await screen.findByLabelText("Mapa de lecturas")).toBeInTheDocument();
    expect(screen.getByText("Historial de lecturas")).toBeInTheDocument();
    // Rounded: chapter numbers are REAL, so 2 + 0.5 must not surface as
    // "2.5 capítulos" here and must never surface as a float tail either.
    expect(screen.getByText(/2 días con lecturas · 3 capítulos · zona America\/Caracas/)).toBeInTheDocument();
  });

  it("does not offer the per-manga timeline", async () => {
    // The owner removed the way in on 2026-08-21: he has no interest in
    // reading one manga's publications against his own reads. The endpoint
    // and component still exist; this pins that the screen does not reach
    // them, so the picker cannot reappear by accident.
    stubFetch();

    render(<HistoryContainer />);
    await screen.findByLabelText("Mapa de lecturas");

    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByText(/línea de tiempo/i)).not.toBeInTheDocument();
  });

  it("asks for the heatmap only, not the bookmark list", async () => {
    // The picker was the only reason this screen fetched /api/bookmarks.
    // Dropping it halved the screen's requests, and the stub throws on any
    // URL it does not expect, so a reintroduced fetch fails loudly here.
    const fetchMock = stubFetch();

    render(<HistoryContainer />);
    await screen.findByLabelText("Mapa de lecturas");

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("shows the Spanish error state when a fetch fails, with a working retry", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("network down");
      }),
    );

    render(<HistoryContainer />);

    expect(await screen.findByText("No se pudo cargar el historial.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
  });
});
