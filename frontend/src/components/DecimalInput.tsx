import type { KeyboardEvent } from "react";

interface Props {
  /** The raw text draft; "" means "not typed yet" (the caller decides what
   *  that submits as — the add modal treats it as 0). */
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  placeholder?: string;
  /** Passed straight to the native input (fase 5 slice 2a): the commit
   *  contract for the popover editors is blur-or-Enter, never per
   *  keystroke, and this is the seam that lets a caller implement it
   *  without a second input component -- "the difference lives in the
   *  commit validator, not in a second component" (design D11). */
  onBlur?: () => void;
  onKeyDown?: (event: KeyboardEvent<HTMLInputElement>) => void;
  "aria-label"?: string;
}

/**
 * Keeps only what a positive decimal may carry: digits plus at most one dot,
 * with the leading-zero artifact stripped ("0170" -> "170", "00.5" -> "0.5",
 * but "0" and "0.5" stay). Everything else — letters, signs, spaces, commas,
 * exponents — is dropped at the keystroke, so the field can never hold an
 * invalid draft.
 */
export function sanitizeDecimal(raw: string): string {
  let out = "";
  let dotSeen = false;
  for (const ch of raw) {
    if (ch >= "0" && ch <= "9") {
      out += ch;
    } else if (ch === "." && !dotSeen) {
      out += ch;
      dotSeen = true;
    }
  }
  // "0" is only an artifact when a digit follows it ("0170"); before a dot
  // ("0.5") or alone it is the real value.
  return out.replace(/^0+(?=\d)/, "");
}

/**
 * Positive-decimal text input, replacing `<input type="number">` by owner
 * decision (2026-08-19): the native control shows spinners he dislikes and
 * lets a draft render as "0170". A text input with `inputMode="decimal"`
 * keeps the numeric keyboard on touch, has no spinner, and filters every
 * keystroke through `sanitizeDecimal`. Reuse this for any future numeric
 * field — the preference is standing, not modal-specific.
 */
export function DecimalInput({
  value,
  onChange,
  disabled = false,
  placeholder = "0",
  onBlur,
  onKeyDown,
  "aria-label": ariaLabel,
}: Props) {
  return (
    <input
      type="text"
      inputMode="decimal"
      autoComplete="off"
      spellCheck={false}
      placeholder={placeholder}
      value={value}
      disabled={disabled}
      aria-label={ariaLabel}
      onChange={(event) => onChange(sanitizeDecimal(event.target.value))}
      onBlur={onBlur}
      onKeyDown={onKeyDown}
    />
  );
}
