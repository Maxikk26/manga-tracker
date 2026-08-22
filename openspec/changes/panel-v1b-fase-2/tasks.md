# Tasks: Panel V1b Phase 2 — Reading History and Heatmap

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~750-950 (backend + frontend + Playwright + docs) |
| 400-line budget risk | High |
| Chained PRs recommended | No — owner waived the budget |
| Suggested split | Single PR, `size:exception` |
| Delivery strategy | single-pr |
| Chain strategy | size-exception |

Decision needed before apply: Yes
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Backend endpoints + repositories + `timezone_name` wiring | single PR (commit 1) | `./.venv/Scripts/python.exe -m pytest -q tests/web/test_history_api.py tests/test_cli.py tests/web/test_panel_api.py tests/web/test_add_manga_api.py tests/web/test_add_manga_wiring.py` | `manga_tracker.cli panel` boots and both routes return real data | revert `app.py` routes, `repositories.py` history block, `cli.py:322` kwarg |
| 2 | Frontend nav + History screen + seams | same PR (commit 2) | `npm test` in `frontend/` | Manual: switch to «Historial», heatmap renders | revert `App.tsx` switch, new components; list screen untouched |
| 3 | Playwright smoke + fixture server | same PR (commit 3) | `npx playwright test` (manual, not in `npm test`) | `npx playwright install chromium` then the smoke against `tests/e2e/fixture_server.py` | remove devDependency, script, fixture server |
| 4 | `docs/` correction | same PR (commit 4) | N/A — doc-only | N/A — doc-only | revert doc edits alone |

## Phase 1: Backend Foundation

- [x] 1.1 Add `reading_days(conn, *, days, timezone_name, now)` to `manga_tracker/storage/repositories.py` in a new `# --- history family` block: fixed-width UTC string window, `zoneinfo` shift, group-by-local-date, sum `chapter_num - previous_chapter_num`, exclude `chapter_num <= previous_chapter_num`, `previous_chapter_num IS NULL` → 0 chapters/1 edit, round to 2 decimals, sparse output.
- [x] 1.2 Add `manga_history(conn, manga_id)` to the same block: interleave `reading_history` + `chapter_history` (COALESCE `source_published_at`/`detected_at`), sort desc, `publications_since` = min `detected_at` or null, 404 contract via caller.
- [x] 1.3 Add `GET /api/history/reading` and `GET /api/mangas/{id}/history` to `manga_tracker/web/app.py`; `days` bounded `ge=1, le=3650`, default 365.
- [x] 1.4 Change `create_app` signature to `create_app(db_path, intake, frontend_dist=None, *, timezone_name)` — required kwarg, no default.
- [x] 1.5 Update `manga_tracker/cli.py:322` to `create_app(config.db_path, intake, timezone_name=config.timezone_name)`.

## Phase 2: Backend Test-Site Updates (blast radius of 1.4)

- [x] 2.1 Update `tests/web/test_panel_api.py:51` and `:426` `create_app(...)` calls to pass `timezone_name=`.
- [x] 2.2 Update `tests/web/test_add_manga_api.py:89` `create_app(...)` call to pass `timezone_name=`.
- [x] 2.3 Update `tests/web/test_add_manga_wiring.py:62` `create_app(...)` call to pass `timezone_name=`.
- [x] 2.4 Update `tests/test_cli.py:175` and `:211` — both monkeypatch `create_app` with `lambda db_path, intake: ...`; change each to `lambda db_path, intake, *, timezone_name: ...` so `cli.py:322`'s new kwarg does not raise `TypeError`.

## Phase 3: Backend Tests (RED before GREEN)

- [x] 3.1 RED: `tests/web/test_history_api.py` — hard-bar scenario: `read_at="2026-08-20T03:30:00Z"` groups under local date `2026-08-19` (Caracas), not `2026-08-20`. Drive the row through PATCH so the trigger writes it for real, temp-file SQLite.
- [x] 3.2 RED: same file — a 50→45 correction contributes zero to `chapters`; `previous_chapter_num IS NULL` yields `chapters: 0, edits: 1`.
- [x] 3.3 RED: window boundary — a reading at local midnight of day `days-1` is included, one second earlier is excluded, using the `now` argument (no real clock).
- [x] 3.4 RED: two edits same day sum deltas (175→190, 40→42 → 17), default window is trailing 365 days ending `now`, not since Jan 1.
- [x] 3.5 RED: `/api/mangas/{id}/history` — interleaved order, correction visible with negative `delta`, 404 for absent manga vs 200 + `events: []` for a manga with none.
- [x] 3.6 RED: `create_app(...)` without `timezone_name` raises `TypeError`.
- [x] 3.7 GREEN: confirm 1.1-1.5 satisfy 3.1-3.6; run full backend suite: `./.venv/Scripts/python.exe -m pytest -q`. **560/560 passed** (550 baseline + 10 new in `test_history_api.py`), stable across repeat runs.

## Phase 4: Frontend — Seams and Wiring

