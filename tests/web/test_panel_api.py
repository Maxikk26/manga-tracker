"""The panel API, fase 1 (docs/spec-panel-v1b.md), driven through FastAPI's
TestClient against a real SQLite file — the same storage layer production
uses, `reading_history_capture_progress` trigger included. No sockets:
TestClient talks ASGI in-process.

The `origin='panel'` correction gets the most attention here because the
spec's stated mechanism is wrong: `last_insert_rowid()` REVERTS when a
trigger program ends (SQLite documented behavior, verified on 3.49), so an
implementation that trusted it would rewrite an unrelated row — or, worse,
correct a row when the trigger never fired. Both corruptions are pinned by
tests below."""

import pytest
from fastapi.testclient import TestClient

from manga_tracker.storage.db import connect
from manga_tracker.web.app import create_app

NOW = "2026-08-17T12:00:00Z"

BOOKMARK_KEYS = {
    "id", "manga_id", "title", "status", "last_chapter_read", "progress_is_approx",
    "latest_chapter_num", "latest_chapter_url", "latest_chapter_at", "behind", "last_read_at",
    "status_changed_at",
}


@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "panel.db")


@pytest.fixture()
def client(db_path, tmp_path):
    # An explicit nonexistent dist: the API must work without a frontend
    # build, and the real frontend/dist must not leak into these tests.
    return TestClient(create_app(db_path, frontend_dist=tmp_path / "no-dist"))


def _site(conn) -> int:
    site_id = conn.execute(
        "INSERT INTO sites (name, base_url, created_at, updated_at) VALUES (?, ?, ?, ?)",
        ("manganato", "https://www.manganato.gg", NOW, NOW),
    ).lastrowid
    conn.commit()
    return site_id


def _bookmark(
    conn, site_id, title, *, status="reading", last_chapter_read=None, progress_is_approx=0,
    latest_chapter_num=None, latest_chapter_url=None, latest_chapter_at=None, mapped=True,
):
    """One manga + mapping + bookmark, returning (manga_id, bookmark_id)."""
    manga_id = conn.execute(
        "INSERT INTO mangas (title, created_at, updated_at) VALUES (?, ?, ?)", (title, NOW, NOW)
    ).lastrowid
    if mapped:
        conn.execute(
            "INSERT INTO manga_sites (manga_id, site_id, source_key, latest_chapter_num, "
            "latest_chapter_url, latest_chapter_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (manga_id, site_id, title.lower().replace(" ", "-"), latest_chapter_num,
             latest_chapter_url, latest_chapter_at, NOW, NOW),
        )
    bookmark_id = conn.execute(
        "INSERT INTO bookmarks (manga_id, status, last_chapter_read, progress_is_approx, origin, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, 'seed', ?, ?)",
        (manga_id, status, last_chapter_read, progress_is_approx, NOW, NOW),
    ).lastrowid
    conn.commit()
    return manga_id, bookmark_id


def _history(conn, manga_id):
    return conn.execute(
        "SELECT chapter_num, previous_chapter_num, origin FROM reading_history "
        "WHERE manga_id = ? ORDER BY id", (manga_id,),
    ).fetchall()


# --- GET /api/bookmarks ---------------------------------------------------------


def test_list_returns_every_bookmark_with_manga_and_source_state(client, db_path):
    conn = connect(db_path)
    site_id = _site(conn)
    _bookmark(conn, site_id, "One Piece", last_chapter_read=1100.0, latest_chapter_num=1120.0,
              latest_chapter_url="https://www.manganato.gg/manga/one-piece/chapter-1120",
              latest_chapter_at="2026-08-15T10:00:00Z")
    _bookmark(conn, site_id, "Berserk", status="on_hold", last_chapter_read=364.0)

    response = client.get("/api/bookmarks")

    assert response.status_code == 200
    body = response.json()
    assert [item["title"] for item in body] == ["Berserk", "One Piece"]  # ordered by title
    one_piece = body[1]
    assert set(one_piece) == BOOKMARK_KEYS
    assert one_piece["status"] == "reading"
    assert one_piece["last_chapter_read"] == 1100.0
    assert one_piece["latest_chapter_num"] == 1120.0
    assert one_piece["latest_chapter_url"] == "https://www.manganato.gg/manga/one-piece/chapter-1120"
    assert one_piece["latest_chapter_at"] == "2026-08-15T10:00:00Z"
    assert one_piece["behind"] == 20.0
    assert one_piece["progress_is_approx"] is False


