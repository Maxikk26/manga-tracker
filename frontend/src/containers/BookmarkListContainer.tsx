import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, fetchBookmarks, patchBookmark } from "../api/bookmarks";
import { ALL_TAB, type Bookmark, type BookmarkStatus, type TabKey } from "../domain/types";
import { STATUS_LABELS } from "../domain/statusLabels";
import { StatusTabs } from "../components/StatusTabs";
import { BookmarkGrid } from "../components/BookmarkGrid";
import { AddMangaContainer } from "./AddMangaContainer";
import { filterBookmarks } from "../domain/filterBookmarks";
import { applyFrozenOrder, sortBookmarksForAll, sortBookmarksForTab } from "../domain/sortBookmarks";

type LoadState = "loading" | "ready" | "error";

/** "Todo" for the sentinel, the Spanish status label otherwise -- used only
 *  for the result count and the "Sin resultados" message (fase 5 slice 3). */
function tabName(tab: TabKey): string {
  return tab === ALL_TAB ? "Todo" : STATUS_LABELS[tab];
}

/**
 * Container: owns fetching, filtering and the PATCH flow.
 * The list is fetched whole and filtered client-side (~230 rows on a LAN);
 * after a successful PATCH it is refetched, so the server stays the only
 * source of truth for derived fields (behind, progress_is_approx, ...).
 */
export function BookmarkListContainer() {
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [activeTab, setActiveTab] = useState<TabKey>("reading");
  const [query, setQuery] = useState("");
  const [savingIds, setSavingIds] = useState<ReadonlySet<number>>(new Set());
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [addModalOpen, setAddModalOpen] = useState(false);

  // The search field's own node, so the scope-jump (Q3) and the clear
  // button can return focus to it without a synthetic key or a ref prop
  // threaded down through a child.
  const searchInputRef = useRef<HTMLInputElement>(null);

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
      setActiveTab(added.status);
      void load(false);
    },
    [load],
  );

  const handleViewExistingFromAdd = useCallback((status: BookmarkStatus) => {
    setAddModalOpen(false);
    setActiveTab(status);
  }, []);

  const handleCloseAddModal = useCallback(() => {
    setAddModalOpen(false);
  }, []);

  // The scope jump (Q3, PROTO binding): switches to "Todo" but leaves the
  // typed query untouched, and returns focus to the field it came from.
  const handleScopeJump = useCallback(() => {
    setActiveTab(ALL_TAB);
    searchInputRef.current?.focus();
  }, []);

  const handleClearSearch = useCallback(() => {
    setQuery("");
    searchInputRef.current?.focus();
  }, []);

  // Per-status counts, always off the raw fetched list -- the tabs' own
  // totals are not affected by the search query (design's diagram: counts
  // come straight off `bookmarks`, before `filterBookmarks` ever runs).
  const counts = useMemo(() => {
    const result: Partial<Record<BookmarkStatus, number>> = {};
    for (const bookmark of bookmarks) {
      result[bookmark.status] = (result[bookmark.status] ?? 0) + 1;
    }
    return result;
  }, [bookmarks]);

  // The chain is filter -> scope -> sort (design D10): `filterBookmarks`
  // never sees a status, so the identical function serves both a single
  // tab and "Todo" -- only the rows handed to it differ.
  const filtered = useMemo(() => filterBookmarks(bookmarks, query), [bookmarks, query]);

  // The tab's true current order -- always fresh, never frozen. This is
  // what the freeze snapshots *from* on open, and what every render falls
  // back to once no popover is open.
  const sortedVisible = useMemo(() => {
    if (activeTab === ALL_TAB) return sortBookmarksForAll(filtered);
    return sortBookmarksForTab(
      filtered.filter((bookmark) => bookmark.status === activeTab),
      activeTab,
    );
  }, [filtered, activeTab]);

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

  // "Todo" is the only tab where a card could have come from any status,
  // so it is the only one that ever shows the status pill (closes out
  // slices 1/1.6's temporary `false` default, Q5).
  const showStatus = activeTab === ALL_TAB;

  const trimmedQuery = query.trim();
  const resultCount = sortedVisible.length;
  const resultCountText =
    trimmedQuery === ""
      ? activeTab === ALL_TAB
        ? `${resultCount} título${resultCount === 1 ? "" : "s"} en toda la lista.`
        : ""
      : `${resultCount} resultado${resultCount === 1 ? "" : "s"} en «${tabName(activeTab)}».`;

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
      {/* Rendered unconditionally, never keyed: the search field must
          survive every re-render this component makes while the owner is
          mid-word, including one that flips the three-way empty state below
          on or off (design D13's `mountShell()` hazard, restated as a React
          rule). */}
      <div className="search-row">
        <div className="search-field">
          <input
            ref={searchInputRef}
            type="search"
            aria-label="Buscar por título"
            placeholder="Buscar por título"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          {query !== "" && (
            <button
              type="button"
              className="search-clear"
              aria-label="Limpiar la búsqueda"
              onClick={handleClearSearch}
            >
              ×
            </button>
          )}
        </div>
        <button type="button" className="add-manga-button" onClick={() => setAddModalOpen(true)}>
          Agregar manga
        </button>
      </div>
      <StatusTabs active={activeTab} counts={counts} onSelect={setActiveTab} />
      <p className="result-count" role="status" aria-live="polite">
        {resultCountText}
      </p>
      {errorMessage && (
        <p className="error-banner" role="alert">
          {errorMessage}
        </p>
      )}
      {visible.length === 0 ? (
        <div className="empty-state">
          {trimmedQuery === "" ? (
            <p>
              {activeTab === ALL_TAB
                ? "Todavía no hay mangas en tu lista."
                : "No hay mangas en este estado."}
            </p>
          ) : (
            <>
              <p>
                Sin resultados para «{trimmedQuery}» en «{tabName(activeTab)}».
              </p>
              {activeTab !== ALL_TAB && (
                <button type="button" onClick={handleScopeJump}>
                  Buscar en toda la lista
                </button>
              )}
            </>
          )}
        </div>
      ) : (
        <BookmarkGrid
          bookmarks={visible}
          savingIds={savingIds}
          showStatus={showStatus}
          onChangeProgress={handleChangeProgress}
          onChangeStatus={handleChangeStatus}
          onChangeScore={handleChangeScore}
          onEditingChange={handleEditingChange}
        />
      )}
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
