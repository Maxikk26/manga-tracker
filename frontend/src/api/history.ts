import type { MangaHistoryResponse, ReadingHistoryResponse } from "../domain/types";
import { ApiError, readDetail } from "./http";

export async function fetchReadingHistory(days = 365): Promise<ReadingHistoryResponse> {
  let response: Response;
  try {
    response = await fetch(`/api/history/reading?days=${days}`);
  } catch {
    throw new ApiError("No se pudo contactar la API. ¿Está corriendo el panel?");
  }
  if (!response.ok) {
    const { detail } = await readDetail(response);
    throw new ApiError(
      detail ?? `La API respondió con un error (HTTP ${response.status}).`,
    );
  }
  return (await response.json()) as ReadingHistoryResponse;
}

export async function fetchMangaHistory(mangaId: number): Promise<MangaHistoryResponse> {
  let response: Response;
  try {
    response = await fetch(`/api/mangas/${mangaId}/history`);
  } catch {
    throw new ApiError("No se pudo contactar la API. ¿Está corriendo el panel?");
  }
  if (!response.ok) {
    const { detail } = await readDetail(response);
    throw new ApiError(
      detail ?? `La API respondió con un error (HTTP ${response.status}).`,
    );
  }
  return (await response.json()) as MangaHistoryResponse;
}
