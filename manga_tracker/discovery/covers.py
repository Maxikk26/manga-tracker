"""One-off cover cache.

Why this exists: the Kitsu import brought a cover URL for everything it touched
(212 of 229 mangas) and the hand-typed seed brought none, so the gap is not
spread across the library — it sits in exactly the rows the owner reads daily.

Why it stores bytes and not just a URL: manganato's image hosts
(img-r2.2xstorage.com, storage.waitst.com) answer **403** to a request without a
manganato `Referer` and 200 to one with it. A panel pointing an <img src>
straight at a stored URL would therefore show a broken image for every cover
taken from the source. Measured, not assumed. Caching the file also means the
panel renders covers with no third-party request at all, and keeps them when the
source rotates or removes an image.

Placement follows the structural boundary. This module knows the reading list,
the database and the cache directory, and decides what is worth a request; the
client knows which `Referer` manganato's CDN demands. Neither knows the other's
half.

Not a job: no `job_runs` row, no schedule, sends nothing. It is maintenance, run
by hand, and safe to interrupt — each cover is written and committed on its own,
because each one cost a real request.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from manga_tracker.sources.contracts import NotFound, Transient, Unexpected
from manga_tracker.storage.cover_cache import find_cached, write_cover
from manga_tracker.storage.db import connect
from manga_tracker.storage.repositories import (
    list_cover_candidates,
    list_stored_url_cover_candidates,
    set_manga_cover,
)

logger = logging.getLogger(__name__)

#: Terminal bookmarks consume no requests, ever. A cover for something dropped
#: or completed buys nothing, and that rule is not negotiable per manga.
DEFAULT_STATUSES = ("reading", "want_to_read", "on_hold")


@dataclass
class CoverBackfillReport:
    considered: int = 0
    #: Already had both a URL and a cached file; cost nothing.
    already_cached: int = 0
    #: Learned a cover_url it did not have.
    urls_learned: int = 0
    #: Image bytes written to the cache.
    files_written: int = 0
    #: The source has no such manga, or no such image. Never retried this run.
    not_found: list[str] = field(default_factory=list)
    #: Timeout, 5xx, Cloudflare. Says nothing about the slug; rerun later.
    transient: list[str] = field(default_factory=list)
    #: Well-formed response of the wrong shape, or details carrying no cover.
    unexpected: list[str] = field(default_factory=list)
    #: Stored-url route only: a terminal bookmark with no known cover_url.
    #: Owns a slug or not, this is a skip, never escalated to the mapped
    #: route -- that route may spend a source lookup and this row's status
    #: says it may not (design D5, panel-v1b-fase-4).
    no_url: list[str] = field(default_factory=list)

    @property
    def failed(self) -> int:
        return len(self.not_found) + len(self.transient) + len(self.unexpected)


def backfill_covers(
    *,
    db_path: str,
    client,
    cache_dir: Path,
    statuses: tuple[str, ...] = DEFAULT_STATUSES,
    limit: int | None = None,
    now_fn,
) -> CoverBackfillReport:
    """Give every mapped manga in these statuses a cover file on disk.

    Two steps per manga, each skipped when already done, so a rerun after a
    partial run costs only what is still missing:

    1. no `cover_url` -> ask the source for the manga's details (1 request),
    2. no cached file -> download the image (1 request).

    Sequential, with the transport's own 5-15s delay and single retry; no
    concurrency and no second retry layer here.

    A failure never aborts the run — the next manga is independent, and stopping
    would waste the covers already paid for. `consecutive_failures` is
    deliberately left alone in both directions: that counter drives the
    dead-slug notice off the detection mechanisms, and maintenance must not be
    able to pause a mapping or quietly reset a real streak.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        candidates = list_cover_candidates(conn, statuses=statuses)
        pending = [
            row for row in candidates if not row[3] or find_cached(cache_dir, row[0]) is None
        ]
        if limit is not None:
            pending = pending[:limit]

        report = CoverBackfillReport(
            considered=len(pending), already_cached=len(candidates) - len(pending)
        )

        for manga_id, title, source_key, cover_url in pending:
            if not cover_url:
                try:
                    cover_url = client.fetch_manga_details(source_key).cover_url
                except NotFound:
                    logger.warning("covers: slug not found for %r (%s)", title, source_key)
                    report.not_found.append(title)
                    continue
                except Transient as exc:
                    logger.warning("covers: transient failure on details for %r: %s", title, exc)
                    report.transient.append(title)
                    continue
                except Unexpected as exc:
                    logger.error("covers: unexpected details response for %r: %s", title, exc)
                    report.unexpected.append(title)
                    continue
                if not cover_url:
                    # A 200 whose details carry no cover is the source changing
                    # shape, not an honest empty answer.
                    logger.error("covers: details for %r carried no cover_url", title)
                    report.unexpected.append(title)
                    continue
                set_manga_cover(conn, manga_id, cover_url, now=now_fn())
                report.urls_learned += 1

            if find_cached(cache_dir, manga_id) is not None:
                continue

            try:
                image = client.fetch_cover(cover_url)
            except NotFound:
                logger.warning("covers: image gone for %r (%s)", title, cover_url)
                report.not_found.append(title)
                continue
            except Transient as exc:
                logger.warning("covers: transient failure on image for %r: %s", title, exc)
                report.transient.append(title)
                continue
            except Unexpected as exc:
                logger.error("covers: unexpected image response for %r: %s", title, exc)
                report.unexpected.append(title)
                continue

            destination = write_cover(cache_dir, manga_id, cover_url, image)
            report.files_written += 1
            logger.info("covers: cached %s for %r", destination.name, title)

        return report
    finally:
        conn.close()


