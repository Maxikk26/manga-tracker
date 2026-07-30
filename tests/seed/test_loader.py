"""Seed loader: validate-before-write and the D14 zero-chapters discard.
`ensure_site` isn't built yet, so tests seed the `sites` row directly."""

import csv

from manga_tracker.seed.loader import load_seed
from manga_tracker.sources.contracts import Chapter
from manga_tracker.sources.manganato.client import build_manga_url, extract_slug
from manga_tracker.storage.db import connect

SITE_URL, NOW = "https://www.manganato.gg", "2026-07-28T00:00:00Z"


class FakeClient:
    """Duck-typed SourceClient double.

    `fetch_chapters` is faked, but the two URL operations delegate to the real
    manganato implementations on purpose: they make no request, and stubbing
    them would let the double drift from the contract the loader depends on.
    """

    build_manga_url = staticmethod(build_manga_url)
    extract_slug = staticmethod(extract_slug)

    def __init__(self, chapters_by_slug: dict):
        self._chapters_by_slug = chapters_by_slug

    def fetch_chapters(self, slug, *, limit=50):
        return self._chapters_by_slug[slug]


def _setup(tmp_path, rows):
    csv_path = tmp_path / "seed.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["title", "url", "last_chapter_read", "status"])
        writer.writeheader()
        writer.writerows(rows)
    conn = connect(":memory:")
    site_id = conn.execute(
        "INSERT INTO sites (name, base_url, created_at, updated_at) VALUES ('manganato', ?, ?, ?)",
        (SITE_URL, NOW, NOW),
    ).lastrowid
    return csv_path, conn, site_id


def test_extract_slug_tolerates_ficha_and_chapter_url_variants():
    assert extract_slug(f"{SITE_URL}/manga/one-piece/") == "one-piece"
    assert extract_slug(f"{SITE_URL}/manga/one-piece/chapter-145?ref=x#top") == "one-piece"


def test_loader_holds_no_source_url_knowledge():
    """The loader must ask the client for URL shapes, never hardcode them.

    A hardcoded "/manga/{slug}" is invisible to the AST import test — it is a
    string, not an import — so it is asserted here instead. If manganato ever
    changes its paths, only its client should need editing.
    """
    source = (__import__("pathlib").Path("manga_tracker/seed/loader.py")).read_text(encoding="utf-8")
    code = "\n".join(line for line in source.splitlines() if not line.strip().startswith("#"))
    assert "/manga/" not in code
    assert "urlparse" not in code


def test_invalid_row_blocks_entire_load_and_writes_nothing(tmp_path, capsys):
    csv_path, conn, site_id = _setup(tmp_path, [
        {"title": "", "url": f"{SITE_URL}/manga/one-piece", "last_chapter_read": "5", "status": "reading"},
    ])
    client = FakeClient({"one-piece": [Chapter(chapter_num=5, url="x", published_at=None)]})
    loaded = load_seed(csv_path, conn, client, site_id=site_id)
    assert loaded is False
    assert conn.execute("SELECT COUNT(*) FROM mangas").fetchone()[0] == 0
    assert "title is empty" in capsys.readouterr().out


def test_zero_chapters_row_reported_and_discarded_whole(tmp_path):
    csv_path, conn, site_id = _setup(tmp_path, [
        {"title": "Dead Manga", "url": f"{SITE_URL}/manga/dead-manga", "last_chapter_read": "", "status": "reading"},
    ])
    client = FakeClient({"dead-manga": []})
    loaded = load_seed(csv_path, conn, client, site_id=site_id)
    assert loaded is False
    for table in ("mangas", "manga_sites", "bookmarks"):
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
