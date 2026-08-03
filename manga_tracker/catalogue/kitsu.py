"""Kitsu implementation of `CatalogueClient` (KIT §"Resolucion: del id de MAL
al catalogo"). Chunks internally at `BATCH_SIZE` because 12 is derived from
Kitsu's own `page[limit]=20` — the importer must never carry another
catalogue's page limit.

No dependency on `manga_tracker.sources` or `manga_tracker.importer`: this
file only knows Kitsu's JSON:API shape.
"""

import json
from typing import Sequence

from manga_tracker.catalogue.contracts import (
    CatalogueEntry,
    CatalogueTransient,
    CatalogueUnexpected,
    Response,
    Transport,
)
from manga_tracker.catalogue.transport import TRANSIENT_STATUS_CODES

BASE_URL = "https://kitsu.io/api/edge"
DEFAULT_TIMEOUT = 30.0
HEADERS = {"Accept": "application/vnd.api+json"}

# 12 is derived from Kitsu's own page[limit]=20 (measured: a batch at 20 lost
# entries to pagination — 153 resources for 150 requested links, 2 unresolved
# with no error). Kept well under the limit, not merely under it.
BATCH_SIZE = 12
PAGE_LIMIT = 20
assert BATCH_SIZE < PAGE_LIMIT

# Kitsu's `status` attribute values, mapped to CatalogueEntry.publication_status.
_PUBLICATION_STATUS = {"current": "ongoing", "finished": "finished"}


def _chunks(items: Sequence[str], size: int) -> list[list[str]]:
    return [list(items[i : i + size]) for i in range(0, len(items), size)]


def _title_candidates(attributes: dict) -> list[str]:
    """Ordered `titles.en -> abbreviatedTitles -> canonicalTitle ->
    titles.en_jp` (KIT). No later candidate is reordered or deduplicated —
    the importer tries them exactly in this sequence."""
    titles = attributes.get("titles") or {}
    candidates: list[str] = []
    if titles.get("en"):
        candidates.append(titles["en"])
    candidates.extend(name for name in (attributes.get("abbreviatedTitles") or []) if name)
    if attributes.get("canonicalTitle"):
        candidates.append(attributes["canonicalTitle"])
    if titles.get("en_jp"):
        candidates.append(titles["en_jp"])
    return candidates


def _alt_titles(attributes: dict, canonical: str | None) -> list[str]:
    """Kept "as-is" (KIT §"La frontera del catalogo"): every other name Kitsu
    knows for the manga, canonical title excluded, no reordering."""
    titles = attributes.get("titles") or {}
    names = [name for name in titles.values() if name and name != canonical]
    names.extend(name for name in (attributes.get("abbreviatedTitles") or []) if name and name != canonical)
    return list(dict.fromkeys(names))  # de-duplicate, preserve first-seen order


def _cover_url(attributes: dict) -> str | None:
    poster = attributes.get("posterImage") or {}
    return poster.get("original")


class KitsuCatalogue:
    """`CatalogueClient` implementation. `resolve()` takes all ids and
    chunks internally — batching is catalogue knowledge, not the
    importer's (design D2)."""

    def __init__(self, transport: Transport):
        self._transport = transport

    def resolve(self, external_ids: Sequence[str]) -> list[CatalogueEntry]:
        entries: list[CatalogueEntry] = []
        for chunk in _chunks(list(external_ids), BATCH_SIZE):
            if chunk:
                entries.extend(self._resolve_chunk(chunk))
        return entries

    def _resolve_chunk(self, external_ids: list[str]) -> list[CatalogueEntry]:
        payload = self._fetch_json(
            f"{BASE_URL}/mappings"
            f"?filter[externalSite]=myanimelist/manga"
            f"&filter[externalId]={','.join(external_ids)}"
            f"&include=item&page[limit]={PAGE_LIMIT}"
        )
        mappings = payload.get("data") or []
        included = payload.get("included") or []

        if len(mappings) == PAGE_LIMIT:
            raise CatalogueUnexpected(
                f"mappings batch returned exactly page[limit]={PAGE_LIMIT} resources; "
                "possible truncation — narrow the batch size"
            )
        if mappings and not included:
            raise CatalogueUnexpected(
                "mappings response carries no 'included' resources; include=item is "
                "likely missing (HTTP 200, zero resolvable)"
            )

        items_by_id = {item["id"]: item for item in included if item.get("type") == "manga"}

        resolved: dict[str, dict] = {}  # external_id -> manga item
        for mapping in mappings:
            external_id = mapping["attributes"]["externalId"]
            item_ref = (mapping.get("relationships") or {}).get("item") or {}
            item_data = item_ref.get("data")
            if item_data is None:
                raise CatalogueUnexpected(
                    "mapping relationship 'item' has no 'data' (only 'links'); "
                    "include=item is likely missing"
                )
            item = items_by_id.get(item_data["id"])
            if item is not None:
                resolved[external_id] = item

        genres_by_manga_id = self._fetch_categories([item["id"] for item in resolved.values()])

        return [
            self._build_entry(external_id, item, genres_by_manga_id.get(item["id"], []))
            for external_id, item in resolved.items()
        ]

    def _fetch_categories(self, manga_ids: list[str]) -> dict[str, list[str]]:
        """Genres need a second call: `include=item,item.categories` on
        `/mappings` returns HTTP 400 (measured, KIT §"Resolucion")."""
        if not manga_ids:
            return {}
        payload = self._fetch_json(
            f"{BASE_URL}/manga?filter[id]={','.join(manga_ids)}&include=categories"
        )
        category_titles = {
            item["id"]: (item.get("attributes") or {}).get("title")
            for item in (payload.get("included") or [])
            if item.get("type") == "categories"
        }
        genres_by_manga_id: dict[str, list[str]] = {}
        for manga in payload.get("data") or []:
            refs = ((manga.get("relationships") or {}).get("categories") or {}).get("data") or []
            genres_by_manga_id[manga["id"]] = [
                category_titles[ref["id"]] for ref in refs if category_titles.get(ref["id"])
            ]
        return genres_by_manga_id

    def _build_entry(self, external_id: str, item: dict, genres: list[str]) -> CatalogueEntry:
        attributes = item.get("attributes") or {}
        canonical = attributes.get("canonicalTitle")
        return CatalogueEntry(
            external_id=external_id,
            catalogue_id=item["id"],
            title=canonical or "",
            title_candidates=_title_candidates(attributes),
            alt_titles=_alt_titles(attributes, canonical),
            synopsis=attributes.get("synopsis"),
            genres=genres,
            cover_url=_cover_url(attributes),
            total_chapters=attributes.get("chapterCount"),  # None when absent, never 0
            publication_status=_PUBLICATION_STATUS.get(attributes.get("status"), "ongoing"),
        )

    def _fetch_json(self, url: str) -> dict:
        response = self._get(url)
        try:
            return json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise CatalogueUnexpected(f"kitsu response is not valid JSON: {response.text[:200]!r}") from exc

    def _get(self, url: str) -> Response:
        """The transport itself only raises on a network-level failure that
        outlives its own retry; a persistent transient status code (e.g. two
        5xx in a row) is returned as data, mirroring `CurlCffiTransport`, so
        it is this call site's job to turn it into the right exception."""
        response = self._transport.get(url, headers=HEADERS, timeout=DEFAULT_TIMEOUT)
        if response.status in TRANSIENT_STATUS_CODES:
            raise CatalogueTransient(f"kitsu API returned status {response.status} for {url}")
        if response.status != 200:
            raise CatalogueUnexpected(f"kitsu API returned status {response.status} for {url}")
        return response
