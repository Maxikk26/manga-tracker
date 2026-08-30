# Archive Report: panel-v1b-fase-4

**Status**: CLOSED — all work delivered and deployed  
**Date**: 2026-08-30  
**Change**: `panel-v1b-fase-4` (`my_score`, scores backfill, terminal covers)

## Executive Summary

Panel-v1b-fase-4 is archived as complete. All four functional slices (terminal covers, migration 3, my_score end-to-end, import-scores) were delivered, merged to main, and deployed to production on 2026-08-30. The change added three new specs to the main spec library (`panel-bookmark-score`, `cover-backfill`) and merged delta requirements into the existing `kitsu-import` spec.

## Artifacts and Observation IDs (Engram Traceability)

| Artifact | Type | Engram ID | Status |
|---|---|---|---|
| Proposal | `sdd/panel-v1b-fase-4/proposal` | #397 | COMPLETE |
| Spec | `sdd/panel-v1b-fase-4/spec` | #399 | COMPLETE |
| Design | `sdd/panel-v1b-fase-4/design` | #400 | COMPLETE |
| Tasks | `sdd/panel-v1b-fase-4/tasks` | #401 | COMPLETE |
| Verify Report | `sdd/panel-v1b-fase-4/verify-report` | #403 | FINAL (PASS after corrective pass #388d309) |

## Spec Merge Results

### New Capabilities Created

1. **`panel-bookmark-score`** — Created at `openspec/specs/panel-bookmark-score/spec.md`
   - 5 requirements covering migration 3, NULL-as-unscored semantics, PATCH three-state contract, reading_history guard, and list payload presence.
   - Delivered via slice 3 (my_score end-to-end).

2. **`cover-backfill`** — Created at `openspec/specs/cover-backfill/spec.md`
   - 5 requirements covering mapped route scope, terminal route zero-source-cost guarantee, data-driven eligibility, idempotency, and CLI reach.
   - Delivered via slice 1 (terminal covers).

### Existing Capability Modified

3. **`kitsu-import`** (main spec at `openspec/specs/kitsu-import/spec.md`)
   - Delta merged: 5 new requirements added covering ExportEntry.my_score, import-scores resolution and safety, skip policies, dry-run behavior.
   - Delivered via slice 4 (import-scores).

## Task Completion

| Metric | Count | Status |
|---|---|---|
| Implementation tasks total | 35 | ✓ COMPLETE |
| Implementation tasks checked | 35 | ✓ CHECKED |
| Deliberately unchecked tasks | 2 | ✓ LEGITIMATE |

**Deliberately unchecked:**
- **Task 2.5** (production backup confirmation): Manual operator step, not automatable. Backup taken 2026-08-26 before migration 3 deploy, verified in runbook.
- **Task 5.1** (post-merge full suite): Orchestration verification task owned by post-merge gate. Satisfied by fact: 606 backend tests passing (600 baseline + 6 new CLI tests), 126 frontend vitest tests, green npm run build.

## Verification and Correction History

**Slice 4 Verification (initial attempt)**: FAIL with 1 CRITICAL
- Issue: Spec scenario "Dry-run makes no network or database call" was untested at CLI level.
- Fix: Corrective commit 388d309 added comprehensive CLI test battery for import-scores.

**Slice 4 Fix Validation**: PASS (commit 388d309)
- CRITICAL closed: dry-run ordering now has covering tests (test_import_scores_dry_run_reports_file_counts_and_builds_nothing, test_import_scores_reads_the_export_before_opening_anything, etc.)
- WARNING closed: CLI-level test coverage added (4 test cases mirroring import-kitsu battery)
- One SUGGESTION recorded for future: CLI-level happy-path test (CLI-level success path with real DB write) — not required for closure but improves parity with import-kitsu

**Final Test Counts**:
- Backend: 606 passing (600 from baseline + 6 from corrective tests)
- Frontend: 126 vitest tests passing
- Architecture: tests/test_architecture.py passed (no boundary violations)
- Build: npm run build green

## Deployment Record

**Delivery Timeline**:
- PR #38: feat/panel-v1b-fase-4-terminal-covers (slice 1) — merged
- PR #39: feat/panel-v1b-fase-4-migration-3 (slice 2) — merged  
- PR #41: feat/panel-v1b-fase-4-my-score (slice 3, includes slice 2) — merged
- PR #43: feat/panel-v1b-fase-4-import-scores (slice 4) — merged
- Corrective: commit 388d309 (CLI test battery) — included in PR #43

