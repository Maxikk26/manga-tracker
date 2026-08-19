"""The only `MangaIntake` implementation (design D1): sequences slug -> ficha
-> duplicate gates -> chapters -> one transaction -> cover, so `web` never
has to. Imports `sources.contracts` (the Protocol, never a concrete client),
`storage.*`, and `importer.matching` — the pure normalizer, shared with
reconciliation key 3 (design D9)."""

import logging
from pathlib import Path

from manga_tracker.importer import matching
from manga_tracker.intake.contracts import AddPreview, AddResult, AlreadyTracked, InvalidUrl
from manga_tracker.sources.contracts import NotFound, SourceClient, Transient, Unexpected
from manga_tracker.storage.cover_cache import write_cover
from manga_tracker.storage.repositories import (
    IntegrityError,
    find_slug_owner,
    list_tracked_titles,
    write_manual_add,
)

logger = logging.getLogger(__name__)


class PastedUrlIntake:
    """`web` holds this behind the `MangaIntake` Protocol only (design D1)."""

    def __init__(self, client: SourceClient, site_id: int, cache_dir: Path):
        self._client = client
        self._site_id = site_id
        self._cache_dir = cache_dir

    def preview(self, conn, url: str) -> AddPreview:
        """Resolve the slug and validate without writing (spec.md "Preview
        validates without writing"). Zero requests through the duplicate
        gates 1-2; one request (`fetch_manga_details`) for gate 3 and the
        matched metadata."""
        slug = self._client.extract_slug(url)
        if slug is None:
            raise InvalidUrl(f"no slug segment could be extracted from {url!r}")

        self._check_gates_before_request(conn, slug)

        details = self._client.fetch_manga_details(slug)  # 1 req; NotFound/Transient/Unexpected propagate

        self._check_gate_after_ficha(conn, details.title)

        return AddPreview(
            slug=slug,
            url=self._client.build_manga_url(slug),
            title=details.title,
            cover_url=details.cover_url,
            publication_status_text=details.publication_status_text,
        )

    def confirm(
        self,
        conn,
        *,
        url: str,
        title: str,
        cover_url: str | None,
        status: str,
        last_chapter_read: float,
        now: str,
    ) -> AddResult:
        """Write the manga (spec.md "Confirm is atomic; any rejection leaves
        zero rows"). The slug is re-derived from `url` — never trusted from
        the client (design D4) — and the three gates are re-run against
        current data (TOCTOU): the ficha is not re-fetched, so gate 3 checks
        the `title` this call already carries, echoed from `preview()`.
        """
        slug = self._client.extract_slug(url)
        if slug is None:
            raise InvalidUrl(f"no slug segment could be extracted from {url!r}")

        self._check_gates_before_request(conn, slug)
        self._check_gate_after_ficha(conn, title)

        chapters = self._client.fetch_chapters(slug)  # 1 req; NotFound/Transient/Unexpected propagate

        try:
            manga_id, bookmark_id = write_manual_add(
                conn,
                title=title,
                site_id=self._site_id,
                slug=slug,
                url=url,
                chapters=chapters,
                status=status,
                last_chapter_read=last_chapter_read,
                cover_url=cover_url,
                now=now,
            )
        except IntegrityError:
            # The pre-checks above missed a concurrent add that committed in
            # between; idx_manga_sites_site_source_key is the last line of
            # defence (design D3) and turns what would otherwise be a 500 into
            # a clean, named 409. write_manual_add's own transaction() already
            # rolled the failed write back to zero rows.
            owner = find_slug_owner(conn, self._site_id, slug)
            if owner is not None:
                owner_title, _kitsu_id = owner
                raise AlreadyTracked(
                    title=owner_title, status=_status_of(list_tracked_titles(conn), owner_title)
                ) from None
            raise

        cover_cached = False
        if cover_url:
            # Outside the transaction, on purpose (design D6): the add must
            # stand even when the cover never arrives.
            try:
                image = self._client.fetch_cover(cover_url)
                write_cover(self._cache_dir, manga_id, cover_url, image)
                cover_cached = True
            except (NotFound, Transient, Unexpected) as exc:
                logger.warning("intake: cover fetch failed for manga %s: %s", manga_id, exc)

        return AddResult(
            manga_id=manga_id,
            bookmark_id=bookmark_id,
            chapters_found=len(chapters),
            cover_cached=cover_cached,
        )

    # --- duplicate gates (design D3) -------------------------------------------

    def _check_gates_before_request(self, conn, slug: str) -> None:
        """Gates 1-2, zero source requests: any slug already mapped in any
        state (gate 1), and every terminal Kitsu row the slug lookup alone
        cannot see, caught by re-deriving its slug candidates (gate 2)."""
        tracked = list_tracked_titles(conn)
        owner = find_slug_owner(conn, self._site_id, slug)
        if owner is not None:
            owner_title, _kitsu_id = owner
            raise AlreadyTracked(title=owner_title, status=_status_of(tracked, owner_title))

        for title, status in tracked:
            if slug in matching.slug_variants(title):
                raise AlreadyTracked(title=title, status=status)

    def _check_gate_after_ficha(self, conn, resolved_title: str) -> None:
        """Gate 3: the residue gate 2 misses, when the source's title differs
        from every slug candidate but still normalizes to a tracked title."""
        normalized = matching.normalize(resolved_title)
        for title, status in list_tracked_titles(conn):
            if matching.normalize(title) == normalized:
                raise AlreadyTracked(title=title, status=status)


def _status_of(tracked: list[tuple[str, str]], title: str) -> str:
    """The bookmark status for a title `list_tracked_titles` already carries.

    A manga always has exactly one bookmark by construction (repositories.py:
    `list_tracked_titles`'s own docstring), so `find_slug_owner` returning a
    title means this lookup always succeeds — the RuntimeError below is an
    assertion against that invariant breaking, not an expected path.
    """
    for tracked_title, status in tracked:
        if tracked_title == title:
            return status
    raise RuntimeError(f"manga {title!r} has a manga_sites row but no bookmark")
