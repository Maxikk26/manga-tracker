import { useRef, useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Popover } from "./Popover";

/** A real trigger (its own ref, exactly like `BookmarkCard`'s chapter
 *  trigger) + a real field, so focus/placement/dismissal all have a
 *  genuine DOM to act on -- this component owns nothing beyond "is it
 *  open", starting closed like every real trigger does. */
function Harness({ onDismiss }: { onDismiss?: () => void }) {
  const [open, setOpen] = useState(false);
  const anchorRef = useRef<HTMLButtonElement>(null);
  const dismiss = () => {
    onDismiss?.();
    setOpen(false);
  };
  return (
    <div className="bookmark-grid" tabIndex={-1}>
      <button ref={anchorRef} type="button" onClick={() => setOpen(true)}>
        abrir
      </button>
      {open && (
        <Popover anchor={anchorRef.current} label="Panel de prueba" onDismiss={dismiss}>
          <input aria-label="campo" />
          <select aria-label="otro campo">
            <option value="a">a</option>
          </select>
        </Popover>
      )}
    </div>
  );
}

describe("Popover", () => {
  it("renders role=dialog with the given label and no aria-modal", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "abrir" }));

    const dialog = screen.getByRole("dialog", { name: "Panel de prueba" });
    expect(dialog).not.toHaveAttribute("aria-modal");
  });

  it("focuses and selects the first field on open", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "abrir" }));

    expect(screen.getByLabelText("campo")).toHaveFocus();
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "abrir" }));

    await user.keyboard("{Escape}");

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes on an outside click", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "abrir" }));

    await user.click(document.body);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes on scroll", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "abrir" }));

    fireEvent.scroll(window);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("returns focus to the anchor on close", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "abrir" }));

    await user.keyboard("{Escape}");

    expect(screen.getByRole("button", { name: "abrir" })).toHaveFocus();
  });

  describe("never scrolls the page when it moves focus", () => {
    // Closing re-sorts the list (the freeze ends), so the anchor may now sit
    // somewhere else on the page; a plain `focus()` would scroll the
    // viewport to follow it. Every focus this component moves must pass
    // `preventScroll`.
    function focusCallsOn(spy: { mock: { contexts: unknown[]; calls: unknown[][] } }, element: Element) {
      return spy.mock.calls.filter((_args, index) => spy.mock.contexts[index] === element);
    }

    it("on open, focusing the first field", async () => {
      const user = userEvent.setup();
      render(<Harness />);
      const spy = vi.spyOn(HTMLElement.prototype, "focus");
      await user.click(screen.getByRole("button", { name: "abrir" }));
      const field = screen.getByRole("textbox", { name: "campo" });
      expect(focusCallsOn(spy, field)).toContainEqual([{ preventScroll: true }]);
      expect(focusCallsOn(spy, field)).not.toContainEqual([]);
      spy.mockRestore();
    });

    it("on close, returning focus to the anchor", async () => {
      const user = userEvent.setup();
      render(<Harness />);
      const anchor = screen.getByRole("button", { name: "abrir" });
      await user.click(anchor);
      const spy = vi.spyOn(HTMLElement.prototype, "focus");
      await user.keyboard("{Escape}");
      expect(anchor).toHaveFocus();
      expect(focusCallsOn(spy, anchor)).toEqual([[{ preventScroll: true }]]);
      spy.mockRestore();
    });

    it("on close, falling back to the grid when the anchor is gone", () => {
      const detachedAnchor = document.createElement("button");
      function Fallback({ open }: { open: boolean }) {
        return (
          <div className="bookmark-grid" tabIndex={-1} data-testid="grid">
            {open && (
              <Popover anchor={detachedAnchor} label="Panel de prueba" onDismiss={() => {}}>
                <input aria-label="campo" />
              </Popover>
            )}
          </div>
        );
      }
      const { rerender } = render(<Fallback open />);
      const spy = vi.spyOn(HTMLElement.prototype, "focus");
      rerender(<Fallback open={false} />);
      const grid = screen.getByTestId("grid");
      expect(grid).toHaveFocus();
      expect(focusCallsOn(spy, grid)).toEqual([[{ preventScroll: true }]]);
      spy.mockRestore();
    });
  });

  it("does nothing on a focusout whose relatedTarget is null", async () => {
    // A native <select> dropdown, or a click outside the browser window,
    // both produce this -- closing here would kill the status row (design
    // D2). The one case a naive "any focusout closes" implementation breaks.
    const onDismiss = vi.fn();
    const user = userEvent.setup();
    render(<Harness onDismiss={onDismiss} />);
    await user.click(screen.getByRole("button", { name: "abrir" }));

    fireEvent.blur(screen.getByRole("dialog"), { relatedTarget: null });

    expect(onDismiss).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("closes on a focusout whose relatedTarget is a real element outside the panel and the anchor", async () => {
    const onDismiss = vi.fn();
    const user = userEvent.setup();
    render(<Harness onDismiss={onDismiss} />);
    await user.click(screen.getByRole("button", { name: "abrir" }));
    const outside = document.createElement("button");
    document.body.appendChild(outside);

    fireEvent.blur(screen.getByRole("dialog"), { relatedTarget: outside });

    expect(onDismiss).toHaveBeenCalledOnce();
    document.body.removeChild(outside);
  });
});