def test_behind_is_null_when_either_side_is_null_and_clamps_at_zero(client, db_path):
    conn = connect(db_path)
    site_id = _site(conn)
    # No progress recorded: behind is unknowable, not zero.
    _bookmark(conn, site_id, "A No Progress", latest_chapter_num=42.0)
    # No detection yet: same.
    _bookmark(conn, site_id, "B No Latest", last_chapter_read=10.0)
    # Reading ahead of what was detected (another source) clamps to 0, never negative.
    _bookmark(conn, site_id, "C Ahead", last_chapter_read=50.0, latest_chapter_num=48.0)

    body = client.get("/api/bookmarks").json()

    assert [item["behind"] for item in body] == [None, None, 0]


def test_list_includes_a_bookmark_whose_manga_has_no_source_mapping(client, db_path):
    """A pending Kitsu entry has a bookmark and no manga_sites row; the list
    must still show it, with the source-side columns as null."""
    conn = connect(db_path)
    site_id = _site(conn)
    _bookmark(conn, site_id, "Unmapped", last_chapter_read=3.0, mapped=False)

    body = client.get("/api/bookmarks").json()

    assert len(body) == 1
    assert body[0]["latest_chapter_num"] is None
    assert body[0]["latest_chapter_url"] is None
    assert body[0]["behind"] is None


def test_list_filters_by_status(client, db_path):
    conn = connect(db_path)
    site_id = _site(conn)
    _bookmark(conn, site_id, "Reading One")
    _bookmark(conn, site_id, "Dropped One", status="dropped")

    body = client.get("/api/bookmarks", params={"status": "dropped"}).json()

    assert [item["title"] for item in body] == ["Dropped One"]


def test_list_rejects_a_status_outside_the_enum(client):
    response = client.get("/api/bookmarks", params={"status": "binged"})
    assert response.status_code == 422


# --- PATCH /api/bookmarks/{id} ----------------------------------------------------


def test_patch_progress_captures_a_reading_event_with_origin_panel(client, db_path):
    conn = connect(db_path)
    manga_id, bookmark_id = _bookmark(conn, _site(conn), "One Piece", last_chapter_read=1100.0)

    response = client.patch(f"/api/bookmarks/{bookmark_id}", json={"last_chapter_read": 1105})

    assert response.status_code == 200
    assert response.json()["last_chapter_read"] == 1105.0
    assert _history(conn, manga_id) == [(1105.0, 1100.0, "panel")]


def test_patch_correction_targets_the_trigger_row_not_last_insert_rowid(client, db_path):
    """The spec prescribes `last_insert_rowid()` and SQLite disproves it: the
    value reverts when the trigger program ends. This pins the honest
    mechanism — with earlier captured rows in place, only the row this edit's
    trigger inserted flips to 'panel'; every prior row keeps its origin."""
    conn = connect(db_path)
    manga_id, bookmark_id = _bookmark(conn, _site(conn), "One Piece", last_chapter_read=10.0)
    # A direct SQLite edit: the trigger records it as 'manual' and it must stay so.
    conn.execute("UPDATE bookmarks SET last_chapter_read = 20 WHERE id = ?", (bookmark_id,))
    conn.commit()

    assert client.patch(f"/api/bookmarks/{bookmark_id}", json={"last_chapter_read": 30}).status_code == 200

    assert _history(conn, manga_id) == [(20.0, 10.0, "manual"), (30.0, 20.0, "panel")]


