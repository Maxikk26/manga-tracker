"""Manganato source client: JSON chapters endpoint plus HTML feed and
manga-details pages. Knows manganato's URLs/JSON/HTML selectors; nothing
about the reading list, bookmark states, or the DB (CD Parte A / CLAUDE.md)."""

import json
from urllib.parse import urlparse

from manga_tracker.sources.contracts import (
    Chapter,
    FeedItem,
    MangaDetails,
    NotFound,
    ProgressCallback,
    Transient,
    Transport,
    Unexpected,
)
from manga_tracker.sources.manganato.parsing import parse_feed, parse_manga_details
from manga_tracker.sources.manganato.sitemap import fetch_published_entries, fetch_published_urls
from manga_tracker.sources.manganato.transport import TRANSIENT_STATUS_CODES

BASE_URL = "https://www.manganato.gg"
FEED_PATH = "/manga-list/latest-manga"
DEFAULT_TIMEOUT = 30.0


def build_chapter_url(slug: str, chapter_num: float | str) -> str:
    """Pattern-built guess (SRC Section 5) — no request made, and the result
    is an unverified guess: the caller decides whether to use it.

    `chapter_num` may arrive as a string from the CSV/seed or JSON paths, so
    a naive `int(n)` raises on `'80.0'` (design B10). Coercing through
    `float` first survives both the numeric and the string-of-integral case.
    """
    value = float(chapter_num)
    num = int(value) if value.is_integer() else value
    return f"{BASE_URL}/manga/{slug}/chapter-{str(num).replace('.', '-')}"


def build_manga_url(slug: str) -> str:
    """Canonical ficha URL for a slug (SRC section 5)."""
    return f"{BASE_URL}/manga/{slug}"


def extract_slug(url: str) -> str | None:
    """Slug from any manganato URL, ficha or chapter (SRC section 5).

    Tolerates `www`, a trailing slash, a query and a fragment. Any segment
    after the slug — a chapter, typically — is ignored: progress never comes
    from a URL, only from the caller's own data.
    """
    parts = [p for p in urlparse(url).path.split("/") if p]
    if "manga" not in parts:
        return None
    idx = parts.index("manga")
    return parts[idx + 1] if idx + 1 < len(parts) else None


