# Verify Report: panel-v1b-fase-4 -- Slice 1 (terminal covers)

**Change**: `panel-v1b-fase-4` | **Scope**: Slice 1 only (tasks 1.1-1.12) | **Branch**: `feat/panel-v1b-fase-4-terminal-covers` (6 commits off `main`@`4d2d555`) | **Date**: 2026-08-25
**Mode**: hybrid (Engram `sdd/panel-v1b-fase-4/verify-report` + this file)
**Skill resolution**: none -- no registry entry matches

## Pass 1 recap (superseded by this report)

Pass 1 (4 commits) found: **CRITICAL** -- no automated test exercised the `cache-covers` `--status` partition/dispatch logic in `cli.py` (spec `cover-backfill` Requirement 5, proven only by a manual smoke test); **WARNING** -- `cover-backfill/spec.md` References section still pinned `docs/spec-panel-v1b.md v1.6` after this same slice bumped it to v1.7. Verdict: **FAIL**. Full pass-1 detail (7-item deep verification, guard-break exercise, compliance matrix) remains in Engram history under this topic key prior revision; not reproduced here except where re-run below.

## What changed since pass 1 (2 commits)

- `b8b020a test(cli): cover cache-covers status dispatch through main()` -- 4 new tests in `tests/test_cli.py` (`FakeCoverClient`, `_cover_fixture_db`), closing the CRITICAL; fixed the `cover-backfill/spec.md` pin, closing the WARNING.
- `1b43484 docs(sdd): repoint the two remaining delta-spec pins at v1.7` -- orchestrator commit, repointing `specs/kitsu-import/spec.md` and `specs/panel-bookmark-score/spec.md` References (same staleness pass 1 flagged as out-of-scope for slice 1, then reclassified as in-scope since both files ship in `3ef00a4`).

## Tests

`./.venv/Scripts/python.exe -m pytest -q` -> **575 passed**, 0 failed, 7.32s. Matches the expected baseline (571 pass-1 plus 4 new CLI-dispatch tests).

## Re-run: independent break-and-restore of the CLI dispatch (not taken on trust)

Target: `manga_tracker/cli.py:318-319`, `_cmd_cache_covers`:
```python
mapped_statuses = tuple(status for status in requested if status not in TERMINAL_STATUSES)
terminal_statuses = tuple(status for status in requested if status in TERMINAL_STATUSES)
```

Procedure, performed directly rather than re-reading the applying agent account as proof:
1. Swapped `not in` and `in` on both lines (inverting the partition -- terminal statuses now route to `_cache_covers_mapped_route` and vice versa).
2. `git diff manga_tracker/cli.py` confirmed exactly the 2-line swap, nothing else touched.
3. `./.venv/Scripts/python.exe -m pytest tests/test_cli.py -k cache_covers -v`: **all 4 new tests failed**:
   - `test_cache_covers_terminal_only_status_never_reaches_the_mapped_route` -- FAILED (mapped-route `_explode` fired for a `completed`-only request)
   - `test_cache_covers_non_terminal_status_never_reaches_the_terminal_route` -- FAILED (terminal-route `_explode` fired for a `reading`-only request)
   - `test_cache_covers_mixed_status_partitions_each_row_to_its_own_route` -- FAILED (`details_calls == []` vs expected `[slug-1]`)
   - `test_cache_covers_dry_run_reports_both_populations_and_requests_nothing` -- FAILED (`Mapped route (reading):` not in output; got `Mapped route (dropped):` instead)
4. `git checkout -- manga_tracker/cli.py` restored the file; `git diff manga_tracker/cli.py` is empty.
5. `./.venv/Scripts/python.exe -m pytest -q` -> 575 passed again.

**Verdict on this item**: confirmed independently. All 4 tests are load-bearing; none passed under the broken partition. The applying agent account matches what was reproduced here. CRITICAL #1 from pass 1 is resolved.

## Re-verified: the two-file pin repoint (`1b43484`)

Claim to check: the two References lines were repointed to named sections in `docs/spec-panel-v1b.md` v1.7, and those sections exist and say what the references claim.

