import { useCallback, useEffect, useState } from "react";
import { fetchReadingHistory } from "../api/history";
import { ApiError } from "../api/http";
import type { ReadingHistoryResponse } from "../domain/types";
import { ReadingHeatmap } from "../components/ReadingHeatmap";

type LoadState = "loading" | "ready" | "error";

/**
 * Container for the History screen (spec-panel-v1b.md fase 2).
 *
 * Scope note: this screen shows the reading heatmap and nothing else. The
 * per-manga timeline the phase also built is deliberately not reachable from
 * here — the owner said on 2026-08-21 he has no interest in reading a single
 * manga's publications against his own reads. Its endpoint and component
 * still exist; only the way in was removed.
 */
export function HistoryContainer() {
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [reading, setReading] = useState<ReadingHistoryResponse | null>(null);

  const load = useCallback(async () => {
    setLoadState("loading");
    try {
      setReading(await fetchReadingHistory());
      setLoadState("ready");
    } catch (error) {
      // Kept for parity with the list screen: an ApiError carries a message
      // worth showing, anything else does not.
      if (!(error instanceof ApiError)) {
        // eslint-disable-next-line no-console
        console.error(error);
      }
      setLoadState("error");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loadState === "loading") {
    return <p className="empty-state">Cargando…</p>;
  }

  if (loadState === "error") {
    return (
      <div className="error-panel">
        <p>No se pudo cargar el historial.</p>
        <button type="button" className="retry-button" onClick={() => void load()}>
          Reintentar
        </button>
      </div>
    );
  }

  const data = reading!;
  const chapters = data.days.reduce((total, day) => total + day.chapters, 0);
  // Rounded for display for the same reason the behind-pill is: chapter
  // numbers are REAL, so a sum of halves reaches here as 36.999999999999996.
  const summary = `${data.days.length} ${data.days.length === 1 ? "día" : "días"} con lecturas · ${Math.round(chapters)} capítulos · zona ${data.timezone}`;

  return (
    <section className="history-screen">
      <h2 className="history-title">Historial de lecturas</h2>
      <p className="history-summary">{summary}</p>

      <div className="history-card">
        <ReadingHeatmap data={data} />
      </div>
    </section>
  );
}
