import { useCallback, useState } from "react";
import { addManga, previewManga } from "../api/mangas";
import { ApiError } from "../api/http";
import { AddMangaModal } from "../components/AddMangaModal";
import type { Bookmark, BookmarkStatus, ExistingManga, MangaPreview } from "../domain/types";

interface Props {
  /** A confirm succeeded; the parent refetches and switches to this status. */
  onAdded: (bookmark: Bookmark) => void;
  /** The "Ver en «…»" affordance was clicked: parent switches tabs and closes. */
  onViewExisting: (status: BookmarkStatus) => void;
  /** The dialog was dismissed (Escape/backdrop/Cancelar) without confirming. */
  onRequestClose: () => void;
}

/**
 * Owns the add-manga flow's state: the form fields, the preview round-trip,
 * the confirm round-trip, and the error/`existing` pair a rejection leaves
 * behind. `AddMangaModal` stays a pure renderer of whatever this holds.
 *
 * Changing the URL after a preview (or after a rejection) drops both: an
 * edited URL invalidates the old match, and confirm must not fire against a
 * preview that no longer corresponds to what is in the field (spec.md
 * "Abandoning the preview writes nothing" extends to "changing it writes
 * nothing either, until previewed again").
 */
export function AddMangaContainer({ onAdded, onViewExisting, onRequestClose }: Props) {
  const [url, setUrl] = useState("");
  const [status, setStatus] = useState<BookmarkStatus>("reading");
  const [lastChapterRead, setLastChapterRead] = useState(0);
  const [preview, setPreview] = useState<MangaPreview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [existing, setExisting] = useState<ExistingManga | null>(null);

  const handleChangeUrl = useCallback((value: string) => {
    setUrl(value);
    setPreview(null);
    setExisting(null);
    setErrorMessage(null);
  }, []);

  const handlePreview = useCallback(async () => {
    const trimmed = url.trim();
    if (!trimmed) return;
    setPreviewing(true);
    setErrorMessage(null);
    setExisting(null);
    try {
      setPreview(await previewManga(trimmed));
    } catch (error) {
      setPreview(null);
      if (error instanceof ApiError) {
        setErrorMessage(error.message);
        setExisting(error.existing ?? null);
      } else {
        setErrorMessage("Ocurrió un error inesperado al buscar el manga.");
      }
    } finally {
      setPreviewing(false);
    }
  }, [url]);

  const handleConfirm = useCallback(async () => {
    if (!preview) return;
    setConfirming(true);
    setErrorMessage(null);
    setExisting(null);
    try {
      const bookmark = await addManga({
        url: preview.url,
        title: preview.title,
        cover_url: preview.cover_url,
        status,
        last_chapter_read: lastChapterRead,
      });
      onAdded(bookmark);
    } catch (error) {
      if (error instanceof ApiError) {
        setErrorMessage(error.message);
        setExisting(error.existing ?? null);
      } else {
        setErrorMessage("Ocurrió un error inesperado al agregar el manga.");
      }
    } finally {
      setConfirming(false);
    }
  }, [preview, status, lastChapterRead, onAdded]);

  const handleViewExisting = useCallback(() => {
    if (existing) onViewExisting(existing.status);
  }, [existing, onViewExisting]);

  return (
    <AddMangaModal
      url={url}
      onChangeUrl={handleChangeUrl}
      status={status}
      onChangeStatus={setStatus}
      lastChapterRead={lastChapterRead}
      onChangeLastChapterRead={setLastChapterRead}
      preview={preview}
      previewing={previewing}
      confirming={confirming}
      errorMessage={errorMessage}
      existing={existing}
      onPreview={handlePreview}
      onConfirm={handleConfirm}
      onViewExisting={handleViewExisting}
      onClose={onRequestClose}
    />
  );
}
