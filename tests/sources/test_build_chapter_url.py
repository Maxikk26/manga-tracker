"""build_chapter_url — pattern guess, no request (SRC Section 5, design B10).
The autouse socket-blocking fixture in tests/conftest.py already fails any
accidental real request; nothing extra to assert here for "no request"."""

import pytest

from manga_tracker.sources.manganato.client import BASE_URL, build_chapter_url


@pytest.mark.parametrize(
    "chapter_num, expected_suffix",
    [
        (80, "chapter-80"),
        ("80.0", "chapter-80"),  # design B10: naive int(n) raises on this
        (145.0, "chapter-145"),
        (45.5, "chapter-45-5"),
    ],
)
def test_build_chapter_url_formats_decimals_with_a_hyphen(chapter_num, expected_suffix):
    url = build_chapter_url("one-piece", chapter_num)

    assert url == f"{BASE_URL}/manga/one-piece/{expected_suffix}"
