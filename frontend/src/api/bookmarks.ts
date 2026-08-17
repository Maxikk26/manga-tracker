import type { Bookmark, BookmarkPatch } from "../domain/types";

/** User-facing (Spanish) error carrying whatever detail the API returned. */
export class ApiError extends Error {}

async function readDetail(response: Response): Promise<string | null> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    return typeof body.detail === "string" ? body.detail : null;
  } catch {
    return null;
  }
}

export async function fetchBookmarks(): Promise<Bookmark[]> {
  let response: Response;
  try {
    response = await fetch("/api/bookmarks");
  } catch {
    throw new ApiError("No se pudo contactar la API. ¿Está corriendo el panel?");
  }
  if (!response.ok) {
    const detail = await readDetail(response);
    throw new ApiError(
      detail ?? `La API respondió con un error (HTTP ${response.status}).`,
    );
  }
  return (await response.json()) as Bookmark[];
}

export async function patchBookmark(
  id: number,
  patch: BookmarkPatch,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`/api/bookmarks/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
  } catch {
    throw new ApiError("No se pudo contactar la API. El cambio no se guardó.");
  }
  if (!response.ok) {
    const detail = await readDetail(response);
    throw new ApiError(
      detail ??
        `No se pudo guardar el cambio (HTTP ${response.status}). Intenta de nuevo.`,
    );
  }
}
