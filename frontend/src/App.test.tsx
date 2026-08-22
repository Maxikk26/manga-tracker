import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "./App";
import { makeBookmark } from "./test/fixtures";
import type { ReadingHistoryResponse } from "./domain/types";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const bookmarksBody = [makeBookmark({ id: 1, title: "One Piece" })];

const readingBody: ReadingHistoryResponse = {
  timezone: "America/Caracas",
  from: "2025-08-22",
  to: "2026-08-21",
  days: [],
};

function stubFetch() {
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (init?.method === "PATCH") return jsonResponse({});
      if (url.startsWith("/api/history/reading")) return jsonResponse(readingBody);
      if (url === "/api/bookmarks") return jsonResponse(bookmarksBody);
      throw new Error(`unexpected fetch: ${url}`);
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("App navigation", () => {
  it("switching to Historial and back leaves the list screen unaffected", async () => {
    stubFetch();
    const user = userEvent.setup();
    render(<App />);

    expect(await screen.findByText("One Piece")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Historial" }));

    expect(
      await screen.findByText("Todavía no hay lecturas registradas."),
    ).toBeInTheDocument();
    // The list screen's own toolbar button is gone — the History screen, not
    // a leftover list, is what is mounted now. ("One Piece" alone would not
    // prove this: it also appears as an option in the timeline picker.)
    expect(screen.queryByRole("button", { name: "Agregar manga" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Lista" }));

    expect(await screen.findByText("One Piece")).toBeInTheDocument();
  });
});
