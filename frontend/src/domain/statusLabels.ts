import type { BookmarkStatus } from "./types";

/**
 * Single mapping from domain status values (verbatim, per the schema)
 * to the Spanish labels the user sees. Nothing else translates statuses.
 */
export const STATUS_LABELS: Record<BookmarkStatus, string> = {
  reading: "Leyendo",
  want_to_read: "Por leer",
  completed: "Completado",
  on_hold: "En pausa",
  dropped: "Abandonado",
};
