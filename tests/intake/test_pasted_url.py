"""`PastedUrlIntake`: the only `MangaIntake` implementation (design D1).
`preview()` and `confirm()` — the transactional write and the cover fetch."""

import pytest

from manga_tracker.intake.contracts import AlreadyTracked, InvalidUrl
from manga_tracker.intake.pasted_url import PastedUrlIntake
from manga_tracker.sources.contracts import Chapter, MangaDetails, NotFound, Transient, Unexpected
from manga_tracker.storage.cover_cache import find_cached, preview_cache_path, write_preview
from manga_tracker.storage.db import connect

NOW = "2026-08-19T12:00:00Z"
SITE_ID = 1

CHAPTERS = [
    Chapter(chapter_num=12.0, url="https://host/manga/some-manga/chapter-12", published_at="2026-08-18T00:00:00Z"),
    Chapter(chapter_num=11.0, url="https://host/manga/some-manga/chapter-11", published_at="2026-08-17T00:00:00Z"),
]
IMAGE = b"\x89PNG fake bytes"


class FakeClient:
    """A `SourceClient`-shaped fake — no request classes hit the wire.

    `extract_slug`/`build_manga_url` are the same pure functions the concrete
    `ManganatoClient` exposes as staticmethods, reused here rather than
    reimplemented so the fake's URL shape matches production exactly."""

    def __init__(
        self, *, details=None, details_error=None, chapters=None, chapters_error=None,
        cover_image=IMAGE, cover_error=None,
    ):
        from manga_tracker.sources.manganato.client import build_manga_url, extract_slug

        self.extract_slug = extract_slug
        self.build_manga_url = build_manga_url
        self._details = details or MangaDetails(
            title="Some Manga", cover_url="https://host/cover.webp",
            publication_status_text="Ongoing", last_updated_text=None,
        )
        self._details_error = details_error
        self._chapters = CHAPTERS if chapters is None else chapters
        self._chapters_error = chapters_error
        self._cover_image = cover_image
        self._cover_error = cover_error
        self.details_calls: list[str] = []
        self.chapters_calls: list[str] = []
        self.cover_calls: list[str] = []

    def fetch_manga_details(self, slug):
        self.details_calls.append(slug)
        if self._details_error:
            raise self._details_error
        return self._details

    def fetch_chapters(self, slug, *, limit=50):
        self.chapters_calls.append(slug)
        if self._chapters_error:
            raise self._chapters_error
        return self._chapters

    def fetch_cover(self, cover_url):
        self.cover_calls.append(cover_url)
        if self._cover_error:
            raise self._cover_error
        return self._cover_image


@pytest.fixture()
def conn(tmp_path):
    connection = connect(str(tmp_path / "intake.db"))
    connection.execute(
        "INSERT INTO sites (id, name, base_url, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (SITE_ID, "manganato", "https://www.manganato.gg", NOW, NOW),
    )
    connection.commit()
    return connection


def _intake(*, cache_dir=None, **client_kwargs) -> PastedUrlIntake:
    return PastedUrlIntake(FakeClient(**client_kwargs), SITE_ID, cache_dir=cache_dir)


def _tracked(conn, title, status, *, slug=None):
    """Seed a tracked manga: a bookmark plus (optionally) a manga_sites row —
    a terminal Kitsu row has no manga_sites row at all (spec.md scenario)."""
    manga_id = conn.execute(
        "INSERT INTO mangas (title, created_at, updated_at) VALUES (?, ?, ?)", (title, NOW, NOW)
    ).lastrowid
    if slug is not None:
        conn.execute(
            "INSERT INTO manga_sites (manga_id, site_id, source_key, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (manga_id, SITE_ID, slug, NOW, NOW),
        )
    conn.execute(
        "INSERT INTO bookmarks (manga_id, status, origin, created_at, updated_at) VALUES (?, ?, 'seed', ?, ?)",
        (manga_id, status, NOW, NOW),
    )
    conn.commit()
    return manga_id


# --- malformed URL -------------------------------------------------------------


def test_preview_rejects_a_url_with_no_slug(conn):
    with pytest.raises(InvalidUrl):
        _intake().preview(conn, "https://www.manganato.gg/genre/action")


# --- gates 1-2: zero client calls ----------------------------------------------


