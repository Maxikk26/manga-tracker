import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BookmarkRow } from "./BookmarkRow";
import { makeBookmark } from "../test/fixtures";
import type { Bookmark } from "../domain/types";

function renderRow(bookmark: Bookmark) {
  const onChangeProgress = vi.fn();
  const onChangeStatus = vi.fn();
  render(
    <table>
      <tbody>
        <BookmarkRow
          bookmark={bookmark}
          saving={false}
          onChangeProgress={onChangeProgress}
          onChangeStatus={onChangeStatus}
        />
      </tbody>
    </table>,
  );
  return { onChangeProgress, onChangeStatus };
}

describe("BookmarkRow", () => {
  describe("approx marker", () => {
    it("renders '~' when progress_is_approx is true (JSON boolean, not 0/1)", () => {
      renderRow(makeBookmark({ progress_is_approx: true }));
      expect(screen.getByTitle(/aproximado/i)).toHaveTextContent("~");
    });

    it("does not render '~' when progress_is_approx is false", () => {
      renderRow(makeBookmark({ progress_is_approx: false }));
      expect(screen.queryByTitle(/aproximado/i)).not.toBeInTheDocument();
    });
  });

  describe("null progress (never-read bookmark)", () => {
    const neverRead = () =>
      makeBookmark({ last_chapter_read: null, behind: null, last_read_at: null });

    it("renders an em dash, never the string 'null'", () => {
      renderRow(neverRead());
      expect(
        screen.getByTitle(/haz clic para editar/i),
      ).toHaveTextContent("—");
      expect(screen.queryByText(/null/)).not.toBeInTheDocument();
    });

    it("opens an empty editor and fires no PATCH on blur without typing", async () => {
      const user = userEvent.setup();
      const { onChangeProgress } = renderRow(neverRead());

      await user.click(screen.getByTitle(/haz clic para editar/i));
      const input = screen.getByRole("spinbutton");
      expect(input).toHaveValue(null); // empty editor, not 0

      await user.tab(); // blur without typing
      expect(onChangeProgress).not.toHaveBeenCalled();
    });
  });

  describe("behind badge", () => {
    it("uses the singular for 1 chapter", () => {
      renderRow(makeBookmark({ behind: 1 }));
      expect(screen.getByText("Vas atrasado 1 capítulo")).toBeInTheDocument();
    });

    it("uses the plural for more than 1 chapter", () => {
      renderRow(makeBookmark({ behind: 7 }));
      expect(screen.getByText("Vas atrasado 7 capítulos")).toBeInTheDocument();
    });

    it("is absent when behind is 0", () => {
      renderRow(makeBookmark({ behind: 0 }));
      expect(screen.queryByText(/atrasado/i)).not.toBeInTheDocument();
    });

    it("is absent when behind is null", () => {
      renderRow(makeBookmark({ behind: null }));
      expect(screen.queryByText(/atrasado/i)).not.toBeInTheDocument();
    });
  });

  it("fires onChangeProgress with the row id and the committed value", async () => {
    const user = userEvent.setup();
    const { onChangeProgress } = renderRow(
      makeBookmark({ id: 42, last_chapter_read: 10 }),
    );

    await user.click(screen.getByTitle(/haz clic para editar/i));
    const input = screen.getByRole("spinbutton");
    await user.clear(input);
    await user.type(input, "12{Enter}");

    expect(onChangeProgress).toHaveBeenCalledExactlyOnceWith(42, 12);
  });

  it("fires onChangeStatus when the status select changes", async () => {
    const user = userEvent.setup();
    const { onChangeStatus } = renderRow(makeBookmark({ id: 42 }));

    await user.selectOptions(screen.getByRole("combobox"), "on_hold");

    expect(onChangeStatus).toHaveBeenCalledExactlyOnceWith(42, "on_hold");
  });
});
