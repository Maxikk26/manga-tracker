export type Screen = "list" | "history";

interface Props {
  active: Screen;
  onSelect: (screen: Screen) => void;
}

/**
 * Top-level navigation between the primary list and the History screen
 * (design D10): a `useState<Screen>` in `App.tsx` plus this presentational
 * nav — the same shape as `StatusTabs`, since no routing library is
 * installed and a modal would be an interruption, not a destination.
 */
export function AppNav({ active, onSelect }: Props) {
  return (
    <nav className="app-nav" aria-label="Navegación del panel">
      {/* `aria-current` is the only thing that tells a screen reader which
          screen you are on. Without it the accent fill is the sole signal,
          which is invisible to anyone not looking at it (WCAG 4.1.2). */}
      <button
        type="button"
        className={active === "list" ? "app-nav-tab app-nav-tab-active" : "app-nav-tab"}
        aria-current={active === "list" ? "page" : undefined}
        onClick={() => onSelect("list")}
      >
        Lista
      </button>
      <button
        type="button"
        className={active === "history" ? "app-nav-tab app-nav-tab-active" : "app-nav-tab"}
        aria-current={active === "history" ? "page" : undefined}
        onClick={() => onSelect("history")}
      >
        Historial
      </button>
    </nav>
  );
}
