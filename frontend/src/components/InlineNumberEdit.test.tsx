import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { InlineNumberEdit } from "./InlineNumberEdit";

function setup(
  value: number | null,
  { max, onClear }: { max?: number; onClear?: () => void } = {},
) {
  const onCommit = vi.fn();
  render(
    <InlineNumberEdit
      value={value}
      disabled={false}
      max={max}
      onClear={onClear}
      onCommit={onCommit}
    />,
  );
  return { onCommit };
}

describe("InlineNumberEdit", () => {
  it("commits a changed value on Enter", async () => {
    const user = userEvent.setup();
    const { onCommit } = setup(5);

    await user.click(screen.getByRole("button"));
    const input = screen.getByRole("spinbutton");
    await user.clear(input);
    await user.type(input, "8{Enter}");

    expect(onCommit).toHaveBeenCalledExactlyOnceWith(8);
  });

  it("does not commit the unchanged value", async () => {
    const user = userEvent.setup();
    const { onCommit } = setup(5);

    await user.click(screen.getByRole("button"));
    await user.keyboard("{Enter}"); // draft still "5"

    expect(onCommit).not.toHaveBeenCalled();
  });

  it("cancels on Escape even after typing a new value", async () => {
    const user = userEvent.setup();
    const { onCommit } = setup(5);

    await user.click(screen.getByRole("button"));
    const input = screen.getByRole("spinbutton");
    await user.clear(input);
    await user.type(input, "9{Escape}");

    expect(onCommit).not.toHaveBeenCalled();
    // Back to display mode showing the original value.
    expect(screen.getByRole("button")).toHaveTextContent("5");
  });

  it("does not commit a negative value", async () => {
    const user = userEvent.setup();
    const { onCommit } = setup(5);

    await user.click(screen.getByRole("button"));
    const input = screen.getByRole("spinbutton");
    await user.clear(input);
    await user.type(input, "-3{Enter}");

    expect(onCommit).not.toHaveBeenCalled();
  });

  it("does not commit garbage input", async () => {
    const user = userEvent.setup();
    const { onCommit } = setup(5);

    await user.click(screen.getByRole("button"));
    const input = screen.getByRole("spinbutton");
    await user.clear(input);
    await user.type(input, "abc{Enter}");

    expect(onCommit).not.toHaveBeenCalled();
  });

  it("does not commit a value above max", async () => {
    const user = userEvent.setup();
    const { onCommit } = setup(5, { max: 10 });

    await user.click(screen.getByRole("button"));
    const input = screen.getByRole("spinbutton");
    await user.clear(input);
    await user.type(input, "11{Enter}");

    expect(onCommit).not.toHaveBeenCalled();
  });

  describe("without onClear", () => {
    it("a blank blur stays a no-op even with a non-null value", async () => {
      const user = userEvent.setup();
      const { onCommit } = setup(7);

      await user.click(screen.getByRole("button"));
      const input = screen.getByRole("spinbutton");
      await user.clear(input);
      await user.tab(); // blur with the editor now empty

      expect(onCommit).not.toHaveBeenCalled();
      expect(screen.getByRole("button")).toHaveTextContent("7"); // unchanged
    });
  });

  describe("with onClear", () => {
    it("a blank blur calls onClear exactly once, not onCommit", async () => {
      const user = userEvent.setup();
      const onClear = vi.fn();
      const { onCommit } = setup(7, { onClear });

      await user.click(screen.getByRole("button"));
      const input = screen.getByRole("spinbutton");
      await user.clear(input);
      await user.tab();

      expect(onClear).toHaveBeenCalledOnce();
      expect(onCommit).not.toHaveBeenCalled();
    });
  });

  describe("with a null value (never-read bookmark)", () => {
    it("renders an em dash, never the string 'null'", () => {
      setup(null);
      const display = screen.getByRole("button");
      expect(display).toHaveTextContent("—");
      expect(display).not.toHaveTextContent("null");
    });

    it("opens an empty editor on click", async () => {
      const user = userEvent.setup();
      setup(null);

      await user.click(screen.getByRole("button"));

      expect(screen.getByRole("spinbutton")).toHaveValue(null);
    });

    it("fires no commit when blurred without typing (Number('') === 0 guard)", async () => {
      const user = userEvent.setup();
      const { onCommit } = setup(null);

      await user.click(screen.getByRole("button"));
      await user.tab(); // blur with the editor still empty

      expect(onCommit).not.toHaveBeenCalled();
      expect(screen.getByRole("button")).toHaveTextContent("—");
    });
  });
});
