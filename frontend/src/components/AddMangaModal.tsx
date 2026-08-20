import { useEffect, useState } from "react";
import { BOOKMARK_STATUSES, type BookmarkStatus, type ExistingManga, type MangaPreview } from "../domain/types";
import { STATUS_LABELS } from "../domain/statusLabels";
import { DecimalInput } from "./DecimalInput";

interface Props {
  url: string;
  onChangeUrl: (value: string) => void;
  status: BookmarkStatus;
  onChangeStatus: (value: BookmarkStatus) => void;
  /** Raw text draft — DecimalInput guarantees it is a positive decimal or
   *  "" (the container submits "" as 0). */
  lastChapterRead: string;
  onChangeLastChapterRead: (value: string) => void;
  preview: MangaPreview | null;
  previewing: boolean;
  confirming: boolean;
  errorMessage: string | null;
  existing: ExistingManga | null;
  onPreview: () => void;
  onConfirm: () => void;
  onViewExisting: () => void;
  /** Called once the exit transition has finished — the caller unmounts. */
  onClose: () => void;
}

// The exit transition's own duration (design: 140ms). Kept in one place so
// the unmount timer and the CSS `.modal-closing` duration cannot drift.
const EXIT_DURATION_MS = 140;

/**
 * Pure modal chrome: a plain `<div role="dialog" aria-modal="true">`, not
 * `<dialog>` — `showModal` is unevenly implemented in jsdom and the suite
 * must stay deterministic (design's Modal UX decisions). All add-flow state
 * (url/status/chapter, the preview, in-flight flags, the error/`existing`
 * pair) lives in `AddMangaContainer`; this component only renders it and
 * reports intent upward.
 */
export function AddMangaModal({
  url,
  onChangeUrl,
  status,
  onChangeStatus,
  lastChapterRead,
  onChangeLastChapterRead,
  preview,
  previewing,
  confirming,
  errorMessage,
  existing,
  onPreview,
  onConfirm,
  onViewExisting,
  onClose,
}: Props) {
  const busy = previewing || confirming;
  const [mounted, setMounted] = useState(false);
  const [closing, setClosing] = useState(false);
  const [coverFailed, setCoverFailed] = useState(false);

  // Entrance: mount at the initial (scale 0.96, opacity 0) frame, then flip to
  // the open frame on the next animation frame so the browser has a state to
  // transition from (the legacy `data-mounted` pattern; no @starting-style
  // dependency).
  useEffect(() => {
    const id = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(id);
  }, []);

  // A new preview candidate gets its own fallback chance.
  useEffect(() => {
    setCoverFailed(false);
  }, [preview?.cover_url]);

  useEffect(() => {
    if (!closing) return;
    const id = setTimeout(onClose, EXIT_DURATION_MS);
    return () => clearTimeout(id);
  }, [closing, onClose]);

  function requestClose() {
    if (busy) return; // a request is in flight: Escape/backdrop do nothing
    setClosing(true);
  }

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") requestClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busy]);

  const stateClass = closing ? "modal-closing" : mounted ? "modal-open" : "";

  return (
    <div
      className={`modal-backdrop ${stateClass}`.trim()}
      onClick={(event) => {
        if (event.target === event.currentTarget) requestClose();
      }}
    >
      <div
        className={`modal ${stateClass}`.trim()}
        role="dialog"
        aria-modal="true"
        aria-label="Agregar manga"
      >
        <form
          onSubmit={(event) => {
            event.preventDefault();
            onPreview();
          }}
        >
          <label className="modal-field">
            URL de la ficha
            <input
              type="url"
              required
              autoFocus
              value={url}
              disabled={busy}
              onChange={(event) => onChangeUrl(event.target.value)}
            />
          </label>

          <label className="modal-field">
            Estado
            <select
              value={status}
              disabled={busy}
              onChange={(event) => onChangeStatus(event.target.value as BookmarkStatus)}
            >
              {BOOKMARK_STATUSES.map((value) => (
                <option key={value} value={value}>
                  {STATUS_LABELS[value]}
                </option>
              ))}
            </select>
          </label>

          <label className="modal-field">
            Capítulo inicial
            <DecimalInput
              value={lastChapterRead}
              onChange={onChangeLastChapterRead}
              disabled={busy}
            />
          </label>

          {errorMessage && (
            <p className="modal-error" role="alert">
              {errorMessage}
              {existing && (
                <button
                  type="button"
                  className="modal-view-existing"
                  onClick={onViewExisting}
                >
                  Ver en «{STATUS_LABELS[existing.status]}»
                </button>
              )}
            </p>
          )}

          {preview && (
            <div className="modal-preview">
              {preview.cover_url && !coverFailed ? (
                <img
                  className="modal-preview-cover"
                  // Proxied through the panel, never the raw CDN URL: the
                  // source's image hosts answer 403 to a hotlinked <img>
                  // (no manganato Referer), so the raw URL always fell back.
                  src={`/api/mangas/preview-cover?url=${encodeURIComponent(preview.cover_url)}`}
                  alt=""
                  onError={() => setCoverFailed(true)}
                />
              ) : (
                <span
                  className="modal-preview-cover modal-preview-cover-fallback"
                  aria-hidden="true"
                >
                  Sin portada
                </span>
              )}
              <div>
                <p className="modal-preview-title">{preview.title}</p>
                {preview.publication_status_text && (
                  <p className="modal-preview-status muted">
                    {preview.publication_status_text}
                  </p>
                )}
              </div>
            </div>
          )}

          <div className="modal-actions">
            <button
              type="button"
              className="modal-cancel"
              onClick={requestClose}
              disabled={busy}
            >
              Cancelar
            </button>
            <button type="submit" className="modal-submit" disabled={busy || !url.trim()}>
              {previewing ? "Buscando…" : "Vista previa"}
            </button>
            <button
              type="button"
              className="modal-confirm"
              disabled={busy || !preview}
              onClick={onConfirm}
            >
              {confirming ? "Agregando…" : "Agregar"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
