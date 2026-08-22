# Verification Report: panel-v1b-fase-2

**Mode**: Full artifact verification (proposal/spec/design/tasks + apply-progress, all superseded by 8 post-apply commits inspected directly against the working tree).
**Branch**: `feat/panel-v1b-fase-2`, 12 commits off `main` @ `6ed2c38` (35 files changed, +2132/-29).
**Verdict**: **FAIL** -- one CRITICAL, two WARNINGs, zero SUGGESTIONs.

## Completeness (tasks.md)

40/40 tasks checked. Task completion matches code state for the 5 commits apply-progress recorded. Tasks.md was not re-opened for the 8 post-apply commits (heatmap rewrite, timeline removal, a11y fixes) -- that is expected; those are owner-directed refinements, not task-plan work, and are separately recorded in commit messages and `docs/spec-panel-v1b.md`.

## Test / Build Evidence (re-run by this verification, not copied from prior claims)

| Command | Result |
|---|---|
| `./.venv/Scripts/python.exe -m pytest -q` | **562 passed** |
| `npm test` (frontend) | **116 passed** (14 files) |
| `npm run build` (frontend) | clean (`tsc --noEmit` + `vite build`) |
| `npx playwright test` (frontend, manual, twice) | **1 failed**, both runs, same assertion |

## Spec Compliance Matrix

