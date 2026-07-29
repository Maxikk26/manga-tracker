"""Manganato source client: JSON chapters endpoint plus HTML feed and
manga-details pages. Knows manganato's URLs/JSON/HTML selectors; nothing
about the reading list, bookmark states, or the DB (CD Parte A / CLAUDE.md)."""

import json

from manga_tracker.sources.contracts import Chapter, FeedItem, MangaDetails, NotFound, Transport, Unexpected
from manga_tracker.sources.manganato.parsing import parse_feed, parse_manga_details

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


class ManganatoClient:
    """All three CD operations: feed, chapters, manga details."""

    def __init__(self, transport: Transport):
        self._transport = transport

    def fetch_latest_feed(self) -> list[FeedItem]:
        """CD Op. 1: one isolated request — the transport's inter-request
        delay never applies here (it only fires from a 2nd+ call)."""
        response = self._transport.get(f"{BASE_URL}{FEED_PATH}", headers={}, timeout=DEFAULT_TIMEOUT)
        return parse_feed(response.text)

    def fetch_manga_details(self, slug: str) -> MangaDetails:
        """CD Operacion 3: fallback-only, never called by any detection mechanism."""
        response = self._transport.get(f"{BASE_URL}/manga/{slug}", headers={}, timeout=DEFAULT_TIMEOUT)
        if response.status == 404:
            raise NotFound(f"manga details 404 for slug {slug!r}")
        return parse_manga_details(response.text)

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

    def build_chapter_url(self, slug: str, chapter_num: float) -> str:
        return build_chapter_url(slug, chapter_num)
