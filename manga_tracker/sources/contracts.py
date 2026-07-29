"""Source-agnostic shapes. Knows nothing about manganato specifically —
no URLs, HTML, or JSON shape — only the contract a client must satisfy."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, Sequence


@dataclass(frozen=True)
class Response:
    """Never curl-cffi's own type — re-exporting it would leak curl_cffi
    out of transport.py."""

    status: int
    text: str
    headers: dict[str, str]


class Transport(Protocol):
    def get(self, url: str, *, headers: dict[str, str], timeout: float) -> Response: ...


@dataclass(frozen=True)
class FeedItem:
    source_key: str
    title: str
    chapter_num: float
    url: str
    published_at: datetime | None


@dataclass(frozen=True)
class Chapter:
    chapter_num: float
    url: str
    published_at: datetime | None


@dataclass(frozen=True)
class MangaDetails:
    title: str
    source_key: str
    url: str


class NotFound(Exception):
    """The source reports the item does not exist (404 or false success)."""


class Transient(Exception):
    """Retryable failure: timeout, connection error, 5xx, Cloudflare challenge."""


class Unexpected(Exception):
    """Well-formed response with an unexpected shape — the source likely changed."""


class SourceClient(Protocol):
    def fetch_latest_feed(self) -> Sequence[FeedItem]: ...
    def fetch_chapters(self, source_key: str, *, limit: int = 50) -> Sequence[Chapter]: ...
    def fetch_manga_details(self, source_key: str) -> MangaDetails: ...
    def build_chapter_url(self, slug: str, chapter_num: float) -> str: ...
