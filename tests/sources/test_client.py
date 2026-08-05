"""ManganatoClient — JSON chapters path and HTML feed/manga-details path."""

from pathlib import Path

import pytest

from manga_tracker.sources.contracts import NotFound, Response, Unexpected
from manga_tracker.sources.manganato.client import BASE_URL, ManganatoClient

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


class FakeTransport:
    """Injected Transport double — never a real socket (see conftest)."""

    def __init__(self, response: Response):
        self._response = response
        self.calls: list[dict] = []

    def get(self, url, *, headers, timeout):
        self.calls.append({"url": url, "headers": headers, "timeout": timeout})
        return self._response


def _client(status: int, fixture: str | None) -> tuple[ManganatoClient, FakeTransport]:
    text = (FIXTURES / fixture).read_text(encoding="utf-8") if fixture else ""
    transport = FakeTransport(Response(status=status, text=text, headers={}))
    return ManganatoClient(transport), transport


def test_fetch_chapters_happy_path_newest_first_with_organic_referer():
    client, transport = _client(200, "chapters_ok.json")

    chapters = client.fetch_chapters("one-piece")

    assert [c.chapter_num for c in chapters] == [46, 45.5]
    assert chapters[1].url == f"{BASE_URL}/manga/one-piece/chapter-45-5"
    assert chapters[1].published_at == "2026-07-21T00:23:02.000000Z"  # never reparsed
    call = transport.calls[0]
    assert call["url"] == f"{BASE_URL}/api/manga/one-piece/chapters"
    assert call["headers"]["Referer"] == f"{BASE_URL}/manga/one-piece"


@pytest.mark.parametrize("status, fixture", [(200, "chapters_false_success.json"), (404, None)])
def test_fetch_chapters_not_found(status, fixture):
    client, _ = _client(status, fixture)

    with pytest.raises(NotFound):
        client.fetch_chapters("gone-manga")


def test_fetch_chapters_empty_array_is_a_success_not_an_error():
    """D14. A well-formed `success: true` carrying zero chapters is a success.

    It is the one payload that looks like a failure and is not: the slug exists,
    the endpoint answered, and the answer is "no chapters". Under CD's taxonomy
    that is neither not-found nor transient nor unexpected, so the client returns
    an empty list and lets each caller decide - and they decide differently on
    purpose (`active_sweep` resets the dead-slug counter, the seed loader
    discards the row whole; SEED "Fila cuyo slug existe pero devuelve cero
    capitulos"). Both of those hinge on this returning `[]` rather than raising,
    which is why it is asserted here and not inferred.
    """
    client, _ = _client(200, "chapters_empty.json")

    assert client.fetch_chapters("quiet-manga") == []


def test_fetch_chapters_missing_array_is_unexpected():
    client, _ = _client(200, "chapters_missing_array.json")

    with pytest.raises(Unexpected):
        client.fetch_chapters("weird-manga")


def test_fetch_latest_feed_requests_the_feed_url_and_parses_items():
    client, transport = _client(200, "feed_page.html")

    items = client.fetch_latest_feed()

    assert [i.source_key for i in items] == ["one-piece", "solo-leveling"]
    assert transport.calls[0]["url"] == f"{BASE_URL}/manga-list/latest-manga"


def test_fetch_manga_details_requests_the_manga_page():
    client, transport = _client(200, "manga_details.html")

    details = client.fetch_manga_details("one-piece")

    assert details.title == "One Piece"
    assert transport.calls[0]["url"] == f"{BASE_URL}/manga/one-piece"


def test_fetch_manga_details_not_found():
    client, _ = _client(404, None)

    with pytest.raises(NotFound):
        client.fetch_manga_details("gone-manga")
