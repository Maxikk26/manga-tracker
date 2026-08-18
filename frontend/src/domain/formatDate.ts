/**
 * The API sends UTC timestamps. Display is in the browser's local zone
 * (America/Caracas for this deployment) via Intl.
 *
 * Defensive parsing: SQLite-style "YYYY-MM-DD HH:MM:SS" strings carry no
 * timezone marker, and `new Date()` would read them as local time. Any
 * string without an explicit offset is treated as UTC.
 */
function parseUtc(value: string): Date | null {
  let iso = value.trim();
  if (iso.includes(" ") && !iso.includes("T")) {
    iso = iso.replace(" ", "T");
  }
  if (!/(?:Z|[+-]\d{2}:?\d{2})$/.test(iso)) {
    iso += "Z";
  }
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : date;
}

const formatter = new Intl.DateTimeFormat("es-VE", {
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

export function formatLocalDateTime(value: string | null): string {
  if (!value) return "—";
  const date = parseUtc(value);
  return date ? formatter.format(date) : "—";
}
