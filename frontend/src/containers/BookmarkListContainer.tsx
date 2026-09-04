import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, fetchBookmarks, patchBookmark } from "../api/bookmarks";
import type { Bookmark, BookmarkStatus } from "../domain/types";
import { StatusTabs } from "../components/StatusTabs";
import { BookmarkGrid } from "../components/BookmarkGrid";
import { AddMangaContainer } from "./AddMangaContainer";
import { applyFrozenOrder, sortBookmarksForTab } from "../domain/sortBookmarks";

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
  const [addModalOpen, setAddModalOpen] = useState(false);

  // The ordering freeze (fase 5 slice 2a, design D3/D4): while any card's
  // popover is open, the list renders the sequence captured at the moment
  // it opened, however the fresh data re-sorts underneath. `editingId` is
  // the container's only knowledge that a row is being edited -- never
  // which one, or what kind of popover (design D3).
  const [editingId, setEditingId] = useState<number | null>(null);
  const [frozenIds, setFrozenIds] = useState<readonly number[] | null>(null);

  // Per-bookmark write serialization (design D5): a FIFO promise chain and
  // a burst counter, so a slow response can never overwrite a newer commit.
  const tails = useRef(new Map<number, Promise<void>>());
  const seqs = useRef(new Map<number, number>());

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

  /**
   * Enqueues one PATCH onto this bookmark's own FIFO (design D5). Each link
   * awaits its own `patchBookmark`, then refetches only if no later commit
   * has arrived for the same id while it was in flight -- request N+1 is
   * never sent until N's write *and* its conditional refetch have settled,
   * so two responses for the same bookmark can never interleave.
   */
  const enqueuePatch = useCallback(
    (id: number, patch: Parameters<typeof patchBookmark>[1]) => {
      const seq = (seqs.current.get(id) ?? 0) + 1;
      seqs.current.set(id, seq);
      setErrorMessage(null);
      setSavingIds((ids) => new Set(ids).add(id));

      const previousTail = tails.current.get(id) ?? Promise.resolve();
      const nextTail = previousTail.then(async () => {
        try {
          await patchBookmark(id, patch);
          // A newer commit already bumped the sequence: this link's own
          // refetch would show fresher data as if it were stale, or worse,
          // race the newer link's own refetch. Skip it -- the last link of
          // the burst is the only one that ever refetches.
          if (seqs.current.get(id) === seq) {
            await load(false);
          }
        } catch (error) {
          setErrorMessage(
            error instanceof ApiError ? error.message : "Ocurrió un error inesperado al guardar.",
          );
        } finally {
          if (seqs.current.get(id) === seq) {
            setSavingIds((ids) => {
              const next = new Set(ids);
              next.delete(id);
              return next;
            });
          }
        }
      });
      tails.current.set(id, nextTail);
    },
    [load],
  );

  const handleChangeProgress = useCallback(
    (id: number, value: number) => enqueuePatch(id, { last_chapter_read: value }),
    [enqueuePatch],
  );

  const handleChangeStatus = useCallback(
    (id: number, status: BookmarkStatus) => enqueuePatch(id, { status }),
    [enqueuePatch],
  );

  const handleChangeScore = useCallback(
    (id: number, value: number | null) => enqueuePatch(id, { my_score: value }),
    [enqueuePatch],
  );

  const handleEditingChange = useCallback((id: number, open: boolean) => {
    setEditingId((prev) => (open ? id : prev === id ? null : prev));
  }, []);

  const handleAdded = useCallback(
    (added: Bookmark) => {
      setAddModalOpen(false);
      setActiveStatus(added.status);
      void load(false);
    },
    [load],
  );

  const handleViewExistingFromAdd = useCallback((status: BookmarkStatus) => {
    setAddModalOpen(false);
    setActiveStatus(status);
  }, []);

  const handleCloseAddModal = useCallback(() => {
    setAddModalOpen(false);
  }, []);

  const counts = useMemo(() => {
    const result: Partial<Record<BookmarkStatus, number>> = {};
    for (const bookmark of bookmarks) {
      result[bookmark.status] = (result[bookmark.status] ?? 0) + 1;
    }
    return result;
  }, [bookmarks]);

  // The tab's true current order -- always fresh, never frozen. This is
  // what the freeze snapshots *from* on open, and what every render falls
  // back to once no popover is open.
  const sortedVisible = useMemo(
    () =>
      sortBookmarksForTab(
        bookmarks.filter((bookmark) => bookmark.status === activeStatus),
        activeStatus,
      ),
    [bookmarks, activeStatus],
  );

  // A ref mirror so `handleEditingChange` (a stable callback, memoized with
  // no deps) can read the *current* order without becoming a new function
  // on every fetch -- the popover-open handshake must not re-render every
  // `BookmarkCard` on refetch.
  const sortedVisibleRef = useRef(sortedVisible);
  sortedVisibleRef.current = sortedVisible;

  useEffect(() => {
    if (editingId === null) {
      setFrozenIds(null);
    } else {
      setFrozenIds((prev) => prev ?? sortedVisibleRef.current.map((bookmark) => bookmark.id));
    }
  }, [editingId]);

  const visible =
    editingId !== null && frozenIds !== null
      ? applyFrozenOrder(sortedVisible, frozenIds)
      : sortedVisible;

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
      <div className="panel-toolbar">
        <StatusTabs active={activeStatus} counts={counts} onSelect={setActiveStatus} />
        <button
          type="button"
          className="add-manga-button"
          onClick={() => setAddModalOpen(true)}
        >
          Agregar manga
        </button>
      </div>
      {errorMessage && (
        <p className="error-banner" role="alert">
          {errorMessage}
        </p>
      )}
      <BookmarkGrid
        bookmarks={visible}
        savingIds={savingIds}
        onChangeProgress={handleChangeProgress}
        onChangeStatus={handleChangeStatus}
        onChangeScore={handleChangeScore}
        onEditingChange={handleEditingChange}
      />
      {addModalOpen && (
        <AddMangaContainer
          onAdded={handleAdded}
          onViewExisting={handleViewExistingFromAdd}
          onRequestClose={handleCloseAddModal}
        />
      )}
    </>
  );
}
