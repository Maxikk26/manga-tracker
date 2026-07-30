"""links.resolve_link - BOT "Resolucion del enlace": chapter_history's own
registered URL wins over the client's pattern-built guess, which wins over the
newest chapter's URL. No network - the fake client only records calls."""

from manga_tracker.discovery.links import resolve_link
from manga_tracker.storage.db import connect

NOW = "2026-07-28T04:00:00Z"


class FakeClient:
    """Exposes only build_chapter_url - resolve_link must never call anything
    else on it, and a real client's URL shape is irrelevant to this test."""

    def __init__(self):
        self.calls = []

    def build_chapter_url(self, source_key, chapter_num):
        self.calls.append((source_key, chapter_num))
        return f"GUESS-{source_key}-{chapter_num}"


def _seed_manga_site(conn) -> int:
    manga_id = conn.execute(
        "INSERT INTO mangas (title, created_at, updated_at) VALUES ('OP', ?, ?)", (NOW, NOW)
    ).lastrowid
    site_id = conn.execute(
        "INSERT INTO sites (name, base_url, created_at, updated_at) VALUES ('manganato', 'x', ?, ?)", (NOW, NOW)
    ).lastrowid
    ms_id = conn.execute(
        "INSERT INTO manga_sites (manga_id, site_id, source_key, created_at, updated_at) "
        "VALUES (?, ?, 'op', ?, ?)",
        (manga_id, site_id, NOW, NOW),
    ).lastrowid
    conn.commit()
    return ms_id


def _write_history(conn, ms_id: int, chapter_num, chapter_url):
    conn.execute(
        "INSERT INTO chapter_history (manga_site_id, chapter_num, chapter_url, detected_at, detected_via) "
        "VALUES (?, ?, ?, ?, 'feed')",
        (ms_id, chapter_num, chapter_url, NOW),
    )
    conn.commit()


def test_prefers_registered_chapter_history_url_over_pattern_built():
    conn = connect(":memory:")
    ms_id = _seed_manga_site(conn)
    _write_history(conn, ms_id, 101, "https://real/chapter-101")
    client = FakeClient()

    result = resolve_link(conn, client, manga_site_id=ms_id, source_key="op",
                           newest_url="NEWEST-FALLBACK", last_chapter_read=100)

    assert result == "https://real/chapter-101"
    assert client.calls == []


def test_falls_back_to_pattern_built_when_chapter_not_registered_with_a_url():
    conn = connect(":memory:")
    ms_id = _seed_manga_site(conn)
    _write_history(conn, ms_id, 101, None)  # registered, but no URL yet
    client = FakeClient()

    result = resolve_link(conn, client, manga_site_id=ms_id, source_key="op",
                           newest_url="NEWEST-FALLBACK", last_chapter_read=100)

    # chapter_num round-trips through the REAL column as a Python float.
    assert result == "GUESS-op-101.0"
    assert client.calls == [("op", 101.0)]


def test_falls_back_to_newest_when_neither_applies():
    conn = connect(":memory:")
    ms_id = _seed_manga_site(conn)  # no chapter_history row at all
    client = FakeClient()

    result = resolve_link(conn, client, manga_site_id=ms_id, source_key="op",
                           newest_url="NEWEST-FALLBACK", last_chapter_read=100)

    assert result == "NEWEST-FALLBACK"
    assert client.calls == []


def test_null_progress_resolves_to_newest():
    conn = connect(":memory:")
    ms_id = _seed_manga_site(conn)
    _write_history(conn, ms_id, 101, "https://real/chapter-101")  # would win at step 1 if reached
    client = FakeClient()

    result = resolve_link(conn, client, manga_site_id=ms_id, source_key="op",
                           newest_url="NEWEST-FALLBACK", last_chapter_read=None)

    assert result == "NEWEST-FALLBACK"
    assert client.calls == []
