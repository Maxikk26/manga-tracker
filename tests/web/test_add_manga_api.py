"""POST /api/mangas/preview and POST /api/mangas: one case per row of
design.md's Error Taxonomy, driven through FastAPI's TestClient against a
real SQLite file. `intake` is a fake here — `PastedUrlIntake` has its own
suite in tests/intake/ — so this file proves only what `web` itself does:
request validation, exception-to-HTTP-response translation, and that it
never writes anything the injected `MangaIntake` did not."""

import pytest
from fastapi.testclient import TestClient

from manga_tracker.intake.contracts import (
    AddPreview,
    AddResult,
    AlreadyTracked,
    InvalidUrl,
    NotFound,
    Transient,
    Unexpected,
)
from manga_tracker.storage.db import connect
from manga_tracker.web.app import create_app

NOW = "2026-08-19T12:00:00Z"

BOOKMARK_KEYS = {
    "id", "manga_id", "title", "status", "last_chapter_read", "progress_is_approx",
    "manga_url", "latest_chapter_num", "latest_chapter_url", "latest_chapter_at", "behind",
    "last_read_at", "status_changed_at",
}

_PREVIEW = AddPreview(
    slug="some-manga", url="https://www.manganato.gg/manga/some-manga", title="Some Manga",
    cover_url="https://host/cover.webp", publication_status_text="Ongoing",
)


class FakeIntake:
    """Records every call; raises or returns whatever the test configures."""

    def __init__(
        self,
        *,
        preview_error=None,
        confirm_error=None,
        cover_cached=True,
        preview_cover_result=(b"cover-bytes", "image/webp"),
    ):
        self._preview_error = preview_error
        self._confirm_error = confirm_error
        self._cover_cached = cover_cached
        self._preview_cover_result = preview_cover_result
        self.preview_calls: list[str] = []
        self.confirm_calls: list[dict] = []
        self.preview_cover_calls: list[str] = []

    def preview(self, conn, url):
        self.preview_calls.append(url)
        if self._preview_error:
            raise self._preview_error
        return _PREVIEW

    def preview_cover(self, cover_url):
        self.preview_cover_calls.append(cover_url)
        return self._preview_cover_result

    def confirm(self, conn, **kwargs):
        self.confirm_calls.append(kwargs)
        if self._confirm_error:
            raise self._confirm_error
        manga_id = conn.execute(
            "INSERT INTO mangas (title, created_at, updated_at) VALUES (?, ?, ?)",
            (kwargs["title"], NOW, NOW),
        ).lastrowid
        bookmark_id = conn.execute(
            "INSERT INTO bookmarks (manga_id, status, last_chapter_read, progress_is_approx, origin, "
            "status_changed_at, created_at, updated_at) VALUES (?, ?, ?, 0, 'manual', ?, ?, ?)",
            (manga_id, kwargs["status"], kwargs["last_chapter_read"], NOW, NOW, NOW),
        ).lastrowid
        conn.commit()
        return AddResult(manga_id=manga_id, bookmark_id=bookmark_id, chapters_found=2, cover_cached=self._cover_cached)


@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "panel.db")


def _client(db_path, tmp_path, intake) -> TestClient:
    return TestClient(create_app(db_path, intake, frontend_dist=tmp_path / "no-dist"))


def _counts(db_path) -> tuple[int, int, int, int]:
    conn = connect(db_path)
    counts = (
        conn.execute("SELECT COUNT(*) FROM mangas").fetchone()[0],
        conn.execute("SELECT COUNT(*) FROM manga_sites").fetchone()[0],
        conn.execute("SELECT COUNT(*) FROM bookmarks").fetchone()[0],
        conn.execute("SELECT COUNT(*) FROM chapter_history").fetchone()[0],
    )
    conn.close()
    return counts


_ADD_BODY = {"url": "https://www.manganato.gg/manga/some-manga", "title": "Some Manga", "status": "reading"}


# --- preview -------------------------------------------------------------------


def test_preview_writes_nothing_and_returns_publication_status_text(db_path, tmp_path):
    intake = FakeIntake()
    client = _client(db_path, tmp_path, intake)

    response = client.post("/api/mangas/preview", json={"url": "https://www.manganato.gg/manga/some-manga"})

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Some Manga"
    assert body["publication_status_text"] == "Ongoing"
    assert body["cover_url"] == "https://host/cover.webp"
    assert intake.preview_calls == ["https://www.manganato.gg/manga/some-manga"]
    assert _counts(db_path) == (0, 0, 0, 0)