def test_preview_gate_1_refuses_a_slug_already_mapped_with_zero_client_calls(conn):
    _tracked(conn, "Reading Already", "reading", slug="some-manga")
    client = FakeClient()
    intake = PastedUrlIntake(client, SITE_ID, cache_dir=None)

    with pytest.raises(AlreadyTracked) as excinfo:
        intake.preview(conn, "https://www.manganato.gg/manga/some-manga")

    assert (excinfo.value.title, excinfo.value.status) == ("Reading Already", "reading")
    assert client.details_calls == []


def test_preview_gate_2_refuses_a_terminal_title_with_no_manga_sites_row(conn):
    """The re-add scenario spec.md names explicitly: a completed manga whose
    manga_sites row was removed, so slug identity alone cannot see it — only
    re-deriving the slug from the stored title (gate 2) catches it."""
    _tracked(conn, "Some Manga", "completed", slug=None)
    client = FakeClient()
    intake = PastedUrlIntake(client, SITE_ID, cache_dir=None)

    with pytest.raises(AlreadyTracked) as excinfo:
        intake.preview(conn, "https://www.manganato.gg/manga/some-manga")

    assert (excinfo.value.title, excinfo.value.status) == ("Some Manga", "completed")
    assert client.details_calls == []


# --- gate 3: after exactly one client call --------------------------------------


def test_preview_gate_3_refuses_after_one_call_when_the_source_title_differs(conn):
    """The source's title does not slug-match any tracked title (gate 2
    misses), but normalizes to one after the ficha resolves it."""
    _tracked(conn, "Some Manga!", "dropped", slug=None)
    details = MangaDetails(
        title="Some, Manga", cover_url=None, publication_status_text=None, last_updated_text=None,
    )
    client = FakeClient(details=details)
    intake = PastedUrlIntake(client, SITE_ID, cache_dir=None)

    with pytest.raises(AlreadyTracked) as excinfo:
        intake.preview(conn, "https://www.manganato.gg/manga/wildly-different-slug")

    assert (excinfo.value.title, excinfo.value.status) == ("Some Manga!", "dropped")
    assert client.details_calls == ["wildly-different-slug"]


# --- source failure classes propagate untranslated ------------------------------


@pytest.mark.parametrize("error", [NotFound("gone"), Transient("timeout"), Unexpected("shape")])
def test_preview_propagates_source_failures_untranslated(conn, error):
    intake = _intake(details_error=error)

    with pytest.raises(type(error)):
        intake.preview(conn, "https://www.manganato.gg/manga/some-manga")


# --- the happy path --------------------------------------------------------------


def test_preview_returns_the_matched_metadata_and_writes_nothing(conn):
    intake = _intake()

    preview = intake.preview(conn, "https://www.manganato.gg/manga/some-manga")

    assert preview.slug == "some-manga"
    assert preview.url == "https://www.manganato.gg/manga/some-manga"
    assert preview.title == "Some Manga"
    assert preview.cover_url == "https://host/cover.webp"
    assert preview.publication_status_text == "Ongoing"
    assert conn.execute("SELECT COUNT(*) FROM mangas").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM manga_sites").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM bookmarks").fetchone()[0] == 0


# ================================================================================
# preview_cover()
# ================================================================================


COVER_URL = "https://host/cover.webp"


def test_preview_cover_fetches_once_and_replays_from_the_cache_file(tmp_path):
    cache_dir = tmp_path / "covers"
    client = FakeClient()
    intake = PastedUrlIntake(client, SITE_ID, cache_dir=cache_dir)

    first = intake.preview_cover(COVER_URL)
    second = intake.preview_cover(COVER_URL)

    assert first == (IMAGE, "image/webp")
    assert second == first
    assert client.cover_calls == [COVER_URL]  # the replay cost zero requests
    cached = preview_cache_path(cache_dir, COVER_URL)
    assert cached.exists() and cached.suffix == ".webp"
    assert cached.read_bytes() == IMAGE


@pytest.mark.parametrize("bad", ["http://host/cover.webp", "not-a-url", "https:///no-host.webp"])
def test_preview_cover_rejects_an_unacceptable_url_without_fetching(tmp_path, bad):
    """Same gate as confirm's (`_acceptable_cover_url`): the server GETs this
    client-echoed URL, so anything not https-with-a-host never reaches the
    client. None, not an exception — the modal just shows its placeholder."""
    client = FakeClient()
    intake = PastedUrlIntake(client, SITE_ID, cache_dir=tmp_path / "covers")

    assert intake.preview_cover(bad) is None
    assert client.cover_calls == []