- [x] 4.1 Create `frontend/src/domain/heatmapBuckets.ts` (Seam #1, provisional bucket function, deliberately untested — owner's `/prototype` replaces it wholesale).
- [x] 4.2 Add `.behind-pill` tone/size hook in `frontend/src/styles.css` as a no-JSX-change seam (Seam #2), left at current values.
- [x] 4.3 Create `frontend/src/api/history.ts` fetchers (`ApiError` + `readDetail` pattern from `bookmarks.ts`); extend `frontend/src/domain/types.ts` with the two response shapes.
- [x] 4.4 Create `frontend/src/containers/HistoryContainer.tsx` (owns both fetches, load/error states).
- [x] 4.5 Create `frontend/src/components/ReadingHeatmap.tsx` and `MangaTimeline.tsx` — Spanish copy/aria-labels, accessible label states local date + chapter count per cell.
- [x] 4.6 Create `frontend/src/components/AppNav.tsx` — presentational, Spanish labels («Lista», «Historial»).
- [x] 4.7 Wire `useState<Screen>` + switch into `frontend/src/App.tsx`.

## Phase 5: Frontend Tests

- [x] 5.1 RTL: `HistoryContainer` load/error states.
- [x] 5.2 RTL: heatmap renders one cell per active day, accessible label carries the right local date under the `TZ: "America/Caracas"` pin (`vite.config.ts:28`).
- [x] 5.3 RTL: `AppNav`/`App` — switching to «Historial» and back leaves the list screen unaffected.
- [x] 5.4 N/A — `types.ts` additions (`ReadingHistoryDay`, `MangaHistoryEvent`, ...) are new interfaces, not new required fields on `Bookmark`; `sortBookmarks.test.ts`'s hand-built `Bookmark` literal is untouched and still matches the wire shape.
- [x] 5.5 `npm test`: 108/108 passed (103 baseline + 5 new: `ReadingHeatmap.test.tsx`, `HistoryContainer.test.tsx`, `App.test.tsx`). `npm run build`: green (`tsc --noEmit` + `vite build`).

## Phase 6: Playwright Smoke (Phase-1 Debt)

- [x] 6.1 Verify `npx playwright install chromium` succeeds on this machine BEFORE writing smoke assertions — record the result. **Succeeded**: Chrome for Testing 151.0.7922.34, FFmpeg, Chrome Headless Shell and Winldd all downloaded to `C:\Users\Maximiliano\AppData\Local\ms-playwright\` without error.
- [x] 6.2 Create `tests/e2e/fixture_server.py`: temp SQLite DB + stub intake, fixed non-production port; RED test that it refuses to start against a path equal to the configured production DB. `tests/e2e/test_fixture_server.py` — 2 tests, both passing (562/562 full backend suite).
- [x] 6.3 Add `@playwright/test` devDependency, `frontend/playwright.config.ts`, `test:e2e` script kept OUT of `npm test`. `vite.config.ts` also excludes `e2e/**` from vitest's own glob (it was picking the Playwright spec up and failing on its async `test.describe`).
- [x] 6.4 Write `frontend/e2e/panel.smoke.spec.ts`: load panel → trigger 409 duplicate/terminal add → "Ver en «…»" tab jump → nav to «Historial» → heatmap present.
- [x] 6.5 Run the smoke locally against `npm run build` output; record pass/fail. **PASSED**: `1 passed (1.9s)`, chromium, against `tests/e2e/fixture_server.py`'s stub intake and the built `frontend/dist`.

## Phase 7: Docs

- [x] 7.1 `docs/spec-panel-v1b.md` line ~161 (fases table): correct phase-2 row to state the Playwright smoke as the only remaining test debt; note the terminal-state regression closed in PR #33 (`e22309f`, `tests/web/test_panel_api.py:357`). Went further since phase 2 fully landed in this apply: row marked ✅ entregada, both endpoints marked delivered in §API, §Pantallas item 2 marked delivered, and the "Ver en «…»" pendiente closed.
- [x] 7.2 Add changelog entry v1.5 — 2026-08-21 documenting the two endpoints, local-day `zoneinfo` rule now implemented, downward-correction exclusion, the closed terminal-state debt, and remaining Playwright-only debt; bump the version header and any dependent pins. Version bumped 1.4 → 1.5; no dependent pins changed (same `one-pager-v1a.md`/`spec-modelo-de-datos.md`/`decision-arquitectura-v1b.md` versions apply).
- [x] 7.3 `docs/runbook-desarrollo-local.md`: document how and when to run the Playwright smoke (`npx playwright install chromium`, `npm run build`, `npx playwright test`), and that no CI runs it. New §Smoke E2E con Playwright section; version bumped 1.0 → 1.1; test counts corrected (108 frontend, 562 backend); pin to `spec-panel-v1b.md` bumped to v1.5.

## Phase 8: Final Verification

- [x] 8.1 Full backend suite: `./.venv/Scripts/python.exe -m pytest -q` green. **562/562 passed.**
- [x] 8.2 Frontend: `npm test` and `npm run build` green. **108/108 passed**; build (`tsc --noEmit` + `vite build`) green.
- [x] 8.3 Playwright smoke passes locally (manual run, recorded). **`1 passed (1.9s)`**, chromium, against `npm run build` output and `tests/e2e/fixture_server.py`.
- [x] 8.4 Break one guard on purpose (e.g. flip the hard-bar timestamp) and confirm it fails, per the owner's "siempre hacer testing" rule. **Done**: removed the `.astimezone(tz)` shift in `reading_days`'s grouping key — `test_hard_bar_midnight_crossing_only_in_local_time` failed exactly as expected (`AssertionError: assert '2026-08-19' in {'2026-08-20'}`), confirming the guard actually catches the bug class it exists for. Restored; full suite re-run green (562/562), `git status` clean.

## Owner-Reserved — Not Planned Here

Heatmap visual format (buckets, colours, weeks vs months) and `.behind-pill` tone/size — seams built in 4.1/4.2 only. Flagged, not resolved: 0→175 upward-correction outlier (no cap, D7), `previous_chapter_num IS NULL` counting as an edit with 0 chapters (D5). Open item, not blocking: whether the per-manga timeline is reachable from a list card or only from Historial.