**Deployed to Production**: 2026-08-30
- Migration 3 applied (`PRAGMA user_version` = 3)
- Every bookmark row intact, `my_score` NULL on unfilled rows and zero rows holding `my_score = 0`
- import-scores ran once: 218 of 218 export ids resolved, 20 scores filled, 0 already scored, 0 unresolved, 0 absent from the database
- A second run reported `0 filled, 20 already scored` — idempotency confirmed against production, not a fixture
- `reading_history` unchanged by the backfill: a score is not a reading event
- Production integrity check: `integrity_check = ok`

## Final-State Authority Ranking

Per the Archive Phase Skill, final-state claims are ranked as follows:

1. **Native review authority** (N/A — no gentle-ai review gate covered this change)
2. **Persisted tasks artifact**: All 35 implementation tasks checked; 2 deliberately unchecked (manual operator step, post-merge orchestration task)
3. **Launch prompt final-state facts**: Explicit close facts provided state at 2026-08-30 (all slices merged, deployed, 606 tests, corrective pass closed CRITICAL)
4. **Verify report and apply progress**: Intermediate snapshots (slice 4 verify-report shows FAIL with fix validation PASS; earlier slices verified in sequence)

**Resolved contradiction**: Verify-report entry (#403) shows FAIL verdict for slice 4 alone at verification time (2026-08-25), but launch prompt documents corrective commit 388d309 that closed the CRITICAL and now-current final state. Archive records this as resolved-via-correction-history, not as a conflicting claim.

## Known Gaps and Decisions Deferred

**One SUGGESTION recorded, not a blocker**:
- import-scores CLI lacks a CLI-level happy-path test exercising real success path through main([...]) with real DB write, unlike import-kitsu. Module-level tests (5 tests in tests/importer/test_scores.py) cover the underlying function; CLI glue is correctly ordered (read file first) but not directly tested at CLI layer. Recorded for future phase 5+ work.

**Two follow-ups, not blockers** (from design document):
- Unmapped non-terminal rows with stored cover_url are reachable by neither cover route today (zero rows); worth a spec line if the panel ever moves a mapped manga to terminal status.
- Heatmap cap decision deferred to phase 5 per spec-panel-v1b.md v1.6 §232, explicitly marked decided-no-cap in v1.7.

## Rollback Capability

Each slice has independent rollback; change is fully reversible:
- Slices 1, 3, 4: Revert commits — no data residue except cached cover files (each recoverable for one request)
- Migration 3 (slice 2): Safe to revert — rollback to `SCHEMA_VERSION = 2` against a database stamped 3 walks `range(4,3)` which is empty (no-op). Column remains, v2 code ignores it. Destructive cleanup (`DROP COLUMN`) via pre-deploy backup only.
- Data: `UPDATE bookmarks SET my_score = NULL` cleans import-scores fills; reading_history untouched (trigger guard on last_chapter_read).

## Archive Contents

- proposal.md: Original proposal with scope, approach, risks, rollback
- design.md: Technical decisions (D1-D8), architecture, file changes, testing strategy
- exploration.md: Initial exploration findings and design questions
- tasks.md: Task breakdown by slice with final completion status
- specs/panel-bookmark-score/spec.md: New capability spec (created from delta)
- specs/cover-backfill/spec.md: New capability spec (created from delta)
- specs/kitsu-import/spec.md: Modified capability spec (delta merged)
- ARCHIVE.md: This file

## Lessons and Patterns

1. **Four-slice delivery with stacked PRs** worked well for the ~1315-line change against 800-line review budget. Natural dependencies (migration gates scoring and covers) made the slice boundaries clean.
2. **Manual operator steps should not block implementation task completion**: Task 2.5 (backup confirmation) correctly stayed unchecked as a deliberate choice, with the actual backup verified out-of-band.
3. **CLI-level test coverage gaps** were the only blocker; the implementation was correct but unprotected. Lesson: mirror existing CLI verb test batteries (import-kitsu precedent) for new verbs.
4. **Export zero-to-None translation** at parse time (rather than in importer logic) proved the right boundary — keeps the file format fact where it belongs.
5. **Conditional UPDATE with AND guard** (D6) was verified both by inspection and by independent injected-break reproduction; the test for the already-scored case cannot discriminate it alone, so slice 4 learned to value the fill-path test more highly.

## Closure

This change is complete and requires no further work.

Next phase: panel-v1b-fase-5 (visual styling and refinement).

---

**Archived**: 2026-08-30  
**Archived by**: sdd-archive executor (automated)  
**Branch context**: chore/phase-4-close-out, off main@ac82dbd  
**Git commit**: [Will be written by orchestrator after archive artifact is staged]
