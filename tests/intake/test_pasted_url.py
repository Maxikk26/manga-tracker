"""`PastedUrlIntake`: the only `MangaIntake` implementation (design D1).
`preview()` here; `confirm()` follows in a later commit alongside the
transactional write and the cover fetch."""

import pytest

from manga_tracker.intake.contracts import AlreadyTracked, InvalidUrl
from manga_tracker.intake.pasted_url import PastedUrlIntake
from manga_tracker.sources.contracts import MangaDetails, NotFound, Transient, Unexpected
from manga_tracker.storage.db import connect

NOW = "2026-08-19T12:00:00Z"
SITE_ID = 1


class FakeClient:
    """A `SourceClient`-shaped fake — no request classes hit the wire.

    `extract_slug`/`build_manga_url` are the same pure functions the concrete
    `ManganatoClient` exposes as staticmethods, reused here rather than
    reimplemented so the fake's URL shape matches production exactly."""

    def __init__(self, *, details=None, details_error=None):
        from manga_tracker.sources.manganato.client import build_manga_url, extract_slug

        self.extract_slug = extract_slug
        self.build_manga_url = build_manga_url
        self._details = details or MangaDetails(
            title="Some Manga", cover_url="https://host/cover.webp",
            publication_status_text="Ongoing", last_updated_text=None,
        )
        self._details_error = details_error
        self.details_calls: list[str] = []

    def fetch_manga_details(self, slug):
        self.details_calls.append(slug)
        if self._details_error:
            raise self._details_error
        return self._details


@pytest.fixture()
def conn(tmp_path):
    connection = connect(str(tmp_path / "intake.db"))
    connection.execute(
        "INSERT INTO sites (id, name, base_url, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (SITE_ID, "manganato", "https://www.manganato.gg", NOW, NOW),
    )
    connection.commit()
    return connection


def _intake(**client_kwargs) -> PastedUrlIntake:
    return PastedUrlIntake(FakeClient(**client_kwargs), SITE_ID, cache_dir=None)


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
