import { memo, useState } from "react";
import { BOOKMARK_STATUSES, type Bookmark, type BookmarkStatus } from "../domain/types";
import { STATUS_LABELS } from "../domain/statusLabels";
import { coverUrl, hueOf, initials } from "../domain/covers";
import { InlineNumberEdit } from "./InlineNumberEdit";

interface Props {
  bookmark: Bookmark;
  saving: boolean;
  /** Only true from the "Todo" tab (fase 5 slice 3), where a card could have
   *  come from any status. Defaults false so every other tab keeps showing
   *  the "Al día" chip instead — one chip per corner, never both (Q5). */
  showStatus?: boolean;
  onChangeProgress: (id: number, value: number) => void;
  onChangeStatus: (id: number, status: BookmarkStatus) => void;
  onChangeScore: (id: number, value: number | null) => void;
}

/**
 * One manga as a cover-led card: the poster fills the card, and a scrim at
 * the bottom carries the title and a single-line meta row (chapter + score).
 *
 * The cover is the entry point, not decoration: the owner scans covers first
 * and opens what catches him, so the poster itself is the link and the title
 * over it is confirmation. Demoting the image to a thumbnail beside a text
 * link would undo the reason this design was chosen.
 *
 * The link targets the manga's CHAPTER LIST, not its latest chapter. Sending
 * the owner to the newest chapter was wrong for the only case that matters:
 * read up to 175 with 800 available, the latest is 625 chapters past where he
 * left off. Opening the list lets him find his place. Resolving the actual
 * next unread chapter is a later stage and needs the real chapter list from
 * the source, because numbers are decimal and have gaps — it is never
 * `last_chapter_read + 1`.
 */
function BookmarkCardComponent({
  bookmark,
  saving,
  showStatus = false,
  onChangeProgress,
  onChangeStatus,
  onChangeScore,
}: Props) {
  // The API 404s for a manga whose cover was never cached, which is an ordinary
  // state rather than an error, so the fallback is a first-class branch.
  const [coverFailed, setCoverFailed] = useState(false);

  const approxMarker = bookmark.progress_is_approx ? (
    <span
      className="approx-marker"
      title="Progreso aproximado: viene del import de Kitsu, no de una lectura confirmada"
    >
      ~
    </span>
  ) : null;

  const hue = hueOf(bookmark.title);
  const poster = coverFailed ? (
    <span
      className="cover-fallback"
      style={{
        background: `linear-gradient(160deg, hsl(${hue} 52% 46%), hsl(${(hue + 28) % 360} 54% 34%))`,
      }}
      aria-hidden="true"
    >
      {initials(bookmark.title)}
    </span>
  ) : (
    <img
      className="cover-image"
      src={coverUrl(bookmark.manga_id)}
      alt=""
      loading="lazy"
      onError={() => setCoverFailed(true)}
    />
  );

  // Gated on the manga page alone, no longer on a detected chapter: the
  // chapter list is a valid destination for a mapped title even before the
  // first detection lands.
  const readable = bookmark.manga_url !== null;

  // One chip per corner (Q5, read off PROTO): the status pill wins whenever a
  // card could have come from any tab, "Al día" otherwise. Never both.
  const chip = showStatus ? (
    <span className="chip chip-status" data-st={bookmark.status}>
      {STATUS_LABELS[bookmark.status]}
    </span>
  ) : bookmark.behind === 0 ? (
    <span className="chip">Al día</span>
  ) : null;

  return (
    <>
      <article
        className={saving ? "card card-saving" : "card"}
        data-done={bookmark.behind === 0 || undefined}
      >
        {readable ? (
          <a
            className="poster"
            href={bookmark.manga_url!}
            target="_blank"
            rel="noreferrer"
            aria-label={`Ver capítulos de ${bookmark.title}`}
          >
            {poster}
          </a>
        ) : (
          // No source mapping at all — a pending Kitsu entry whose url was
          // never pasted, 59 of 229 in production. The cover stays, the link
          // does not, because a dead anchor reads as a broken feature.
          <span className="poster">{poster}</span>
        )}
        {chip}
        <div className="scrim">
          <h3 className="title" title={bookmark.title}>
            {bookmark.title}
          </h3>
          <div className="meta">
            <InlineNumberEdit
              value={bookmark.last_chapter_read}
              prefix={approxMarker}
              disabled={saving}
              onCommit={(value) => onChangeProgress(bookmark.id, value)}
            />
            <span className="muted">
              {bookmark.latest_chapter_num !== null ? ` de ${bookmark.latest_chapter_num}` : ""}
            </span>
            <InlineNumberEdit
              value={bookmark.my_score}
              max={10}
              disabled={saving}
              onCommit={(value) => onChangeScore(bookmark.id, value)}
              onClear={() => onChangeScore(bookmark.id, null)}
            />
          </div>
        </div>
      </article>

      {/* Temporary layout: this control belongs inside the chapter popover
          (design D12, fase 5 slice 2b) and moves there once that popover
          exists. Until then it renders as a plain sibling below the card --
          a review artifact of the chain never reaching main mid-slice, not a
          shipped regression (design's Slicing note). */}
      <select
        className="status-select"
        value={bookmark.status}
        disabled={saving}
        aria-label={`Estado de ${bookmark.title}`}
        onChange={(event) => onChangeStatus(bookmark.id, event.target.value as BookmarkStatus)}
      >
        {BOOKMARK_STATUSES.map((status) => (
          <option key={status} value={status}>
            {STATUS_LABELS[status]}
          </option>
        ))}
      </select>
    </>
  );
}

// `Todo` renders ~236 cards and every keystroke in the (future) search field
// re-renders the tree; the props are already stable (`useCallback` handlers,
// a boolean `saving`, a row identity that only changes on refetch), so `memo`
// makes that cheap with zero new dependencies (D13).
export const BookmarkCard = memo(BookmarkCardComponent);
