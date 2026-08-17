import type { Bookmark, BookmarkStatus } from "../domain/types";
import { BookmarkRow } from "./BookmarkRow";

interface Props {
  bookmarks: Bookmark[];
  savingIds: ReadonlySet<number>;
  onChangeProgress: (id: number, value: number) => void;
  onChangeStatus: (id: number, status: BookmarkStatus) => void;
}

export function BookmarkTable({
  bookmarks,
  savingIds,
  onChangeProgress,
  onChangeStatus,
}: Props) {
  if (bookmarks.length === 0) {
    return <p className="empty-state">No hay mangas en este estado.</p>;
  }

  return (
    <table className="bookmark-table">
      <thead>
        <tr>
          <th className="col-title">Título</th>
          <th className="col-status">Estado</th>
          <th className="col-progress">Voy por</th>
          <th className="col-latest">Último capítulo</th>
          <th className="col-read-at">Última lectura</th>
        </tr>
      </thead>
      <tbody>
        {bookmarks.map((bookmark) => (
          <BookmarkRow
            key={bookmark.id}
            bookmark={bookmark}
            saving={savingIds.has(bookmark.id)}
            onChangeProgress={onChangeProgress}
            onChangeStatus={onChangeStatus}
          />
        ))}
      </tbody>
    </table>
  );
}
