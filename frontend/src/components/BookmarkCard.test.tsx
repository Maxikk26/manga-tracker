import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BookmarkCard } from "./BookmarkCard";
import { makeBookmark } from "../test/fixtures";
import type { Bookmark } from "../domain/types";

function renderCard(bookmark: Bookmark, { saving = false } = {}) {
  const onChangeProgress = vi.fn();
  const onChangeStatus = vi.fn();
  const onChangeScore = vi.fn();
  render(
    <BookmarkCard
      bookmark={bookmark}
      saving={saving}
      onChangeProgress={onChangeProgress}
      onChangeStatus={onChangeStatus}
      onChangeScore={onChangeScore}
    />,
  );
  return { onChangeProgress, onChangeStatus, onChangeScore };
}

const image = () => document.querySelector("img.cover-image") as HTMLImageElement | null;

// The progress and score editors are both `InlineNumberEdit`s and share the
// exact same accessible name -- rendered in this order (progress first),
// which is what disambiguates them here, not a new label (BookmarkCard is
// placed plainly per the hard constraint: zero visual/labelling decisions).
const progressEditor = () => screen.getAllByTitle(/haz clic para editar/i)[0];
const scoreEditor = () => screen.getAllByTitle(/haz clic para editar/i)[1];

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

  it("makes the poster itself the link to the manga's chapter list", () => {
    // The cover is the entry point, not decoration: demoting it to a thumbnail
    // beside a text link would undo the reason this design was chosen.
    renderCard(
      makeBookmark({
        title: "One Piece",
        manga_url: "https://example.test/manga/one-piece",
        latest_chapter_num: 1120,
        latest_chapter_url: "https://example.test/manga/one-piece/chapter-1120",
      }),
    );

    const link = screen.getByRole("link", { name: /Ver capítulos de One Piece/i });
    expect(link).toHaveAttribute("href", "https://example.test/manga/one-piece");
    expect(link.querySelector("img.cover-image")).toBeInTheDocument();
  });

  it("never sends the owner to the latest chapter", () => {
    // The regression this whole change exists to kill: read up to 175 with 800
    // available, the latest chapter is 625 past where he left off. The list is
    // the destination; the chapter url must not appear on the anchor at all.
    renderCard(
      makeBookmark({
        manga_url: "https://example.test/manga/necromancer",
        last_chapter_read: 175,
        latest_chapter_num: 800,
        latest_chapter_url: "https://example.test/manga/necromancer/chapter-800",
      }),
    );

    expect(screen.getByRole("link")).toHaveAttribute(
      "href",
      "https://example.test/manga/necromancer",
    );
  });

  it("links a mapped title that has no detected chapter yet", () => {
    // Added by hand and not yet swept. The chapter list is still a real page,
    // so gating the link on a detection would hide it for no reason.
    renderCard(
      makeBookmark({
        manga_url: "https://example.test/manga/just-added",
        latest_chapter_num: null,
        latest_chapter_url: null,
        behind: null,
      }),
    );

    expect(screen.getByRole("link")).toHaveAttribute(
      "href",
      "https://example.test/manga/just-added",
    );
  });

  it("renders no link when the manga has no source mapping", () => {
    // A pending Kitsu entry whose url was never pasted — 59 of 229 in
    // production. A dead anchor reads as a broken feature; the cover stays.
    renderCard(
      makeBookmark({ manga_url: null, latest_chapter_num: null, latest_chapter_url: null }),
    );

    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(image()).toBeInTheDocument();
  });
});

describe("the backlog-count pill", () => {
  // Retired on purpose (design decision 4): it fired on 18 of 18 reading rows
  // in production, so as a signal it carried no information. This guard
  // exists so nobody restores it later thinking its absence is a regression
  // -- recoverable only from git history if it is ever reconsidered.
  it("never renders, at any backlog size", () => {
    renderCard(makeBookmark({ behind: 50 }));

    expect(document.querySelector(".behind-pill")).not.toBeInTheDocument();
  });
});

