import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./http";
import { addManga, previewManga } from "./mangas";
import type { MangaAdd } from "../domain/types";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("previewManga", () => {
  it("posts the url and returns the preview", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({
        slug: "one-piece",
        url: "https://example.test/manga/one-piece",
        title: "One Piece",
        cover_url: "https://example.test/cover.jpg",
        publication_status_text: "En curso",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const preview = await previewManga("https://example.test/manga/one-piece");

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/mangas/preview",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ url: "https://example.test/manga/one-piece" }),
      }),
    );
    expect(preview.title).toBe("One Piece");
    expect(preview.publication_status_text).toBe("En curso");
  });

  it("throws ApiError with the existing payload on a 409", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          {
            detail: "«Berserk» ya está en tu lista, con estado Abandonado.",
            existing: { title: "Berserk", status: "dropped", terminal: true },
          },
          409,
        ),
      ),
    );

    await expect(previewManga("https://example.test/manga/berserk")).rejects.toMatchObject({
      message: "«Berserk» ya está en tu lista, con estado Abandonado.",
      existing: { title: "Berserk", status: "dropped", terminal: true },
    });
  });

  it("maps a network failure to a Spanish ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("network down");
      }),
    );

    await expect(previewManga("x")).rejects.toBeInstanceOf(ApiError);
  });
});

describe("addManga", () => {
  const body: MangaAdd = {
    url: "https://example.test/manga/one-piece",
    title: "One Piece",
    cover_url: null,
    status: "reading",
    last_chapter_read: 0,
  };

  it("posts the body and returns the created bookmark", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse({ id: 1, manga_id: 10, title: "One Piece", status: "reading" }, 201),
    );
    vi.stubGlobal("fetch", fetchMock);

    const bookmark = await addManga(body);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/mangas",
      expect.objectContaining({ method: "POST", body: JSON.stringify(body) }),
    );
    expect(bookmark.id).toBe(1);
  });

  it("throws ApiError with existing on a terminal 409", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          {
            detail:
              "«Vagabond» ya está en tu lista, con estado Completado. Para retomarlo…",
            existing: { title: "Vagabond", status: "completed", terminal: true },
          },
          409,
        ),
      ),
    );

    await expect(addManga(body)).rejects.toMatchObject({
      existing: { title: "Vagabond", status: "completed", terminal: true },
    });
  });

  it("maps a network failure to a Spanish ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("network down");
      }),
    );

    await expect(addManga(body)).rejects.toBeInstanceOf(ApiError);
  });
});
