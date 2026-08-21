import type { ReadingHistoryResponse } from "../domain/types";
import { heatmapLevel } from "../domain/heatmapBuckets";

interface Props {
  data: ReadingHistoryResponse;
}

/**
 * Sparse heatmap of days with reading activity (spec-panel-v1b.md fase 2).
 *
 * Bucket boundaries, colours and the weeks-vs-months layout are
 * owner-reserved (design D7/D8) — this component only asks
 * `domain/heatmapBuckets.ts` (seam #1) for a 0-4 level per day and renders
 * whatever it says, so the owner's later `/prototype` pass changes one file
 * and zero tests.
 *
 * `day.date` and `day.chapters` are already resolved server-side (local
 * calendar day, corrections excluded) — nothing here re-derives them.
 */
export function ReadingHeatmap({ data }: Props) {
  if (data.days.length === 0) {
    return <p className="empty-state">Todavía no hay lecturas registradas.</p>;
  }

  return (
    <section className="reading-heatmap" aria-label="Mapa de lecturas">
      <ul className="heatmap-grid">
        {data.days.map((day) => {
          const level = heatmapLevel(day.chapters);
          const label = `${day.date}: ${day.chapters} capítulos leídos`;
          return (
            <li
              key={day.date}
              className={`heatmap-cell heatmap-level-${level}`}
              aria-label={label}
              title={label}
            />
          );
        })}
      </ul>
    </section>
  );
}
