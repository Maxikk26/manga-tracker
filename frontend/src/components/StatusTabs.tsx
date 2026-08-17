import { BOOKMARK_STATUSES, type BookmarkStatus } from "../domain/types";
import { STATUS_LABELS } from "../domain/statusLabels";

interface Props {
  active: BookmarkStatus;
  counts: Partial<Record<BookmarkStatus, number>>;
  onSelect: (status: BookmarkStatus) => void;
}

export function StatusTabs({ active, counts, onSelect }: Props) {
  return (
    <nav className="status-tabs" aria-label="Filtrar por estado">
      {BOOKMARK_STATUSES.map((status) => (
        <button
          key={status}
          type="button"
          className={status === active ? "tab tab-active" : "tab"}
          onClick={() => onSelect(status)}
        >
          {STATUS_LABELS[status]}
          <span className="tab-count">{counts[status] ?? 0}</span>
        </button>
      ))}
    </nav>
  );
}
