import { useRef, useState, type KeyboardEvent } from "react";
import { BOOKMARK_STATUSES, type Bookmark, type BookmarkStatus } from "../domain/types";
import { STATUS_LABELS } from "../domain/statusLabels";
import { DecimalInput } from "./DecimalInput";

interface Props {
  bookmark: Bookmark;
  onCommit: (value: number) => void;
  /** Fired by the status row (design D12/Q4). Selecting a different status
   *  commits it and closes the popover -- the caller is expected to call
   *  `onRequestClose` right after, same as the select's own `onChange` does
   *  below. */
  onCommitStatus: (status: BookmarkStatus) => void;
  /** The popover's own close, threaded straight through (design D3: the card
   *  owns the popover, this is the same callback passed as `onDismiss` to
   *  `Popover`). Enter commits, then closes. */
  onRequestClose: () => void;
}

/** Floors at zero, rounds to the nearest tenth -- PROTO's stepper
 *  arithmetic, verbatim (chapters are decimal: the source publishes
 *  numbers like 32.2). */
function stepValue(current: number, delta: number): number {
  return Math.max(0, Math.round((current + delta) * 10) / 10);
}

/**
 * The chapter half of the popover (design D2/D11/D3), plus the status row
 * (design D12): the chapter popover is where status now lives too, so the
 * standalone `<select>` that used to sit below the card is gone (fase 5
 * slice 2b).
 *
 * The draft is seeded once, from the bookmark prop at the moment this
 * component is created (never re-seeded from a later refetch while the
 * popover stays open -- the same class of bug the ordering freeze exists to
 * prevent). A never-read bookmark (`last_chapter_read: null`) seeds an empty
 * field, never the literal string "null" (the guard PROTO's own
 * `openChapterPop` is missing).
 */
export function ChapterEditor({ bookmark, onCommit, onCommitStatus, onRequestClose }: Props) {
  const [draft, setDraft] = useState(() =>
    bookmark.last_chapter_read === null ? "" : String(bookmark.last_chapter_read),
  );
  // The value already known to be committed -- server truth on mount, then
  // whatever the last successful commit (stepper or typed) sent. Comparing
  // against this, not the original prop, is what makes a blur after a
  // stepper commit correctly a no-op.
  const committedRef = useRef(bookmark.last_chapter_read);
  // Escape must not let a resulting blur commit the abandoned draft.
  const cancelledRef = useRef(false);

  function commit(raw: string) {
    const trimmed = raw.trim();
    if (trimmed === "") return; // blank never clears a chapter (unlike score)
    const parsed = Number(trimmed);
    if (!Number.isFinite(parsed) || parsed < 0) return;
    if (parsed === committedRef.current) return; // unchanged: no PATCH
    committedRef.current = parsed;
    onCommit(parsed);
  }

  function step(delta: number) {
    const current = draft.trim() === "" ? 0 : Number(draft);
    const next = stepValue(Number.isFinite(current) ? current : 0, delta);
    const nextDraft = String(next);
    setDraft(nextDraft);
    commit(nextDraft); // stepper commits immediately, never waits for blur
  }

  function handleBlur() {
    if (cancelledRef.current) {
      cancelledRef.current = false;
      return;
    }
    commit(draft);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") {
      commit(draft);
      onRequestClose();
    } else if (event.key === "Escape") {
      // Guard only -- the popover's own Escape-on-panel handler is what
      // actually closes (design D2); this just stops a stray blur from
      // committing the abandoned draft first.
      cancelledRef.current = true;
    }
  }

  const currentValue = draft.trim() === "" ? 0 : Number(draft);
  const minusDisabled = !(Number.isFinite(currentValue) && currentValue > 0);
  const hasTotal = bookmark.latest_chapter_num !== null;

  return (
    <>
      <span className="pop-label">Capítulo leído</span>
      <div className="pop-row">
        <button
          type="button"
          className="pop-step"
          aria-label="Uno menos"
          disabled={minusDisabled}
          onClick={() => step(-1)}
        >
          −
        </button>
        <DecimalInput
          value={draft}
          onChange={setDraft}
          onBlur={handleBlur}
          onKeyDown={handleKeyDown}
          aria-label="Capítulo leído"
        />
        <button type="button" className="pop-step" aria-label="Uno más" onClick={() => step(1)}>
          +
        </button>
      </div>
      {hasTotal && <span className="pop-hint">de {bookmark.latest_chapter_num} publicados</span>}
      {bookmark.progress_is_approx && (
        <span className="pop-hint">El progreso guardado es aproximado.</span>
      )}
      <span className="pop-hint">Se guarda solo.</span>
      <div className="pop-status">
        <span className="pop-label">Estado</span>
        <select
          className="pop-select"
          value={bookmark.status}
          // Kept verbatim (design D12): the existing container tests still
          // select this control by this exact label now that it lives here
          // instead of below the card.
          aria-label={`Estado de ${bookmark.title}`}
          onChange={(event) => {
            onCommitStatus(event.target.value as BookmarkStatus);
            onRequestClose(); // status choice closes the popover (Q4)
          }}
        >
          {BOOKMARK_STATUSES.map((status) => (
            <option key={status} value={status}>
              {STATUS_LABELS[status]}
            </option>
          ))}
        </select>
      </div>
    </>
  );
}
