import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { HistoryContainer } from "./HistoryContainer";
import { makeBookmark } from "../test/fixtures";
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
  days: [{ date: "2026-08-19", chapters: 2, edits: 1 }],
};

const bookmarksBody = [makeBookmark({ id: 1, manga_id: 10, title: "One Piece" })];

function stubFetch() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.startsWith("/api/history/reading")) return jsonResponse(readingBody);
    if (url === "/api/bookmarks") return jsonResponse(bookmarksBody);
    if (url === "/api/mangas/10/history") {
      return jsonResponse({
        manga_id: 10,
        title: "One Piece",
        publications_since: null,
        events: [],
      });
    }
    throw new Error(`unexpected fetch: ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("HistoryContainer", () => {
  it("renders the heatmap and the manga picker once both fetches resolve", async () => {
    stubFetch();

    render(<HistoryContainer />);

    expect(await screen.findByLabelText("Mapa de lecturas")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "One Piece" })).toBeInTheDocument();
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