# --- preview-cover ---------------------------------------------------------------


def test_preview_cover_serves_the_bytes_with_media_type_and_a_modest_cache_header(db_path, tmp_path):
    """The modal's <img> points here, never at the CDN URL: the source's image
    hosts answer 403 to a hotlinked request, so `web` asks `intake` (which owns
    the fetch) and serves the bytes itself, like /api/covers/{id} does."""
    intake = FakeIntake()
    client = _client(db_path, tmp_path, intake)

    response = client.get("/api/mangas/preview-cover", params={"url": "https://host/cover.webp"})

    assert response.status_code == 200
    assert response.content == b"cover-bytes"
    assert response.headers["content-type"] == "image/webp"
    assert response.headers["cache-control"] == "public, max-age=3600"
    assert intake.preview_cover_calls == ["https://host/cover.webp"]


def test_preview_cover_none_from_intake_is_404_not_500(db_path, tmp_path):
    """None covers both the unacceptable URL and the source failure: a missing
    preview image is ordinary, and the modal's onError fallback handles it."""
    client = _client(db_path, tmp_path, FakeIntake(preview_cover_result=None))

    response = client.get("/api/mangas/preview-cover", params={"url": "http://host/cover.webp"})

    assert response.status_code == 404


# --- the taxonomy, one case per row ---------------------------------------------


def test_malformed_body_is_422(db_path, tmp_path):
    client = _client(db_path, tmp_path, FakeIntake())
    assert client.post("/api/mangas/preview", json={}).status_code == 422


def test_status_off_enum_is_422(db_path, tmp_path):
    client = _client(db_path, tmp_path, FakeIntake())
    body = {**_ADD_BODY, "status": "binged"}
    assert client.post("/api/mangas", json=body).status_code == 422


def test_negative_initial_chapter_is_422(db_path, tmp_path):
    client = _client(db_path, tmp_path, FakeIntake())
    body = {**_ADD_BODY, "last_chapter_read": -1}
    assert client.post("/api/mangas", json=body).status_code == 422


def test_invalid_url_is_422_with_the_taxonomy_message(db_path, tmp_path):
    client = _client(db_path, tmp_path, FakeIntake(preview_error=InvalidUrl("no slug")))

    response = client.post("/api/mangas/preview", json={"url": "https://www.manganato.gg/genre/action"})

    assert response.status_code == 422
    assert "URL" in response.json()["detail"]


def test_already_tracked_non_terminal_is_409_without_the_reactivation_sentence(db_path, tmp_path):
    client = _client(
        db_path, tmp_path, FakeIntake(confirm_error=AlreadyTracked(title="Some Manga", status="reading"))
    )

    response = client.post("/api/mangas", json=_ADD_BODY)

    assert response.status_code == 409
    body = response.json()
    assert "Some Manga" in body["detail"] and "Leyendo" in body["detail"]
    assert "retomarlo" not in body["detail"]
    assert body["existing"] == {"title": "Some Manga", "status": "reading", "terminal": False}
    assert _counts(db_path) == (0, 0, 0, 0)


@pytest.mark.parametrize("status", ["completed", "dropped"])
def test_already_tracked_terminal_is_409_naming_the_reactivation_path(db_path, tmp_path, status):
    client = _client(
        db_path, tmp_path, FakeIntake(confirm_error=AlreadyTracked(title="Some Manga", status=status))
    )

    response = client.post("/api/mangas", json=_ADD_BODY)

    assert response.status_code == 409
    body = response.json()
    assert "Some Manga" in body["detail"]
    assert "no hace falta agregarlo de nuevo" in body["detail"]
    assert body["existing"] == {"title": "Some Manga", "status": status, "terminal": True}
    assert _counts(db_path) == (0, 0, 0, 0)


def test_unknown_slug_is_404(db_path, tmp_path):
    client = _client(db_path, tmp_path, FakeIntake(preview_error=NotFound("gone")))

    response = client.post("/api/mangas/preview", json={"url": "https://www.manganato.gg/manga/gone"})

    assert response.status_code == 404


