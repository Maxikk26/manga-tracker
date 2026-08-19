import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BookmarkCard } from "./BookmarkCard";
import { makeBookmark } from "../test/fixtures";
import type { Bookmark } from "../domain/types";

function renderCard(bookmark: Bookmark, { saving = false } = {}) {
  const onChangeProgress = vi.fn();
  const onChangeStatus = vi.fn();
  render(
    <BookmarkCard
      bookmark={bookmark}
      saving={saving}
      onChangeProgress={onChangeProgress}
      onChangeStatus={onChangeStatus}
    />,
  );
  return { onChangeProgress, onChangeStatus };
}

const image = () => document.querySelector("img.cover-image") as HTMLImageElement | null;

describe("the cover", () => {
  it("asks the panel's own api, never the address the database stored", () => {
    // The source's image hosts answer 403 without their own Referer, so a
    // hotlinked cover renders broken. This is the guard against reintroducing
    // that by pointing the img at cover_url.
    renderCard(makeBookmark({ manga_id: 77 }));

    expect(image()).toHaveAttribute("src", "/api/covers/77");
  });

  it("falls back to the title's initials when the api has no cover", () => {
    // 404 there is ordinary: a manga can be listed long before cache-covers
    // reaches it.
    renderCard(makeBookmark({ title: "The Regressed Mercenary" }));

    fireEvent.error(image()!);

    expect(image()).not.toBeInTheDocument();
    expect(screen.getByText("RM")).toBeInTheDocument();
  });

  it("gives colliding titles different initials", () => {
    // The reason the fallback is not a grey box: on the real list "Genius"
    // appears in three titles and "Regressed" in two.
    renderCard(makeBookmark({ title: "Supreme Academy Genius" }));
    fireEvent.error(image()!);

    expect(screen.getByText("SA")).toBeInTheDocument();
  });

  it("makes the poster itself the link to the next chapter", () => {
    // The cover is the entry point, not decoration: demoting it to a thumbnail
    // beside a text link would undo the reason this design was chosen.
    renderCard(
      makeBookmark({
        title: "One Piece",
        latest_chapter_num: 1120,
        latest_chapter_url: "https://example.test/one-piece/1120",
      }),
    );

    const link = screen.getByRole("link", { name: /Leer One Piece, capítulo 1120/i });
    expect(link).toHaveAttribute("href", "https://example.test/one-piece/1120");
    expect(link.querySelector("img.cover-image")).toBeInTheDocument();
  });

  it("renders no link when nothing has been detected at the source", () => {
    // A dead anchor reads as a broken feature; the cover still shows.
    renderCard(makeBookmark({ latest_chapter_num: null, latest_chapter_url: null }));

    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(image()).toBeInTheDocument();
  });
});

describe("the behind pill", () => {
  it("shows the count compactly instead of as a sentence", () => {
    // It fires on 18 of 18 reading rows in production, so as prose it carried
    // no information and competed with the title.
    renderCard(makeBookmark({ behind: 7 }));

    expect(screen.getByText("+7")).toBeInTheDocument();
    expect(screen.queryByText(/atrasado/i)).not.toBeInTheDocument();
  });

  it("never shows a floating point tail", () => {
    // Real production value: chapter 32.2 minus 11 is 21.200000000000003 in
    // IEEE 754, and it reached the panel verbatim.
    renderCard(makeBookmark({ behind: 21.200000000000003 }));

    expect(screen.getByText("+21")).toBeInTheDocument();
    expect(screen.queryByText(/\.\d/)).not.toBeInTheDocument();
  });

  it("keeps the exact value one hover away", () => {
    renderCard(makeBookmark({ behind: 21.5 }));
    expect(screen.getByTitle("21.5 sin leer")).toBeInTheDocument();
  });

  it("is absent when behind is 0", () => {
    renderCard(makeBookmark({ behind: 0 }));
    expect(screen.queryByText(/^\+/)).not.toBeInTheDocument();
  });

  it("is absent when behind is null", () => {
    renderCard(makeBookmark({ behind: null }));
    expect(screen.queryByText(/^\+/)).not.toBeInTheDocument();
  });
});

describe("progress", () => {
  it("renders '~' when progress_is_approx is true (JSON boolean, not 0/1)", () => {
    renderCard(makeBookmark({ progress_is_approx: true }));
    expect(screen.getByTitle(/aproximado/i)).toHaveTextContent("~");
  });

  it("does not render '~' when progress_is_approx is false", () => {
    renderCard(makeBookmark({ progress_is_approx: false }));
    expect(screen.queryByTitle(/aproximado/i)).not.toBeInTheDocument();
  });

  it("renders an em dash for a never-read bookmark, never the string 'null'", () => {
    renderCard(makeBookmark({ last_chapter_read: null, behind: null }));

    expect(screen.getByTitle(/haz clic para editar/i)).toHaveTextContent("—");
    expect(screen.queryByText(/null/)).not.toBeInTheDocument();
  });

  it("opens an empty editor and fires no PATCH on blur without typing", async () => {
    const user = userEvent.setup();
    const { onChangeProgress } = renderCard(makeBookmark({ last_chapter_read: null }));

    await user.click(screen.getByTitle(/haz clic para editar/i));
    expect(screen.getByRole("spinbutton")).toHaveValue(null); // empty, not 0

    await user.tab();
    expect(onChangeProgress).not.toHaveBeenCalled();
  });

  it("fires onChangeProgress with the bookmark id and the committed value", async () => {
    const user = userEvent.setup();
    const { onChangeProgress } = renderCard(makeBookmark({ id: 42, last_chapter_read: 10 }));

    await user.click(screen.getByTitle(/haz clic para editar/i));
    const input = screen.getByRole("spinbutton");
    await user.clear(input);
    await user.type(input, "12{Enter}");

    expect(onChangeProgress).toHaveBeenCalledExactlyOnceWith(42, 12);
  });
});

describe("status", () => {
  it("fires onChangeStatus when the select changes", async () => {
    // Carried over from the table deliberately: changing status is fase 1
    // functionality and the prototype's card did not have it.
    const user = userEvent.setup();
    const { onChangeStatus } = renderCard(makeBookmark({ id: 42 }));

    await user.selectOptions(screen.getByRole("combobox"), "on_hold");

    expect(onChangeStatus).toHaveBeenCalledExactlyOnceWith(42, "on_hold");
  });

  it("locks both editors while the row is saving", () => {
    renderCard(makeBookmark(), { saving: true });

    expect(screen.getByRole("combobox")).toBeDisabled();
    expect(screen.getByTitle(/haz clic para editar/i)).toBeDisabled();
  });
});
