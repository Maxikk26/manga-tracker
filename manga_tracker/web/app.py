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
from typing import Annotated

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

from manga_tracker.intake.contracts import (
    AlreadyTracked,
    InvalidUrl,
    MangaIntake,
    NotFound,
    Transient,
    Unexpected,
)
from manga_tracker.storage.cover_cache import cache_dir_for, find_cached, media_type_for
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

# A Python mirror of the five Spanish status labels frontend/src/domain/
# statusLabels.ts:7 already holds (design D2). Needed because a duplicate or
# terminal add's `detail` string (spec.md "Duplicate active slug is rejected,
# naming the owner") must name the state in Spanish for a reader who only has
# `detail` — a curl caller, a log line — and that string is composed here,
# not in `intake` (D2: no Spanish, no HTTP outside `web`). statusLabels.ts
# says "nothing else translates statuses"; this mirror breaks that claim
# rather than hiding it, so the drift is pinned executably by
# tests/web/test_status_labels_parity.py, which parses the TS file as text
# and asserts the two maps are equal. The set can only grow through a
# bookmarks.status CHECK migration, so five entries is a hard ceiling.
STATUS_LABELS = {
    "reading": "Leyendo",
    "want_to_read": "Por leer",
    "completed": "Completado",
    "on_hold": "En pausa",
    "dropped": "Abandonado",
}

# The two statuses a bookmark cannot resume out of by itself — reactivation is
# a PATCH, never a second add (spec.md "Existing terminal title is rejected;
# reactivation is a PATCH"). Computed here, server-side, so a 409's `existing.
# terminal` is a fact the frontend reads rather than a rule it re-derives.
TERMINAL_STATUSES = frozenset({"completed", "dropped"})


class MangaPreviewRequest(BaseModel):
    """Body of POST /api/mangas/preview: just the pasted URL."""

    model_config = ConfigDict(extra="forbid")

    url: str


class MangaAddRequest(BaseModel):
    """Body of POST /api/mangas: the preview's echoed `url`/`title`/
    `cover_url` (design D4 — the slug is re-derived server-side, never
    trusted from the client) plus the owner's chosen status and initial
    chapter."""

    model_config = ConfigDict(extra="forbid")

    url: str
    # min_length=1 alone accepts "   " - strip_whitespace runs first, so a
    # whitespace-only title also fails the length check. This closes the
    # write path (spec's "empty or whitespace-only title is unwritable"):
    # confirm() trusts the title preview() echoed and never re-fetches it, so
    # a title lost to a details failure or any other cause cannot reach
    # `mangas`. strip_whitespace is also a real write-path change, not a
    # side effect to gloss over: the stored title is now trimmed, matching
    # the `TRIM(title)` production audit.
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    cover_url: str | None = None
    status: BookmarkStatus
    last_chapter_read: float = Field(default=0.0, ge=0)


def _conflict_response(exc: AlreadyTracked) -> JSONResponse:
    """The one body with a sibling key (design's Error Taxonomy): `detail` is
    self-sufficient — it names the title, the Spanish state and, for a
    terminal row, the reactivation instruction — and `existing` additionally
    buys the modal a "Ver en «…»" button."""
    label = STATUS_LABELS[exc.status]
    terminal = exc.status in TERMINAL_STATUSES
    detail = f"«{exc.title}» ya está en tu lista, con estado {label}."
    if terminal:
        detail += (
            f" Para retomarlo, cámbiale el estado desde su pestaña «{label}»; "
            "no hace falta agregarlo de nuevo."
        )
    return JSONResponse(
        status_code=409,
        content={"detail": detail, "existing": {"title": exc.title, "status": exc.status, "terminal": terminal}},
    )


def _source_error(exc: Exception) -> HTTPException:
    """The rest of the Error Taxonomy: each failure class distinct, Spanish,
    naming the next action (no `Retry-After`, no server-side retry — owner
    decision 4 puts the retry in the owner's hands)."""
    if isinstance(exc, InvalidUrl):
        return HTTPException(
            status_code=422,
            detail="La URL no es de una ficha de la fuente. Pega el enlace que contiene /manga/…",
        )
    if isinstance(exc, NotFound):
        return HTTPException(
            status_code=404, detail="La fuente no tiene ningún manga con ese enlace. Revisa la URL."
        )
    if isinstance(exc, Transient):
        return HTTPException(
            status_code=503, detail="La fuente no respondió. Espera un momento y vuelve a intentar."
        )
    if isinstance(exc, Unexpected):
        return HTTPException(
            status_code=502,
            detail="La fuente respondió algo inesperado; probablemente cambió. Revisa los logs.",
        )
    raise exc  # exhaustive by construction — a new intake failure class needs a case above first


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


