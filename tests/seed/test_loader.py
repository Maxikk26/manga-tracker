"""Seed loader: validate-before-write and the D14 zero-chapters discard.
`ensure_site` isn't built yet, so tests seed the `sites` row directly."""

import csv

import pytest

from manga_tracker.seed.loader import load_seed
from manga_tracker.sources.contracts import Chapter, NotFound, Unexpected
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
        self.calls: list[str] = []

    def fetch_chapters(self, slug, *, limit=50):
        self.calls.append(slug)
        outcome = self._chapters_by_slug[slug]
        if isinstance(outcome, type) and issubclass(outcome, Exception):
            raise outcome(f"{slug} failed")
        return outcome


def _row(title, slug, last_read="", status="reading"):
    return {"title": title, "url": f"{SITE_URL}/manga/{slug}", "last_chapter_read": last_read,
            "status": status}


def _existing_manga(conn, site_id, *, title, slug, kitsu_id=None):
    """A manga already mapped to `slug`, as a previous load or the Kitsu import
    would have left it. `kitsu_id` is what marks the title as the catalogue's."""
    manga_id = conn.execute(
        "INSERT INTO mangas (title, kitsu_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (title, kitsu_id, NOW, NOW),
    ).lastrowid
    conn.execute(
        "INSERT INTO manga_sites (manga_id, site_id, source_key, url, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (manga_id, site_id, slug, f"{SITE_URL}/manga/{slug}", NOW, NOW),
    )
    conn.commit()
    return manga_id


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


def test_load_prints_progress_per_row_before_its_request(tmp_path, capsys):
    """SEED requires progress during the load, and the reason is operational.

    The validation report prints instantly; then every row costs one request
    with a 5-15s delay. Without progress the command looks frozen for minutes,
    and a real bring-up was interrupted with Ctrl+C halfway through because of
    it. Each row must be announced BEFORE its request, so the line on screen is
    the one being waited on.
    """
    rows = [
        {"title": f"Manga {n}", "url": f"{SITE_URL}/manga/m{n}", "last_chapter_read": "1", "status": "reading"}
        for n in (1, 2, 3)
    ]
    csv_path, conn, site_id = _setup(tmp_path, rows)
    chapters = {f"m{n}": [Chapter(chapter_num=2, url="u", published_at=None)] for n in (1, 2, 3)}

    assert load_seed(csv_path, conn, FakeClient(chapters), site_id=site_id) is True

    out = capsys.readouterr().out
    assert "[1/3]" in out and "[2/3]" in out and "[3/3]" in out
    assert "Done: 3 of 3" in out
    # The announcement precedes the summary, not the other way round.
    assert out.index("[1/3]") < out.index("Done:")


# --- SEED "Validacion": the errors and warnings only the whole file can see ---


def test_a_slug_repeated_in_the_file_blocks_the_load(tmp_path, capsys):
    """One slug maps to exactly one manga, so two rows claiming it is a mistake
    in the file and not something to resolve by last-write-wins.

    Left unchecked it loads silently and wrongly: `write_seed_backfill` reuses the
    mapping the first row created, so the second row's bookmark lands on the first
    row's manga and one of the two titles disappears from the database.
    """
    csv_path, conn, site_id = _setup(tmp_path, [
        _row("One Piece", "one-piece", "5"),
        _row("Wrongly Pasted", "one-piece", "12"),
    ])
    client = FakeClient({"one-piece": [Chapter(chapter_num=46, url="u", published_at=None)]})

    assert load_seed(csv_path, conn, client, site_id=site_id) is False
    out = capsys.readouterr().out
    assert "ERROR slug 'one-piece' appears in 2 rows of this file" in out
    assert conn.execute("SELECT COUNT(*) FROM mangas").fetchone()[0] == 0
    assert client.calls == []  # blocked before any request, not after


def test_the_same_slug_on_one_row_is_not_a_duplicate(tmp_path, capsys):
    """The boundary of the check above: one occurrence is the normal case."""
    csv_path, conn, site_id = _setup(tmp_path, [_row("One Piece", "one-piece", "5")])
    client = FakeClient({"one-piece": [Chapter(chapter_num=46, url="u", published_at=None)]})

    assert load_seed(csv_path, conn, client, site_id=site_id) is True
    assert "appears in" not in capsys.readouterr().out