def test_transient_failure_is_503(db_path, tmp_path):
    client = _client(db_path, tmp_path, FakeIntake(confirm_error=Transient("timeout")))

    response = client.post("/api/mangas", json=_ADD_BODY)

    assert response.status_code == 503
    assert "vuelve a intentar" in response.json()["detail"]


def test_a_details_403_never_produces_a_200_preview_with_an_empty_title(db_path, tmp_path):
    """D2/D5: when the source responds 403 to a details fetch, the client
    raises Transient (not a 200 carrying an empty title), and the intake
    layer's Transient reaches this endpoint as 503, never 200."""
    client = _client(db_path, tmp_path, FakeIntake(preview_error=Transient("403 from source")))

    response = client.post("/api/mangas/preview", json={"url": "https://www.manganato.gg/manga/some-manga"})

    assert response.status_code == 503
    assert "vuelve a intentar" in response.json()["detail"]
    assert _counts(db_path) == (0, 0, 0, 0)


def test_unexpected_response_is_502(db_path, tmp_path):
    client = _client(db_path, tmp_path, FakeIntake(confirm_error=Unexpected("shape")))

    response = client.post("/api/mangas", json=_ADD_BODY)

    assert response.status_code == 502


def test_a_rejected_confirm_leaves_zero_rows_in_all_four_tables(db_path, tmp_path):
    client = _client(db_path, tmp_path, FakeIntake(confirm_error=Unexpected("shape")))
    connect(db_path).close()  # bootstrap the schema before counting
    before = _counts(db_path)

    client.post("/api/mangas", json=_ADD_BODY)

    assert _counts(db_path) == before == (0, 0, 0, 0)


# --- 201 --------------------------------------------------------------------------


def test_zero_chapters_and_uncached_cover_are_not_errors(db_path, tmp_path):
    """D5/D6: both are legal successful-add states, not failure classes."""
    client = _client(db_path, tmp_path, FakeIntake(cover_cached=False))

    response = client.post("/api/mangas", json=_ADD_BODY)

    assert response.status_code == 201  # cover_cached is not on the wire response; the add still succeeds


def test_201_returns_the_bookmark_keys_shape(db_path, tmp_path):
    client = _client(db_path, tmp_path, FakeIntake())

    response = client.post("/api/mangas", json=_ADD_BODY)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == BOOKMARK_KEYS
    assert body["title"] == "Some Manga"
    assert body["status"] == "reading"
    # `manga_url` is in the shape but not asserted by value here: FakeIntake
    # writes no manga_sites row, so any value check would be testing the stub.
    # The real write is pinned in tests/storage/test_write_manual_add.py and
    # the serialization in tests/web/test_panel_api.py.


def test_confirm_receives_the_raw_status_value_and_the_default_chapter(db_path, tmp_path):
    intake = FakeIntake()
    client = _client(db_path, tmp_path, intake)

    client.post("/api/mangas", json={"url": _ADD_BODY["url"], "title": _ADD_BODY["title"], "status": "reading"})

    call = intake.confirm_calls[0]
    assert call["status"] == "reading"
    assert call["last_chapter_read"] == 0.0
    assert call["cover_url"] is None


# --- empty title unwritable ------------------------------------------------------


def test_empty_title_is_422_and_writes_nothing(db_path, tmp_path):
    intake = FakeIntake()
    client = _client(db_path, tmp_path, intake)

    response = client.post("/api/mangas", json={**_ADD_BODY, "title": ""})

    assert response.status_code == 422
    assert intake.confirm_calls == []
    assert _counts(db_path) == (0, 0, 0, 0)


def test_whitespace_only_title_is_422_and_writes_nothing(db_path, tmp_path):
    """min_length=1 alone would accept this - it is not empty, only blank."""
    intake = FakeIntake()
    client = _client(db_path, tmp_path, intake)

    response = client.post("/api/mangas", json={**_ADD_BODY, "title": "   "})

    assert response.status_code == 422
    assert intake.confirm_calls == []
    assert _counts(db_path) == (0, 0, 0, 0)


def test_a_normal_title_still_validates_and_reaches_the_write_path(db_path, tmp_path):
    intake = FakeIntake()
    client = _client(db_path, tmp_path, intake)

    response = client.post("/api/mangas", json=_ADD_BODY)

    assert response.status_code == 201
    assert intake.confirm_calls[0]["title"] == "Some Manga"
