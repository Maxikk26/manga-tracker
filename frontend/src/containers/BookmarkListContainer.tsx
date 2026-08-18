import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError, fetchBookmarks, patchBookmark } from "../api/bookmarks";
import type { Bookmark, BookmarkStatus } from "../domain/types";
import { StatusTabs } from "../components/StatusTabs";
import { BookmarkTable } from "../components/BookmarkTable";
import { sortBookmarksForTab } from "../domain/sortBookmarks";

type LoadState = "loading" | "ready" | "error";

/**
 * Container: owns fetching, filtering and the PATCH flow.
 * The list is fetched whole and filtered client-side (~230 rows on a LAN);
 * after a successful PATCH it is refetched, so the server stays the only
 * source of truth for derived fields (behind, progress_is_approx, ...).
 */
export function BookmarkListContainer() {
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [activeStatus, setActiveStatus] = useState<BookmarkStatus>("reading");
  const [savingIds, setSavingIds] = useState<ReadonlySet<number>>(new Set());
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const load = useCallback(async (initial: boolean) => {
    if (initial) setLoadState("loading");
    try {
      setBookmarks(await fetchBookmarks());
      setLoadState("ready");
    } catch (error) {
      if (initial) {
        setLoadState("error");
      } else {
        // A failed refresh after a successful save: the save happened,
        // only the reload failed. Say so instead of dropping the list.
        setErrorMessage(
          error instanceof ApiError
            ? `El cambio se guardó, pero no se pudo recargar la lista: ${error.message}`
            : "El cambio se guardó, pero no se pudo recargar la lista.",
        );
      }
    }
  }, []);

  useEffect(() => {
    void load(true);
  }, [load]);

  const applyPatch = useCallback(
    async (id: number, patch: Parameters<typeof patchBookmark>[1]) => {
      setErrorMessage(null);
      setSavingIds((ids) => new Set(ids).add(id));
      try {
        await patchBookmark(id, patch);
        await load(false);
      } catch (error) {
        setErrorMessage(
          error instanceof ApiError
            ? error.message
            : "Ocurrió un error inesperado al guardar.",
        );
      } finally {
        setSavingIds((ids) => {
          const next = new Set(ids);
          next.delete(id);
          return next;
        });
      }
    },
    [load],
  );

  const handleChangeProgress = useCallback(
    (id: number, value: number) => void applyPatch(id, { last_chapter_read: value }),
    [applyPatch],
  );

  const handleChangeStatus = useCallback(
    (id: number, status: BookmarkStatus) => void applyPatch(id, { status }),
    [applyPatch],
  );

  const counts = useMemo(() => {
    const result: Partial<Record<BookmarkStatus, number>> = {};
    for (const bookmark of bookmarks) {
      result[bookmark.status] = (result[bookmark.status] ?? 0) + 1;
    }
    return result;
  }, [bookmarks]);

  const visible = useMemo(
    () =>
      sortBookmarksForTab(
        bookmarks.filter((bookmark) => bookmark.status === activeStatus),
        activeStatus,
      ),
    [bookmarks, activeStatus],
  );

  if (loadState === "loading") {
    return <p className="empty-state">Cargando…</p>;
  }

  if (loadState === "error") {
    return (
      <div className="error-panel">
        <p>No se pudo cargar la lista de mangas.</p>
        <button type="button" className="retry-button" onClick={() => void load(true)}>
          Reintentar
        </button>
      </div>
    );
  }

  return (
    <>
      <StatusTabs active={activeStatus} counts={counts} onSelect={setActiveStatus} />
      {errorMessage && (
        <p className="error-banner" role="alert">
          {errorMessage}
        </p>
      )}
      <BookmarkTable
        bookmarks={visible}
        savingIds={savingIds}
        onChangeProgress={handleChangeProgress}
        onChangeStatus={handleChangeStatus}
      />
    </>
  );
}
