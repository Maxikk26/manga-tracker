# Design: add a manga from the panel (`panel-v1b-fase-3`)

Contract: `docs/spec-panel-v1b.md` v1.1. Proposal: `proposal.md`. File map: `exploration.md` (trusted, not restated).
Owner product decisions of 2026-08-19 are authoritative and override the proposal's assumption table.

## Technical Approach

A new top-level package **`manga_tracker/intake/`** owns the add flow end to end. `web` gains two endpoints
that call it and translate its typed failures into Spanish HTTP errors; it never names a source module again.
The panel says *"agrega esto"* (PAN §36) because the sequencing — slug → ficha → duplicate gates → chapters
→ one transaction → cover — lives entirely outside `web`.

```
browser ── POST /api/mangas/preview ──► web/app.py ──► intake.preview(conn, url)
                                            │                 │ extract_slug (0 req)
                                            │                 │ duplicate gates (0 req)
                                            │                 └─ fetch_manga_details (1 req)
           POST /api/mangas ─────────────► web/app.py ──► intake.confirm(conn, ...)
                                            │                 │ gates again, in-transaction
                                            │                 │ fetch_chapters (1 req)
                                            │                 │ repo.write_manual_add  ← one transaction
                                            │                 └─ fetch_cover (1 req, failure tolerated)
                                            └── 201 get_panel_bookmark(conn, bookmark_id)
```

(Content truncated for archive — see the full design.md in the change folder)