def backfill_stored_url_covers(
    *,
    db_path: str,
    client,
    cache_dir: Path,
    statuses: tuple[str, ...],
    limit: int | None = None,
    now_fn,
) -> CoverBackfillReport:
    """Give every terminal bookmark in these statuses a cover file on disk,
    from a `cover_url` already stored on the `mangas` row.

    Sibling of `backfill_covers`, not a branch inside it, and never calls
    `fetch_manga_details`: `list_stored_url_cover_candidates` has no
    `manga_sites` join, so `source_key` is never in this function's scope
    and there is no slug to call it with, even by mistake (design D5,
    panel-v1b-fase-4 -- the zero-manganato guarantee is structural).

    One request per manga at most, the image itself, and only when a
    `cover_url` is already known: a NULL one costs nothing and is counted in
    `report.no_url`, never routed to `backfill_covers` to look one up --
    status is the permission that route needs, and this route's candidates
    are terminal by construction.

    `consecutive_failures` is left alone, exactly as `backfill_covers`
    leaves it.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        candidates = list_stored_url_cover_candidates(conn, statuses=statuses)
        no_url = [title for _, title, cover_url in candidates if not cover_url]
        for title in no_url:
            logger.info("covers: %r has no cover_url; skipped, no source lookup permitted", title)

        downloadable = [row for row in candidates if row[2]]
        pending = [row for row in downloadable if find_cached(cache_dir, row[0]) is None]
        if limit is not None:
            pending = pending[:limit]

        report = CoverBackfillReport(
            considered=len(pending),
            already_cached=len(downloadable) - len(pending),
            no_url=no_url,
        )

        for manga_id, title, cover_url in pending:
            try:
                image = client.fetch_cover(cover_url)
            except NotFound:
                logger.warning("covers: image gone for %r (%s)", title, cover_url)
                report.not_found.append(title)
                continue
            except Transient as exc:
                logger.warning("covers: transient failure on image for %r: %s", title, exc)
                report.transient.append(title)
                continue
            except Unexpected as exc:
                logger.error("covers: unexpected image response for %r: %s", title, exc)
                report.unexpected.append(title)
                continue

            destination = write_cover(cache_dir, manga_id, cover_url, image)
            report.files_written += 1
            logger.info("covers: cached %s for %r", destination.name, title)

        return report
    finally:
        conn.close()
