import { useEffect, useRef, useState, type ReactNode } from "react";

interface Props {
  /** null = never read; the schema allows it and the seed/import produce it. */
  value: number | null;
  /** Rendered next to the number in display mode (e.g. the "~" marker). */
  prefix?: ReactNode;
  /** Upper bound, validated exactly like the existing `min={0}` floor. */
  max?: number;
  disabled: boolean;
  onCommit: (value: number) => void;
  /** Additive, not a widened `onCommit` (design D4, panel-v1b-fase-4):
   *  widening `onCommit` to accept `null` would be a breaking change under
   *  `strictFunctionTypes`, forcing every existing caller to handle a null it
   *  may not legally send. This field's *absence* is what encodes "this
   *  value cannot be cleared" -- `last_chapter_read` passes none and keeps
   *  its blank-blur no-op unchanged, with no new branch. When present, a
   *  blank blur calls it instead of no-op'ing. */
  onClear?: () => void;
}

/**
 * Click-to-edit number. Enter or blur commits, Escape cancels.
 * Committing the unchanged value is a no-op (no PATCH fired).
 */
export function InlineNumberEdit({ value, prefix, max, disabled, onCommit, onClear }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const cancelledRef = useRef(false);

  useEffect(() => {
    if (editing) {
      // focus before select: without it the editor never holds focus, so the
      // blur-commit path can never fire. Found by the component tests.
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [editing]);

  function startEditing() {
    if (disabled) return;
    cancelledRef.current = false;
    setDraft(value === null ? "" : String(value));
    setEditing(true);
  }

  function commit() {
    setEditing(false);
    if (cancelledRef.current) return;
    if (draft.trim() === "") {
      // Number("") is 0 — a blank blur must not PATCH 0. Without `onClear`
      // this stays the existing no-op; with it, a blank blur means "clear".
      onClear?.();
      return;
    }
    const parsed = Number(draft);
    if (!Number.isFinite(parsed) || parsed < 0 || (max !== undefined && parsed > max)) return;
    if (parsed === value) return;
    onCommit(parsed);
  }

  if (!editing) {
    return (
      <button
        type="button"
        className="progress-display"
        onClick={startEditing}
        disabled={disabled}
        title="Haz clic para editar"
      >
        {prefix}
        {value ?? "—"}
      </button>
    );
  }

  return (
    <input
      ref={inputRef}
      className="progress-input"
      type="number"
      min={0}
      max={max}
      step="any"
      value={draft}
      onChange={(event) => setDraft(event.target.value)}
      onBlur={commit}
      onKeyDown={(event) => {
        if (event.key === "Enter") {
          event.currentTarget.blur();
        } else if (event.key === "Escape") {
          cancelledRef.current = true;
          event.currentTarget.blur();
        }
      }}
    />
  );
}
