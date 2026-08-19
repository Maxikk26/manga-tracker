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
}

/**
 * One manga as a cover-led card.
 *
 * The cover is the entry point, not decoration: the owner scans covers first
 * and opens what catches him, so the poster itself is the link to the next
 * chapter and the title below is confirmation. Demoting the image to a
 * thumbnail beside a text link would undo the reason this design was chosen.
 *
 * The "behind" count is a pill on the poster rather than the sentence it used
 * to be. It fires on every reading row -- 18 of 18 in production -- so as prose
 * it carried no information and competed with the title for attention; as two
 * characters over the image it is still readable and costs nothing.
 */
export function BookmarkCard({ bookmark, saving, onChangeProgress, onChangeStatus }: Props) {
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

  const readable = bookmark.latest_chapter_url && bookmark.latest_chapter_num !== null;

  return (
    <article className={saving ? "card card-saving" : "card"}>
      {readable ? (
        <a
          className="cover"
          href={bookmark.latest_chapter_url!}
          target="_blank"
          rel="noreferrer"
          aria-label={`Leer ${bookmark.title}, capítulo ${bookmark.latest_chapter_num}`}
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
        // Nothing detected at the source yet: the cover stays, the link does
        // not, because a dead anchor reads as a broken feature.
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
