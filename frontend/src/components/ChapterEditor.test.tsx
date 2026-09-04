import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChapterEditor } from "./ChapterEditor";
import { makeBookmark } from "../test/fixtures";

const input = () => screen.getByRole("textbox", { name: "Capítulo leído" }) as HTMLInputElement;
const minus = () => screen.getByRole("button", { name: "Uno menos" });
const plus = () => screen.getByRole("button", { name: "Uno más" });

function renderEditor(overrides: Parameters<typeof makeBookmark>[0] = {}) {
  const onCommit = vi.fn();
  const onRequestClose = vi.fn();
  render(
    <ChapterEditor
      bookmark={makeBookmark(overrides)}
      onCommit={onCommit}
      onRequestClose={onRequestClose}
    />,
  );
  return { onCommit, onRequestClose };
}

describe("ChapterEditor", () => {
  it("seeds an empty field for a never-read bookmark, never the literal string 'null'", () => {
    renderEditor({ last_chapter_read: null });

    expect(input().value).toBe("");
    expect(screen.queryByDisplayValue("null")).not.toBeInTheDocument();
  });

  it("disables the minus stepper at 0", () => {
    renderEditor({ last_chapter_read: 0 });

    expect(minus()).toBeDisabled();
  });

  it("does not disable the minus stepper above 0", () => {
    renderEditor({ last_chapter_read: 5 });

    expect(minus()).not.toBeDisabled();
  });

  it("commits immediately on a stepper click, never waiting for blur", async () => {
    const user = userEvent.setup();
    const { onCommit } = renderEditor({ id: 7, last_chapter_read: 10 });

    await user.click(plus());

    expect(onCommit).toHaveBeenCalledExactlyOnceWith(11);
    expect(input().value).toBe("11");
  });

  it("the minus stepper commits one less, floored at 0", async () => {
    const user = userEvent.setup();
    const { onCommit } = renderEditor({ last_chapter_read: 0.5 });

    await user.click(minus());

    expect(onCommit).toHaveBeenCalledExactlyOnceWith(0);
  });

  it("a typed value commits on blur, never per keystroke", async () => {
    const user = userEvent.setup();
    const { onCommit } = renderEditor({ last_chapter_read: 10 });

    await user.clear(input());
    await user.type(input(), "12");
    expect(onCommit).not.toHaveBeenCalled();

    await user.tab();
    expect(onCommit).toHaveBeenCalledExactlyOnceWith(12);
  });

  it("a typed value commits on Enter and requests the popover close", async () => {
    const user = userEvent.setup();
    const { onCommit, onRequestClose } = renderEditor({ last_chapter_read: 10 });

    await user.clear(input());
    await user.type(input(), "15{Enter}");

    expect(onCommit).toHaveBeenCalledExactlyOnceWith(15);
    expect(onRequestClose).toHaveBeenCalledOnce();
  });

  it("fires no commit when the typed value is unchanged", async () => {
    const user = userEvent.setup();
    const { onCommit } = renderEditor({ last_chapter_read: 10 });

    await user.click(input());
    await user.tab();

    expect(onCommit).not.toHaveBeenCalled();
  });

  it("Escape cancels the typed draft without committing", async () => {
    const user = userEvent.setup();
    const { onCommit } = renderEditor({ last_chapter_read: 10 });

    await user.clear(input());
    await user.type(input(), "99{Escape}");
    await user.tab();

    expect(onCommit).not.toHaveBeenCalled();
  });

  it("shows the total hint when latest_chapter_num is known", () => {
    renderEditor({ latest_chapter_num: 560 });

    expect(screen.getByText("de 560 publicados")).toBeInTheDocument();
  });

  it("omits the total hint when latest_chapter_num is unknown", () => {
    renderEditor({ latest_chapter_num: null });

    expect(screen.queryByText(/publicados/)).not.toBeInTheDocument();
  });

  it("shows the approx hint only when progress_is_approx is true", () => {
    renderEditor({ progress_is_approx: true });

    expect(screen.getByText("El progreso guardado es aproximado.")).toBeInTheDocument();
  });
});
