"""Source-agnostic shapes. Knows nothing about manganato specifically —
no URLs, HTML, or JSON shape — only the contract a client must satisfy."""

from dataclasses import dataclass
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
    cover_url: str | None
    # SRC section 8 names this field `updated_at_hint`, and CD Operacion 1 is
    # explicit that the feed's date is "el texto tal cual, sin convertir" — the
    # feed gives no reliable timestamp. Kept as raw text under the documented
    # name: calling it `published_at: datetime` would invite treating a vague
    # string as authoritative, which is why chapter_history.source_published_at
    # stays NULL for feed detections and is only filled by a sweep.
    updated_at_hint: str | None


@dataclass(frozen=True)
class Chapter:
    chapter_num: float
    url: str
    # CD Operacion 2: the JSON endpoint already gives UTC ISO-8601; passed
    # through as-is, never reparsed into a datetime (would change format).
    published_at: str | None


@dataclass(frozen=True)
class MangaDetails:
    # CD Operacion 3's actual return shape: title, cover URL (fallback-only),
    # publication-status text, last-updated text. No source_key/url — those
    # were carried over before fetch_manga_details was implemented against
    # the real contract.
    title: str
    cover_url: str | None
    publication_status_text: str | None
    last_updated_text: str | None


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
