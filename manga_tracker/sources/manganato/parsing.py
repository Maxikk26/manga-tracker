"""Feed and manga-page parsing (SRC Sections 2 and 4). Only module allowed to import bs4."""

import logging
import re

from bs4 import BeautifulSoup

from manga_tracker.sources.contracts import FeedItem, MangaDetails, Unexpected

_CHAPTER_NUM_RE = re.compile(r"Chapter\s+(\d+(?:\.\d+)?)", re.IGNORECASE)


def _is_ad(tag) -> bool:
    """`[class^="js-banner-"]` misses a non-first token — checked in Python."""
    return tag.has_attr("hidden") or any(c.startswith("js-banner-") for c in tag.get("class", []))


def parse_feed(html: str, logger: logging.Logger | None = None) -> list[FeedItem]:
    """Ad filter first. Zero real items after filtering is `Unexpected` — the
    feed structure changed, not that publishing stopped."""
    logger = logger or logging.getLogger(__name__)
    real = [t for t in BeautifulSoup(html, "html.parser").select("div.list-comic-item-wrap") if not _is_ad(t)]
    items = []
    for tag in real:
        title_link = tag.select_one("h3 a")
        chapter_link = tag.select_one("a.list-story-item-wrap-chapter")
        if title_link is None or chapter_link is None:
            continue
        chapter_text = chapter_link.get_text(strip=True)
        match = _CHAPTER_NUM_RE.search(chapter_text)
        if match is None:
            logger.warning("dropping feed item, unparseable chapter text: %r", chapter_text)
            continue
        cover = tag.select_one("a.list-story-item img")
        # updated_at_hint is always None for this source. Verified against a
        # real feed page (2026-07-28): a manganato item carries only the title
        # link, the chapter link, the cover and a view count — there is no
        # dated element at all, which is why SRC §2 lists none. The chapter
        # link's `title` attribute holds the chapter NAME ("Chapter 102"), so
        # using it here would put a chapter name in a date field: worse than
        # None, because it looks populated. CD Operación 1 asks the contract to
        # carry a hint for sources that have one; manganato does not. Harmless:
        # chapter_history.source_published_at is unconditionally NULL for
        # feed-sourced detections and is only ever filled by a sweep.
        items.append(FeedItem(
            source_key=title_link.get("href", "").rstrip("/").rsplit("/manga/", 1)[-1],
            title=title_link.get_text(strip=True),
            chapter_num=float(match.group(1)),
            url=chapter_link.get("href", ""),
            cover_url=(cover.get("data-src") or cover.get("src")) if cover else None,
            updated_at_hint=None,
        ))
    if not items:
        raise Unexpected("zero real items after ad filtering: feed structure likely changed")
    return items


def parse_manga_details(html: str) -> MangaDetails:
    """SRC §4 — cover fallback only in V1a; never called by detection."""
    soup = BeautifulSoup(html, "html.parser")
    title_tag, cover_tag = soup.select_one("ul.manga-info-text h1"), soup.select_one("div.manga-info-pic img")
    status_text = updated_text = None
    for li in soup.select("ul.manga-info-text li"):
        text = li.get_text(" ", strip=True)
        if text.lower().startswith("status"):
            status_text = text.split(":", 1)[-1].strip()
        elif text.lower().startswith("last updated"):
            updated_text = text.split(":", 1)[-1].strip()
    return MangaDetails(
        title=title_tag.get_text(strip=True) if title_tag else "",
        cover_url=cover_tag.get("src") if cover_tag else None,
        publication_status_text=status_text,
        last_updated_text=updated_text,
    )
