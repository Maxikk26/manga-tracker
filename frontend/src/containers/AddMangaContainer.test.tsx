import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AddMangaContainer } from "./AddMangaContainer";
import { makeBookmark } from "../test/fixtures";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

async function pasteUrl(user: ReturnType<typeof userEvent.setup>, url: string) {
  await user.type(screen.getByRole("textbox"), url);
}

describe("AddMangaContainer", () => {
  it("previews then confirms with the expected request bodies", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input) === "/api/mangas/preview") {
        return jsonResponse({
          slug: "one-piece",
          url: "https://example.test/manga/one-piece",
          title: "One Piece",
          cover_url: "https://example.test/cover.jpg",
          publication_status_text: "En curso",
        });
      }
      return jsonResponse(makeBookmark({ id: 9, title: "One Piece" }), 201);
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    const onAdded = vi.fn();

    render(
      <AddMangaContainer
        onAdded={onAdded}
        onViewExisting={vi.fn()}
        onRequestClose={vi.fn()}
      />,
    );

    await pasteUrl(user, "https://example.test/manga/one-piece");
    await user.click(screen.getByRole("button", { name: /vista previa/i }));

    expect(await screen.findByText("One Piece")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/mangas/preview",
      expect.objectContaining({
        body: JSON.stringify({ url: "https://example.test/manga/one-piece" }),
      }),
    );

    await user.click(screen.getByRole("button", { name: /^agregar$/i }));

    expect(onAdded).toHaveBeenCalledWith(expect.objectContaining({ id: 9 }));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/mangas",
      expect.objectContaining({
        body: JSON.stringify({
          url: "https://example.test/manga/one-piece",
          title: "One Piece",
          cover_url: "https://example.test/cover.jpg",
          status: "reading",
          last_chapter_read: 0,
        }),
      }),
    );
  });

  it("renders the terminal 409 reactivation sentence and its button switches tabs", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          {
            detail:
              "«Berserk» ya está en tu lista, con estado Abandonado. Para retomarlo, cámbiale el estado desde su pestaña «Abandonado»; no hace falta agregarlo de nuevo.",
            existing: { title: "Berserk", status: "dropped", terminal: true },
          },
          409,
        ),
      ),
    );
    const user = userEvent.setup();
    const onViewExisting = vi.fn();

    render(
      <AddMangaContainer
        onAdded={vi.fn()}
        onViewExisting={onViewExisting}
        onRequestClose={vi.fn()}
      />,
    );

    await pasteUrl(user, "https://example.test/manga/berserk");
    await user.click(screen.getByRole("button", { name: /vista previa/i }));

    expect(await screen.findByText(/Berserk/)).toBeInTheDocument();
    expect(screen.getByText(/no hace falta agregarlo de nuevo/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /ver en «abandonado»/i }));

    expect(onViewExisting).toHaveBeenCalledWith("dropped");
  });

  it("abandoning the preview (changing the URL) sends no confirm request", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({
        slug: "one-piece",
        url: "https://example.test/manga/one-piece",
        title: "One Piece",
        cover_url: null,
        publication_status_text: null,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(
      <AddMangaContainer onAdded={vi.fn()} onViewExisting={vi.fn()} onRequestClose={vi.fn()} />,
    );

    await pasteUrl(user, "https://example.test/manga/one-piece");
    await user.click(screen.getByRole("button", { name: /vista previa/i }));
    expect(await screen.findByText("One Piece")).toBeInTheDocument();

    // Editing the URL drops the stale preview: confirm is disabled again and
    // no POST /api/mangas is ever issued.
    await user.type(screen.getByRole("textbox"), "x");

    expect(screen.queryByText("One Piece")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^agregar$/i })).toBeDisabled();
    expect(fetchMock).toHaveBeenCalledTimes(1); // only the one preview call
  });
});
