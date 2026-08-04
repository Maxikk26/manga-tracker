"""Source-agnostic shapes. Knows nothing about manganato specifically —
no URLs, HTML, or JSON shape — only the contract a client must satisfy."""

from dataclasses import dataclass
from typing import Callable, Protocol, Sequence

# Reported as `(unit, total)` before each remote call of a multi-request
# operation, so a caller can show that a long silence is progress and not a
# hang. Both values are plain integers on purpose: what a unit *is* — a page,
# a batch, a file — is the client's business, and naming it here would leak
# one source's internals into the contract every source shares.
ProgressCallback = Callable[[int, int], None]


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

    # The two operations below are on the contract for the same reason
    # build_chapter_url is: a URL shape is source knowledge. Without them, a
    # consumer has to hardcode "/manga/{slug}" or "the slug is the segment
    # after /manga/", and a source that changes its paths would force edits
    # outside its own client — exactly what the layer boundary forbids. The
    # AST import test cannot catch that leak, because a hardcoded path is a
    # string, not an import.
    def build_manga_url(self, slug: str) -> str: ...
    def extract_slug(self, url: str) -> str | None: ...

    # Every slug the source currently publishes, for membership tests: asking
    # "does this slug exist?" once for the whole catalogue instead of probing
    # the source title by title. How a client enumerates its catalogue is its
    # own knowledge — the caller receives a set of slugs and learns nothing
    # about which files, pages or endpoints produced it.
    #
    # It is a frozenset, not a Sequence, because membership is the entire
    # point: the caller tests ~150 candidates against ~91k slugs.
    #
    # A failure that outlives the transport's retry propagates: a partial set
    # is worse than none, since a slug missing from it is indistinguishable
    # from a title the source does not carry (KIT v1.3).
    def fetch_known_slugs(self, *, progress: ProgressCallback | None = None) -> frozenset[str]: ...
    def fetch_slug_update_times(
        self, *, progress: ProgressCallback | None = None
    ) -> dict[str, str | None]: ...