def test_the_same_row_twice_is_reported_once_as_the_slug_error(tmp_path, capsys):
    """One mistake, one message.

    The duplicate-title warning is about a title spread over *different* slugs -
    a possible dual publication. The same row typed twice is the repeated-slug
    error above, and emitting both would describe one mistake as two.
    """
    csv_path, conn, site_id = _setup(tmp_path, [
        _row("One Piece", "one-piece", "5"),
        _row("One Piece", "one-piece", "5"),
    ])
    client = FakeClient({"one-piece": [Chapter(chapter_num=46, url="u", published_at=None)]})

    assert load_seed(csv_path, conn, client, site_id=site_id) is False
    out = capsys.readouterr().out
    assert "appears in 2 rows of this file" in out
    assert "different slugs" not in out


def test_a_slug_the_database_gave_to_another_manga_blocks_the_load(tmp_path, capsys):
    """A mis-pasted url, and the most expensive kind: without this the row loads
    with no error at all and files my progress under a manga I was not reading.

    Reuse by slug is the documented re-run path (SEED "Re-ejecucion"), so the
    stored title is the only thing that can tell reuse apart from a mis-paste.
    """
    csv_path, conn, site_id = _setup(tmp_path, [_row("One Piece", "solo-leveling", "5")])
    _existing_manga(conn, site_id, title="Solo Leveling", slug="solo-leveling")
    client = FakeClient({"solo-leveling": [Chapter(chapter_num=200, url="u", published_at=None)]})

    assert load_seed(csv_path, conn, client, site_id=site_id) is False
    out = capsys.readouterr().out
    assert "ERROR slug 'solo-leveling' already points at 'Solo Leveling' in the database" in out
    assert "not at 'One Piece'" in out
    assert client.calls == []


def test_the_same_title_on_that_slug_is_a_re_run_and_loads(tmp_path):
    """The other side of the check: matching titles are exactly the re-run SEED
    calls safe, so nothing may block it."""
    csv_path, conn, site_id = _setup(tmp_path, [_row("Solo Leveling", "solo-leveling", "9")])
    manga_id = _existing_manga(conn, site_id, title="Solo Leveling", slug="solo-leveling")
    client = FakeClient({"solo-leveling": [Chapter(chapter_num=200, url="u", published_at=None)]})

    assert load_seed(csv_path, conn, client, site_id=site_id) is True
    assert conn.execute("SELECT COUNT(*) FROM mangas").fetchone()[0] == 1
    assert conn.execute(
        "SELECT last_chapter_read FROM bookmarks WHERE manga_id = ?", (manga_id,)
    ).fetchone()[0] == 9


def test_a_catalogue_owned_title_is_not_compared_against_the_typed_one(tmp_path, capsys):
    """The exemption that keeps the check from eating the re-run workflow.

    SEED "El archivo" says the typed title "no necesita ser el canonico; Kitsu lo
    puede reemplazar despues", and the importer replaces `mangas.title` outright
    for every entry it matches. So after one import almost every hand-typed title
    differs from the stored one, and a strict comparison would reject most of the
    file - blocking the re-run SEED "Re-ejecucion" calls safe. A non-null
    `kitsu_id` is what says the catalogue owns that title.
    """
    csv_path, conn, site_id = _setup(tmp_path, [_row("Regressed Mercenary", "mercenary", "40")])
    _existing_manga(conn, site_id, title="The Regressed Mercenary's Machinations",
                    slug="mercenary", kitsu_id="12345")
    client = FakeClient({"mercenary": [Chapter(chapter_num=41, url="u", published_at=None)]})

    assert load_seed(csv_path, conn, client, site_id=site_id) is True
    assert "already points at" not in capsys.readouterr().out


def test_warnings_are_reported_and_load_anyway(tmp_path, capsys):
    """SEED "Avisos": these do not block. A `reading` row with no chapter is
    legitimate - the bookmark carries a null progress and the digest links to the
    newest chapter - and one title on two slugs may be a real dual publication."""
    csv_path, conn, site_id = _setup(tmp_path, [
        _row("Vinland Saga", "vinland-saga"),                   # reading, no chapter
        _row("Berserk", "berserk-a", "10"),
        _row("Berserk", "berserk-b", "10"),                     # same title, two slugs
    ])
    chapters = [Chapter(chapter_num=1, url="u", published_at=None)]
    client = FakeClient({slug: chapters for slug in ("vinland-saga", "berserk-a", "berserk-b")})

    assert load_seed(csv_path, conn, client, site_id=site_id) is True

    out = capsys.readouterr().out
    assert "WARNING status is 'reading' but last_chapter_read is empty" in out
    assert "WARNING title 'Berserk' appears 2 times with 2 different slugs" in out
    assert "ERROR" not in out
    assert conn.execute("SELECT COUNT(*) FROM mangas").fetchone()[0] == 3


