import { useState } from "react";
import { BOOKMARK_STATUSES, type Bookmark, type BookmarkStatus } from "../domain/types";
import { STATUS_LABELS } from "../domain/statusLabels";
import { coverUrl, hueOf, initials } from "../domain/covers";
import { InlineNumberEdit } from "./InlineNumberEdit";

interface Props {
  bookmark: Bookmark;
  saving: boolean;
  onChangeProgress: (id: number, value: number) => void;
  onChangeStatus: (id: number, status: BookmarkStatus) => void;
  onChangeScore: (id: number, value: number | null) => void;
}

/**
 * One manga as a cover-led card.
 *
 * The cover is the entry point, not decoration: the owner scans covers first
 * and opens what catches him, so the poster itself is the link and the title
 * below is confirmation. Demoting the image to a thumbnail beside a text link
 * would undo the reason this design was chosen.
 *
 * The link targets the manga's CHAPTER LIST, not its latest chapter. Sending
 * the owner to the newest chapter was wrong for the only case that matters:
 * read up to 175 with 800 available, the latest is 625 chapters past where he
 * left off. Opening the list lets him find his place. Resolving the actual
 * next unread chapter is a later stage and needs the real chapter list from
 * the source, because numbers are decimal and have gaps — it is never
 * `last_chapter_read + 1`.
 *
 * The "behind" count is a pill on the poster rather than the sentence it used
 * to be. It fires on every reading row -- 18 of 18 in production -- so as prose
 * it carried no information and competed with the title for attention; as two
 * characters over the image it is still readable and costs nothing.
 */
export function BookmarkCard({
  bookmark,
  saving,
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

  return (
    <article className={saving ? "card card-saving" : "card"}>
      {readable ? (
        <a
          className="cover"
          href={bookmark.manga_url!}
          target="_blank"
          rel="noreferrer"
          aria-label={`Ver capítulos de ${bookmark.title}`}
        >
          {poster}
          {bookmark.behind !== null && bookmark.behind > 0 && (
            // Rounded for display. Chapter numbers are REAL — the source
            // publishes 32.2 — so "behind" can legitimately be 21.5, but half a
            // chapter is not a decision the pill helps with, and the exact
            // value stays one hover away.
            <span className="behind-pill" title={`${bookmark.behind} sin leer`}>
              +{Math.round(bookmark.behind)}
            </span>
          )}
        </a>
      ) : (
        // No source mapping at all — a pending Kitsu entry whose url was never
        // pasted, 59 of 229 in production. The cover stays, the link does not,
        // because a dead anchor reads as a broken feature.
        <span className="cover">{poster}</span>
      )}

      <h3 className="card-title" title={bookmark.title}>
        {bookmark.title}
      </h3>

      <p className="card-progress">
        <InlineNumberEdit
          value={bookmark.last_chapter_read}
          prefix={approxMarker}
          disabled={saving}
          onCommit={(value) => onChangeProgress(bookmark.id, value)}
        />
        <span className="muted">
          {bookmark.latest_chapter_num !== null ? ` de ${bookmark.latest_chapter_num}` : ""}
        </span>
      </p>

      {/* Placed plainly, no styling decision made here: the visual pass is
          phase 5's (PAN §195) and has not started. */}
      <p>
        <InlineNumberEdit
          value={bookmark.my_score}
          max={10}
          disabled={saving}
          onCommit={(value) => onChangeScore(bookmark.id, value)}
          onClear={() => onChangeScore(bookmark.id, null)}
        />
      </p>

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
    </article>
  );
}
