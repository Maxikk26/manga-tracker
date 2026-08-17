"""FastAPI app factory for the V1b panel, fase 1 (docs/spec-panel-v1b.md).

No SQL lives here: every query is a repository function in
`storage/repositories.py`, and this module never learns what the source's
HTML looks like or how a Telegram message is sent — that is the directional
rule `web -> storage` and nothing else.

Connection discipline mirrors the jobs': one sqlite3 connection per request,
opened through `storage.db.connect`, which sets `busy_timeout` — required
here because the panel and the scheduler are separate processes sharing the
database file, so a write colliding with a sweep must wait, not fail.
"""

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

from manga_tracker.storage.db import connect
from manga_tracker.storage.repositories import (
    BOOKMARK_STATUSES,
    UNSET,
    get_panel_bookmark,
    list_panel_bookmarks,
    update_panel_bookmark,
)

# repo root / frontend / dist — produced by the frontend build. The API must
# work when it does not exist (a checkout that never ran `npm run build`).
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

# Built from the storage tuple so the two cannot drift. Typing a query or body
# field with it makes FastAPI answer 422 to any value outside the enum.
BookmarkStatus = Enum("BookmarkStatus", {status: status for status in BOOKMARK_STATUSES}, type=str)


class BookmarkPatch(BaseModel):
    """Body of PATCH /api/bookmarks/{id}: progress and/or status, at least one.

    Both fields are optional but neither may be null when present: NULLing
    progress back out is not a panel operation, and "absent" is expressed by
    omitting the key. `model_fields_set` is what tells the two apart.
    """

    model_config = ConfigDict(extra="forbid")

    last_chapter_read: float | None = Field(default=None, ge=0)
    status: BookmarkStatus | None = None

    @model_validator(mode="after")
    def _check_presence(self) -> "BookmarkPatch":
        if not self.model_fields_set:
            raise ValueError("the body must carry last_chapter_read and/or status")
        if "last_chapter_read" in self.model_fields_set and self.last_chapter_read is None:
            raise ValueError("last_chapter_read cannot be null; omit it to leave progress alone")
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("status cannot be null; omit it to leave the status alone")
        return self


class _SPAStaticFiles(StaticFiles):
    """`frontend/dist` with the SPA fallback: a path that matches no file
    serves index.html, so a client-side route survives a refresh. /api never
    lands here — API routes are registered before the mount and win."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def create_app(db_path: str, frontend_dist: Path | None = None) -> FastAPI:
    """Build the panel app against one database path. `frontend_dist` exists
    for tests; production always means the checked-in build location."""
    dist = FRONTEND_DIST if frontend_dist is None else frontend_dist
    app = FastAPI(title="manga-tracker panel")

    @app.get("/api/bookmarks")
    def list_bookmarks(status: BookmarkStatus | None = None) -> list[dict]:
        conn = connect(db_path)
        try:
            return list_panel_bookmarks(conn, status=status.value if status is not None else None)
        finally:
            conn.close()

    @app.patch("/api/bookmarks/{bookmark_id}")
    def patch_bookmark(bookmark_id: int, patch: BookmarkPatch) -> dict:
        fields = patch.model_fields_set
        conn = connect(db_path)
        try:
            found = update_panel_bookmark(
                conn,
                bookmark_id,
                last_chapter_read=patch.last_chapter_read if "last_chapter_read" in fields else UNSET,
                status=patch.status.value if "status" in fields else UNSET,
                now=_utc_now(),
            )
            if not found:
                raise HTTPException(status_code=404, detail=f"No bookmark with id {bookmark_id}")
            return get_panel_bookmark(conn, bookmark_id)
        finally:
            conn.close()

    if dist.is_dir():
        app.mount("/", _SPAStaticFiles(directory=dist, html=True), name="frontend")
    return app