`docs/spec-panel-v1b.md` v1.7 heading list (`grep -n "^## "`) confirms both target sections exist verbatim:
- ``## `my_score` (fase 4)`` -- line 177
- `## Fases y criterios de terminado` -- line 183

Content check, not just heading presence:
- `specs/kitsu-import/spec.md` now cites ``docs/spec-panel-v1b.md v1.7 section `my_score` (fase 4)``. That section second bullet (line 180) is the exact paragraph documenting the correction kitsu-import requirement describes: the export id is a MAL id, resolved through the Kitsu catalogue (`/mappings`, chunked at 12) before the bookmark lookup, roughly 38 requests measured for 218 entries, zero to manganato. This is a precise match, not a generic pointer.
- `specs/panel-bookmark-score/spec.md` now cites the same section plus a Fases y criterios de terminado reference ("El orden entre la 4 y la 5" -- the data, not its form). Line 201 of the doc opens with the bolded phrase "El orden entre la 4 y la 5, y que se pisa de verdad." -- exact string match -- and its content is "la distincion es entre el dato y su forma" / "la fase 4 entrega el dato ... y no gasta ni una decision visual en el," which is precisely "the data, not its form." Match confirmed, replacing the old section 195 (data vs. form) pointer that no longer resolves to that content at v1.7 line numbers.

**Verdict on this item**: both repoints are accurate. The commit stated reasoning (v1.6 lines 171-175 pointed at `my_score`; at v1.7 those same line numbers fall inside "Portadas de los terminales") is independently plausible given the document grew by roughly 30 lines in the terminal-covers section landed in `3ef00a4`, and repointing by name rather than restoring old line numbers was the correct call. No CRITICAL or WARNING here.

## Confirmed: nothing else changed under the two new commits

`git diff --stat 3ef00a4 HEAD` touches only 3 spec References lines and adds `tests/test_cli.py`. `manga_tracker/discovery/covers.py`, `manga_tracker/storage/repositories.py`, `manga_tracker/sources/manganato/client.py`, and `manga_tracker/cli.py` non-test logic are byte-identical to the state pass 1 already verified. This means every pass-1 structural finding still holds by construction, not by re-trust; the items below were spot-re-confirmed anyway per the request:

- **Zero-manganato guarantee, structural**: `list_stored_url_cover_candidates` (repositories.py) has no `manga_sites` join and no `source_key` column in its SELECT; `backfill_stored_url_covers` (discovery/covers.py) has zero references to `fetch_manga_details` in its body. Unchanged since pass 1.
- **Permission/cost split**: status decides route dispatch (`TERMINAL_STATUSES` in `cli.py`); `cover_url IS NULL` decides download eligibility inside `backfill_stored_url_covers`, independent of mapping. A mapped terminal still goes down the thin route. Unchanged.
- **`no_url` accounting**: a NULL `cover_url` terminal row, mapped or not, is skipped and counted in `report.no_url`, never escalated to the mapped/source-calling route. Unchanged.
- **`consecutive_failures` and `retry=False`**: `backfill_stored_url_covers` has zero writes to `manga_sites`; `sources/manganato/client.py` has zero diff lines across `main..HEAD` (confirmed via `git diff main..HEAD -- manga_tracker/sources/manganato/client.py`, empty); `fetch_cover` `retry=False` at `client.py:118` unmodified.
- **`docs/spec-panel-v1b.md` v1.7**: version bump, pins re-verified in prose (three pins unchanged, all explicitly re-verified), changelog entry present, the corrected claim about `completed` rows not linking to their chapter list now reads as a practical consequence today, not an invariant. Unchanged since pass 1; the only new doc edits since pass 1 are the two References-line repoints already covered above.
- **Conventions**: `docs/spec-panel-v1b.md` diff 100% Spanish; touched Python (`tests/test_cli.py`, spec `.md` References lines) 100% English comments/identifiers where applicable; commit log (6 commits) all conventional-commit format, zero AI-attribution trailers (full commit log inspected via git log).

## Completeness -- tasks 1.1-1.12

