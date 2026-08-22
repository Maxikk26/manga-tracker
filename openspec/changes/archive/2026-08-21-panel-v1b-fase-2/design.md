# Design: Panel V1b Phase 2 — Reading History and Heatmap

## Technical Approach

Two read-only GET routes in `manga_tracker/web/app.py`, each delegating to a new function in `manga_tracker/storage/repositories.py` that owns both the SQL and the Python-side shaping — the precedent is `_panel_bookmark_row`, which already derives `behind` inside the repository. Local-day grouping runs in Python via `zoneinfo` over `config.timezone_name`, threaded into `create_app` as a required keyword argument. The frontend gains its first real second screen through a top-level state switch in `App.tsx`. The two owner-reserved visual decisions are isolated behind named seams so backend and navigation land without them.

## Architecture Decisions

| # | Choice | Rejected | Rationale |
|---|---|---|---|
| D1 | `create_app(db_path, intake, frontend_dist=None, *, timezone_name)` — required kwarg, no default; `_cmd_panel` passes `config.timezone_name` | A `"America/Caracas"` default; reading config inside `web` | A default is either a third hardcoded zone or a silent UTC fallback — the exact bug this phase exists to prevent. Composition root already builds everything (`cli.py:322`). Cost: 4 test call sites. |
| D2 | Trailing window filtered as `read_at >= ?` against a fixed-width `%Y-%m-%dT%H:%M:%SZ` string, computed in Python from local midnight of `today - (days-1)` | `strftime`/`julianday`/date modifiers | Zero SQL date functions exist in `repositories.py`; the production SQLite build's function set is untrusted. Text comparison is exact at fixed width and uses the `read_at` index. |
| D3 | Grouping key is `read_at` parsed → `.astimezone(ZoneInfo(timezone_name))` → `.date()`, applied **before** grouping | Grouping UTC days and shifting after | `spec-panel-v1b.md` §Decisiones de plataforma: shift before grouping or a 23:00 reading lands on the wrong day. |
| D4 | Intensity = **chapters read** = `SUM(chapter_num - previous_chapter_num)`, rounded to 2 decimals | Counting edit events | Owner decision. Rounding mirrors `behind` — chapter numbers are REAL and IEEE subtraction produced `21.200000000000003` in phase 1. |
| D5 | Rows with `previous_chapter_num IS NULL` contribute `0` to `chapters` but do count in `edits` | Treating NULL as `0.0` | A bookmark whose progress was unknown and became 175 is bookkeeping, not a 175-chapter day. |
| D6 | Downward corrections (`chapter_num <= previous_chapter_num`) are excluded from the heatmap in SQL, but remain **visible** in the per-manga timeline with a negative `delta` | Filtering them everywhere | The heatmap measures reading; the timeline is history, and hiding a correction there would misrepresent it. |
| D7 | **No backend cap** on a day's `chapters`; the payload carries the exact value | Clamping server-side | The bucket scale is an owner-reserved visual decision and top-bucket saturation already absorbs a 175-chapter outlier. The exact number stays available on hover — the `.behind-pill` `title` precedent. **Flagged for owner** below. |
| D8 | Sparse payload: only days with activity | Dense 365-entry array | The empty-cell grid shape is a visual decision; a sparse list does not prejudge weeks-vs-months. |
| D9 | Timeline returns `publications_since` (min `detected_at`, null when none) | A constant-`true` `is_partial` flag | `CHAPTER_HISTORY_LIMIT=50` caps only the one-time backfill, so completeness is bounded by *when the mapping was learned*. A timestamp states that; a flag that is always true carries no information. |
| D10 | Navigation: `useState<Screen>` in `App.tsx` + presentational `AppNav({active, onSelect})` | A router; another modal | No routing library installed; `StatusTabs` is the same shape. A modal is an interruption, not a destination (`spec-panel-v1b.md` §Pantallas). `_SPAStaticFiles` already serves the SPA fallback, so a router stays possible later without a backend change. |
| D11 | E2E fixture server: `tests/e2e/fixture_server.py` builds a **temp** SQLite DB with a stub intake and serves it on a fixed port via Playwright `webServer` | `manga_tracker.cli panel` | The CLI resolves the real configured DB path; an E2E harness must never be able to reach production data. The stub intake also makes the 409 "Ver en «…»" path deterministic and network-free. |

## Data Flow

    GET /api/history/reading?days=365
      app.py: validate days, _utc_now() ──→ repositories.reading_days(conn, days, tz, now)
                                              │ SQL: read_at >= <utc-string>
                                              │      AND chapter_num > previous_chapter_num
                                              └─→ Python: ZoneInfo shift → group by local date → sum deltas
                                                                                   │
                                            sparse [{date, chapters, edits}] ←──────┘

    GET /api/mangas/{id}/history
      repositories.manga_history ─→ readings (reading_history)  ─┐
                                  └─ publications (chapter_history, COALESCE(source_published_at, detected_at))
                                                                 └─→ merge + sort desc on fixed-width UTC text

## File Changes

