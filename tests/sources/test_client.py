"""ManganatoClient.fetch_chapters — JSON path only this slice.
fetch_latest_feed / fetch_manga_details land with the HTML path next."""

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


def test_fetch_chapters_missing_array_is_unexpected():
    client, _ = _client(200, "chapters_missing_array.json")

    with pytest.raises(Unexpected):
        client.fetch_chapters("weird-manga")
