"""Temp-DB, stub-intake HTTP server for the Playwright smoke (design D11,
spec-panel-v1b.md fase 2's Playwright debt).

This is never `manga_tracker.cli panel` pointed at a temp file: it builds
its OWN app over a temporary SQLite database with a network-free
`StubIntake`, on a fixed non-production port. An E2E harness must never be
able to reach production data or the real source over the network —
`check_not_production_db` is the one guard that keeps that true even if a
caller tries to point this at a real path.

Run directly (used by `frontend/playwright.config.ts`'s `webServer`):

    python -m tests.e2e.fixture_server [db_path]
"""

import sys
import tempfile
from pathlib import Path

import uvicorn

from manga_tracker.config import load_config
from manga_tracker.intake.contracts import AddPreview, AddResult, AlreadyTracked
from manga_tracker.storage.db import connect
from manga_tracker.web.app import create_app

FIXTURE_HOST = "127.0.0.1"
FIXTURE_PORT = 8765

# The smoke pastes this URL to trigger the 409 "Ver en «…»" tab jump
# deterministically — no real source, no seeded add-flow race.
DUPLICATE_URL = "https://www.manganato.gg/manga/duplicate-fixture"
DUPLICATE_TITLE = "Duplicate Fixture"
DUPLICATE_STATUS = "dropped"  # terminal: also exercises the reactivation sentence

# A title the smoke can find already tracked, with a real reading_history row
# so the History screen it navigates to afterward has a heatmap cell.
SEEDED_TITLE = "One Piece"

NOW = "2026-08-21T12:00:00Z"


class StubIntake:
    """Deterministic, network-free `MangaIntake` (design D11): `preview()`
    always answers with the one canned duplicate, so the smoke's add-flow
    409 needs no real source and no timing-dependent seed."""

    def preview(self, conn, url: str) -> AddPreview:
        raise AlreadyTracked(DUPLICATE_TITLE, DUPLICATE_STATUS)

    def preview_cover(self, cover_url: str) -> tuple[bytes, str] | None:
        return None

    def confirm(self, conn, **kwargs) -> AddResult:
        raise NotImplementedError("the smoke never reaches confirm()")


def check_not_production_db(db_path: str) -> None:
    """Refuses a path equal to the configured production DB (design D11's
    threat-matrix response to the Playwright `webServer` spawning a real
    subprocess): an E2E harness must never be able to reach production
    data."""
    production_db_path = load_config().db_path
    if Path(db_path).resolve() == Path(production_db_path).resolve():
        raise RuntimeError(
            f"refusing to start the E2E fixture server against the production DB path {db_path!r}"
        )


def _seed(conn) -> None:
    """One duplicate-tracked bookmark (terminal, for the 409 sentence) plus
    one seeded, read bookmark with a real reading_history row so the History
    screen has something to show."""
    site_id = conn.execute(
        "INSERT INTO sites (name, base_url, created_at, updated_at) VALUES (?, ?, ?, ?)",
        ("manganato", "https://www.manganato.gg", NOW, NOW),
    ).lastrowid

    manga_id = conn.execute(
        "INSERT INTO mangas (title, created_at, updated_at) VALUES (?, ?, ?)",
        (SEEDED_TITLE, NOW, NOW),
    ).lastrowid
    conn.execute(
        "INSERT INTO manga_sites (manga_id, site_id, source_key, url, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (manga_id, site_id, "one-piece", "https://www.manganato.gg/manga/one-piece", NOW, NOW),
    )
    bookmark_id = conn.execute(
        "INSERT INTO bookmarks (manga_id, status, last_chapter_read, progress_is_approx, origin, "
        "created_at, updated_at) VALUES (?, 'reading', 10.0, 0, 'seed', ?, ?)",
        (manga_id, NOW, NOW),
    ).lastrowid
    # One real edit through the trigger, so reading_history is not empty —
    # the heatmap the smoke navigates to must have at least one cell.
    conn.execute(
        "UPDATE bookmarks SET last_chapter_read = 12.0, updated_at = ? WHERE id = ?",
        (NOW, bookmark_id),
    )
    conn.commit()


def build_app(db_path: str):
    check_not_production_db(db_path)
    conn = connect(db_path)  # bootstraps the schema
    _seed(conn)
    conn.close()
    return create_app(db_path, StubIntake(), timezone_name="America/Caracas")


def main(argv: list[str]) -> int:
    db_path = argv[0] if argv else str(Path(tempfile.mkdtemp()) / "fixture.db")
    app = build_app(db_path)
    uvicorn.run(app, host=FIXTURE_HOST, port=FIXTURE_PORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
