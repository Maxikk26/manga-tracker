import type { Bookmark, BookmarkStatus } from "../domain/types";
import { BookmarkCard } from "./BookmarkCard";

interface Props {
  bookmarks: Bookmark[];
  savingIds: ReadonlySet<number>;
  /** Threaded straight to every `BookmarkCard` (design D8). Defaults false --
   *  the container does not wire the real "Todo"-tab value until fase 5
   *  slice 3 exists; every tab keeps showing "Al día" until then. */
  showStatus?: boolean;
  onChangeProgress: (id: number, value: number) => void;
  onChangeStatus: (id: number, status: BookmarkStatus) => void;
  onChangeScore: (id: number, value: number | null) => void;
  onEditingChange: (id: number, open: boolean) => void;
}

/**
 * The reading list as a grid of covers, replacing the table.
 *
 * Ordering is not decided here: the container hands the list already sorted for
 * the active tab, so this component stays a layout and nothing else.
 */
export function BookmarkGrid({
  bookmarks,
  savingIds,
  showStatus = false,
  onChangeProgress,
  onChangeStatus,
  onChangeScore,
  onEditingChange,
}: Props) {
  if (bookmarks.length === 0) {
    return <p className="empty-state">No hay mangas en este estado.</p>;
  }

  return (
    // `tabIndex={-1}` makes this a focus sink (design D6): when a popover
    // closes and its trigger has since unmounted (a status change removed
    // the row from this tab, fase 5 slice 2b), focus lands here instead of
    // silently falling to `<body>`.
    <div className="bookmark-grid" tabIndex={-1}>
      {bookmarks.map((bookmark) => (
        <BookmarkCard
          key={bookmark.id}
          bookmark={bookmark}
          saving={savingIds.has(bookmark.id)}
          showStatus={showStatus}
          onChangeProgress={onChangeProgress}
          onChangeStatus={onChangeStatus}
          onChangeScore={onChangeScore}
          onEditingChange={onEditingChange}
        />
      ))}
    </div>
  );
}
