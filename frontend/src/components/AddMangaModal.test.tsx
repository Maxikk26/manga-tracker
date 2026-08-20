import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AddMangaModal } from "./AddMangaModal";
import type { MangaPreview } from "../domain/types";

const preview: MangaPreview = {
  slug: "one-piece",
  url: "https://example.test/manga/one-piece",
  title: "One Piece",
  cover_url: "https://example.test/cover.jpg",
  publication_status_text: "En curso",
};

// The modal's own cover image, never queried by role: alt="" gives it the
// "presentation" role, not "img" (same convention as BookmarkCard.test.tsx).
const modalCoverImage = () =>
  document.querySelector("img.modal-preview-cover") as HTMLImageElement | null;

function baseProps() {
  return {
    url: "https://example.test/manga/one-piece",
    onChangeUrl: vi.fn(),
    status: "reading" as const,
    onChangeStatus: vi.fn(),
    lastChapterRead: "",
    onChangeLastChapterRead: vi.fn(),
    preview: null,
    previewing: false,
    confirming: false,
    errorMessage: null,
    existing: null,
    onPreview: vi.fn(),
    onConfirm: vi.fn(),
    onViewExisting: vi.fn(),
    onClose: vi.fn(),
  };
}

describe("AddMangaModal", () => {
  it("renders as a dialog with a required, autofocused URL field", () => {
    render(<AddMangaModal {...baseProps()} />);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    const input = screen.getByLabelText(/url de la ficha/i);
    expect(input).toHaveFocus();
    expect(input).toBeRequired();
  });

  it("the chapter field is the decimal text input, not a native number input", () => {
    render(<AddMangaModal {...baseProps()} />);
    const input = screen.getByLabelText(/capítulo inicial/i);
    expect(input).toHaveAttribute("type", "text");
    expect(input).toHaveAttribute("inputmode", "decimal");
    expect(input).toHaveAttribute("placeholder", "0");
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
  });

  it("shows the preview panel with title, cover and publication status", () => {
    render(<AddMangaModal {...baseProps()} preview={preview} />);

    expect(screen.getByText("One Piece")).toBeInTheDocument();
    expect(screen.getByText("En curso")).toBeInTheDocument();
    // Proxied through the panel — the raw CDN URL 403s without a manganato
    // Referer, so pointing the <img> at it always showed the fallback.
    expect(modalCoverImage()).toHaveAttribute(
      "src",
      `/api/mangas/preview-cover?url=${encodeURIComponent(preview.cover_url!)}`,
    );
  });

  it("falls back when the cover candidate fails to load", () => {
    render(<AddMangaModal {...baseProps()} preview={preview} />);

    fireEvent.error(modalCoverImage()!);

    expect(modalCoverImage()).not.toBeInTheDocument();
    expect(screen.getByText("Sin portada")).toBeInTheDocument();
  });

  it("disables the confirm button until a preview exists", () => {
    const { rerender } = render(<AddMangaModal {...baseProps()} />);
    expect(screen.getByRole("button", { name: /^agregar$/i })).toBeDisabled();

    rerender(<AddMangaModal {...baseProps()} preview={preview} />);
    expect(screen.getByRole("button", { name: /^agregar$/i })).toBeEnabled();
  });

  it("closes (after the exit transition) on Escape", async () => {
    const onClose = vi.fn();
    render(<AddMangaModal {...baseProps()} onClose={onClose} />);

    fireEvent.keyDown(document, { key: "Escape" });

    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it("closes (after the exit transition) on a backdrop click", async () => {
    const onClose = vi.fn();
    const { container } = render(<AddMangaModal {...baseProps()} onClose={onClose} />);

    fireEvent.click(container.querySelector(".modal-backdrop")!);

    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it("does not close on a click inside the dialog itself", () => {
    const onClose = vi.fn();
    render(<AddMangaModal {...baseProps()} onClose={onClose} />);

    fireEvent.click(screen.getByRole("dialog"));

    expect(onClose).not.toHaveBeenCalled();
  });

  it("ignores Escape and backdrop clicks while a request is in flight", () => {
    const onClose = vi.fn();
    const { container } = render(
      <AddMangaModal {...baseProps()} onClose={onClose} confirming />,
    );

    fireEvent.keyDown(document, { key: "Escape" });
    fireEvent.click(container.querySelector(".modal-backdrop")!);

    expect(onClose).not.toHaveBeenCalled();
  });

  it("disables every control while busy", () => {
    const { container } = render(
      <AddMangaModal {...baseProps()} preview={preview} confirming />,
    );

    expect(screen.getByLabelText(/url de la ficha/i)).toBeDisabled();
    expect(screen.getByRole("combobox")).toBeDisabled();
    expect(screen.getByLabelText(/capítulo inicial/i)).toBeDisabled();
    expect(screen.getByRole("button", { name: /cancelar/i })).toBeDisabled();
    expect(container.querySelector(".modal-confirm")).toBeDisabled();
  });

  it("shows the reactivation affordance for a terminal duplicate", async () => {
    const onViewExisting = vi.fn();
    const user = userEvent.setup();
    render(
      <AddMangaModal
        {...baseProps()}
        errorMessage="«Berserk» ya está en tu lista, con estado Abandonado. Para retomarlo, cámbiale el estado…"
        existing={{ title: "Berserk", status: "dropped", terminal: true }}
        onViewExisting={onViewExisting}
      />,
    );

    expect(screen.getByText(/Berserk/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /ver en «abandonado»/i }));

    expect(onViewExisting).toHaveBeenCalledTimes(1);
  });

  it("submits the form (Enter in the URL field) as a preview request", () => {
    const onPreview = vi.fn();
    render(<AddMangaModal {...baseProps()} onPreview={onPreview} />);

    fireEvent.submit(screen.getByLabelText(/url de la ficha/i).closest("form")!);

    expect(onPreview).toHaveBeenCalledTimes(1);
  });
});