All 12 still checked `[x]` in `tasks.md`, unchanged from pass 1 confirmation; slices 2-4 (tasks 2.1-5.1) correctly `[ ]`, not reported as gaps. `.gitignore` pending unstaged edit (a personal `.claude/settings.local.json` ignore rule) is unrelated to this SDD change and pre-dates the branch -- out of scope, not a finding.

## Spec compliance matrix (cover-backfill/spec.md) -- delta from pass 1

| Requirement | Scenario | Runtime-covering test | Verdict |
|---|---|---|---|
| Reachable via existing CLI | `--status completed` does real work | `test_cache_covers_terminal_only_status_never_reaches_the_mapped_route` plus 3 more, re-run and independently broken/restored above | **PASS** (was CRITICAL/UNTESTED in pass 1) |

The other 5 requirements/scenarios were already PASS in pass 1 and are unaffected by the 2 new commits (see "Confirmed: nothing else changed" above). All 6 scenarios now PASS.

## Findings

**CRITICAL**: none.
**WARNING**: none. (Pass 1 WARNING -- stale pin in `cover-backfill/spec.md` -- was closed in `b8b020a`; the two pins that were explicitly out-of-scope in pass 1 corrective batch were repointed and independently re-verified accurate in `1b43484`, above.)
**SUGGESTION**: none.

## Verdict

**PASS.** Both pass-1 findings are closed and independently re-proven, not merely taken on the applying agent word: the CLI-dispatch CRITICAL was closed by re-running the exact break-and-restore exercise directly (all 4 new tests failed under the broken partition, passed restored), and the third pin fix made directly by the orchestrator was checked for accuracy against the actual v1.7 section names and content, not just presence of a version number. 575 passed, 0 failed. All 12 slice-1 tasks complete and match code state. Slice 1 is clean for delivery.

**Next recommended**: PR. The orchestrator hands `feat/panel-v1b-fase-4-terminal-covers` to the owner for merge from the GitHub UI; `sdd-archive` is not the immediate next step for a chained-PR slice still awaiting merge (per the tasks artifact stacked-to-main delivery strategy) -- that is an orchestrator/owner call, not this report to make, but there is nothing left here to block it.

---

# Verify Report: panel-v1b-fase-4 -- Slice 2 (Migration 3)

**Change**: `panel-v1b-fase-4` | **Scope**: Slice 2 only (tasks 2.1-2.5) | **Branch**: `feat/panel-v1b-fase-4-migration-3`, cut from `main`@`7d61511`, not pushed, 3 commits | **Date**: 2026-08-26
**Mode**: hybrid (Engram `sdd/panel-v1b-fase-4/verify-report`, merged with the slice-1 revision, + this file)
**Skill resolution**: paths-injected

## Commits under review

- `b8ba322 feat(storage): add migration 3 for bookmarks.my_score` -- `manga_tracker/storage/schema.sql`, `manga_tracker/storage/db.py`, `tests/storage/test_migrations.py`; 125 insertions, 10 deletions.
- `edcc9d6 docs(sdd): mark slice 2 tasks 2.1-2.4 complete` -- `tasks.md` bookkeeping only.
- `8012b64 docs(runbook-deploy): correct the backup convention to the one actually used` -- orchestrator-authored, in scope because task 2.5 depends on it; `docs/runbook-deploy.md` only, 18 insertions, 3 deletions.

## Tests

`./.venv/Scripts/python.exe -m pytest -q` -> 580 passed, 0 failed, 8.68s. Matches the reported baseline (575 on main + 5 net-new/rewritten migration-3 tests).
`./.venv/Scripts/python.exe -m pytest tests/storage/test_migrations.py -q` -> 17 passed, 0 failed. Matches reported.

## Guard-break exercise (three real violations, not taken on trust)

### 1. Removed the my_score line from schema.sql

Stripped the literal column declaration line from schema.sql and re-ran tests/storage/test_migrations.py.

Result: 2 failed, 15 passed.
- test_a_fresh_database_is_born_with_my_score -- FAILED: the born-empty path no longer stamps the column because schema.sql no longer declares it.
- test_my_score_is_declared_on_its_own_line -- FAILED: the fixture guard itself catches the missing declaration directly.

Reverted with git checkout; diff empty; back to 17 passed.

