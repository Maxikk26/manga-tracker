import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BookmarkListContainer } from "./BookmarkListContainer";
import { makeBookmark } from "../test/fixtures";
import type { Bookmark } from "../domain/types";

// Realistic wire payload: a plain row, a never-read row (nulls) and an
// approx-progress row — the shapes that broke the first implementation.
const payload: Bookmark[] = [
  makeBookmark({ id: 1, title: "One Piece", last_chapter_read: 1100, behind: 2 }),
  makeBookmark({
    id: 2,
    title: "Berserk",
    last_chapter_read: null,
    behind: null,
    last_read_at: null,
    latest_chapter_num: null,
    latest_chapter_url: null,
    latest_chapter_at: null,
  }),
  makeBookmark({
    id: 3,
    title: "Vagabond",
    last_chapter_read: 200,
    progress_is_approx: true,
    behind: 0,
  }),
];

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function stubFetch() {
  const fetchMock = vi.fn(
    async (_input: RequestInfo | URL, init?: RequestInit) =>
      init?.method === "PATCH" ? jsonResponse({}) : jsonResponse(payload),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("BookmarkListContainer", () => {
  it("renders the fetched list, including null-progress and approx rows", async () => {
    stubFetch();
    render(<BookmarkListContainer />);

    expect(await screen.findByText("One Piece")).toBeInTheDocument();
    expect(screen.getByText("Berserk")).toBeInTheDocument();
    expect(screen.getByText("Vagabond")).toBeInTheDocument();

    // The never-read row shows an em dash, not "null" or 0.
    const berserkCard = screen.getByText("Berserk").closest("article")!;
    expect(
      within(berserkCard).getByTitle(/haz clic para editar/i),
    ).toHaveTextContent("—");
    expect(within(berserkCard).queryByText(/null/)).not.toBeInTheDocument();

    // The approx row carries the "~" marker.
    const vagabondCard = screen.getByText("Vagabond").closest("article")!;
    expect(within(vagabondCard).getByTitle(/aproximado/i)).toHaveTextContent("~");
  });

  it("PATCHes only the changed field on an inline progress edit", async () => {
    const fetchMock = stubFetch();
    const user = userEvent.setup();
    render(<BookmarkListContainer />);

    const card = (await screen.findByText("One Piece")).closest("article")!;
    await user.click(within(card).getByTitle(/haz clic para editar/i));
    const input = within(card).getByRole("spinbutton");
    await user.clear(input);
    await user.type(input, "1105{Enter}");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/bookmarks/1",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ last_chapter_read: 1105 }),
      }),
    );
    // The list is refetched after a successful PATCH: initial GET + refetch.
    const gets = fetchMock.mock.calls.filter(([, init]) => !init?.method);
    expect(gets).toHaveLength(2);
  });

  it("shows the Spanish error state when the fetch fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("network down");
      }),
    );
    render(<BookmarkListContainer />);

    expect(
      await screen.findByText("No se pudo cargar la lista de mangas."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Reintentar" }),
    ).toBeInTheDocument();
  });

  describe("adding a manga", () => {
    const previewBody = {
      slug: "chainsaw-man",
      url: "https://example.test/manga/chainsaw-man",
      title: "Chainsaw Man",
      cover_url: null,
      publication_status_text: "Finalizado",
    };

    function stubFetchWithAdd(addedBookmark: Bookmark) {
      const fetchMock = vi.fn(
        async (input: RequestInfo | URL, init?: RequestInit) => {
          const url = String(input);
          if (init?.method === "PATCH") return jsonResponse({});
          if (url === "/api/mangas/preview") return jsonResponse(previewBody);
          if (url === "/api/mangas") return jsonResponse(addedBookmark, 201);
          return jsonResponse(payload);
        },
      );
      vi.stubGlobal("fetch", fetchMock);
      return fetchMock;
    }

    it("opens the add-manga dialog from the toolbar button", async () => {
      stubFetchWithAdd(makeBookmark({ id: 4, title: "Chainsaw Man", status: "completed" }));
      const user = userEvent.setup();
      render(<BookmarkListContainer />);
      await screen.findByText("One Piece");

      await user.click(screen.getByRole("button", { name: "Agregar manga" }));

      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });

    it("a successful add refetches, closes the modal and switches to the added bookmark's tab", async () => {
      const fetchMock = stubFetchWithAdd(
        makeBookmark({ id: 4, title: "Chainsaw Man", status: "completed" }),
      );
      const user = userEvent.setup();
      render(<BookmarkListContainer />);
      await screen.findByText("One Piece");

      await user.click(screen.getByRole("button", { name: "Agregar manga" }));
      await user.type(
        screen.getByLabelText(/url de la ficha/i),
        "https://example.test/manga/chainsaw-man",
      );
      await user.click(screen.getByRole("button", { name: /vista previa/i }));
      expect(await screen.findByText("Chainsaw Man")).toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: /^agregar$/i }));

      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
      // Switched to the added bookmark's own status tab ("completed"), so the
      // "reading" tab's One Piece card is no longer the visible grid.
      expect(screen.queryByText("One Piece")).not.toBeInTheDocument();
      // Refetched: the GET was called again after the confirm POST.
      const gets = fetchMock.mock.calls.filter(
        ([requestInput, init]) => String(requestInput) === "/api/bookmarks" && !init?.method,
      );
      expect(gets).toHaveLength(2);
    });

    it("closing the modal without confirming (Cancelar) sends no confirm request", async () => {
      const fetchMock = stubFetchWithAdd(makeBookmark({ id: 4, title: "Chainsaw Man" }));
      const user = userEvent.setup();
      render(<BookmarkListContainer />);
      await screen.findByText("One Piece");

      await user.click(screen.getByRole("button", { name: "Agregar manga" }));
      await user.type(
        screen.getByLabelText(/url de la ficha/i),
        "https://example.test/manga/chainsaw-man",
      );
      await user.click(screen.getByRole("button", { name: /vista previa/i }));
      expect(await screen.findByText("Chainsaw Man")).toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: /cancelar/i }));

      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
      expect(
        fetchMock.mock.calls.some(([requestInput]) => String(requestInput) === "/api/mangas"),
      ).toBe(false);
      // The grid is unchanged: still on "reading", still showing One Piece.
      expect(screen.getByText("One Piece")).toBeInTheDocument();
    });
  });
});
