import { useEffect, useLayoutEffect, useRef, type FocusEvent, type KeyboardEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";

interface Props {
  /** The trigger that opened this popover. Used for placement, for the
   *  outside-click/focusout exclusion zone, and for where focus returns on
   *  close (design D2/D6). */
  anchor: HTMLElement | null;
  /** Spanish, product copy -- the dialog's accessible name. */
  label: string;
  onDismiss: () => void;
  children: ReactNode;
}

/**
 * One popover shell for both editors (fase 5 design D2): placement,
 * dismissal, focus management and `role="dialog"`. `ChapterEditor` and
 * `ScoreEditor` are bodies -- PROTO's own comment states the intent, and it
 * is binding: "same panel, same placement, same keys. Only the body
 * differs."
 *
 * Mounted via `createPortal` to `document.body`, not inside the card: the
 * card needs `overflow: hidden` to round its poster, which clips anything
 * wider than the card itself (the panel is 178px against a ~162px card).
 *
 * Non-modal on purpose: `role="dialog"` with no `aria-modal` and no focus
 * trap -- claiming the page is inert would be a lie for a panel this size.
 * `AddMangaModal` keeps `aria-modal="true"` because it earns it.
 */
export function Popover({ anchor, label, onDismiss, children }: Props) {
  const panelRef = useRef<HTMLDivElement>(null);

  // Placement: computed once, from the anchor's rect and the panel's own
  // rendered size, in page coordinates (`position: absolute`). PROTO's
  // arithmetic, verbatim (design D2). jsdom has no layout engine, so every
  // rect here is 0 in tests -- a documented limitation, not a bug; the
  // real placement is verified by eye on the homelab.
  useLayoutEffect(() => {
    const panel = panelRef.current;
    if (!panel || !anchor) return;
    const rect = anchor.getBoundingClientRect();
    const vw = document.documentElement.clientWidth;
    const vh = document.documentElement.clientHeight;
    const w = panel.offsetWidth;
    const h = panel.offsetHeight;
    let left = rect.left;
    let top = rect.bottom + 6;
    if (left + w > vw - 8) left = vw - w - 8;
    if (left < 8) left = 8;
    if (top + h > vh - 8) top = Math.max(8, rect.top - h - 6);
    panel.style.left = `${left + window.scrollX}px`;
    panel.style.top = `${top + window.scrollY}px`;
    // Runs once on open, deliberately -- not on every render (design D2).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Focus the first field on open. On close, return it to the anchor when
  // it still exists, otherwise to the grid (design D6) -- a status change
  // from inside the popover (fase 5 slice 2b) can remove the row the
  // anchor belonged to before this cleanup runs.
  useEffect(() => {
    const field = panelRef.current?.querySelector<HTMLElement>("input, select, button");
    field?.focus();
    if (field instanceof HTMLInputElement) field.select();
    return () => {
      if (anchor && document.contains(anchor)) {
        anchor.focus();
      } else {
        document.querySelector<HTMLElement>(".bookmark-grid")?.focus();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Outside click (capture phase, so it runs before another card's own
  // trigger opens its popover -- mutual exclusion falls out of this rule,
  // no registry needed) and scroll (the anchor's measured rect is
  // invalidated the moment the page scrolls) both dismiss.
  useEffect(() => {
    function handleOutsideClick(event: MouseEvent) {
      const target = event.target as Node;
      if (panelRef.current?.contains(target)) return;
      if (anchor?.contains(target)) return;
      onDismiss();
    }
    function handleScroll() {
      onDismiss();
    }
    document.addEventListener("click", handleOutsideClick, true);
    window.addEventListener("scroll", handleScroll, { capture: true, once: true });
    return () => {
      document.removeEventListener("click", handleOutsideClick, true);
      window.removeEventListener("scroll", handleScroll, true);
    };
  }, [anchor, onDismiss]);

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") onDismiss();
  }

  // A native <select>'s own dropdown, or a click outside the browser
  // window, both fire a `focusout` whose `relatedTarget` is `null` -- that
  // must do nothing, or opening the (fase 5 slice 2b) status row's own
  // dropdown would close the panel out from under it (design D2).
  function handleFocusOut(event: FocusEvent<HTMLDivElement>) {
    const related = event.relatedTarget;
    if (related === null) return;
    if (panelRef.current?.contains(related)) return;
    if (anchor?.contains(related)) return;
    onDismiss();
  }

  return createPortal(
    <div
      ref={panelRef}
      className="pop"
      role="dialog"
      aria-label={label}
      style={{ position: "absolute" }}
      onKeyDown={handleKeyDown}
      onBlur={handleFocusOut}
    >
      {children}
    </div>,
    document.body,
  );
}
