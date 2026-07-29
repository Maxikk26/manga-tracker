"""Manganato source client.

JSON chapters path only this slice: `fetch_chapters` + `build_chapter_url`.
`fetch_latest_feed` and `fetch_manga_details` land with the HTML path next.
Knows manganato's URLs and JSON shape; nothing about the reading list,
bookmark states, or the DB (CD Parte A / CLAUDE.md structural boundary).
"""

import json

from manga_tracker.sources.contracts import Chapter, NotFound, Transport, Unexpected

BASE_URL = "https://www.manganato.gg"
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
    """JSON-path operations only this slice."""

    def __init__(self, transport: Transport):
        self._transport = transport

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
