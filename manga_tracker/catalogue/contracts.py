"""Catalogue-agnostic shapes and the resolution contract (KIT "El contrato").

Its own `Response`/`Transport`/exception types, deliberately not shared with
`manga_tracker.sources.contracts`: the catalogue is not downstream of the
source client, and duplicating a three-field dataclass costs less than a
shared HTTP package both layers would depend on (design D2). No dependency
on `manga_tracker.sources` anywhere in this module.
"""

from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True)
class Response:
    """Never the underlying HTTP library's own type — re-exporting it would
    leak that library out of transport.py."""

    status: int
    text: str
    headers: dict[str, str]


class Transport(Protocol):
    def get(self, url: str, *, headers: dict[str, str], timeout: float) -> Response: ...


@dataclass(frozen=True)
class CatalogueEntry:
    """KIT §"El contrato". `title_candidates` is ORDERED and catalogue
    knowledge: the importer tries it in order and never learns the field
    names (e.g. `abbreviatedTitles`) that produced it."""

    external_id: str  # the id resolve() was called with (today: a MAL id)
    catalogue_id: str  # the catalogue's own id (today: mangas.kitsu_id)
    title: str  # canonical title, for display
    title_candidates: Sequence[str]
    alt_titles: Sequence[str]
    synopsis: str | None
    genres: Sequence[str]
    cover_url: str | None
    total_chapters: int | None  # None when the catalogue omits it, never 0
    publication_status: str  # 'ongoing' | 'finished'


class CatalogueTransient(Exception):
    """Retryable transport failure: timeout, connection error, or a
    persistent 429/5xx after the one built-in retry."""


class CatalogueUnexpected(Exception):
    """Well-formed response with an unexpected shape — a missing
    `include=item` (HTTP 200, zero resolved) or a possibly-truncated
    page-full batch. The catalogue API likely changed."""


class CatalogueClient(Protocol):
    """One operation, by design (KIT §"El contrato"): batch-only, so a
    per-id method never leaks a bad usage pattern into the importer."""

    def resolve(self, external_ids: Sequence[str]) -> Sequence[CatalogueEntry]: ...
