import type { MangaHistoryResponse } from "../domain/types";
import { formatLocalDateTime } from "../domain/formatDate";

interface Props {
  data: MangaHistoryResponse;
}

/**
 * Chronological reading + publication timeline for one manga
 * (spec-panel-v1b.md fase 2).
 *
 * Never claims completeness: `publications_since` states the earliest
 * publication this panel actually knows about (design D9) —
 * `CHAPTER_HISTORY_LIMIT` caps only the one-time backfill, so a manga mapped
 * late can have decades of publications this panel never saw.
 *
 * A downward correction stays visible with its negative delta — the heatmap
 * excludes it, this timeline does not (design D6).
 */
export function MangaTimeline({ data }: Props) {
  return (
    <section className="manga-timeline" aria-label={`Historial de ${data.title}`}>
      <h3 className="manga-timeline-title">{data.title}</h3>
      {data.publications_since && (
        <p className="manga-timeline-note">
          Publicaciones registradas desde {formatLocalDateTime(data.publications_since)}; las
          anteriores pueden faltar.
        </p>
      )}
      {data.events.length === 0 ? (
        <p className="empty-state">Todavía no hay eventos registrados para este manga.</p>
      ) : (
        <ul className="timeline-list">
          {data.events.map((event, index) => (
            <li
              key={`${event.kind}-${event.at}-${index}`}
              className={`timeline-event timeline-event-${event.kind}`}
            >
              <span className="timeline-date">{formatLocalDateTime(event.at)}</span>
              {event.kind === "reading" ? (
                <span className="timeline-detail">
                  Leído hasta el capítulo {event.chapter_num}
                  {event.delta !== null && event.delta < 0 && " (corrección)"}
                </span>
              ) : (
                <span className="timeline-detail">Capítulo {event.chapter_num} publicado</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