@pytest.mark.parametrize("error", [NotFound("gone"), Transient("timeout"), Unexpected("shape")])
def test_preview_cover_source_failure_is_none_not_an_error(tmp_path, error):
    cache_dir = tmp_path / "covers"
    client = FakeClient(cover_error=error)
    intake = PastedUrlIntake(client, SITE_ID, cache_dir=cache_dir)

    assert intake.preview_cover(COVER_URL) is None
    assert not preview_cache_path(cache_dir, COVER_URL).exists()  # nothing half-written


# ================================================================================
# confirm()
# ================================================================================


def _counts(conn) -> tuple[int, int, int, int]:
    return (
        conn.execute("SELECT COUNT(*) FROM mangas").fetchone()[0],
        conn.execute("SELECT COUNT(*) FROM manga_sites").fetchone()[0],
        conn.execute("SELECT COUNT(*) FROM bookmarks").fetchone()[0],
        conn.execute("SELECT COUNT(*) FROM chapter_history").fetchone()[0],
    )


def _confirm(conn, cache_dir, *, status="reading", last_chapter_read=0.0, **client_kwargs):
    client = FakeClient(**client_kwargs)
    intake = PastedUrlIntake(client, SITE_ID, cache_dir=cache_dir)
    result = intake.confirm(
        conn,
        url="https://www.manganato.gg/manga/some-manga",
        title="Some Manga",
        cover_url="https://host/cover.webp",
        status=status,
        last_chapter_read=last_chapter_read,
        now=NOW,
    )
    return result, client


def test_confirm_drops_a_non_https_cover_url_without_fetching_or_storing_it(conn, tmp_path):
    """The threat-matrix gate: the server GETs the client-echoed cover_url,
    so anything that is not https with a real host never reaches the client
    or the mangas row. The add itself stands, like any missing cover."""
    cache_dir = tmp_path / "covers"
    for bad in ("http://host/cover.webp", "not-a-url", "https:///no-host.webp"):
        conn.execute("DELETE FROM bookmarks")
        conn.execute("DELETE FROM chapter_history")
        conn.execute("DELETE FROM manga_sites")
        conn.execute("DELETE FROM mangas")
        client = FakeClient()
        intake = PastedUrlIntake(client, SITE_ID, cache_dir=cache_dir)

        result = intake.confirm(
            conn,
            url="https://www.manganato.gg/manga/some-manga",
            title="Some Manga",
            cover_url=bad,
            status="reading",
            last_chapter_read=0.0,
            now=NOW,
        )

        assert result.cover_cached is False, bad
        assert client.cover_calls == [], bad  # never fetched
        stored = conn.execute("SELECT cover_url FROM mangas").fetchone()[0]
        assert stored is None, bad  # never stored, so no backfill will fetch it either
        assert conn.execute("SELECT COUNT(*) FROM bookmarks").fetchone()[0] == 1, bad


def test_confirm_happy_path_writes_all_four_tables(conn, tmp_path):
    cache_dir = tmp_path / "covers"

    result, client = _confirm(conn, cache_dir)

    assert client.chapters_calls == ["some-manga"]
    assert result.chapters_found == 2
    assert result.cover_cached is True
    assert conn.execute("SELECT COUNT(*) FROM mangas").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM manga_sites").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM bookmarks").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM chapter_history").fetchone()[0] == 2
    assert find_cached(cache_dir, result.manga_id) is not None


def test_confirm_promotes_a_cached_preview_cover_without_fetching(conn, tmp_path):
    """The request-budget half of the preview cache: when `preview_cover()`
    already fetched the image, confirm reads the file, writes the real cover
    and deletes the preview — zero cover requests, so the whole add stays at
    three (ficha + chapters + the cover the preview already paid for)."""
    cache_dir = tmp_path / "covers"
    write_preview(cache_dir, "https://host/cover.webp", IMAGE)

    result, client = _confirm(conn, cache_dir)

    assert result.cover_cached is True
    assert client.cover_calls == []  # promoted, never re-fetched
    promoted = find_cached(cache_dir, result.manga_id)
    assert promoted is not None and promoted.read_bytes() == IMAGE
    assert not preview_cache_path(cache_dir, "https://host/cover.webp").exists()


def test_confirm_fetches_the_cover_when_no_preview_file_exists(conn, tmp_path):
    result, client = _confirm(conn, tmp_path / "covers")

    assert result.cover_cached is True
    assert client.cover_calls == ["https://host/cover.webp"]