def create_app(db_path: str, intake: MangaIntake, frontend_dist: Path | None = None) -> FastAPI:
    """Build the panel app against one database path.

    `intake` is the only thing this module holds instead of a `SourceClient`
    (design D1): the add flow's slug/ficha/chapters sequencing lives entirely
    behind it, never in this file. `frontend_dist` exists for tests;
    production always means the checked-in build location.
    """
    dist = FRONTEND_DIST if frontend_dist is None else frontend_dist
    cache_dir = cache_dir_for(db_path)
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

    @app.get("/api/covers/{manga_id}")
    def get_cover(manga_id: int) -> FileResponse:
        """Serve a cached cover image.

        The panel serves these itself instead of pointing an <img src> at the
        stored `cover_url`, and that is not a preference: the source's image
        hosts answer 403 to a request that does not carry their own Referer, so
        a hotlinked cover renders broken. Serving locally also means opening the
        panel costs a third party nothing, and a cover survives the remote
        rotating or deleting the file.

        404 when the image was never cached. That is an ordinary state, not an
        error — a manga can be listed long before `cache-covers` reaches it —
        so the frontend is expected to have a fallback rather than to assume
        this always answers.
        """
        path = find_cached(cache_dir, manga_id)
        if path is None:
            raise HTTPException(status_code=404, detail=f"No cached cover for manga {manga_id}")
        # A cover changes only when someone re-caches it deliberately, and the
        # grid asks for every visible one on each load. A day of freshness
        # costs nothing and takes ~18 requests per visit down to zero;
        # FileResponse still sends etag/last-modified, so a changed file is
        # picked up on the next revalidation rather than being pinned forever.
        return FileResponse(
            path,
            media_type=media_type_for(path),
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @app.get("/api/mangas/preview-cover")
    def preview_cover(url: str) -> Response:
        """Serve the cover of a preview that has no manga row — and so no
        /api/covers/{manga_id} — yet. Same hotlinking reality get_cover
        documents: the source's image hosts answer 403 without their own
        Referer, so the modal's <img> must point here, never at the CDN.
        The fetch is delegated to `intake` (the Referer knowledge lives in
        the source client); 404 when it declines the URL or the source did
        not deliver — the modal falls back to its placeholder, an ordinary
        state, never a 500."""
        result = intake.preview_cover(url)
        if result is None:
            raise HTTPException(status_code=404, detail=f"No preview cover available for {url!r}")
        image, media_type = result
        # Modest on purpose: an hour outlives any open modal without pinning
        # a third-party URL's bytes the way the by-id covers route may.
        return Response(
            content=image,
            media_type=media_type,
            headers={"Cache-Control": "public, max-age=3600"},
        )

    @app.post("/api/mangas/preview")
    def preview_manga(body: MangaPreviewRequest):
        """No write (spec.md "Preview validates without writing"). All
        slug/ficha sequencing happens inside `intake`, never here (spec.md
        "web never reaches the source, directly or by sequencing it itself")."""
        conn = connect(db_path)
        try:
            preview = intake.preview(conn, body.url)
        except AlreadyTracked as exc:
            return _conflict_response(exc)
        except (InvalidUrl, NotFound, Transient, Unexpected) as exc:
            raise _source_error(exc)
        finally:
            conn.close()
        return {
            "slug": preview.slug,
            "url": preview.url,
            "title": preview.title,
            "cover_url": preview.cover_url,
            "publication_status_text": preview.publication_status_text,
        }

    @app.post("/api/mangas", status_code=201)
    def add_manga(body: MangaAddRequest):
        """Writes (spec.md "Confirm is atomic; any rejection leaves zero
        rows"). `status`/`cover_url` are unwrapped to raw values here — the
        only place in this call that touches pydantic — before crossing into
        `intake`, which knows nothing about request bodies."""
        conn = connect(db_path)
        try:
            result = intake.confirm(
                conn,
                url=body.url,
                title=body.title,
                cover_url=body.cover_url,
                status=body.status.value,
                last_chapter_read=body.last_chapter_read,
                now=_utc_now(),
            )
        except AlreadyTracked as exc:
            return _conflict_response(exc)
        except (InvalidUrl, NotFound, Transient, Unexpected) as exc:
            raise _source_error(exc)
        else:
            return get_panel_bookmark(conn, result.bookmark_id)
        finally:
            conn.close()

    if dist.is_dir():
        app.mount("/", _SPAStaticFiles(directory=dist, html=True), name="frontend")
    return app
