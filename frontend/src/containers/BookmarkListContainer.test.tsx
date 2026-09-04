import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BookmarkListContainer } from "./BookmarkListContainer";
import { makeBookmark } from "../test/fixtures";
import type { Bookmark } from "../domain/types";

// Realistic wire payload: a plain row, a never-read row (nulls) and an
// approx-progress row — the shapes that broke the first implementation.
const payload: Bookmark[] = [
  makeBookmark({ id: 1, title: "One Piece", last_chapter_read: 1100, behind: 2, my_score: 5 }),
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

    // The never-read row shows a placeholder rest label, not "null" or 0.
    const berserkCard = screen.getByText("Berserk").closest("article")!;
    expect(
      within(berserkCard).getByRole("button", { name: /^Editar capítulo leído/ }),
    ).toHaveTextContent("cap. —");
    expect(within(berserkCard).queryByText(/null/)).not.toBeInTheDocument();

    // The approx row carries the dotted-underline marker (design D13),
    // never the free-standing "~".
    const vagabondCard = screen.getByText("Vagabond").closest("article")!;
    expect(
      within(vagabondCard).getByRole("button", { name: /^Editar capítulo leído/ }),
    ).toHaveAttribute("data-approx");
  });

  it("PATCHes only the changed field from the chapter popover", async () => {
    const fetchMock = stubFetch();
    const user = userEvent.setup();
    render(<BookmarkListContainer />);

    const card = (await screen.findByText("One Piece")).closest("article")!;
    await user.click(within(card).getByRole("button", { name: /^Editar capítulo leído/ }));
    const input = screen.getByRole("textbox", { name: "Capítulo leído" });
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

  it("PATCHes {my_score: n} on an inline score edit", async () => {
    const fetchMock = stubFetch();
    const user = userEvent.setup();
    render(<BookmarkListContainer />);

    const card = (await screen.findByText("One Piece")).closest("article")!;
    // The score trigger has its own aria-label (fase 5 slice 2b's
    // `ScoreEditor`), same as the chapter trigger.
    await user.click(within(card).getByRole("button", { name: /^Editar puntuación/ }));
    const input = screen.getByRole("textbox", { name: /Puntuación de 0 a/ });
    await user.clear(input);
    await user.type(input, "9{Enter}");

    const patchCall = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
    // Assert the actual serialized bytes `patchBookmark` sent, not merely
    // that `fetch` was called with *some* matching object -- that is the
    // only way a regression to `my_score?: number` (D3) would show: an
    // `undefined` value there still lets a loose object-shape check pass,
    // but `JSON.stringify` would have already dropped the key.
    expect(patchCall?.[1]?.body).toBe(JSON.stringify({ my_score: 9 }));
  });

  it("clearing the score sends {\"my_score\":null}, never {} (D3: JSON.stringify drops undefined keys)", async () => {
    const fetchMock = stubFetch();
    const user = userEvent.setup();
    render(<BookmarkListContainer />);

    const card = (await screen.findByText("One Piece")).closest("article")!;
    await user.click(within(card).getByRole("button", { name: /^Editar puntuación/ }));
    const input = screen.getByRole("textbox", { name: /Puntuación de 0 a/ });
    await user.clear(input);
    await user.tab();

    const patchCall = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
    expect(patchCall?.[1]?.body).toBe(JSON.stringify({ my_score: null }));
    expect(patchCall?.[1]?.body).not.toBe("{}");
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

  describe("the PATCH write queue (fase 5 slice 2a, design D5)", () => {
    /** A promise this test settles by hand, so it can control exactly when
     *  each PATCH "response" arrives, independent of the other. */
    function createDeferred() {
      let resolve!: (value: Response) => void;
      const promise = new Promise<Response>((r) => {
        resolve = r;
      });
      return { promise, resolve };
    }

    it(
      "serializes a rapid burst of chapter commits for one bookmark: the second " +
        "PATCH is not even sent until the first's write and refetch settle, " +
        "exactly one refetch follows the whole burst, and the final displayed " +
        "value is the later commit -- never the earlier response",
      async () => {
        const user = userEvent.setup();
        const original = payload;
        // The state the server would report after both stepper commits
        // (1100 -> 1101 -> 1102) have actually been applied.
        const afterBurst = payload.map((bookmark) =>
          bookmark.id === 1 ? { ...bookmark, last_chapter_read: 1102 } : bookmark,
        );

        const patchDeferreds = [createDeferred(), createDeferred()];
        let patchCalls = 0;
        let getCalls = 0;
        const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
          if (init?.method === "PATCH") {
            const deferred = patchDeferreds[patchCalls];
            patchCalls += 1;
            return deferred.promise;
          }
          getCalls += 1;
          return jsonResponse(getCalls === 1 ? original : afterBurst);
        });
        vi.stubGlobal("fetch", fetchMock);

        render(<BookmarkListContainer />);
        const card = (await screen.findByText("One Piece")).closest("article")!;
        await user.click(within(card).getByRole("button", { name: /^Editar capítulo leído/ }));
        const plus = screen.getByRole("button", { name: "Uno más" });

        // Two rapid stepper commits for the SAME bookmark: each commits
        // immediately (design D11), with no blur or Enter in between.
        await user.click(plus);
        await user.click(plus);

        // The discriminating assertion: a naive implementation that just
        // fires requests would have already called `patchBookmark` twice
        // by this point (both commits dispatched back to back). The
        // correctly-serialized queue has not sent the second write yet --
        // it is still waiting on the first's own cycle to settle.
        await waitFor(() => expect(patchCalls).toBe(1));
        expect(getCalls).toBe(1); // just the initial load so far

        // The FIRST (earlier) write's response arrives. Because the second
        // commit already bumped the sequence, this link's own refetch is
        // skipped -- but the queue is now free to send the second write.
        patchDeferreds[0].resolve(jsonResponse({}));
        await waitFor(() => expect(patchCalls).toBe(2));
        expect(getCalls).toBe(1); // still no refetch: link 1's was skipped

        // The SECOND (later, freshest) write's response arrives.
        patchDeferreds[1].resolve(jsonResponse({}));

        // Exactly one refetch follows the whole burst, and the displayed
        // value reflects the later commit -- an earlier response can never
        // overwrite it, by construction.
        await waitFor(() => expect(getCalls).toBe(2));
        await waitFor(() =>
          expect(
            within(card).getByRole("button", { name: /^Editar capítulo leído/ }),
          ).toHaveTextContent("cap. 1102"),
        );
        expect(getCalls).toBe(2);
      },
    );
  });

  describe("the ordering freeze while a popover is open (fase 5 slice 2a, design D3/D4)", () => {
    const rowA = makeBookmark({
      id: 101,
      title: "Alpha Manga",
      last_chapter_read: 99,
      latest_chapter_num: 100,
      behind: 1,
      last_read_at: "2026-08-20T10:00:00Z",
    });
    const rowB = makeBookmark({
      id: 102,
      title: "Beta Manga",
      last_chapter_read: 10,
      latest_chapter_num: 50,
      behind: 40,
      last_read_at: "2026-08-10T10:00:00Z",
    });

    function stubFetchForFreeze() {
      let getCalls = 0;
      const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
        if (init?.method === "PATCH") return jsonResponse({});
        getCalls += 1;
        // After the edit's refetch, Alpha is caught up.
        return jsonResponse(
          getCalls === 1
            ? [rowA, rowB]
            : [{ ...rowA, last_chapter_read: 100, behind: 0 }, rowB],
        );
      });
      vi.stubGlobal("fetch", fetchMock);
      return fetchMock;
    }

    const titlesInOrder = () =>
      screen
        .getAllByRole("article")
        .map((article) => within(article).getByRole("heading").textContent);

    it("does not reorder mid-edit even once the edit makes the row caught-up, then re-sorts and returns focus on close", async () => {
      stubFetchForFreeze();
      const user = userEvent.setup();
      render(<BookmarkListContainer />);
      await screen.findByText("Alpha Manga");

      // Alpha is read more recently and neither row is caught up yet, so it
      // sorts first.
      expect(titlesInOrder()).toEqual(["Alpha Manga", "Beta Manga"]);

      const trigger = screen.getByRole("button", {
        name: /^Editar capítulo leído de Alpha Manga/,
      });
      await user.click(trigger);
      // The stepper commits immediately but does not close the popover.
      await user.click(screen.getByRole("button", { name: "Uno más" }));

      // Wait for the fresh (now caught-up) data to actually land, so the
      // very next assertion proves the freeze -- not just timing.
      await waitFor(() => expect(screen.getByText("Al día")).toBeInTheDocument());

      // Still open: Alpha has not moved, even though it is now caught up.
      expect(titlesInOrder()).toEqual(["Alpha Manga", "Beta Manga"]);

      await user.keyboard("{Escape}");

      // Closed: the list re-sorts (Alpha sinks below Beta), and focus
      // returns to the trigger that opened the popover.
      await waitFor(() => expect(titlesInOrder()).toEqual(["Beta Manga", "Alpha Manga"]));
      expect(
        screen.getByRole("button", { name: /^Editar capítulo leído de Alpha Manga/ }),
      ).toHaveFocus();
    });
  });
});