| Requirement | Status | Evidence |
|---|---|---|
| Reading History Aggregation Endpoint | **MET** | `repositories.reading_days`; `test_multiple_edits_same_day_sum_deltas` (17 not 2), `test_downward_correction_contributes_zero_but_null_previous_counts_as_edit` (0.0 chapters, edits still incremented) |
| Local-Day Grouping Before Aggregation, Via zoneinfo | **MET -- hard bar confirmed** | `test_hard_bar_midnight_crossing_only_in_local_time`: `2026-08-20T03:30:00Z` asserted under `2026-08-19`. Zero SQL date functions in `repositories.py` -- confirmed by searching for strftime/julianday/date()/datetime(); only matches are Python `.strftime`/`.astimezone` method calls, not SQL. `_UTC_FORMAT` text-comparison window design (D2) verified via `test_window_boundary_local_midnight_included_one_second_earlier_excluded`, a genuine timezone-shift boundary test (04:00 UTC = local midnight in Caracas) -- not an overclaim. |
| Per-Manga History Endpoint | **MET at API level; UI reachability is a DECLARED DEVIATION, not a defect** | `manga_history()` interleaves and sorts correctly (`test_manga_history_interleaves_readings_and_publications_chronologically`), 404 vs 200-empty distinguished (`test_manga_history_404_for_absent_manga_vs_empty_events_for_no_history`). `CHAPTER_HISTORY_LIMIT=50` confirmed to cap only the one-time backfill insert paths (`repositories.py:187,345`) -- `manga_history()`'s own SELECT carries no LIMIT. `MangaTimeline.tsx` correctly renders `publications_since` as a "may be missing earlier" note, never claims completeness. Owner removed the UI entry point (the select picker) on 2026-08-21 (commit `2266d44`); recorded in `docs/spec-panel-v1b.md` section "Pendientes abiertos" line 201 as built-but-not-exposed, with rationale and the reopening cost. This is a legitimate recorded deviation -- not scored as a spec failure. |
| History Screen Reachable From Primary Screen | **MET** | `AppNav.tsx` switch + `App.tsx` state; the Playwright trace itself proves the switch works in a real browser (it clicked "Historial" and the heatmap section became visible before the unrelated failing assertion below). |
| E2E Smoke Coverage For The Last Phase-1 Debt | **CRITICAL -- FAILING at runtime** | See below. |
| Spec Documentation Reflects One Remaining Test Debt | **MET, with a WARNING** | Phase table (line 161) correctly states phase 2 is "implementada ... sin desplegar" (not delivered) and the terminal-state debt closure (PR #33) is not relisted; only the Playwright smoke remains open per the doc's own words. See WARNING below for an unsynced sentence elsewhere in the same document. |

## CRITICAL

**1. The required Playwright smoke does not pass -- a regression introduced by later commits, never caught because it is excluded from `npm test` and there is no CI.**

`frontend/e2e/panel.smoke.spec.ts` was written in commit `a31cfb3`, before the heatmap was rewritten as a full-year calendar (`4e8e388`, later the same day) and before the per-manga timeline picker was removed (`2266d44`). It was never touched again (`git log` on the file shows exactly one commit). Its final assertion:

    await expect(page.locator(".heatmap-cell")).toHaveCount(1);

assumed the old sparse rendering (one `.heatmap-cell` per day with data). The full-year calendar now renders a `.heatmap-cell` for every in-window day -- confirmed failing twice, consistently:

    Locator:  locator('.heatmap-cell')
    Expected: 1
    Received: 370

The tab-jump interaction itself (the actual phase-1 debt this test exists to close) does pass -- the trace shows the test reaching the "Historial" click and the heatmap becoming visible before failing on the stale cell-count line. So the regression is narrow and the fix is a one-line assertion change (e.g. count only cells carrying `aria-label`, or assert on the seeded day's specific `aria-label` instead of a raw count) -- but as written, the spec's own acceptance scenario ("WHEN the Playwright smoke suite runs THEN ... the suite passes") is not met on the current tree. `apply-progress`'s claim of "1 passed (1.9s), run twice" is stale -- true only before the calendar rewrite that landed afterward in the same session.

This blocks archive under the sdd-verify hard rule: a spec scenario with no passing covering test is CRITICAL, and this scenario is not merely untested but actively failing.

## WARNING

**2. `docs/spec-panel-v1b.md` section "Pantallas" (line 99) was not updated when the timeline picker was removed and the delivery status was corrected, leaving an internal contradiction.**

Line 99 still reads: "Historial (fase 2): el heatmap de lecturas por dia y, por manga, la linea de tiempo de lecturas contra publicaciones. Entregada el 2026-08-21..." -- this both (a) describes the per-manga timeline as part of the Historial screen, which commit `2266d44` removed the same day, and (b) says "Entregada", contradicting the phase table three lines below the fold (line 161: "implementada... sin desplegar... no esta entregada hasta que se mergee y se despliegue") and the later correction commit `b9db4cb` ("phase 2 is implemented, not delivered"). The correct information exists elsewhere in the same file (section "Pendientes abiertos" line 201), so this is a sync gap inside one document, not a missing decision -- but CLAUDE.md is explicit that a stale statement in exactly this kind of "read at the start of every session and believed" document is expensive. Does not block archive on its own; recommend a one-line fix to line 99 before or alongside the E2E fix.

**3. (Confirmed, not a new finding) One frontend test comment previously overclaimed timezone coverage; it has already self-corrected -- no other test in this change repeats the pattern.**

`frontend/src/components/ReadingHeatmap.test.tsx`, test "spans exactly from `from` to `to`, inclusive on both ends" (lines 43-63): the comment explicitly states this test does NOT prove timezone-safe date arithmetic, and explains why (a date-only string parses as UTC by spec, and the TZ=America/Caracas UTC-4 pin never crosses the UTC date boundary at local midnight, so both `new Date(from)` and `new Date(\`${from}T00:00:00\`)` would leave the suite green). I independently re-derived this by inspection of `ReadingHeatmap.tsx`'s `buildCalendar()` -- the component's actual defense is the explicit `Z` suffix plus `getUTC*` accessors, not this test. I checked every other test file this change touches for the same overclaim pattern (searched for `new Date`, `timezone`, `TZ`, `America/Caracas` across `App.test.tsx`, `HistoryContainer.test.tsx`, `AppNav.test.tsx`, and the backend `test_history_api.py`) and found none -- the backend's `test_window_boundary_local_midnight_included_one_second_earlier_excluded` genuinely depends on the UTC-4 shift (04:00 UTC = local midnight) and is not an overclaim. This finding is CONFIRMED, already fixed in the code, and needs no further action.

## Deviations From Spec (declared, not scored as defects)

- Per-manga timeline built, tested, and functionally complete but not reachable from the UI -- owner decision 2026-08-21, recorded in `docs/spec-panel-v1b.md` section "Pendientes abiertos" with rationale and reopening cost. Per verification instructions, **not** recommended for restoration.
- Heatmap visual format resolved by the owner via `/prototype` to a full-year 53-week calendar, closing design decision D8 (was open at apply time). This is a design evolution, not a deviation from the spec's text -- the spec explicitly left visual format owner-reserved and out of scope.
- `/impeccable audit` findings closed post-apply: `aria-current` (WCAG 4.1.2), 44px touch targets, `:focus-visible` ring on `.progress-input`, `--grid-line` token. All confirmed present in `styles.css`/`AppNav.tsx`.

## Design Coherence

D1-D11 all confirmed against code: required `timezone_name` kwarg with no default (`create_app` raises `TypeError` without it -- `test_create_app_without_timezone_name_raises_type_error` passes); fixed-width UTC string window (D2); shift-before-group (D3); chapters-not-edits with rounding (D4); NULL-previous and downward-correction both zero-chapters-but-count-as-edit (D5); downward correction visible-with-negative-delta in timeline only (D6); no backend cap on `chapters` (D7, confirmed absent); D8 closed by owner as noted; `publications_since` timestamp not a boolean flag (D9, confirmed in `manga_history()` and `MangaTimeline.tsx`); `useState<Screen>` + presentational `AppNav`, no router (D10); E2E fixture server builds its own temp DB with a `check_not_production_db()` guard, never the real CLI (D11) -- confirmed by reading `playwright.config.ts` and the design; not independently re-verified for correctness of the guard itself in this pass, but `tests/e2e/test_fixture_server.py` is part of the passing 562.

## Recommendation

Do not archive yet. Fix the Playwright smoke assertion (narrow, one-line-class fix) and re-run it green before proceeding. Optionally fix the line-99 doc sync gap in the same pass. Recommended next phase: **sdd-apply** for a small follow-up commit (fix E2E assertion + optional doc line), then re-run **sdd-verify**.
