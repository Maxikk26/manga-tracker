export const BOOKMARK_STATUSES = [
  "reading",
  "want_to_read",
  "completed",
  "on_hold",
  "dropped",
] as const;

export type BookmarkStatus = (typeof BOOKMARK_STATUSES)[number];

export interface Bookmark {
  id: number;
  manga_id: number;
  title: string;
  status: BookmarkStatus;
  last_chapter_read: number | null;
  progress_is_approx: boolean;
  latest_chapter_num: number | null;
  latest_chapter_url: string | null;
  latest_chapter_at: string | null;
  behind: number | null;
  last_read_at: string | null;
  /** When `status` last actually changed. Null for every row that predates the
   *  column — that history is not reconstructible. */
  status_changed_at: string | null;
}

/** Fields the panel is allowed to edit; sent one at a time. */
export type BookmarkPatch =
  | { last_chapter_read: number }
  | { status: BookmarkStatus };

/** Wire shape of `POST /api/mangas/preview`'s 200 response (design's
 *  Interfaces block, `AddPreview` echoed as JSON). No write happened yet. */
export interface MangaPreview {
  slug: string;
  url: string;
  title: string;
  cover_url: string | null;
  publication_status_text: string | null;
}

/** Body of `POST /api/mangas`. `url`/`title`/`cover_url` are the preview's own
 *  fields echoed back verbatim (design D4) — the slug is re-derived
 *  server-side, never trusted from the client. */
export interface MangaAdd {
  url: string;
  title: string;
  cover_url: string | null;
  status: BookmarkStatus;
  last_chapter_read: number;
}

/** The 409 conflict's sibling key (design's Error Taxonomy): names the
 *  bookmark that already owns the slug/title and whether its status is
 *  terminal, computed server-side so the frontend never re-derives it. */
export interface ExistingManga {
  title: string;
  status: BookmarkStatus;
  terminal: boolean;
}