class ManganatoClient:
    """All three CD operations: feed, chapters, manga details."""

    build_manga_url = staticmethod(build_manga_url)
    extract_slug = staticmethod(extract_slug)

    def __init__(self, transport: Transport):
        self._transport = transport

    def fetch_latest_feed(self) -> list[FeedItem]:
        """CD Op. 1: one isolated request — the transport's inter-request
        delay never applies here (it only fires from a 2nd+ call)."""
        response = self._transport.get(f"{BASE_URL}{FEED_PATH}", headers={}, timeout=DEFAULT_TIMEOUT)
        return parse_feed(response.text)

    def fetch_manga_details(self, slug: str) -> MangaDetails:
        """CD Operacion 3: fallback-only, never called by any detection mechanism.

        A 403/429/5xx here (`TRANSIENT_STATUS_CODES`, reused from transport.py
        rather than duplicated) means the source is throttling or Cloudflare
        blocked the request, per spec-cliente-fuente-descubrimiento.md:65 -
        neither is evidence the slug is gone or the page shape changed, so it
        raises Transient rather than falling through to parse_manga_details,
        which used to return MangaDetails(title="", ...) on any non-404
        status: an empty-title fabrication that could reach `/api/mangas/preview`.
        Any other non-200 status is a genuine protocol surprise (Unexpected).
        """
        response = self._transport.get(f"{BASE_URL}/manga/{slug}", headers={}, timeout=DEFAULT_TIMEOUT)
        if response.status == 404:
            raise NotFound(f"manga details 404 for slug {slug!r}")
        if response.status in TRANSIENT_STATUS_CODES:
            raise Transient(f"manga details request for slug {slug!r} returned status {response.status}")
        if response.status != 200:
            raise Unexpected(f"manga details request for slug {slug!r} returned status {response.status}")
        return parse_manga_details(response.text)

    def fetch_cover(self, cover_url: str) -> bytes:
        """Download a cover image.

        Source knowledge, and that is the whole reason this lives here: the
        image hosts manganato points at (img-r2.2xstorage.com,
        storage.waitst.com) answer 403 to a request that does not carry a
        manganato `Referer`, and 200 to one that does — measured, not assumed.
        A panel pointing an <img src> straight at those URLs therefore shows a
        broken image for every cover, which is exactly the kind of failure that
        ships silently.

        The header is sent unconditionally. Hosts that do not check it, such as
        the Kitsu CDN the importer stored covers from, ignore it.

        The one operation here that does not retry (`retry=False`). A cover
        that is not there is an ordinary state, not a failure worth waiting on:
        the hosts answer **403** for an absent thumbnail, 403 is transient by
        SRC's taxonomy because a Cloudflare block is indistinguishable from it,
        and the result was a measured 43.9s spent confirming that an image the
        panel was going to fall back on anyway is still missing. The second
        attempt could not have changed the answer.
        """
        response = self._transport.get(
            cover_url, headers={"Referer": f"{BASE_URL}/"}, timeout=DEFAULT_TIMEOUT, retry=False
        )
        if response.status == 404:
            raise NotFound(f"cover 404 at {cover_url!r}")
        if response.status != 200 or not response.content:
            raise Unexpected(
                f"cover request to {cover_url!r} returned status {response.status} "
                f"with {len(response.content)} byte(s)"
            )
        return response.content

    def fetch_chapters(self, slug: str, *, limit: int = 50) -> list[Chapter]:
        """CD Operacion 2: GET the JSON chapters endpoint with an organic
        Referer (the manga's own ficha page). No pagination — one request at
        `limit`. A false-success payload or a 404 is a `NotFound`; a
        well-formed payload missing `data.chapters` is `Unexpected`.
        """
        url = f"{BASE_URL}/api/manga/{slug}/chapters"
        referer = f"{BASE_URL}/manga/{slug}"
        response = self._transport.get(url, headers={"Referer": referer}, timeout=DEFAULT_TIMEOUT)

        if response.status == 404:
            raise NotFound(f"chapters endpoint 404 for slug {slug!r}")

        try:
            payload = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise Unexpected(f"chapters payload is not valid JSON for slug {slug!r}") from exc

        if not payload.get("success", False):
            raise NotFound(f"chapters endpoint reported success=false for slug {slug!r}")

        data = payload.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("chapters"), list):
            raise Unexpected(
                f"chapters payload missing data.chapters for slug {slug!r}: {response.text[:200]!r}"
            )

        return [
            Chapter(
                chapter_num=raw["chapter_num"],
                url=f"{BASE_URL}/manga/{slug}/{raw['chapter_slug']}",
                # Passed through unchanged — never reparsed (CD Op. 2).
                published_at=raw["updated_at"],
            )
            for raw in data["chapters"][:limit]
        ]

    def fetch_known_slugs(self, *, progress: ProgressCallback | None = None) -> frozenset[str]:
        """Every slug the source publishes right now (KIT Seccion "Matching
        contra manganato"), so a caller can test membership instead of probing
        the source once per title: ~91.000 slugs for a handful of requests
        rather than one delayed request per candidate.

        Sequential and delay-bound like every other operation here, which is
        why `progress` exists — the wait is minutes long and silence is
        indistinguishable from a hang.

        Aborts rather than trimming: any failure the transport's retry did not
        absorb propagates, because a short set would read as "the source does
        not have these titles" and send the operator hunting for URLs that
        already exist.
        """
        urls = fetch_published_urls(self._transport, base_url=BASE_URL, progress=progress)
        slugs = frozenset(slug for url in urls if (slug := extract_slug(url)) is not None)
        if not slugs:
            raise Unexpected(
                f"the source published {len(urls)} URLs, none of them a manga: URL layout changed"
            )
        return slugs

    def fetch_slug_update_times(
        self, *, progress: ProgressCallback | None = None
    ) -> dict[str, str | None]:
        """`{slug: last update the source reports}`, for every slug it publishes.

        Lets a sweep ask "did this move since I last looked?" before spending a
        request per title. That mattered little at 16 mappings; after the Kitsu
        import the daily sweep covers 89, so the same answer costs ~10 requests
        instead of 89.

        The value is the source's own text, unconverted — comparing it to a
        stored timestamp is the caller's business, and reparsing here would
        invent precision the sitemap does not promise. `None` means the entry
        carried no timestamp, which a caller must read as "unknown", never as
        "unchanged".

        Aborts on any failure the transport's retry did not absorb, exactly like
        `fetch_known_slugs`: a short map would read as "these never move".
        """
        times: dict[str, str | None] = {}
        for url, stamp in fetch_published_entries(self._transport, base_url=BASE_URL, progress=progress):
            slug = extract_slug(url)
            if slug is not None:
                times[slug] = stamp
        if not times:
            raise Unexpected("the source published no manga URL at all: URL layout changed")
        return times

    def build_chapter_url(self, slug: str, chapter_num: float) -> str:
        return build_chapter_url(slug, chapter_num)
