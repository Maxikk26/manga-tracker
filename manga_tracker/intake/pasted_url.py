"""The only `MangaIntake` implementation (design D1): sequences slug -> ficha
-> duplicate gates -> chapters -> one transaction -> cover, so `web` never
has to. Imports `sources.contracts` (the Protocol, never a concrete client),
`storage.*`, and `importer.matching` — the pure normalizer, shared with
reconciliation key 3 (design D9)."""

from pathlib import Path

from manga_tracker.importer import matching
from manga_tracker.intake.contracts import AddPreview, AlreadyTracked, InvalidUrl
from manga_tracker.sources.contracts import SourceClient
from manga_tracker.storage.repositories import find_slug_owner, list_tracked_titles


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
