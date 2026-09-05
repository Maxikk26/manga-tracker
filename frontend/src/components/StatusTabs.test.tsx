import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StatusTabs } from "./StatusTabs";
import { ALL_TAB } from "../domain/types";

const counts = {
  reading: 48,
  want_to_read: 4,
  completed: 28,
  on_hold: 162,
  dropped: 42,
};

describe("StatusTabs", () => {
  it("renders six tabs, Todo first, with the grand total", () => {
    render(<StatusTabs active={ALL_TAB} counts={counts} onSelect={vi.fn()} />);

    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(6);
    expect(buttons[0]).toHaveTextContent("Todo");
    expect(buttons[0]).toHaveTextContent("284"); // 48+4+28+162+42
  });

  it("marks the active tab with both tab-active and aria-current='true'", () => {
    render(<StatusTabs active="dropped" counts={counts} onSelect={vi.fn()} />);

    const active = screen.getByRole("button", { name: /abandonado/i });
    expect(active).toHaveClass("tab-active");
    expect(active).toHaveAttribute("aria-current", "true");
  });

  it("leaves aria-current absent (not 'false') on every inactive tab", () => {
    // The AppNav.tsx precedent: an inactive tab carries no aria-current
    // attribute at all, never the literal string "false".
    render(<StatusTabs active="dropped" counts={counts} onSelect={vi.fn()} />);

    for (const name of [/^Todo/i, /leyendo/i, /por leer/i, /completado/i, /en pausa/i]) {
      const tab = screen.getByRole("button", { name });
      expect(tab).not.toHaveAttribute("aria-current");
    }
  });

  it(
    "keeps every tab's computed role as 'button', never 'tab' -- guards " +
      "correction 1 (design D1): an explicit role='tab' would override a " +
      "<button>'s implicit role and break the e2e smoke's " +
      "getByRole('button', {name:/abandonado/i}) even with tab-active intact",
    () => {
      render(<StatusTabs active={ALL_TAB} counts={counts} onSelect={vi.fn()} />);

      expect(screen.queryAllByRole("tab")).toHaveLength(0);
      expect(screen.getByRole("button", { name: /abandonado/i })).toBeInTheDocument();
    },
  );

  it("calls onSelect with the ALL_TAB sentinel when Todo is clicked", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<StatusTabs active="reading" counts={counts} onSelect={onSelect} />);

    await user.click(screen.getByRole("button", { name: /^Todo/ }));

    expect(onSelect).toHaveBeenCalledExactlyOnceWith(ALL_TAB);
  });

  it("calls onSelect with the status when a status tab is clicked", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<StatusTabs active={ALL_TAB} counts={counts} onSelect={onSelect} />);

    await user.click(screen.getByRole("button", { name: /en pausa/i }));

    expect(onSelect).toHaveBeenCalledExactlyOnceWith("on_hold");
  });
});