describe("the caught-up fade and its chip", () => {
  it("marks a caught-up card done and shows the Al día chip outside Todo", () => {
    renderCard(makeBookmark({ behind: 0 }));

    expect(document.querySelector(".card")).toHaveAttribute("data-done");
    expect(screen.getByText("Al día")).toBeInTheDocument();
  });

  it("shows neither the fade nor the chip while behind", () => {
    renderCard(makeBookmark({ behind: 5 }));

    expect(document.querySelector(".card")).not.toHaveAttribute("data-done");
    expect(screen.queryByText("Al día")).not.toBeInTheDocument();
  });

  it("shows the status pill instead of Al día when showStatus is set, even caught up", () => {
    const onChangeProgress = vi.fn();
    const onChangeStatus = vi.fn();
    const onChangeScore = vi.fn();
    render(
      <BookmarkCard
        bookmark={makeBookmark({ behind: 0, status: "dropped" })}
        saving={false}
        showStatus
        onChangeProgress={onChangeProgress}
        onChangeStatus={onChangeStatus}
        onChangeScore={onChangeScore}
      />,
    );

    // Not `getByText`: the status `<select>` (task 1.4) also renders an
    // "Abandonado" option, so the chip is asserted by its own selector.
    expect(document.querySelector(".chip-status")).toHaveTextContent("Abandonado");
    expect(screen.queryByText("Al día")).not.toBeInTheDocument();
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

    expect(progressEditor()).toHaveTextContent("—");
    expect(screen.queryByText(/null/)).not.toBeInTheDocument();
  });

  it("opens an empty editor and fires no PATCH on blur without typing", async () => {
    const user = userEvent.setup();
    const { onChangeProgress } = renderCard(makeBookmark({ last_chapter_read: null }));

    await user.click(progressEditor());
    expect(screen.getByRole("spinbutton")).toHaveValue(null); // empty, not 0

    await user.tab();
    expect(onChangeProgress).not.toHaveBeenCalled();
  });

  it("fires onChangeProgress with the bookmark id and the committed value", async () => {
    const user = userEvent.setup();
    const { onChangeProgress } = renderCard(makeBookmark({ id: 42, last_chapter_read: 10 }));

    await user.click(progressEditor());
    const input = screen.getByRole("spinbutton");
    await user.clear(input);
    await user.type(input, "12{Enter}");

    expect(onChangeProgress).toHaveBeenCalledExactlyOnceWith(42, 12);
  });
});

describe("score", () => {
  it("renders an em dash when my_score is null", () => {
    renderCard(makeBookmark({ my_score: null }));

    expect(scoreEditor()).toHaveTextContent("—");
  });

  it("renders the stored score", () => {
    renderCard(makeBookmark({ my_score: 8 }));

    expect(scoreEditor()).toHaveTextContent("8");
  });

  it("fires onChangeScore with the bookmark id and the committed value", async () => {
    const user = userEvent.setup();
    const { onChangeScore } = renderCard(makeBookmark({ id: 42, my_score: null }));

    await user.click(scoreEditor());
    const input = screen.getByRole("spinbutton");
    await user.type(input, "7{Enter}");

    expect(onChangeScore).toHaveBeenCalledExactlyOnceWith(42, 7);
  });

  it("fires onChangeScore with null when the field is blanked out", async () => {
    const user = userEvent.setup();
    const { onChangeScore } = renderCard(makeBookmark({ id: 42, my_score: 6 }));

    await user.click(scoreEditor());
    const input = screen.getByRole("spinbutton");
    await user.clear(input);
    await user.tab();

    expect(onChangeScore).toHaveBeenCalledExactlyOnceWith(42, null);
  });

  it("rejects a score above 10", async () => {
    const user = userEvent.setup();
    const { onChangeScore } = renderCard(makeBookmark({ id: 42, my_score: null }));

    await user.click(scoreEditor());
    const input = screen.getByRole("spinbutton");
    await user.type(input, "11{Enter}");

    expect(onChangeScore).not.toHaveBeenCalled();
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

  it("locks every editor while the row is saving", () => {
    renderCard(makeBookmark(), { saving: true });

    expect(screen.getByRole("combobox")).toBeDisabled();
    for (const editor of screen.getAllByTitle(/haz clic para editar/i)) {
      expect(editor).toBeDisabled();
    }
  });
});
