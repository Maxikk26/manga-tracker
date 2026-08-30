import type { Bookmark, BookmarkStatus } from "../domain/types";
import { BookmarkCard } from "./BookmarkCard";

interface Props {
  bookmarks: Bookmark[];
  savingIds: ReadonlySet<number>;
  onChangeProgress: (id: number, value: number) => void;
  onChangeStatus: (id: number, status: BookmarkStatus) => void;
  onChangeScore: (id: number, value: number | null) => void;
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
  onChangeProgress,
  onChangeStatus,
  onChangeScore,
}: Props) {
  if (bookmarks.length === 0) {
    return <p className="empty-state">No hay mangas en este estado.</p>;
  }

  return (
    <div className="bookmark-grid">
      {bookmarks.map((bookmark) => (
        <BookmarkCard
          key={bookmark.id}
          bookmark={bookmark}
          saving={savingIds.has(bookmark.id)}
          onChangeProgress={onChangeProgress}
          onChangeStatus={onChangeStatus}
          onChangeScore={onChangeScore}
        />
      ))}
    </div>
  );
}
