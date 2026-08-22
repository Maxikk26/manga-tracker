import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AppNav } from "./AppNav";

describe("AppNav", () => {
  it("marks the active screen with aria-current, not colour alone", () => {
    // The accent fill was the only signal of which screen you were on, which
    // is nothing at all to a screen reader: two identically named buttons
    // (WCAG 4.1.2). Found by `/impeccable audit` 2026-08-21.
    render(<AppNav active="history" onSelect={vi.fn()} />);

    expect(screen.getByRole("button", { name: "Historial" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByRole("button", { name: "Lista" })).not.toHaveAttribute("aria-current");
  });

  it("moves aria-current with the active screen", () => {
    render(<AppNav active="list" onSelect={vi.fn()} />);

    expect(screen.getByRole("button", { name: "Lista" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "Historial" })).not.toHaveAttribute("aria-current");
  });

  it("reports the screen the owner clicked", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<AppNav active="list" onSelect={onSelect} />);

    await user.click(screen.getByRole("button", { name: "Historial" }));

    expect(onSelect).toHaveBeenCalledExactlyOnceWith("history");
  });
});