| File | Action | Description |
|---|---|---|
| `manga_tracker/web/app.py` | Modify | Two GET routes; `timezone_name` kwarg on `create_app`; `days` bounded `ge=1, le=3650` |
| `manga_tracker/cli.py` | Modify | Pass `config.timezone_name` at line 322 |
| `manga_tracker/storage/repositories.py` | Modify | `reading_days()`, `manga_history()` in a new `# --- history family` block |
| `frontend/src/App.tsx` | Modify | Screen state + switch |
| `frontend/src/components/AppNav.tsx` | Create | Presentational nav, Spanish labels («Lista», «Historial») |
| `frontend/src/containers/HistoryContainer.tsx` | Create | Owns both fetches, load/error states |
| `frontend/src/components/ReadingHeatmap.tsx`, `MangaTimeline.tsx` | Create | Presentational; Spanish copy and aria-labels |
| `frontend/src/domain/heatmapBuckets.ts` | Create | **Seam #1** — provisional level function, replaced wholesale by the owner's `/prototype` output |
| `frontend/src/styles.css` | Modify | Heatmap/timeline/nav classes. **Seam #2** — `.behind-pill` tone/size is deferred and needs no JSX change |
| `frontend/src/api/history.ts`, `domain/types.ts` | Create/Modify | Fetchers following `bookmarks.ts` (`ApiError` + `readDetail`); wire types |
| `frontend/playwright.config.ts`, `frontend/e2e/panel.smoke.spec.ts`, `package.json` | Create/Modify | `@playwright/test`, chromium only, `test:e2e` script kept **out** of `npm test` |
| `tests/e2e/fixture_server.py` | Create | Temp-DB + stub-intake server for D11 |
| `tests/web/test_history_api.py` | Create | Endpoint tests |
| `docs/spec-panel-v1b.md` | Modify | One remaining test debt, not two; v1.5 + changelog |
| `docs/runbook-desarrollo-local.md` | Modify | How and when to run the smoke |

## Interfaces / Contracts

```jsonc
// GET /api/history/reading?days=365
{ "timezone": "America/Caracas", "from": "2025-08-22", "to": "2026-08-21",
  "days": [ { "date": "2026-08-19", "chapters": 12.5, "edits": 3 } ] }  // sparse

// GET /api/mangas/{id}/history  — 404 when the manga row is absent;
// 200 with "events": [] when it exists but has none.
{ "manga_id": 7, "title": "…", "publications_since": "2026-01-04T10:00:00Z",
  "events": [
    { "kind": "reading", "at": "2026-08-19T03:30:00Z", "chapter_num": 12.0,
      "previous_chapter_num": 11.0, "delta": 1.0, "origin": "panel" },
    { "kind": "publication", "at": "2026-08-18T22:00:00Z", "chapter_num": 13.0,
      "chapter_url": "…", "source_published_at": null, "detected_via": "feed" }
  ] }
```

`reading_days(conn, *, days: int, timezone_name: str, now: str)` — `now` is passed in from `_utc_now()`, matching `update_panel_bookmark`, so the window is deterministic in tests without freezing a clock.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Backend | **Hard bar**: `read_at = "…T03:30:00Z"` groups on the *previous* Caracas date | `TestClient` + real temp-file SQLite, trigger live |
| Backend | Downward correction absent from `chapters`; NULL `previous_chapter_num` yields `chapters: 0`, `edits: 1` | Drive rows through PATCH so the trigger writes them |
| Backend | Window boundary: a reading at local midnight of day `days-1` is in, one second earlier is out | Fixed `now` argument |
| Backend | Timeline interleave order; correction visible with negative delta; 404 vs empty `events` | Same fixture |
| Backend | `create_app` without `timezone_name` is a `TypeError` | Direct call |
| Frontend | Container load/error; heatmap renders one cell per active day with the right local date and chapter count in its accessible label | Vitest + RTL under the `TZ: "America/Caracas"` pin (`vite.config.ts:28`) |
| Frontend | Nav switches screens and the list screen is unaffected | RTL on `App` |
| Frontend | **Not tested by design**: bucket boundaries, colours, `.behind-pill` tone | So the owner's visual pass changes one file and zero tests |
| E2E | Smoke: load panel → 409 "Ver en «…»" tab jump → nav to Historial → heatmap present | Playwright chromium against `tests/e2e/fixture_server.py`; `npm run build` first |

**How the smoke actually gets run.** Nothing gates it: no `.github/workflows/` exists and this phase does not invent CI. It is a documented manual step in `docs/runbook-desarrollo-local.md`, run before a phase deploy. It stays out of `npm test` so a failed browser download never blocks the ordinary loop. Verify `npx playwright install chromium` succeeds before the smoke's assertions are committed — that is a network risk, not an implementation one. **This is a recorded process gap, accepted, not closed here.**

## Threat Matrix

| Boundary | Applicability | Design response |
|---|---|---|
| Documentation-like paths | N/A — no file classification or execution of repo content |  |
| Git repository selection | N/A — no VCS invocation |  |
| Commit state | N/A |  |
| Push state | N/A |  |
| PR commands | N/A |  |
| Subprocess (added row) | **Applicable** — Playwright `webServer` spawns a server process | D11: temp DB only, stub intake, no network, fixed non-production port. RED test: the fixture server refuses to start against a path equal to the configured production DB. |

## Migration / Rollout

No schema migration; `user_version` unchanged. Both routes are read-only, so rollback is reverting the routes and their repository functions with no data to undo. Work units, each revertible alone: (1) backend endpoints + tests, (2) nav primitive + History screen, (3) Playwright smoke + fixture server, (4) `docs/` correction. Delivery is `single-pr` with `size:exception` pre-accepted.

## Open Questions

- [ ] **Owner — outlier treatment.** D7 leaves a 0→175 correction as an exact 175-chapter day, absorbed by top-bucket saturation. Alternative if that reads wrong on screen: cap a *single event's* delta at a stated threshold, or split `chapters` into `chapters` + `chapters_from_large_jumps`. Not chosen here.
- [ ] **Owner-reserved (visual, plug into seam #1/#2)**: heatmap buckets, colours, weeks vs months; `.behind-pill` tone and size; any `cadence_days_estimate` consumer.
- [ ] Should the History screen's per-manga timeline be reachable from a card on the list screen, or only from a picker inside Historial? The spec is silent; the state-switch design supports either.