def test_patch_progress_makes_it_exact_and_seals_last_read_at(client, db_path):
    conn = connect(db_path)
    _, bookmark_id = _bookmark(conn, _site(conn), "Berserk", last_chapter_read=300.0, progress_is_approx=1)

    body = client.patch(f"/api/bookmarks/{bookmark_id}", json={"last_chapter_read": 364}).json()

    assert body["progress_is_approx"] is False
    assert body["last_read_at"] is not None
    row = conn.execute(
        "SELECT progress_is_approx, last_read_at, updated_at FROM bookmarks WHERE id = ?", (bookmark_id,)
    ).fetchone()
    assert row[0] == 0
    assert row[1] is not None and row[1].endswith("Z")  # UTC, sealed by the edit
    assert row[2] != NOW  # updated_at bumped like every other writer does


def test_patch_status_only_creates_no_event_and_rewrites_no_origin(client, db_path):
    """The trigger stays silent on a status-only UPDATE, so there is no
    freshly captured row to correct — and correcting anyway would rewrite
    whatever reading_history row happens to be the latest."""
    conn = connect(db_path)
    manga_id, bookmark_id = _bookmark(conn, _site(conn), "One Piece", last_chapter_read=10.0)
    conn.execute("UPDATE bookmarks SET last_chapter_read = 20 WHERE id = ?", (bookmark_id,))
    conn.commit()

    body = client.patch(f"/api/bookmarks/{bookmark_id}", json={"status": "on_hold"}).json()

    assert body["status"] == "on_hold"
    assert body["last_chapter_read"] == 20.0  # untouched
    assert _history(conn, manga_id) == [(20.0, 10.0, "manual")]  # still exactly one, still manual


def _status_changed_at(conn, bookmark_id):
    return conn.execute(
        "SELECT status_changed_at FROM bookmarks WHERE id = ?", (bookmark_id,)
    ).fetchone()[0]


def test_patch_status_stamps_status_changed_at(client, db_path):
    """The column exists so "En pausa" can be ordered by when a manga was
    actually paused. Nothing else in the schema can answer that question."""
    conn = connect(db_path)
    _, bookmark_id = _bookmark(conn, _site(conn), "One Piece")
    assert _status_changed_at(conn, bookmark_id) is None  # seeded rows know nothing

    body = client.patch(f"/api/bookmarks/{bookmark_id}", json={"status": "on_hold"}).json()

    assert body["status"] == "on_hold"
    stamped = _status_changed_at(conn, bookmark_id)
    assert stamped is not None
    assert stamped.endswith("Z"), "must match the fixed-width UTC format every writer emits"
    assert body["status_changed_at"] == stamped  # and it reaches the wire


def test_patch_resubmitting_the_same_status_does_not_move_the_date(client, db_path):
    """Re-picking the current value in the dropdown is not a transition. If it
    stamped anyway, "paused on" would decay into "last time the select was
    touched" — and the ordering it exists to feed would be noise."""
    conn = connect(db_path)
    _, bookmark_id = _bookmark(conn, _site(conn), "One Piece", status="on_hold")
    conn.execute(
        "UPDATE bookmarks SET status_changed_at = ? WHERE id = ?", ("2026-08-01T00:00:00Z", bookmark_id)
    )
    conn.commit()

    assert client.patch(f"/api/bookmarks/{bookmark_id}", json={"status": "on_hold"}).status_code == 200

    assert _status_changed_at(conn, bookmark_id) == "2026-08-01T00:00:00Z"


def test_patch_progress_alone_does_not_stamp_status_changed_at(client, db_path):
    """Reading a chapter is not a status change."""
    conn = connect(db_path)
    _, bookmark_id = _bookmark(conn, _site(conn), "One Piece", last_chapter_read=10.0)

    assert client.patch(f"/api/bookmarks/{bookmark_id}", json={"last_chapter_read": 11}).status_code == 200

    assert _status_changed_at(conn, bookmark_id) is None


