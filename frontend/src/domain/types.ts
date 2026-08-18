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
}

/** Fields the panel is allowed to edit; sent one at a time. */
export type BookmarkPatch =
  | { last_chapter_read: number }
  | { status: BookmarkStatus };
