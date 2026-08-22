import type { ReadingHistoryResponse } from "../domain/types";
import { heatmapLevel } from "../domain/heatmapBuckets";

interface Props {
  data: ReadingHistoryResponse;
}

const WEEKDAY_LABELS = ["", "lun", "", "mié", "", "vie", ""];
const MONTH_LABELS = [
  "ene", "feb", "mar", "abr", "may", "jun",
  "jul", "ago", "sep", "oct", "nov", "dic",
];

/** One entry per day in the window, including days with no reading.
 *
 * Date arithmetic runs in UTC on purpose. `from`/`to`/`date` are already
 * local calendar day LABELS resolved server-side — they are not instants, and
 * parsing them without the `Z` would re-apply the browser's offset and shift
 * every cell by a day in half the world's timezones. That is the exact bug
 * class this phase exists to prevent, one layer up.
 */
function buildCalendar(data: ReadingHistoryResponse) {
  const byDate = new Map(data.days.map((day) => [day.date, day]));
  const start = new Date(`${data.from}T00:00:00Z`);
  const end = new Date(`${data.to}T00:00:00Z`);

  // Pad back to the week's first column so every column is one whole week and
  // the weekday rows line up. Padding days sit outside the window and render
  // as invisible spacers.
  const padded = new Date(start);
  padded.setUTCDate(padded.getUTCDate() - padded.getUTCDay());

  const cells = [];
  for (let d = new Date(padded); d <= end; d.setUTCDate(d.getUTCDate() + 1)) {
    const date = d.toISOString().slice(0, 10);
    cells.push({
      date,
      inWindow: d >= start,
      month: d.getUTCMonth(),
      firstOfColumn: d.getUTCDay() === 0,
      chapters: byDate.get(date)?.chapters ?? 0,
    });
  }
  return cells;
}

/**
 * Year-scale heatmap of reading activity (spec-panel-v1b.md fase 2).
 *
 * The owner chose the full-calendar direction over a short recent window
 * (`/prototype`, 2026-08-21): every day in the range gets a cell, so an empty
 * stretch reads as a real absence rather than being collapsed away. He picked
 * it knowing the cost — with the history three days old the grid is nearly
 * blank, and it only pays off once months of reading have accumulated. Until
 * then this screen is referential, not a decision tool, and that was the
 * accepted trade.
 *
 * Bucket boundaries still come from `domain/heatmapBuckets.ts` (seam #1), so
 * the scale can be retuned without touching this file.
 *
 * `day.date` and `day.chapters` are already resolved server-side (local
 * calendar day, corrections excluded) — nothing here re-derives them.
 */
export function ReadingHeatmap({ data }: Props) {
  if (data.days.length === 0) {
    return <p className="empty-state">Todavía no hay lecturas registradas.</p>;
  }

  const cells = buildCalendar(data);
  const columns = Math.ceil(cells.length / 7);

  // One label per month, placed on the column where that month first appears.
  const months: { column: number; label: string }[] = [];
  cells.forEach((cell, index) => {
    if (!cell.firstOfColumn || !cell.inWindow) return;
    if (months.length && months[months.length - 1].label === MONTH_LABELS[cell.month]) return;
    months.push({ column: Math.floor(index / 7) + 1, label: MONTH_LABELS[cell.month] });
  });

  return (
    <section className="reading-heatmap" aria-label="Mapa de lecturas">
      <div className="heatmap-scroll">
        <div className="heatmap-months" style={{ gridTemplateColumns: `repeat(${columns}, 11px)` }}>
          {months.map((month) => (
            <span key={month.column} style={{ gridColumn: month.column }}>
              {month.label}
            </span>
          ))}
        </div>

        <div className="heatmap-body">
          <div className="heatmap-weekdays" aria-hidden="true">
            {WEEKDAY_LABELS.map((label, index) => (
              <span key={index}>{label}</span>
            ))}
          </div>

          <ul className="heatmap-grid">
            {cells.map((cell) => {
              if (!cell.inWindow) {
                return <li key={cell.date} className="heatmap-pad" aria-hidden="true" />;
              }
              // The label format is a pinned contract: it echoes the
              // server-resolved local day verbatim so no client-side
              // reformatting can sneak a re-derivation in.
              const label = `${cell.date}: ${cell.chapters} capítulos leídos`;
              const quiet = cell.chapters === 0;
              return (
                <li
                  key={cell.date}
                  className={`heatmap-cell heatmap-level-${heatmapLevel(cell.chapters)}`}
                  // Days with no reading carry the tooltip but stay out of the
                  // accessibility tree: announcing "sin lecturas" 300-odd times
                  // buries the handful of days that actually say something.
                  {...(quiet
                    ? { "aria-hidden": true, title: `${cell.date}: sin lecturas` }
                    : { "aria-label": label, title: label })}
                />
              );
            })}
          </ul>
        </div>
      </div>

      <p className="heatmap-legend" aria-hidden="true">
        <span>Menos</span>
        {[0, 1, 2, 3, 4].map((level) => (
          <i key={level} className={`heatmap-cell heatmap-level-${level}`} />
        ))}
        <span>Más</span>
      </p>
    </section>
  );
}