def test_a_row_that_is_not_reading_and_has_no_chapter_does_not_warn(tmp_path, capsys):
    """`want_to_read` with no progress is the definition of that state, not a
    warning. The empty status column defaults to `reading` before the check runs,
    so the second row here does warn - one warning between the two."""
    csv_path, conn, site_id = _setup(tmp_path, [
        _row("Not Started", "not-started", "", "want_to_read"),
        _row("Also Reading", "also-reading", "", ""),  # empty status means reading
    ])
    chapters = [Chapter(chapter_num=1, url="u", published_at=None)]
    client = FakeClient({"not-started": chapters, "also-reading": chapters})

    assert load_seed(csv_path, conn, client, site_id=site_id) is True
    assert capsys.readouterr().out.count("WARNING status is 'reading'") == 1


def test_more_than_thirty_rows_warns_without_blocking(tmp_path, capsys):
    """SEED "Validacion" reads 30+ rows as a sign of doing the Kitsu import's
    work by hand. It is a warning precisely because the file is still valid.

    Asserted on both sides of the boundary. The importer's own pending list is fed
    back through this loader and that list measures 5 rows, so a warning firing
    early would be noise on a file the design expects to arrive here.
    """
    chapters = [Chapter(chapter_num=1, url="u", published_at=None)]

    def load(count):
        rows = [_row(f"Manga {n}", f"m{n}", "1") for n in range(count)]
        csv_path, conn, site_id = _setup(tmp_path, rows)
        client = FakeClient({f"m{n}": chapters for n in range(count)})
        assert load_seed(csv_path, conn, client, site_id=site_id) is True
        return capsys.readouterr().out

    assert "more than 30" not in load(30)
    assert "WARNING 31 rows, more than 30" in load(31)


# --- the load itself: discards and re-runs ------------------------------------


@pytest.mark.parametrize("failure", [NotFound, Unexpected], ids=["not-found", "unexpected"])
def test_a_failing_row_is_discarded_whole_and_the_others_continue(tmp_path, capsys, failure):
    """SEED: "se reporta y se descarta completa (...) Las demas filas continuan."

    Both failure classes discard, and neither may abort the load: one badly pasted
    url in a 16-row file would otherwise cost every row after it. The row that
    follows is asserted written, which is what "continuan" means.
    """
    csv_path, conn, site_id = _setup(tmp_path, [
        _row("Broken", "broken", "5"),
        _row("Fine", "fine", "7"),
    ])
    client = FakeClient({"broken": failure, "fine": [Chapter(chapter_num=8, url="u", published_at=None)]})

    assert load_seed(csv_path, conn, client, site_id=site_id) is True

    assert "DISCARDED 'Broken'" in capsys.readouterr().out
    assert [t for (t,) in conn.execute("SELECT title FROM mangas")] == ["Fine"]
    assert conn.execute("SELECT COUNT(*) FROM bookmarks").fetchone()[0] == 1


def test_re_running_the_file_reuses_rows_and_records_only_the_progress_that_moved(tmp_path):
    """SEED "Re-ejecucion". The last clause is the one worth pinning: the
    `reading_history` trigger is UPDATE-only, so an identical re-run must record
    nothing and one that advances progress must record exactly one event.
    Otherwise every re-run reads as "I read this again today"."""
    chapters = [Chapter(chapter_num=46, url="u46", published_at=None),
                Chapter(chapter_num=45, url="u45", published_at=None)]
    client = FakeClient({"one-piece": chapters})

    # One database across all three runs; only the file's progress column changes.
    csv_path, conn, site_id = _setup(tmp_path, [_row("One Piece", "one-piece", "5")])

    assert load_seed(csv_path, conn, client, site_id=site_id) is True
    assert load_seed(csv_path, conn, client, site_id=site_id) is True  # identical re-run

    def counts():
        return tuple(
            conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("mangas", "manga_sites", "chapter_history", "reading_history")
        )

    assert counts() == (1, 1, 2, 0)  # reused by slug, history idempotent, no fake read event

    advanced, _, _ = _setup(tmp_path, [_row("One Piece", "one-piece", "7")])
    assert load_seed(advanced, conn, client, site_id=site_id) is True
    assert counts() == (1, 1, 2, 1)  # progress moved 5 -> 7: exactly one event
    assert conn.execute(
        "SELECT previous_chapter_num, chapter_num FROM reading_history"
    ).fetchone() == (5, 7)
