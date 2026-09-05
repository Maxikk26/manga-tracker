import { memo, useRef, useState } from "react";
import type { Bookmark, BookmarkStatus } from "../domain/types";
import { STATUS_LABELS } from "../domain/statusLabels";
import { coverUrl, hueOf, initials } from "../domain/covers";
import { isCaughtUp } from "../domain/sortBookmarks";
import { Popover } from "./Popover";
import { ChapterEditor } from "./ChapterEditor";
import { ScoreEditor } from "./ScoreEditor";

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
  /** Fired whenever this card's own popover opens or closes (design D3) --
   *  the container's only signal that a row is being edited, used to freeze
   *  the list order while any card's panel is open. */
  onEditingChange: (id: number, open: boolean) => void;
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
  onEditingChange,
}: Props) {
  // The API 404s for a manga whose cover was never cached, which is an ordinary
  // state rather than an error, so the fallback is a first-class branch.
  const [coverFailed, setCoverFailed] = useState(false);

  // Which popover is open, if any (design D3): the card owns this, the
  // container only learns the fact that *some* row is being edited via
  // `onEditingChange`.
  const [openPopover, setOpenPopover] = useState<"chapter" | "score" | null>(null);
  const chapterTriggerRef = useRef<HTMLButtonElement>(null);
  const scoreTriggerRef = useRef<HTMLButtonElement>(null);

  function openChapterPopover() {
    setOpenPopover("chapter");
    onEditingChange(bookmark.id, true);
  }

  function openScorePopover() {
    setOpenPopover("score");
    onEditingChange(bookmark.id, true);
  }

  function closePopover() {
    setOpenPopover(null);
    onEditingChange(bookmark.id, false);
  }

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

  const caughtUp = isCaughtUp(bookmark);

  // One chip per corner (Q5, read off PROTO): the status pill wins whenever a
  // card could have come from any tab, "Al día" otherwise. Never both.
  const chip = showStatus ? (
    <span className="chip chip-status" data-st={bookmark.status}>
      {STATUS_LABELS[bookmark.status]}
    </span>
  ) : caughtUp ? (
    <span className="chip">Al día</span>
  ) : null;

  const hasTotal = bookmark.latest_chapter_num !== null;
  // A never-read bookmark renders "Sin empezar" (fase 5 slice 3, design
  // D13), never the literal value `null` and never the rest/full swap --
  // a ratio needs a real left side, so there is no hover swap either.
  const neverRead = bookmark.last_chapter_read === null;
  const chapterAriaLabel = [
    `Editar capítulo leído de ${bookmark.title}.`,
    hasTotal && bookmark.last_chapter_read !== null
      ? `Vas por el ${bookmark.last_chapter_read} de ${bookmark.latest_chapter_num}.`
      : null,
    bookmark.progress_is_approx ? "El progreso es aproximado." : null,
  ]
    .filter((part): part is string => part !== null)
    .join(" ");
  const scoreLabel = bookmark.my_score === null ? "No puntuado" : `${bookmark.my_score}/10`;

  return (
    <>
      <article className={saving ? "card card-saving" : "card"} data-done={caughtUp || undefined}>
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
            <button
              ref={chapterTriggerRef}
              type="button"
              className={hasTotal && !neverRead ? "edit has-total" : "edit"}
              data-approx={bookmark.progress_is_approx || undefined}
              aria-label={chapterAriaLabel}
              onClick={openChapterPopover}
            >
              {neverRead ? (
                "Sin empezar"
              ) : hasTotal ? (
                <>
                  <span className="chapter-rest">cap. {bookmark.last_chapter_read}</span>
                  <span className="chapter-full">
                    {bookmark.last_chapter_read} / {bookmark.latest_chapter_num}
                  </span>
                </>
              ) : (
                `cap. ${bookmark.last_chapter_read}`
              )}
            </button>
            <button
              ref={scoreTriggerRef}
              type="button"
              className="edit"
              aria-label={`Editar puntuación de ${bookmark.title}.`}
              onClick={openScorePopover}
            >
              {scoreLabel}
            </button>
          </div>
        </div>
      </article>
      {openPopover === "chapter" && (
        <Popover
          anchor={chapterTriggerRef.current}
          label={`Capítulo leído de ${bookmark.title}`}
          onDismiss={closePopover}
        >
          <ChapterEditor
            bookmark={bookmark}
            onCommit={(value) => onChangeProgress(bookmark.id, value)}
            onCommitStatus={(status) => onChangeStatus(bookmark.id, status)}
            onRequestClose={closePopover}
          />
        </Popover>
      )}
      {openPopover === "score" && (
        <Popover
          anchor={scoreTriggerRef.current}
          label={`Puntuación de ${bookmark.title}`}
          onDismiss={closePopover}
        >
          <ScoreEditor
            bookmark={bookmark}
            onCommit={(value) => onChangeScore(bookmark.id, value)}
            onRequestClose={closePopover}
          />
        </Popover>
      )}
    </>
  );
}

// `Todo` renders ~236 cards and every keystroke in the (future) search field
// re-renders the tree; the props are already stable (`useCallback` handlers,
// a boolean `saving`, a row identity that only changes on refetch), so `memo`
// makes that cheap with zero new dependencies (D13).
export const BookmarkCard = memo(BookmarkCardComponent);
