import { useCallback, useEffect, useState } from "react";
import { fetchBookmarks } from "../api/bookmarks";
import { fetchMangaHistory, fetchReadingHistory } from "../api/history";
import { ApiError } from "../api/http";
import type { Bookmark, MangaHistoryResponse, ReadingHistoryResponse } from "../domain/types";
import { ReadingHeatmap } from "../components/ReadingHeatmap";
import { MangaTimeline } from "../components/MangaTimeline";

type LoadState = "loading" | "ready" | "error";

/**
 * Container for the History screen (spec-panel-v1b.md fase 2): owns the
 * heatmap fetch and, once a manga is picked, its timeline fetch.
 *
 * The manga picker reuses `fetchBookmarks` — the same list the primary
 * screen already fetches — rather than a new "which mangas exist" endpoint.
 * Design leaves the exact reachability of the per-manga timeline an open
 * question (card on the list screen vs. a picker here); this is the minimal
 * functional answer, not the visual one.
 */
export function HistoryContainer() {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [reading, setReading] = useState<ReadingHistoryResponse | null>(null);
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([]);
  const [selectedMangaId, setSelectedMangaId] = useState<number | null>(null);
  const [timeline, setTimeline] = useState<MangaHistoryResponse | null>(null);
  const [timelineError, setTimelineError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoadState("loading");
    try {
      const [readingResult, bookmarksResult] = await Promise.all([
        fetchReadingHistory(),
        fetchBookmarks(),
      ]);
      setReading(readingResult);
      setBookmarks(bookmarksResult);
      setLoadState("ready");
    } catch (error) {
      setErrorMessage(
        error instanceof ApiError
          ? error.message
          : "Ocurrió un error inesperado al cargar el historial.",
      );
      setLoadState("error");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleSelectManga = useCallback((mangaId: number) => {
    setSelectedMangaId(mangaId);
    setTimeline(null);
    setTimelineError(null);
    fetchMangaHistory(mangaId)
      .then(setTimeline)
      .catch((error: unknown) => {
        setTimelineError(
          error instanceof ApiError
            ? error.message
            : "Ocurrió un error inesperado al cargar la línea de tiempo.",
        );
      });
  }, []);

  if (loadState === "loading") {
    return <p className="empty-state">Cargando…</p>;
  }

  if (loadState === "error") {
    return (
      <div className="error-panel">
        <p>No se pudo cargar el historial.</p>
        <button type="button" className="retry-button" onClick={() => void load()}>
          Reintentar
        </button>
      </div>
    );
  }

  return (
    <div className="history-screen">
      {errorMessage && (
        <p className="error-banner" role="alert">
          {errorMessage}
        </p>
      )}
      <ReadingHeatmap data={reading!} />

      <div className="history-picker">
        <label htmlFor="history-manga-picker">Ver la línea de tiempo de:</label>
        <select
          id="history-manga-picker"
          className="history-manga-select"
          value={selectedMangaId ?? ""}
          onChange={(event) => {
            const value = event.target.value;
            if (value) handleSelectManga(Number(value));
          }}
        >
          <option value="">Elige un manga…</option>
          {bookmarks.map((bookmark) => (
            <option key={bookmark.manga_id} value={bookmark.manga_id}>
              {bookmark.title}
            </option>
          ))}
        </select>
      </div>

      {timelineError && (
        <p className="error-banner" role="alert">
          {timelineError}
        </p>
      )}
      {timeline && <MangaTimeline data={timeline} />}
    </div>
  );
}
