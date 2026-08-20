import type { Bookmark, MangaAdd, MangaPreview } from "../domain/types";
import { ApiError, readDetail } from "./http";

/**
 * Preview a pasted URL (`POST /api/mangas/preview`, no write). Rejects with
 * ApiError; on a 409 duplicate/terminal-title conflict, ApiError.existing
 * names the bookmark that already owns it.
 */
export async function previewManga(url: string): Promise<MangaPreview> {
  let response: Response;
  try {
    response = await fetch("/api/mangas/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
  } catch {
    throw new ApiError("No se pudo contactar la API. Intenta de nuevo.");
  }
  if (!response.ok) {
    const { detail, existing } = await readDetail(response);
    throw new ApiError(
      detail ?? `La API respondió con un error (HTTP ${response.status}).`,
      existing,
    );
  }
  return (await response.json()) as MangaPreview;
}

/**
 * Confirm the add (`POST /api/mangas`, writes). The body echoes the
 * preview's own url/title/cover_url (design D4) plus the owner's chosen
 * status and initial chapter. Returns the created bookmark in the same
 * shape `GET /api/bookmarks` already uses.
 */
export async function addManga(body: MangaAdd): Promise<Bookmark> {
  let response: Response;
  try {
    response = await fetch("/api/mangas", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError("No se pudo contactar la API. El manga no se agregó.");
  }
  if (!response.ok) {
    const { detail, existing } = await readDetail(response);
    throw new ApiError(
      detail ?? `No se pudo agregar el manga (HTTP ${response.status}). Intenta de nuevo.`,
      existing,
    );
  }
  return (await response.json()) as Bookmark;
}
