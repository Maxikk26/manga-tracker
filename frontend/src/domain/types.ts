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
  /** The manga's own page at the source — its chapter list. Comes from the
   *  API, never derived from `latest_chapter_url`: the source's URL shape is
   *  client knowledge and must not live in a component. Null when the manga
   *  has no source mapping yet. */
  manga_url: string | null;
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

// --- panel-reading-history (spec-panel-v1b.md fase 2) --------------------

/** One local calendar day's aggregate. `chapters` is already the sum of
 *  positive deltas (downward corrections excluded) computed server-side —
 *  the frontend never re-derives it. */
export interface ReadingHistoryDay {
  date: string;
  chapters: number;
  edits: number;
}

/** Wire shape of `GET /api/history/reading`. Sparse: only days with
 *  activity appear in `days`. */
export interface ReadingHistoryResponse {
  timezone: string;
  from: string;
  to: string;
  days: ReadingHistoryDay[];
}

/** A recorded reading edit, in the per-manga timeline. Visible here with its
 *  (possibly negative) `delta` even when it is a downward correction — the
 *  heatmap excludes those, the timeline does not (design D6). */
export interface ReadingTimelineEvent {
  kind: "reading";
  at: string;
  chapter_num: number;
  previous_chapter_num: number | null;
  delta: number | null;
  origin: string;
}

/** A detected publication, in the per-manga timeline. */
export interface PublicationTimelineEvent {
  kind: "publication";
  at: string;
  chapter_num: number;
  chapter_url: string | null;
  source_published_at: string | null;
  detected_via: string;
}

export type MangaHistoryEvent = ReadingTimelineEvent | PublicationTimelineEvent;

/** Wire shape of `GET /api/mangas/{id}/history`. `publications_since` is
 *  null when no publication has ever been detected for this manga; when
 *  present it states the timeline is complete only from that point on
 *  (design D9) — `CHAPTER_HISTORY_LIMIT` caps only the one-time backfill. */
export interface MangaHistoryResponse {
  manga_id: number;
  title: string;
  publications_since: string | null;
  events: MangaHistoryEvent[];
}
