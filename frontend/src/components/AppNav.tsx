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
      <button
        type="button"
        className={active === "list" ? "app-nav-tab app-nav-tab-active" : "app-nav-tab"}
        onClick={() => onSelect("list")}
      >
        Lista
      </button>
      <button
        type="button"
        className={active === "history" ? "app-nav-tab app-nav-tab-active" : "app-nav-tab"}
        onClick={() => onSelect("history")}
      >
        Historial
      </button>
    </nav>
  );
}
