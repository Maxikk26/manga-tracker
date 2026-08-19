"""The intake service boundary: frozen shapes, and the one exception that
carries the raw schema value `web` translates to Spanish."""

import dataclasses

import pytest

from manga_tracker.intake.contracts import AddPreview, AddResult, AlreadyTracked


def _preview(**overrides) -> AddPreview:
    fields = {
        "slug": "some-manga",
        "url": "https://example.test/manga/some-manga",
        "title": "Some Manga",
        "cover_url": "https://example.test/cover.webp",
        "publication_status_text": "Ongoing",
    }
    fields.update(overrides)
    return AddPreview(**fields)


def _result(**overrides) -> AddResult:
    fields = {
        "manga_id": 1,
        "bookmark_id": 1,
        "chapters_found": 0,
        "cover_cached": False,
    }
    fields.update(overrides)
    return AddResult(**fields)


def test_add_preview_is_frozen():
    preview = _preview()
    with pytest.raises(dataclasses.FrozenInstanceError):
        preview.title = "Different Title"


def test_add_result_is_frozen():
    result = _result()
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.chapters_found = 5


def test_add_preview_carries_publication_status_text():
    """Design's interfaces note: free from fetch_manga_details, passed
    through raw — not mapped onto the mangas.publication_status enum."""
    preview = _preview(publication_status_text="On hiatus")
    assert preview.publication_status_text == "On hiatus"


def test_add_preview_allows_no_cover_and_no_status_text():
    preview = _preview(cover_url=None, publication_status_text=None)
    assert preview.cover_url is None
    assert preview.publication_status_text is None


def test_add_result_allows_zero_chapters_and_uncached_cover():
    """D5: zero chapters is a legal successful add. D6: a cover fetch
    failure never fails the add."""
    result = _result(chapters_found=0, cover_cached=False)
    assert result.chapters_found == 0
    assert result.cover_cached is False


def test_already_tracked_carries_title_and_status():
    error = AlreadyTracked(title="Some Manga", status="dropped")
    assert error.title == "Some Manga"
    assert error.status == "dropped"
