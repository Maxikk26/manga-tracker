"""manganato's sitemap: the index at `/sitemap.xml` and the comic shards it
lists. The **only** module in the project that knows a sitemap exists — every
caller asks the client for known slugs and never learns how the client got
them, exactly as no caller learns how a chapter URL is assembled (CLAUDE.md,
"The structural boundary"; KIT Seccion "La resolucion no sondea la fuente").

Reading it is sanctioned rather than merely tolerated: the site declares this
sitemap in its own robots.txt.

Returns raw `<loc>` URLs, not slugs. A URL's shape is `client.py`'s knowledge
(`extract_slug`), the sitemap's layout is this file's; splitting them that way
also keeps the two modules free of a circular import.
"""

import xml.etree.ElementTree as ET

from manga_tracker.sources.contracts import ProgressCallback, Transient, Transport, Unexpected

# Same constant the transport classifies on. Imported rather than restated so
# the two can never drift, mirroring `catalogue/kitsu.py` importing it from
# `catalogue/transport.py`.
from manga_tracker.sources.manganato.transport import TRANSIENT_STATUS_CODES

SITEMAP_PATH = "/sitemap.xml"
DEFAULT_TIMEOUT = 30.0
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

# The index also lists a navigation/genre sitemap, which carries no manga.
# Only entries naming a comic shard are fetched.
COMIC_SHARD_MARKER = "sitemap-comic-"

ERROR_EXCERPT_CHARS = 200


def fetch_published_entries(
    transport: Transport,
    *,
    base_url: str,
    progress: ProgressCallback | None = None,
) -> list[tuple[str, str | None]]:
    """Every `(url, last_modified)` pair the sitemap publishes, in document order.

    The timestamp is passed through as raw text, never reparsed — the same rule
    the chapters endpoint follows. It is the newest chapter's `updated_at` at
    snapshot time (verified 2026-07-31: exact match to the second on 4 of 4
    sampled titles), which is what lets a caller skip a title that has not moved.

    `None` when the entry carries no `<lastmod>`. A caller must treat that as
    "unknown", never as "unchanged".
    """
    shard_urls = _fetch_shard_list(transport, base_url=base_url)
    total = len(shard_urls)
    entries: list[tuple[str, str | None]] = []
    for unit, shard_url in enumerate(shard_urls, start=1):
        if progress is not None:
            progress(unit, total)
        entries.extend(_fetch_shard_pairs(transport, shard_url))
    return entries


def fetch_published_urls(
    transport: Transport,
    *,
    base_url: str,
    progress: ProgressCallback | None = None,
) -> list[str]:
    """Every URL the sitemap publishes, in document order.

    Sequential through the caller's own transport, so the 5-15s courtesy delay
    applies from the second request on. The sitemap gets **no exemption** (KIT:
    "No se le hace excepcion") — one policy, no special cases.

    Nothing here catches a failure. That is the requirement, not an oversight:
    a shard that fails after the transport's retry aborts the whole operation
    (KIT v1.3). One lost shard is ~10.000 absent slugs, and the damage would be
    silent — real titles pushed to the caller's pending list as if the source
    did not carry them.
    """
    # (unit, total) and nothing else: the observer sees advancement, never a
    # word of this file's vocabulary.
    return [url for url, _ in fetch_published_entries(transport, base_url=base_url, progress=progress)]


def _fetch_shard_list(transport: Transport, *, base_url: str) -> list[str]:
    """The shard URLs the index declares — discovered, never assumed.

    There were 10 comic shards when this was measured (2026-07-31), and that
    number is the site's to change: hardcoding it would silently truncate the
    slug set the day an eleventh appears.
    """
    index_url = f"{base_url}{SITEMAP_PATH}"
    root = _parse(_fetch(transport, index_url), index_url)
    entries = [loc.text.strip() for loc in root.findall("sm:sitemap/sm:loc", SITEMAP_NS) if loc.text]
    shards = [entry for entry in entries if COMIC_SHARD_MARKER in entry]

    off_host = [shard for shard in shards if not shard.startswith(f"{base_url}/")]
    if off_host:
        # Refusing beats skipping: a skipped shard is a silently short set,
        # and following one is a request to a host the caller never chose.
        raise Unexpected(
            f"sitemap index at {index_url} points outside {base_url}: {off_host[0]!r}"
        )
    if not shards:
        raise Unexpected(
            f"sitemap index at {index_url} lists no {COMIC_SHARD_MARKER!r} entry "
            f"among {len(entries)} entries: the sitemap layout changed"
        )
    return shards


def _fetch_shard_pairs(transport: Transport, shard_url: str) -> list[tuple[str, str | None]]:
    root = _parse(_fetch(transport, shard_url), shard_url)
    pairs: list[tuple[str, str | None]] = []
    for entry in root.findall("sm:url", SITEMAP_NS):
        loc = entry.find("sm:loc", SITEMAP_NS)
        if loc is None or not loc.text:
            continue
        lastmod = entry.find("sm:lastmod", SITEMAP_NS)
        stamp = lastmod.text.strip() if lastmod is not None and lastmod.text else None
        pairs.append((loc.text.strip(), stamp))
    if not pairs:
        # Same rule as the feed's ad filter: zero items after parsing is a
        # structure change, not an empty list. The smallest shard measured
        # carried 1.471 URLs.
        raise Unexpected(f"sitemap shard {shard_url} carries zero <url> entries: layout changed")
    return pairs


def _fetch(transport: Transport, url: str) -> str:
    """The transport already retried once; whatever arrives here is final.

    A transient status that survived that retry comes back as data (the
    transport only raises on a network-level failure), so classifying it is
    this call site's job — the same split `catalogue/kitsu.py` uses.
    """
    response = transport.get(url, headers={}, timeout=DEFAULT_TIMEOUT)
    if response.status in TRANSIENT_STATUS_CODES:
        raise Transient(f"{url} returned status {response.status} after the transport's one retry")
    if response.status != 200:
        # Includes 404: the site declares this path in robots.txt, so its
        # absence means the source changed, not that an item is missing.
        raise Unexpected(f"{url} returned status {response.status}")
    return response.text


def _parse(text: str, url: str) -> ET.Element:
    """Stdlib ElementTree (design D7): it expands no undefined entities and
    fetches no external DTD, and a new dependency is not proportionate for a
    one-shot operator tool reading a robots.txt-declared endpoint.

    Parsed straight from `Response.text`, encoding declaration and all — the
    Transport contract deliberately exposes no `content: bytes` (SRC-3).
    """
    try:
        return ET.fromstring(text)
    except ET.ParseError as exc:
        raise Unexpected(
            f"sitemap XML at {url} did not parse: {text[:ERROR_EXCERPT_CHARS]!r}"
        ) from exc
