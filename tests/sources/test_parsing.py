"""parsing.py — bs4 is confined here; nothing else may import it."""

from pathlib import Path

import pytest

from manga_tracker.sources.contracts import Unexpected
from manga_tracker.sources.manganato.parsing import parse_feed, parse_manga_details

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_feed_filters_ads_and_prefers_data_src():
    items = parse_feed(_read("feed_page.html"))

    assert [i.source_key for i in items] == ["one-piece", "solo-leveling"]
    assert items[0].cover_url == "https://img-r2.2xstorage.com/one-piece.jpg"  # not the placeholder src


def test_parse_feed_never_mistakes_the_chapter_name_for_a_date_hint():
    """manganato's feed carries no dated element — verified against a real page.

    The chapter link's `title` attribute holds the chapter NAME, so a naive
    reading fills `updated_at_hint` with "Chapter 1120". None is the honest
    value: a populated-looking date field is worse than an empty one, and
    chapter_history.source_published_at is NULL for feed detections anyway.
    The fixture mirrors the real convention (title == chapter text) so this
    cannot silently regress.
    """
    items = parse_feed(_read("feed_page.html"))

    assert [i.updated_at_hint for i in items] == [None, None]
    assert all("Chapter" not in (i.updated_at_hint or "") for i in items)


@pytest.mark.parametrize("fixture", ["feed_page_ads_only.html", "feed_page_structure_changed.html"])
def test_parse_feed_zero_real_items_is_unexpected(fixture):
    with pytest.raises(Unexpected):
        parse_feed(_read(fixture))


def test_parse_feed_drops_only_the_unparseable_item():
    items = parse_feed(_read("feed_item_no_number.html"))

    assert [i.source_key for i in items] == ["one-piece"]


def test_parse_manga_details_extracts_four_fields():
    details = parse_manga_details(_read("manga_details.html"))

    assert details.title == "One Piece"
    assert details.cover_url == "https://img-r2.2xstorage.com/one-piece-full.jpg"
    assert details.publication_status_text == "Ongoing"
    assert details.last_updated_text == "Jul 22, 2026 - 03:10 AM"
