# Verification Report: panel-v1b-fase-2

**Mode**: Full artifact verification (spec/design/tasks; apply-progress #368 treated as stale per instructions, verified directly against the working tree instead).
**Branch**: `feat/panel-v1b-fase-2`, 16 commits off `main` @ `6ed2c38`.
**Pass**: SECOND (re-verify after remediation).
**Verdict**: **PASS WITH WARNINGS** -- zero CRITICAL, three WARNINGs, zero SUGGESTIONs.

## First-Pass Record (for continuity, not re-scored)

The first verification pass found one CRITICAL: `frontend/e2e/panel.smoke.spec.ts` asserted `toHaveCount(1)` on `.heatmap-cell`, written before the full-year calendar rewrite; it received 370 on the rewritten tree and failed twice, consistently. It also found two WARNINGs: a docs sync gap at `docs/spec-panel-v1b.md` line 99 (still said Entregada, still described the timeline as part of the screen, still called the heatmap format undecided), and a since-self-corrected test-comment overclaim (no action needed, already fixed before pass 1). Full detail in Engram observation 376.

## What This Pass Re-Verified (not assumed from the fix commit)

Both fixes landed in a single commit, `78aad69`. I did not take the commit message's claims at face value -- I re-ran every check independently.

- **Playwright**: ran `npx playwright test` from `frontend/` twice, independently, in this session. 1 passed both times (~2.0s each). Read the new assertion in `panel.smoke.spec.ts`: it now locates the seeded day via `.heatmap-cell[aria-label*='capitulos leidos']` (`toHaveCount(1)`) plus a bounded `expect(await page.locator(".heatmap-cell").count()).toBeGreaterThan(300)`. This is a real fix, not a relaxation to a tautology -- it still asserts a specific seeded day's presence by name, and the bound (>300) is deliberately not exact because the trailing window moves with the current date, which is documented inline in the test's own comment.
- **Doc sync (line 99)**: read `docs/spec-panel-v1b.md` line 99 directly. It now reads "Historial (fase 2): el heatmap de lecturas por dia. Implementada el 2026-08-21, sin desplegar" and correctly states the per-manga timeline "no es alcanzable desde la pantalla (ver Pendientes abiertos)" and that the heatmap format is no longer pending (closed via /prototype). This matches the phase table (line 161: "implementada... sin desplegar... no esta entregada hasta que se mergee y se despliegue") and Pendientes abiertos (line 201). The specific contradiction from pass 1 is gone.

## Test / Build Evidence (re-run by this pass, not copied)

| Command | Result |
|---|---|
| `./.venv/Scripts/python.exe -m pytest -q` | 562 passed |
| `npm test` (frontend) | 116 passed (14 files) |
| `npm run build` (frontend) | clean (tsc --noEmit + vite build) |
| `npx playwright test` (frontend, run twice) | 1 passed, 1 passed -- no flake observed |

No regression in backend/frontend counts since pass 1 (562/116, unchanged).

## Spec Compliance Matrix

| Requirement | Status | Evidence |
|---|---|---|
| Reading History Aggregation Endpoint | MET | `repositories.reading_days` sums only positive deltas; downward corrections (`chapter_num <= previous_chapter_num`) contribute 0 to `chapters` but still increment `edits`; covered by `test_multiple_edits_same_day_sum_deltas`, `test_downward_correction_contributes_zero_but_null_previous_counts_as_edit`. |
| Local-Day Grouping Before Aggregation, Via zoneinfo | MET -- hard bar re-confirmed | `test_hard_bar_midnight_crossing_only_in_local_time`: `_set_read_at(..., "2026-08-20T03:30:00Z")` then `reading_days(...)` asserts `"2026-08-19" in dates` and `"2026-08-20" not in dates`. Re-ran this test as part of the full suite (passing). Searched `manga_tracker/storage/repositories.py` for strftime/julianday/date(/datetime( -- the only matches are Python method calls (`.astimezone(...).strftime(_UTC_FORMAT)`, `.astimezone(tz).date()`), not SQL functions. Grouping key is computed via `ZoneInfo(timezone_name)` shift applied to the parsed UTC value before grouping (D3), confirmed in code. |
| Per-Manga History Endpoint | MET at API/component level; UI reachability is a DECLARED DEVIATION | `manga_history()` interleaves chronologically (`test_manga_history_interleaves_readings_and_publications_chronologically`), downward correction visible with negative delta in the timeline test fixture. `MangaTimeline.tsx` and the endpoint both exist and are tested. The owner removed the UI entry point (`2266d44`, 2026-08-21); recorded in `docs/spec-panel-v1b.md` Pendientes abiertos line 201 with rationale ("no le interesa verla") and reopening cost. Confirmed as a legitimate recorded deviation, not scored as a defect. Not recommending restoration, per instructions. |
| History Screen Reachable From Primary Screen | MET | `AppNav.tsx` + `App.tsx` switch; the Playwright trace itself proves it works end-to-end in a real browser -- the test clicks "Historial" and asserts the heatmap's aria-label becomes visible. |
| E2E Smoke Coverage For The Last Phase-1 Debt | MET -- was the pass-1 CRITICAL, now closed | See "What This Pass Re-Verified" above. Ran twice, passed twice. |
| Spec Documentation Reflects One Remaining Test Debt | MET | Line 161 states the smoke was the only remaining test debt and that it is now closed; the terminal-state debt (PR #33) is correctly not relisted. |

## New Findings This Pass

No new CRITICAL. Two new WARNING-level doc-staleness findings surfaced by the requested sweep of `docs/spec-panel-v1b.md` and `README.md` -- neither was caught by pass 1, and neither blocks archive on its own, but per CLAUDE.md's own standing rule ("a stale statement here is expensive -- it is read at the start of every session and believed"), both are worth a follow-up line-fix.

## WARNING

**1. `README.md` line 25 states phase 2 is "no empezada" (not started) -- flatly false on the current tree.**

The V1b phase table at line 25 reads: `Fase 2 -- historial y heatmap | no empezada`. Sixteen commits, two new endpoints, a full history screen, 562+116 passing tests and a green Playwright smoke later, "not started" is not merely stale but actively wrong -- line 184 of the same file is closer ("falta la fase 2", i.e. still missing/not deployed) but line 25's status marker was never touched when phase 2 landed. `README.md` is outside this change's own file-changes table in `design.md` (only `docs/spec-panel-v1b.md` and `docs/runbook-desarrollo-local.md` were planned for edits), so this is not a spec-scenario failure -- but the sweep explicitly asked for a fourth stale claim, and this is it. Recommend a one-line fix (e.g. "implementada, sin desplegar") alongside whichever commit next touches this branch or its follow-up.

**2. `docs/spec-panel-v1b.md` API table (lines 86-87) marks both phase-2 endpoints "Entregado el 2026-08-21", using the same word the same table uses elsewhere to mean "deployed to production" -- which phase 2 explicitly is not.**

Lines 88-92 use "Entregado el 2026-08-20" / "Entregado el 2026-08-18" for the phase-3 and phase-4 endpoints, and those phases genuinely are deployed (checked off in the phase table, lines 160-163). Lines 86-87 apply the identical word to `GET /api/history/reading` and `GET /api/mangas/{id}/history`, but the phase-2 row three lines below (line 161) explicitly says phase 2 is "implementada... sin desplegar... no esta entregada hasta que se mergee y se despliegue" (implemented, not delivered, not delivered until merged and deployed). Within one document, "Entregado" carries two different meanings depending on which table you are reading -- for phase 3/4 it means "shipped to users", for phase 2 it apparently means "the code landed in this branch." This is the same kind of self-contradiction line 99 had before the `78aad69` fix, just in a different table. Does not block archive (it does not misstate what the endpoints do, only when they became reachable in production) but should be corrected -- e.g. "Implementado el 2026-08-21, sin desplegar" -- for consistency with line 99's own corrected wording.

**3. (Confirmed carried over, not a new finding) One frontend test comment previously overclaimed timezone coverage; already self-corrected before pass 1, no action needed.** See pass-1 record above.

## Deviations From Spec (declared, not scored as defects)

- Per-manga timeline built, tested, and functionally complete but not reachable from the UI -- owner decision 2026-08-21, recorded in `docs/spec-panel-v1b.md` Pendientes abiertos with rationale and reopening cost. Not recommended for restoration.
- Heatmap visual format resolved by the owner via /prototype to a full-year 53-week calendar, closing design decision D8 -- a design evolution, not a spec deviation (the spec left visual format owner-reserved).
- 0->175 upward-correction outlier (D7, no server cap) and NULL-`previous_chapter_num` counting as an edit with 0 chapters (D5) remain explicitly flagged-not-resolved in both the design and `docs/spec-panel-v1b.md` Pendientes abiertos line 204 -- matches the spec's own Known Limitation section verbatim. Not a defect.

## Design Coherence

D1-D11 re-spot-checked against the current tree (not re-deriving every line from pass 1, since no design-relevant code changed between passes -- only the E2E assertion and one doc line changed in `78aad69`): D1 (`create_app(..., *, timezone_name)` required kwarg) unchanged and still enforced by `test_create_app_without_timezone_name_raises_type_error`; D2/D3 (fixed-width UTC window, shift-before-group) re-confirmed directly this pass via the hard-bar test and the source read above; D6 (downward correction visible with negative delta in the timeline, excluded from the heatmap) re-confirmed via the timeline test fixture. No design decision was touched by the remediation commit.

## Task Completion

40/40 tasks in `tasks.md` remain checked; the remediation commits (`78aad69`, `04ae855`) are outside the task list by design (owner-directed post-apply fixes responding to sdd-verify findings, not task-plan work) -- consistent with how pass 1 already treated the earlier post-apply commits.

## Recommendation

Archive is unblocked. Optionally fold the two new WARNING doc-line fixes (`README.md:25`, `docs/spec-panel-v1b.md:86-87`) into the same follow-up commit if one is opened before merge; neither is a re-verification blocker. Recommended next phase: sdd-archive.
