import type { Bookmark, BookmarkPatch } from "../domain/types";
import { ApiError, readDetail } from "./http";

// Re-exported so existing importers (`import { ApiError } from "./bookmarks"`)
// do not churn now that it lives in http.ts alongside `readDetail`.
export { ApiError };

export async function fetchBookmarks(): Promise<Bookmark[]> {
  let response: Response;
  try {
    response = await fetch("/api/bookmarks");
  } catch {
    throw new ApiError("No se pudo contactar la API. ¿Está corriendo el panel?");
  }
  if (!response.ok) {
    const { detail } = await readDetail(response);
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
    const { detail } = await readDetail(response);
    throw new ApiError(
      detail ??
        `No se pudo guardar el cambio (HTTP ${response.status}). Intenta de nuevo.`,
    );
  }
}
