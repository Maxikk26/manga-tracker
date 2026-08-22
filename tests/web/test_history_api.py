"""`GET /api/history/reading` and `GET /api/mangas/{id}/history`
(spec-panel-v1b.md fase 2), driven through FastAPI's `TestClient` against a
real temp-file SQLite — `reading_history_capture_progress` fires for real,
same discipline as `test_panel_api.py`.

The local-day date-math edge cases (the hard bar, the window boundary,
correction exclusion) call `repositories.reading_days` directly with an
explicit `now` — exactly the point of that parameter (design: "`now` is
passed in from `_utc_now()` ... deterministic in tests without freezing a
clock"). The HTTP layer is exercised separately for the endpoint's own
contract: defaults, bounds, and JSON shape.

The trigger always stamps `strftime('now')`, so a controlled instant for a
row is set with one direct UPDATE right after the PATCH that drove the
trigger for real — the row exists because of the trigger, only its
timestamp is corrected afterward so the test is not tied to wall-clock time.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from manga_tracker.storage.db import connect
from manga_tracker.storage.repositories import reading_days
from manga_tracker.web.app import create_app

NOW = "2026-08-17T12:00:00Z"
TZ = "America/Caracas"


@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "history.db")


class _UnusedIntake:
    """This suite never touches /api/mangas/preview or /api/mangas; a real
    `MangaIntake` needs a `SourceClient` this file has no business
    constructing."""

    def preview(self, conn, url):
        raise NotImplementedError

    def confirm(self, conn, **kwargs):
        raise NotImplementedError


@pytest.fixture()
def client(db_path, tmp_path):
    return TestClient(
        create_app(db_path, _UnusedIntake(), frontend_dist=tmp_path / "no-dist", timezone_name=TZ)
    )


def _site(conn) -> int:
    site_id = conn.execute(
        "INSERT INTO sites (name, base_url, created_at, updated_at) VALUES (?, ?, ?, ?)",
        ("manganato", "https://www.manganato.gg", NOW, NOW),
    ).lastrowid
    conn.commit()
    return site_id


def _bookmark(conn, site_id, title, *, last_chapter_read=None):
    """One manga + mapping + bookmark, returning (manga_id, bookmark_id)."""
    manga_id = conn.execute(
        "INSERT INTO mangas (title, created_at, updated_at) VALUES (?, ?, ?)", (title, NOW, NOW)
    ).lastrowid
    slug = title.lower().replace(" ", "-")
    conn.execute(
        "INSERT INTO manga_sites (manga_id, site_id, source_key, url, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (manga_id, site_id, slug, f"https://www.manganato.gg/manga/{slug}", NOW, NOW),
    )
    bookmark_id = conn.execute(
        "INSERT INTO bookmarks (manga_id, status, last_chapter_read, progress_is_approx, origin, "
        "created_at, updated_at) VALUES (?, 'reading', ?, 0, 'seed', ?, ?)",
        (manga_id, last_chapter_read, NOW, NOW),
    ).lastrowid
    conn.commit()
    return manga_id, bookmark_id


def _edit(client, bookmark_id, last_chapter_read):
    """Drives `reading_history_capture_progress` for real via one PATCH."""
    response = client.patch(f"/api/bookmarks/{bookmark_id}", json={"last_chapter_read": last_chapter_read})
    assert response.status_code == 200
    return response


def _set_read_at(conn, manga_id, chapter_num, read_at):
    conn.execute(
        "UPDATE reading_history SET read_at = ? WHERE manga_id = ? AND chapter_num = ?",
        (read_at, manga_id, chapter_num),
    )
    conn.commit()


def _day(result, local_date):
    return next(entry for entry in result["days"] if entry["date"] == local_date)


# --- GET /api/history/reading — local-day math (direct repository calls) -------


def test_hard_bar_midnight_crossing_only_in_local_time(client, db_path):
    """`2026-08-20T03:30:00Z` is `23:30` on `2026-08-19` in Caracas (UTC-4);
    it MUST group under `2026-08-19`, never `2026-08-20`."""
    conn = connect(db_path)
    manga_id, bookmark_id = _bookmark(conn, _site(conn), "One Piece", last_chapter_read=10.0)
    _edit(client, bookmark_id, 12)
    _set_read_at(conn, manga_id, 12.0, "2026-08-20T03:30:00Z")

    result = reading_days(conn, days=3650, timezone_name=TZ, now="2026-08-21T00:00:00Z")

    dates = {entry["date"] for entry in result["days"]}
    assert "2026-08-19" in dates
    assert "2026-08-20" not in dates
    assert _day(result, "2026-08-19")["chapters"] == 2.0


def test_downward_correction_contributes_zero_but_null_previous_counts_as_edit(client, db_path):
    conn = connect(db_path)
    site_id = _site(conn)
    manga_a, bookmark_a = _bookmark(conn, site_id, "Berserk", last_chapter_read=50.0)
    _edit(client, bookmark_a, 45)  # downward correction: 50 -> 45
    _set_read_at(conn, manga_a, 45.0, "2026-08-19T12:00:00Z")

    manga_b, bookmark_b = _bookmark(conn, site_id, "Vagabond", last_chapter_read=None)
    _edit(client, bookmark_b, 175)  # previous_chapter_num IS NULL
    _set_read_at(conn, manga_b, 175.0, "2026-08-19T13:00:00Z")

    result = reading_days(conn, days=3650, timezone_name=TZ, now="2026-08-21T00:00:00Z")

    entry = _day(result, "2026-08-19")
    assert entry["chapters"] == 0.0
    assert entry["edits"] == 2


def test_window_boundary_local_midnight_included_one_second_earlier_excluded(client, db_path):
    conn = connect(db_path)
    site_id = _site(conn)
    manga_in, bookmark_in = _bookmark(conn, site_id, "Included", last_chapter_read=10.0)
    _edit(client, bookmark_in, 11)
    _set_read_at(conn, manga_in, 11.0, "2026-08-19T04:00:00Z")  # local midnight of day (days-1)

    manga_out, bookmark_out = _bookmark(conn, site_id, "Excluded", last_chapter_read=10.0)
    _edit(client, bookmark_out, 11)
    _set_read_at(conn, manga_out, 11.0, "2026-08-19T03:59:59Z")  # one second earlier

    # now = local midnight of 2026-08-21 -> window of 3 days starts local
    # midnight of 2026-08-19.
    result = reading_days(conn, days=3, timezone_name=TZ, now="2026-08-21T04:00:00Z")

    entry = _day(result, "2026-08-19")
    assert entry["chapters"] == 1.0
    assert entry["edits"] == 1


def test_multiple_edits_same_day_sum_deltas(client, db_path):
    conn = connect(db_path)
    site_id = _site(conn)
    manga_a, bookmark_a = _bookmark(conn, site_id, "A", last_chapter_read=175.0)
    _edit(client, bookmark_a, 190)
    _set_read_at(conn, manga_a, 190.0, "2026-08-19T15:00:00Z")

    manga_b, bookmark_b = _bookmark(conn, site_id, "B", last_chapter_read=40.0)
    _edit(client, bookmark_b, 42)
    _set_read_at(conn, manga_b, 42.0, "2026-08-19T16:00:00Z")

    result = reading_days(conn, days=3650, timezone_name=TZ, now="2026-08-21T00:00:00Z")

    entry = _day(result, "2026-08-19")
    assert entry["chapters"] == 17.0  # (190-175) + (42-40), not 2 edits
    assert entry["edits"] == 2


def test_default_window_via_http_is_trailing_not_calendar_year(client):
    """Default `days` is 365 trailing days ending today, not since Jan 1."""
    body = client.get("/api/history/reading").json()

    to_date = date.fromisoformat(body["to"])
    from_date = date.fromisoformat(body["from"])
    assert (to_date - from_date).days == 364  # 365-day span, inclusive of both ends
    assert body["timezone"] == TZ


# --- GET /api/history/reading — HTTP contract -----------------------------------


def test_days_param_is_bounded(client):
    assert client.get("/api/history/reading?days=0").status_code == 422
    assert client.get("/api/history/reading?days=3651").status_code == 422
    assert client.get("/api/history/reading?days=1").status_code == 200


def test_reading_history_response_shape(client, db_path):
    conn = connect(db_path)
    manga_id, bookmark_id = _bookmark(conn, _site(conn), "One Piece", last_chapter_read=10.0)
    _edit(client, bookmark_id, 11)

    body = client.get("/api/history/reading?days=3650").json()

    assert set(body) == {"timezone", "from", "to", "days"}
    assert len(body["days"]) == 1
    assert set(body["days"][0]) == {"date", "chapters", "edits"}


# --- GET /api/mangas/{id}/history ------------------------------------------------


def test_manga_history_interleaves_readings_and_publications_chronologically(client, db_path):
    conn = connect(db_path)
    site_id = _site(conn)
    manga_id, bookmark_id = _bookmark(conn, site_id, "One Piece", last_chapter_read=10.0)
    manga_site_id = conn.execute(
        "SELECT id FROM manga_sites WHERE manga_id = ?", (manga_id,)
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO chapter_history (manga_site_id, chapter_num, chapter_url, source_published_at, "
        "detected_at, detected_via) VALUES (?, ?, ?, ?, ?, 'feed')",
        (manga_site_id, 11.0, "https://www.manganato.gg/manga/one-piece/chapter-11", None,
         "2026-08-18T22:00:00Z"),
    )
    conn.commit()

    _edit(client, bookmark_id, 11)
    _set_read_at(conn, manga_id, 11.0, "2026-08-19T03:30:00Z")
    _edit(client, bookmark_id, 9)  # a correction, visible here with a negative delta
    _set_read_at(conn, manga_id, 9.0, "2026-08-20T00:00:00Z")

    body = client.get(f"/api/mangas/{manga_id}/history").json()

    ats = [event["at"] for event in body["events"]]
    assert ats == sorted(ats, reverse=True)  # chronological, newest first
    kinds = {event["kind"] for event in body["events"]}
    assert kinds == {"reading", "publication"}
    correction = next(e for e in body["events"] if e["kind"] == "reading" and e["chapter_num"] == 9.0)
    assert correction["delta"] == -2.0  # excluded from the heatmap, still visible here
    assert body["publications_since"] == "2026-08-18T22:00:00Z"
    assert body["title"] == "One Piece"


def test_manga_history_404_for_absent_manga_vs_empty_events_for_no_history(client, db_path):
    conn = connect(db_path)
    manga_id, _bookmark_id = _bookmark(conn, _site(conn), "No History Yet")

    empty = client.get(f"/api/mangas/{manga_id}/history")
    assert empty.status_code == 200
    assert empty.json()["events"] == []

    absent = client.get("/api/mangas/999999/history")
    assert absent.status_code == 404


# --- create_app's required timezone_name -----------------------------------------


def test_create_app_without_timezone_name_raises_type_error(db_path, tmp_path):
    with pytest.raises(TypeError):
        create_app(db_path, _UnusedIntake(), frontend_dist=tmp_path / "no-dist")