def test_confirm_zero_chapters_is_a_successful_add_with_null_latest(conn, tmp_path):
    result, _ = _confirm(conn, tmp_path / "covers", chapters=[])

    assert result.chapters_found == 0
    manga_site = conn.execute(
        "SELECT latest_chapter_num FROM manga_sites WHERE manga_id = ?", (result.manga_id,)
    ).fetchone()
    assert manga_site[0] is None
    assert conn.execute("SELECT COUNT(*) FROM bookmarks").fetchone()[0] == 1  # still added


@pytest.mark.parametrize("error", [NotFound("gone"), Transient("timeout"), Unexpected("shape")])
def test_confirm_cover_fetch_failure_leaves_the_add_standing(conn, tmp_path, error):
    cache_dir = tmp_path / "covers"

    result, client = _confirm(conn, cache_dir, cover_error=error)

    assert result.cover_cached is False
    assert conn.execute("SELECT COUNT(*) FROM bookmarks").fetchone()[0] == 1  # add still succeeded
    assert find_cached(cache_dir, result.manga_id) is None


@pytest.mark.parametrize("error", [NotFound("gone"), Transient("timeout"), Unexpected("shape")])
def test_confirm_chapters_failure_leaves_zero_rows(conn, tmp_path, error):
    with pytest.raises(type(error)):
        _confirm(conn, tmp_path / "covers", chapters_error=error)

    assert _counts(conn) == (0, 0, 0, 0)


def test_confirm_gate_1_rejects_and_writes_zero_rows(conn, tmp_path):
    _tracked(conn, "Some Manga", "reading", slug="some-manga")
    before = _counts(conn)

    with pytest.raises(AlreadyTracked) as excinfo:
        _confirm(conn, tmp_path / "covers")

    assert (excinfo.value.title, excinfo.value.status) == ("Some Manga", "reading")
    assert _counts(conn) == before


def test_confirm_terminal_gate_carries_the_raw_terminal_status(conn, tmp_path):
    _tracked(conn, "Some Manga", "dropped", slug="some-manga")

    with pytest.raises(AlreadyTracked) as excinfo:
        _confirm(conn, tmp_path / "covers")

    assert excinfo.value.status == "dropped"


def test_confirm_a_concurrent_race_becomes_alreadytracked_not_a_500(conn, tmp_path, monkeypatch):
    """The unique index (idx_manga_sites_site_source_key) is the last line of
    defence (design D3): a race the pre-checks missed must surface as a clean
    409, not an unhandled IntegrityError."""
    import manga_tracker.intake.pasted_url as pasted_url_module

    real_find_slug_owner = pasted_url_module.find_slug_owner
    calls = {"n": 0}

    def racing_find_slug_owner(conn, site_id, slug):
        # First call (the pre-check) sees nothing; by the time write_manual_add
        # runs, a concurrent add has already committed the same slug.
        calls["n"] += 1
        if calls["n"] == 1:
            _tracked(conn, "Winner Of The Race", "reading", slug=slug)
            return None
        return real_find_slug_owner(conn, site_id, slug)

    monkeypatch.setattr(pasted_url_module, "find_slug_owner", racing_find_slug_owner)

    with pytest.raises(AlreadyTracked) as excinfo:
        _confirm(conn, tmp_path / "covers")

    assert excinfo.value.title == "Winner Of The Race"
    # Only the racing winner's rows exist — the loser wrote nothing.
    assert conn.execute("SELECT COUNT(*) FROM mangas").fetchone()[0] == 1


# ================================================================================
# the request budget of one whole add
# ================================================================================


def test_the_whole_add_costs_exactly_three_source_requests(conn, tmp_path):
    """The number the interactive traffic class is priced against.

    Preview resolves the ficha (1), the modal asks for the cover image (2),
    confirm reads the chapters (3) and promotes the already-fetched preview
    file instead of downloading it again. Three, not four — and not two, which
    would mean the modal is showing a placeholder where a cover exists.

    Asserted as one sequence per operation rather than as a total, so a fourth
    request is not only counted but attributed.
    """
    cache_dir = tmp_path / "covers"
    client = FakeClient()
    intake = PastedUrlIntake(client, SITE_ID, cache_dir=cache_dir)
    url = "https://www.manganato.gg/manga/some-manga"

    preview = intake.preview(conn, url)
    intake.preview_cover(preview.cover_url)
    result = intake.confirm(
        conn,
        url=preview.url,
        title=preview.title,
        cover_url=preview.cover_url,
        status="reading",
        last_chapter_read=0.0,
        now=NOW,
    )

    assert client.details_calls == ["some-manga"]
    assert client.chapters_calls == ["some-manga"]
    assert client.cover_calls == [COVER_URL]
    assert result.cover_cached is True
