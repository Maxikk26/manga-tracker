import { useRef, useState, type KeyboardEvent } from "react";
import type { Bookmark } from "../domain/types";
import { DecimalInput } from "./DecimalInput";

interface Props {
  bookmark: Bookmark;
  /** `null` clears the score -- the same wire contract `BookmarkPatch` already
   *  carries (design D1, panel-v1b-fase-4). */
  onCommit: (value: number | null) => void;
  onRequestClose: () => void;
}

const SCORE_MAX = 10;

/**
 * The score half of the popover (design D2/D11/D3). No stepper -- a score is
 * picked, not incremented, so this is `DecimalInput` + the `/ 10` scale +
 * `Quitar puntuación`.
 *
 * The draft is seeded once, from the bookmark prop at the moment this
 * component is created -- `value ?? ""`, the same D11 null guard
 * `ChapterEditor` uses, so an unscored bookmark opens blank, never the
 * literal string "null".
 */
export function ScoreEditor({ bookmark, onCommit, onRequestClose }: Props) {
  const [draft, setDraft] = useState(() =>
    bookmark.my_score === null ? "" : String(bookmark.my_score),
  );
  // Mirrors `ChapterEditor`'s `committedRef`: compared against the last
  // successful commit, not the original prop, so a blur after `Quitar
  // puntuación` already having committed is correctly a no-op.
  const committedRef = useRef(bookmark.my_score);
  // Escape must not let a resulting blur commit the abandoned draft.
  const cancelledRef = useRef(false);

  function commit(raw: string) {
    const trimmed = raw.trim();
    if (trimmed === "") {
      // Blank clears the score -- unlike the chapter field, which no-ops on
      // blank (a chapter cannot be "unread").
      if (committedRef.current === null) return; // already unscored: no PATCH
      committedRef.current = null;
      onCommit(null);
      return;
    }
    const parsed = Number(trimmed);
    // `< 0`/`> 10` unreachable through this field in practice --
    // `DecimalInput`'s own sanitizer (slice 2a) strips any character that
    // is not a digit or the first dot, so neither a sign nor a value past
    // what was typed digit-by-digit can land here. Kept anyway: it mirrors
    // `ChapterEditor`'s identical defensive check and guards a value that
    // could still arrive from a future caller that does not route through
    // `DecimalInput`.
    if (!Number.isFinite(parsed) || parsed < 0 || parsed > SCORE_MAX) return;
    const rounded = Math.round(parsed);
    if (rounded === committedRef.current) return; // unchanged: no PATCH
    committedRef.current = rounded;
    onCommit(rounded);
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

  function handleClear() {
    setDraft("");
    commit("");
    onRequestClose();
  }

  return (
    <>
      <span className="pop-label">Puntuación</span>
      <div className="pop-row">
        <DecimalInput
          value={draft}
          onChange={setDraft}
          onBlur={handleBlur}
          onKeyDown={handleKeyDown}
          aria-label={`Puntuación de 0 a ${SCORE_MAX}`}
        />
        <span className="pop-scale">/ {SCORE_MAX}</span>
      </div>
      <span className="pop-hint">Se guarda solo.</span>
      <div className="pop-actions">
        <button
          type="button"
          // Prevents the mousedown from moving focus off the input at all,
          // so clicking this never fires the input's own blur first --
          // `handleClear` is the only commit path this click takes.
          onMouseDown={(event) => event.preventDefault()}
          onClick={handleClear}
        >
          Quitar puntuación
        </button>
      </div>
    </>
  );
}
