import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BookmarkCard } from "./BookmarkCard";
import { makeBookmark } from "../test/fixtures";
import type { Bookmark } from "../domain/types";

function renderCard(bookmark: Bookmark, { saving = false, showStatus = false } = {}) {
  const onChangeProgress = vi.fn();
  const onChangeStatus = vi.fn();
  const onChangeScore = vi.fn();
  const onEditingChange = vi.fn();
  render(
    <BookmarkCard
      bookmark={bookmark}
      saving={saving}
      showStatus={showStatus}
      onChangeProgress={onChangeProgress}
      onChangeStatus={onChangeStatus}
      onChangeScore={onChangeScore}
      onEditingChange={onEditingChange}
    />,
  );
  return { onChangeProgress, onChangeStatus, onChangeScore, onEditingChange };
}

const image = () => document.querySelector("img.cover-image") as HTMLImageElement | null;

// Both triggers open a popover (fase 5 slices 2a/2b) and carry their own
// aria-label -- `InlineNumberEdit`'s old title attribute is gone entirely.
const chapterTrigger = () => screen.getByRole("button", { name: /^Editar capítulo leído/ });
const scoreEditor = () => screen.getByRole("button", { name: /^Editar puntuación/ });

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
    renderCard(makeBookmark({ behind: 0, status: "dropped" }), { showStatus: true });

    // Not `getByText`: the status `<select>` (task 1.4) also renders an
    // "Abandonado" option, so the chip is asserted by its own selector.
    expect(document.querySelector(".chip-status")).toHaveTextContent("Abandonado");
    expect(screen.queryByText("Al día")).not.toBeInTheDocument();
  });
});

describe("the chapter trigger and its popover (fase 5 slice 2a)", () => {
  it("carries the dotted-underline marker when progress_is_approx is true", () => {
    renderCard(makeBookmark({ progress_is_approx: true }));
    expect(chapterTrigger()).toHaveAttribute("data-approx");
  });

  it("carries no marker when progress_is_approx is false", () => {
    renderCard(makeBookmark({ progress_is_approx: false }));
    expect(chapterTrigger()).not.toHaveAttribute("data-approx");
  });

  it("renders 'Sin empezar' for a never-read bookmark, never the literal string 'null' (design D13)", () => {
    renderCard(makeBookmark({ last_chapter_read: null, behind: null }));

    expect(chapterTrigger()).toHaveTextContent("Sin empezar");
    expect(screen.queryByText(/null/)).not.toBeInTheDocument();
  });

  it("opens the chapter popover on click and reports it upward via onEditingChange", async () => {
    const user = userEvent.setup();
    const { onEditingChange } = renderCard(makeBookmark({ id: 42 }));

    await user.click(chapterTrigger());

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(onEditingChange).toHaveBeenCalledExactlyOnceWith(42, true);
  });

  it("wires the popover's commit to onChangeProgress with the bookmark id", async () => {
    const user = userEvent.setup();
    const { onChangeProgress } = renderCard(makeBookmark({ id: 42, last_chapter_read: 10 }));

    await user.click(chapterTrigger());
    const input = screen.getByRole("textbox", { name: "Capítulo leído" });
    await user.clear(input);
    await user.type(input, "12{Enter}");

    expect(onChangeProgress).toHaveBeenCalledExactlyOnceWith(42, 12);
  });

  it("is never disabled while the row is saving (design D5 -- the queue provides ordering, not `disabled`)", () => {
    renderCard(makeBookmark(), { saving: true });
    expect(chapterTrigger()).not.toBeDisabled();
  });
});

describe("score (fase 5 slice 2b)", () => {
  it("reads No puntuado when my_score is null", () => {
    renderCard(makeBookmark({ my_score: null }));

    expect(scoreEditor()).toHaveTextContent("No puntuado");
  });

  it("reads {my_score}/10 when scored", () => {
    renderCard(makeBookmark({ my_score: 8 }));

    expect(scoreEditor()).toHaveTextContent("8/10");
  });

  it("opens the score popover on click and reports it upward via onEditingChange", async () => {
    const user = userEvent.setup();
    const { onEditingChange } = renderCard(makeBookmark({ id: 42 }));

    await user.click(scoreEditor());

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(onEditingChange).toHaveBeenCalledExactlyOnceWith(42, true);
  });

  it("fires onChangeScore with the bookmark id and the committed value", async () => {
    const user = userEvent.setup();
    const { onChangeScore } = renderCard(makeBookmark({ id: 42, my_score: null }));

    await user.click(scoreEditor());
    const input = screen.getByRole("textbox", { name: /Puntuación de 0 a/ });
    await user.type(input, "7{Enter}");

    expect(onChangeScore).toHaveBeenCalledExactlyOnceWith(42, 7);
  });

  it("fires onChangeScore with null when the field is blanked out", async () => {
    const user = userEvent.setup();
    const { onChangeScore } = renderCard(makeBookmark({ id: 42, my_score: 6 }));

    await user.click(scoreEditor());
    const input = screen.getByRole("textbox", { name: /Puntuación de 0 a/ });
    await user.clear(input);
    await user.tab();

    expect(onChangeScore).toHaveBeenCalledExactlyOnceWith(42, null);
  });

  it("rejects a score above 10", async () => {
    const user = userEvent.setup();
    const { onChangeScore } = renderCard(makeBookmark({ id: 42, my_score: null }));

    await user.click(scoreEditor());
    const input = screen.getByRole("textbox", { name: /Puntuación de 0 a/ });
    await user.type(input, "11{Enter}");

    expect(onChangeScore).not.toHaveBeenCalled();
  });

  it("is never disabled while the row is saving (design D5, same as the chapter trigger)", () => {
    renderCard(makeBookmark(), { saving: true });

    expect(scoreEditor()).not.toBeDisabled();
  });
});

describe("status (fase 5 slice 2b -- now inside the chapter popover, design D12)", () => {
  it("fires onChangeStatus with the bookmark id and closes the popover", async () => {
    // Carried over from the table deliberately: changing status is fase 1
    // functionality and the prototype's card did not have it.
    const user = userEvent.setup();
    const { onChangeStatus } = renderCard(makeBookmark({ id: 42, title: "One Piece" }));

    await user.click(chapterTrigger());
    const select = screen.getByRole("combobox", { name: "Estado de One Piece" });
    await user.selectOptions(select, "on_hold");

    expect(onChangeStatus).toHaveBeenCalledExactlyOnceWith(42, "on_hold");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
