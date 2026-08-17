import { useEffect, useRef, useState, type ReactNode } from "react";

interface Props {
  value: number;
  /** Rendered next to the number in display mode (e.g. the "~" marker). */
  prefix?: ReactNode;
  disabled: boolean;
  onCommit: (value: number) => void;
}

/**
 * Click-to-edit number. Enter or blur commits, Escape cancels.
 * Committing the unchanged value is a no-op (no PATCH fired).
 */
export function InlineNumberEdit({ value, prefix, disabled, onCommit }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const cancelledRef = useRef(false);

  useEffect(() => {
    if (editing) inputRef.current?.select();
  }, [editing]);

  function startEditing() {
    if (disabled) return;
    cancelledRef.current = false;
    setDraft(String(value));
    setEditing(true);
  }

  function commit() {
    setEditing(false);
    if (cancelledRef.current) return;
    const parsed = Number(draft);
    if (!Number.isFinite(parsed) || parsed < 0) return;
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
        {value}
      </button>
    );
  }

  return (
    <input
      ref={inputRef}
      className="progress-input"
      type="number"
      min={0}
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