def test_patch_with_the_unchanged_value_creates_no_event(client, db_path):
    """The trigger fires only when the value CHANGES; re-submitting the same
    number must not fabricate a reading event nor touch prior origins."""
    conn = connect(db_path)
    manga_id, bookmark_id = _bookmark(conn, _site(conn), "One Piece", last_chapter_read=10.0)
    conn.execute("UPDATE bookmarks SET last_chapter_read = 20 WHERE id = ?", (bookmark_id,))
    conn.commit()

    assert client.patch(f"/api/bookmarks/{bookmark_id}", json={"last_chapter_read": 20}).status_code == 200

    assert _history(conn, manga_id) == [(20.0, 10.0, "manual")]


def test_patch_accepts_a_downward_correction_and_records_it(client, db_path):
    conn = connect(db_path)
    manga_id, bookmark_id = _bookmark(conn, _site(conn), "One Piece", last_chapter_read=50.0)

    assert client.patch(f"/api/bookmarks/{bookmark_id}", json={"last_chapter_read": 40}).status_code == 200

    # previous_chapter_num greater than chapter_num: the consumer reads this
    # negative delta as a correction, not reading. Existing rule, not skirted.
    assert _history(conn, manga_id) == [(40.0, 50.0, "panel")]


def test_patch_progress_and_status_together(client, db_path):
    conn = connect(db_path)
    manga_id, bookmark_id = _bookmark(conn, _site(conn), "One Piece", last_chapter_read=10.0)

    body = client.patch(
        f"/api/bookmarks/{bookmark_id}", json={"last_chapter_read": 12, "status": "completed"}
    ).json()

    assert (body["last_chapter_read"], body["status"]) == (12.0, "completed")
    assert _history(conn, manga_id) == [(12.0, 10.0, "panel")]


def test_patch_unknown_bookmark_is_404(client, db_path):
    connect(db_path).close()  # bootstrap the schema; the table is just empty
    response = client.patch("/api/bookmarks/999", json={"last_chapter_read": 1})
    assert response.status_code == 404
    assert "999" in response.json()["detail"]


@pytest.mark.parametrize(
    "body",
    [
        {},  # nothing to do is not an edit
        {"last_chapter_read": -1},  # below zero
        {"last_chapter_read": "twelve"},  # not a number
        {"last_chapter_read": None},  # NULLing progress out is not a panel operation
        {"status": "binged"},  # outside the enum
        {"status": None},
        {"latest_chapter_num": 99},  # unknown field: the source columns are not editable
    ],
)
def test_patch_rejects_an_invalid_body_with_422(client, db_path, body):
    conn = connect(db_path)
    manga_id, bookmark_id = _bookmark(conn, _site(conn), "One Piece", last_chapter_read=10.0)

    assert client.patch(f"/api/bookmarks/{bookmark_id}", json=body).status_code == 422

    # Rejected means untouched: no write, no captured event.
    assert conn.execute("SELECT last_chapter_read FROM bookmarks WHERE id = ?", (bookmark_id,)).fetchone()[0] == 10.0
    assert _history(conn, manga_id) == []


# --- statics ----------------------------------------------------------------------


def test_the_api_works_without_a_frontend_build(client, db_path):
    connect(db_path).close()
    assert client.get("/api/bookmarks").status_code == 200
    assert client.get("/").status_code == 404  # nothing mounted, honest 404


def test_statics_serve_index_and_fall_back_to_it_for_client_routes(db_path, tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>panel</html>", encoding="utf-8")
    (dist / "app.js").write_text("console.log('panel')", encoding="utf-8")
    client = TestClient(create_app(db_path, frontend_dist=dist))

    assert "panel" in client.get("/").text
    assert client.get("/app.js").text == "console.log('panel')"
    # A client-side route resolves to index.html so a refresh survives ...
    assert "panel" in client.get("/some/spa/route").text
    # ... while the API keeps answering as itself under the same mount.
    assert client.get("/api/bookmarks").json() == []
