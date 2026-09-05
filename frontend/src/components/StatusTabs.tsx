import { ALL_TAB, BOOKMARK_STATUSES, type BookmarkStatus, type TabKey } from "../domain/types";
import { STATUS_LABELS } from "../domain/statusLabels";

interface Props {
  active: TabKey;
  counts: Partial<Record<BookmarkStatus, number>>;
  onSelect: (tab: TabKey) => void;
}

/**
 * Six tabs: "Todo" first with the grand total, then the five statuses in
 * `BOOKMARK_STATUSES` order (fase 5 slice 3, design D1/D8).
 *
 * **Correction 1 (design D1) -- do NOT add `role="tablist"`/`role="tab"`.**
 * `getByRole` matches the *computed* ARIA role, and an explicit `role="tab"`
 * overrides a `<button>`'s implicit role, so `page.getByRole("button", {
 * name: /abandonado/i })` at `panel.smoke.spec.ts:35` would stop matching
 * even with `tab-active` still present. These stay plain `<button>`s, and
 * `aria-current` is added instead -- the same precedent `AppNav.tsx` already
 * set for this exact problem (WCAG 4.1.2): present as `"true"` on the active
 * tab, absent (never `"false"`) on every inactive one.
 */
export function StatusTabs({ active, counts, onSelect }: Props) {
  const total = BOOKMARK_STATUSES.reduce((sum, status) => sum + (counts[status] ?? 0), 0);

  return (
    <nav className="status-tabs" aria-label="Filtrar por estado">
      <button
        type="button"
        className={active === ALL_TAB ? "tab tab-all tab-active" : "tab tab-all"}
        aria-current={active === ALL_TAB ? "true" : undefined}
        onClick={() => onSelect(ALL_TAB)}
      >
        Todo
        <span className="tab-count">{total}</span>
      </button>
      {BOOKMARK_STATUSES.map((status) => (
        <button
          key={status}
          type="button"
          className={status === active ? "tab tab-active" : "tab"}
          aria-current={status === active ? "true" : undefined}
          onClick={() => onSelect(status)}
        >
          {STATUS_LABELS[status]}
          <span className="tab-count">{counts[status] ?? 0}</span>
        </button>
      ))}
    </nav>
  );
}