### 2. Made the from-zero test stop stripping migration 3's line

In test_migrating_from_zero_applies_all_three_migrations_in_order, changed the strip loop to skip MIGRATION_3_LINE, leaving it unstripped.

Result: 1 failed (ran with -k from_zero): the test failed at its own self-check, `assert "my_score" not in sql, "the strip did not take"`, raising AssertionError: the strip did not take, with my_score visibly present in the constructed fixture SQL. The test catches the trap before it can silently pass on a database that already carries the column, exactly as tasks.md 2.4 requires.

Reverted with git checkout; diff empty; suite back to 17 passed.

### 3. Deleted the PRAGMA table_info guard inside _migration_3_bookmarks_my_score

Replaced the guarded body (PRAGMA table_info check + conditional ALTER) with an unconditional ALTER TABLE.

Direct reproduction against an already-migrated database (schema.sql executed whole, so my_score already exists, then calling the migration function again):

```
EXPECTED FAILURE (guard removed): duplicate column name: my_score
```

Running the full tests/storage/test_migrations.py file with the guard removed cascades further than a single idempotency test: 5 failed, 12 passed -- test_an_existing_database_gains_the_new_columns_and_keeps_its_rows, test_connecting_again_changes_nothing, test_the_migration_is_safe_on_a_database_that_somehow_already_has_the_columns, test_an_existing_database_gains_status_changed_at_and_keeps_its_bookmarks, test_the_migration_does_not_invent_a_pause_date all fail with sqlite3.OperationalError: duplicate column name: my_score. These fixtures reuse the full current schema.sql (which already declares my_score) and stamp an older user_version, so migration 3's now-unguarded ALTER TABLE collides with the column schema.sql already created -- proving the guard is load-bearing well beyond the migration-3-specific tests.

Reverted with git checkout; diff empty; tests/storage/test_migrations.py back to 17 passed; full suite back to 580 passed.

## Claims checked

