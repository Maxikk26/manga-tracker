import type { ExistingManga } from "../domain/types";

/**
 * User-facing (Spanish) error carrying whatever detail the API returned.
 *
 * `existing` is present only on the add-manga 409 (design's Error Taxonomy
 * "sibling key"): it names the bookmark that already owns the slug/title, so
 * the modal can offer a "Ver en «…»" affordance without re-parsing `message`.
 */
export class ApiError extends Error {
  existing?: ExistingManga;

  constructor(message: string, existing?: ExistingManga) {
    super(message);
    this.existing = existing;
  }
}

function isExistingManga(value: unknown): value is ExistingManga {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as Record<string, unknown>).title === "string" &&
    typeof (value as Record<string, unknown>).status === "string" &&
    typeof (value as Record<string, unknown>).terminal === "boolean"
  );
}

/** Parses `{detail, existing?}` out of a non-ok response body. Never throws:
 *  an unparsable body just means no detail and no `existing`. */
export async function readDetail(
  response: Response,
): Promise<{ detail: string | null; existing?: ExistingManga }> {
  try {
    const body = (await response.json()) as { detail?: unknown; existing?: unknown };
    const detail = typeof body.detail === "string" ? body.detail : null;
    const existing = isExistingManga(body.existing) ? body.existing : undefined;
    return { detail, existing };
  } catch {
    return { detail: null };
  }
}
