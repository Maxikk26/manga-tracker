import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ScoreEditor } from "./ScoreEditor";
import { makeBookmark } from "../test/fixtures";

const input = () => screen.getByRole("textbox", { name: /Puntuación de 0 a/ }) as HTMLInputElement;
const clearButton = () => screen.getByRole("button", { name: "Quitar puntuación" });

function renderEditor(overrides: Parameters<typeof makeBookmark>[0] = {}) {
  const onCommit = vi.fn();
  const onRequestClose = vi.fn();
  render(
    <ScoreEditor
      bookmark={makeBookmark(overrides)}
      onCommit={onCommit}
      onRequestClose={onRequestClose}
    />,
  );
  return { onCommit, onRequestClose };
}

describe("ScoreEditor", () => {
  it("seeds an empty field for an unscored bookmark, never the literal string 'null'", () => {
    renderEditor({ my_score: null });

    expect(input().value).toBe("");
    expect(screen.queryByDisplayValue("null")).not.toBeInTheDocument();
  });

  it("seeds the stored score", () => {
    renderEditor({ my_score: 8 });

    expect(input().value).toBe("8");
  });

  it("a typed value commits on blur, never per keystroke", async () => {
    const user = userEvent.setup();
    const { onCommit } = renderEditor({ my_score: null });

    await user.type(input(), "7");
    expect(onCommit).not.toHaveBeenCalled();

    await user.tab();
    expect(onCommit).toHaveBeenCalledExactlyOnceWith(7);
  });

  it("a typed value commits on Enter and requests the popover close", async () => {
    const user = userEvent.setup();
    const { onCommit, onRequestClose } = renderEditor({ my_score: null });

    await user.type(input(), "9{Enter}");

    expect(onCommit).toHaveBeenCalledExactlyOnceWith(9);
    expect(onRequestClose).toHaveBeenCalledOnce();
  });

  it("clearing the typed field commits null and closes on Enter", async () => {
    const user = userEvent.setup();
    const { onCommit, onRequestClose } = renderEditor({ my_score: 6 });

    await user.clear(input());
    await user.keyboard("{Enter}");

    expect(onCommit).toHaveBeenCalledExactlyOnceWith(null);
    expect(onRequestClose).toHaveBeenCalledOnce();
  });

  it("rejects a value above 10, fires no commit", async () => {
    const user = userEvent.setup();
    const { onCommit } = renderEditor({ my_score: null });

    await user.type(input(), "11{Enter}");

    expect(onCommit).not.toHaveBeenCalled();
  });

  it(
    "a leading minus never survives DecimalInput's own sanitizer (slice 2a), so the " +
      "out-of-range-below-zero guard is unreachable through this field: typing '-1' " +
      "leaves only the digit, and committing that unchanged-from-default value fires " +
      "no commit either",
    async () => {
      const user = userEvent.setup();
      const { onCommit } = renderEditor({ my_score: 1 });

      await user.clear(input());
      await user.type(input(), "-1{Enter}");

      // The minus is stripped at the keystroke -- the field never holds
      // "-1", only "1", which equals the already-committed score.
      expect(input().value).toBe("1");
      expect(onCommit).not.toHaveBeenCalled();
    },
  );

  it("fires no commit when the typed value is unchanged", async () => {
    const user = userEvent.setup();
    const { onCommit } = renderEditor({ my_score: 8 });

    await user.click(input());
    await user.tab();

    expect(onCommit).not.toHaveBeenCalled();
  });

  it("rounds a committed decimal score to the nearest integer", async () => {
    const user = userEvent.setup();
    const { onCommit } = renderEditor({ my_score: null });

    await user.type(input(), "7.6");
    await user.tab();

    expect(onCommit).toHaveBeenCalledExactlyOnceWith(8);
  });

  it("Escape cancels the typed draft without committing", async () => {
    const user = userEvent.setup();
    const { onCommit } = renderEditor({ my_score: 5 });

    await user.clear(input());
    await user.type(input(), "9{Escape}");
    await user.tab();

    expect(onCommit).not.toHaveBeenCalled();
  });

  it("Quitar puntuación sets the draft to empty, commits null, and closes", async () => {
    const user = userEvent.setup();
    const { onCommit, onRequestClose } = renderEditor({ my_score: 8 });

    await user.click(clearButton());

    expect(input().value).toBe("");
    expect(onCommit).toHaveBeenCalledExactlyOnceWith(null);
    expect(onRequestClose).toHaveBeenCalledOnce();
  });

  it(
    "clicking Quitar puntuación while the field is focused with an uncommitted edit does not " +
      "fire a stray blur-commit first -- exactly one commit (null) reaches the caller",
    async () => {
      const user = userEvent.setup();
      const { onCommit } = renderEditor({ my_score: 8 });

      // Focuses the field and leaves an uncommitted, unblurred edit -- the
      // discriminating setup: without the mousedown guard, clicking the
      // button below would blur the input first and commit "5" (a valid,
      // in-range, changed value), then the click itself would commit `null`
      // on top of that -- two commits instead of one.
      await user.clear(input());
      await user.type(input(), "5");
      expect(onCommit).not.toHaveBeenCalled();

      await user.click(clearButton());

      expect(onCommit).toHaveBeenCalledExactlyOnceWith(null);
    },
  );
});
