import { BOOKMARK_STATUSES, type Bookmark, type BookmarkStatus } from "../domain/types";
import { STATUS_LABELS } from "../domain/statusLabels";
import { formatLocalDate, formatLocalDateTime } from "../domain/formatDate";
import { InlineNumberEdit } from "./InlineNumberEdit";

interface Props {
  bookmark: Bookmark;
  saving: boolean;
  onChangeProgress: (id: number, value: number) => void;
  onChangeStatus: (id: number, status: BookmarkStatus) => void;
}

export function BookmarkRow({
  bookmark,
  saving,
  onChangeProgress,
  onChangeStatus,
}: Props) {
  const approxMarker =
    bookmark.progress_is_approx ? (
      <span
        className="approx-marker"
        title="Progreso aproximado: viene del import de Kitsu, no de una lectura confirmada"
      >
        ~
      </span>
    ) : null;

  return (
    <tr className={saving ? "row-saving" : undefined}>
      <td className="col-title">
        <span className="title-text">{bookmark.title}</span>
        {bookmark.behind !== null && bookmark.behind > 0 && (
          <span className="behind-badge">
            {bookmark.behind === 1
              ? "Vas atrasado 1 capítulo"
              : `Vas atrasado ${bookmark.behind} capítulos`}
          </span>
        )}
      </td>
      <td className="col-status">
        <select
          className="status-select"
          value={bookmark.status}
          disabled={saving}
          aria-label={`Estado de ${bookmark.title}`}
          onChange={(event) =>
            onChangeStatus(bookmark.id, event.target.value as BookmarkStatus)
          }
        >
          {BOOKMARK_STATUSES.map((status) => (
            <option key={status} value={status}>
              {STATUS_LABELS[status]}
            </option>
          ))}
        </select>
      </td>
      <td className="col-progress">
        <InlineNumberEdit
          value={bookmark.last_chapter_read}
          prefix={approxMarker}
          disabled={saving}
          onCommit={(value) => onChangeProgress(bookmark.id, value)}
        />
      </td>
      <td className="col-latest">
        {bookmark.latest_chapter_url && bookmark.latest_chapter_num !== null ? (
          <a
            href={bookmark.latest_chapter_url}
            target="_blank"
            rel="noreferrer"
            className="read-link"
            title={
              bookmark.latest_chapter_at
                ? `Publicado: ${formatLocalDateTime(bookmark.latest_chapter_at)}`
                : undefined
            }
          >
            Leer cap. {bookmark.latest_chapter_num}
          </a>
        ) : (
          <span className="muted">—</span>
        )}
      </td>
      <td className="col-read-at muted">
        {formatLocalDate(bookmark.last_read_at)}
      </td>
    </tr>
  );
}
