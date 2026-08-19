"""The add-a-manga service boundary (design D1/D2). Knows nothing about how a
slug is validated or a bookmark is written — only the shapes `web` is allowed
to see and the failures it must translate.

No Spanish, no HTTP, no source knowledge: `web` composes the Spanish sentence
from `AlreadyTracked.title`/`.status`, and the sequencing that reaches the
source lives in `pasted_url.py`, never here.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AddPreview:
    """What a preview returns before anything is written."""

    slug: str
    url: str  # canonical ficha URL, from client.build_manga_url
    title: str
    cover_url: str | None
    # spec.md "Preview validates without writing" requires the publication
    # status text too. Free: fetch_manga_details already carries it, so this
    # is a field passed through, not a second request. Raw source text, never
    # mapped onto mangas.publication_status — that enum is 'ongoing' /
    # 'hiatus_detected' / 'finished' and inferring it from a display string is
    # not this change's business.
    publication_status_text: str | None


@dataclass(frozen=True)
class AddResult:
    """What a successful confirm returns."""

    manga_id: int
    bookmark_id: int
    chapters_found: int  # 0 is legal (D5: zero chapters is a successful add)
    cover_cached: bool  # False is legal (D6: cover failure never fails the add)


class InvalidUrl(Exception):
    """The URL yields no slug (per the client's `extract_slug`)."""


class AlreadyTracked(Exception):
    """The slug or the resolved title already has a bookmark.

    `status` is the raw schema value (`reading`, `dropped`, ...) — `web` is
    the layer that names it in Spanish.
    """

    def __init__(self, title: str, status: str):
        super().__init__(f"{title!r} already tracked as {status!r}")
        self.title = title
        self.status = status


class MangaIntake(Protocol):
    """The only thing `web` is allowed to hold instead of a `SourceClient`.

    `web` imports this module and nothing under `sources` — the enforceable
    form of "el panel pide agrega esto, no descarga esto" (PAN §34-37).
    """

    def preview(self, conn, url: str) -> AddPreview: ...

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
    ) -> AddResult: ...
