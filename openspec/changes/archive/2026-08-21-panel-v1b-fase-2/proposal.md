# Proposal: Panel V1b Phase 2 — Reading History and Heatmap

## Intent

Phase 2 is the last unstarted V1b phase (PAN §Fases). Phase 1 has been writing `reading_history` since 2026-08-18, and nothing reads it: the owner cannot see whether he read yesterday, or how a manga's readings track its publications. This phase adds the two read endpoints and the second screen that consume it, and closes the last phase-1 test debt (Playwright E2E smoke).

## Scope

### In Scope

- `GET /api/history/reading` — `reading_history` aggregated by **local** calendar day; `days` param, default 365.
- `GET /api/mangas/{id}/history` — per-manga readings interleaved with `chapter_history` publications.
- History screen: heatmap + per-manga timeline, reached by a second-screen switch.
- Playwright E2E smoke test (phase-1 debt; covers the untested "Ver en «…»" tab jump, PAN §Pendientes).
- Read-side exclusion of downward corrections (`chapter_num < previous_chapter_num`) from heatmap/volume counts.
- `docs/spec-panel-v1b.md` correction: phase 2 carries **one** test debt, not two (terminal-state regression closed in PR #33, `tests/web/test_panel_api.py:357`).

### Out of Scope

- Heatmap visual format (buckets, colours, weeks vs months) — owner-reserved, `/prototype` + `impeccable`.
- `cadence_days_estimate` consumer, covers for terminal states, URL routing, auth.
- `openspec/changes/failure-visibility/` (shipped, unarchived, separate).

## Capabilities

### New Capabilities
- `panel-reading-history`: the two read endpoints, local-day aggregation, correction exclusion, and the timeline's completeness contract.

### Modified Capabilities
- None. The "+N" pill tone/size is presentation-only and has no spec-level capability.

## Approach

| Decision | Choice | Why |
|---|---|---|
| Local-day grouping | Python `zoneinfo` over `LOCAL_TIMEZONE` (`config.py:92`) | Matches `scheduler.py` / `notifier/telegram.py`; zero `strftime`/`julianday` exist in `repositories.py`; the production SQLite build's function set is not trustworthy (`chr()` absent) |
| Navigation | Top-level `useState<'list'\|'history'>` in `App.tsx` | No router installed; matches `StatusTabs` and the Alta modal |
| SQL location | `repositories.py` only | `app.py` holds no SQL |
| Backend tests | `TestClient` + real temp-file SQLite | The trigger must fire for real |

Backend is shaped to land independently of the deferred visual decisions.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `manga_tracker/web/app.py` | Modified | Two GET routes |
| `manga_tracker/storage/repositories.py` | Modified | Aggregation + interleave queries, correction filter |
| `frontend/src/App.tsx` | Modified | Screen switch |
| `frontend/src/containers/`, `components/` | New | `HistoryContainer`, heatmap, timeline (Spanish UI copy) |
| `frontend/package.json` | Modified | Playwright devDependency + script |
| `tests/web/`, `frontend/src/**/*.test.tsx` | New | Endpoint + component tests |
| `docs/spec-panel-v1b.md` | Modified | Test-debt correction, v1.5 changelog |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Local-day off-by-one at 23:00 | High | Hard acceptance criterion below; test with `03:30:00Z` = `23:30` previous day in Caracas |
| Downward corrections counted as reading | High | Filter is read-side and exists nowhere today; explicit requirement, own test |
| Timeline read as complete history | Medium | `CHAPTER_HISTORY_LIMIT=50` caps backfill only; label the timeline as detected-since-mapping |
| Playwright browser download blocked | Medium | Verify `npx playwright install` before committing smoke assertions |
| No CI runs the smoke test | Certain | Record as a process gap; do not invent CI here |
| Blocked on deferred visuals | Medium | Backend + tests land first; visual layer after owner's `/prototype` |

## Rollback Plan

Backend: revert the two routes and their repository functions; nothing writes, so no data to undo. Frontend: revert the screen switch — the list screen is untouched. Playwright: remove the devDependency and script. Each is a separate work-unit commit on `feat/panel-v1b-fase-2`, revertible alone.

## Dependencies

- Phase 1 (delivered) supplies `reading_history` rows.
- `@playwright/test` devDependency + one-time browser download.

## Open Owner Decisions (gate the VISUAL layer only)

- Heatmap format: buckets, colours, weeks vs months (PAN §Pendientes).
- The "+N" pill's new tone/size — no design spec exists anywhere.
- Whether any "publishes every ~N days" display uses `cadence_days_estimate`.

Per the project rule, these are asked, not filled by our own judgment.

## Success Criteria

- [ ] **Hard bar**: a reading whose UTC `read_at` crosses midnight only in local time (`03:30:00Z`) is grouped on the Caracas calendar day, proven by a backend test.
- [ ] Downward corrections are absent from heatmap counts, proven by a test.
- [ ] Both endpoints return real phase-1 rows; heatmap renders them.
- [ ] Per-manga timeline interleaves readings and publications, without claiming completeness.
- [ ] Playwright smoke passes locally, covering the "Ver en «…»" tab jump.
- [ ] `uv run pytest -q` and `npm test` + `npm run build` green.
- [ ] `docs/spec-panel-v1b.md` states one remaining test debt, versioned with changelog.