| Claim | Verified how | Result |
|---|---|---|
| SCHEMA_VERSION = 3 and MIGRATIONS[3] both wired | Read db.py: SCHEMA_VERSION = 3 (line 15) and MIGRATIONS = {1:..., 2:..., 3: _migration_3_bookmarks_my_score} (lines 81-85) | CONFIRMED -- both halves present |
| Migration 3 backfills nothing; NULL stays NULL | test_the_migration_does_not_invent_a_score (passing); guard-break #1/#3 show the ALTER carries no DEFAULT and no UPDATE follows it | CONFIRMED |
| Migration is idempotent; re-running connect() changes nothing | test_connecting_again_after_migration_3_changes_nothing (passing); guard-break #3 independently proves why -- the guard is what prevents duplicate column name | CONFIRMED |
| test_migrating_from_zero_applies_all_three_migrations_in_order strips all three migrations' lines and asserts three applied, in order, ending at SCHEMA_VERSION | Read the test body: strips MIGRATION_3_LINE, MIGRATION_2_LINE, and both ADDED_COLUMNS; calls _migrate(conn) directly; asserts applied == 3, all three columns present, PRAGMA user_version == SCHEMA_VERSION. Guard-break #2 proves the strip is load-bearing | CONFIRMED |
| Task 2.5 remains [ ], not falsely marked done | grep on tasks.md | CONFIRMED -- still unchecked, with an explanatory note |
| The runbook task 2.5 points at now describes a procedure that actually works on the server | ssh mangatracker (production homelab): confirmed ~/backups/ is ABSENT (matches the doc's stated reason for correcting Section 7); confirmed 13 pre-*.db files sit next to manga-tracker.db under ~/manga-tracker-data/, matching the pre-<motivo>-<YYYYMMDD>-<HHMM>.db convention the corrected doc describes, including the exact two files cited 45 minutes apart (pre-migracion2-20260819-0059.db, pre-dedupe-20260819-0144.db) | CONFIRMED against live production, not taken on trust |
| Version bump 1.6 -> 1.7 and repointed pin spec-panel-v1b.md v1.3 -> v1.7 are correct | Read the runbook-deploy.md header diff; cross-checked all four declared dependency versions against the live headers of one-pager-v1a.md (v1.14), spec-panel-v1b.md (v1.7), spec-seed-manual.md (v2.4), spec-cliente-fuente-descubrimiento.md (v1.9) | CONFIRMED -- spec-panel-v1b.md is genuinely at v1.7; all four pins match the live document headers exactly |
| Rollback: v2 codebase against a v3-stamped database walks an empty range, no-op, not a crash | Reproduced the _migrate loop directly: built a database with schema.sql executed whole and PRAGMA user_version = 3, computed range(user_version + 1, SCHEMA_VERSION_v2 + 1) with SCHEMA_VERSION_v2 = 2 | CONFIRMED: user_version on disk: 3, v2 codebase walk range: [] -> empty, no-op |

## Design coherence (D7)

_migration_3_bookmarks_my_score mirrors _migration_2_bookmarks_status_changed_at exactly: PRAGMA table_info guard, one ALTER TABLE, no backfill. schema.sql declares my_score INTEGER, on its own line with the explanatory comment placed above it (mirroring status_changed_at's pattern), and the comment text avoids the literal substring my_score so the fixture's own strip-guard stays meaningful -- confirmed by reading the current comment ("No range CHECK here...") which contains no such literal. No DB-level CHECK was added, matching D7's explicit instruction. All consistent with design.

## Completeness -- tasks 2.1-2.5

- 2.1, 2.2, 2.3, 2.4 -- all checked [x] in tasks.md, and code state matches: schema line present and bare, migration function present with guard, MIGRATIONS[3] registered, SCHEMA_VERSION = 3, five new/rewritten tests present and passing, from-zero test rewritten to strip and assert all three migrations.
- 2.5 -- correctly left [ ]; the runbook it points at (docs/runbook-deploy.md Section 7) was corrected in this branch's third commit and independently verified against the live production server to describe the convention actually in use.

Task completion matches code state for all five items; no task falsely marked done, no task falsely left undone.

## Spec compliance matrix (panel-bookmark-score/spec.md, migration requirement only -- in scope for slice 2)

| Requirement | Scenario | Runtime-covering test | Verdict |
|---|---|---|---|
| Migration 3 adds my_score, idempotently and without inventing a value | Existing database gains the column | test_an_existing_database_gains_my_score_and_keeps_its_bookmarks | PASS |
| (same) | Re-running the migration is a no-op | test_connecting_again_after_migration_3_changes_nothing | PASS |
| (same) | A database born after this change is stamped, not migrated | test_a_fresh_database_is_born_with_my_score | PASS |

The remaining requirements in panel-bookmark-score/spec.md (NULL-as-unscored range validation, PATCH presence semantics, reading_history exclusion, list-payload visibility) belong to Slice 3 and are out of scope for this pass -- correctly unimplemented, not reported as gaps.

## Findings

CRITICAL: none.
WARNING: none.
SUGGESTION: none.

## Verdict

PASS. All three requested guards were broken on purpose and produced real, specific failures (2, 1, and 5 failing tests respectively, plus a direct sqlite3.OperationalError: duplicate column name reproduction for guard 3), then reverted cleanly with an empty diff each time. Full suite 580 passed, focused migration suite 17 passed, matching the reported baseline exactly. SCHEMA_VERSION/MIGRATIONS[3] wiring, NULL-preserving no-backfill behavior, idempotency, and the from-zero three-migration assertion are all confirmed both by passing tests and by independent guard-break reproduction. Task 2.5 correctly remains an unchecked manual operator step, and the runbook doc it depends on was verified against the live production server (not merely read) to now describe a backup procedure that actually matches server reality, replacing a ~/backups/ instruction that was confirmed absent. All four version pins in the corrected runbook match live document headers. The rollback no-op claim was independently reproduced via the migration-walk logic. Slice 2 is clean for delivery.

**Next recommended**: sdd-archive is not the immediate next step for a chained-PR slice still awaiting merge -- that is an orchestrator/owner call. Nothing in this report blocks handing feat/panel-v1b-fase-4-migration-3 to the owner for PR review and merge from the GitHub UI (base: main, since slice 1 already merged).
