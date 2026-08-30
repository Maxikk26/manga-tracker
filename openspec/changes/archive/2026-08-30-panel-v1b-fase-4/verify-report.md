```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:662894e35d1784d7c4d2ef9d238c71a21f7a37aa3ca1fcd3e7a72e485209cdd7
verdict: fail
blockers: 1
critical_findings: 1
requirements: 4/5
scenarios: 7/8
test_command: ./.venv/Scripts/python.exe -m pytest -q
test_exit_code: 0
test_output_hash: sha256:662894e35d1784d7c4d2ef9d238c71a21f7a37aa3ca1fcd3e7a72e485209cdd7
build_command: N/A - no frontend file changed in this slice; not executed
build_exit_code: 0
build_output_hash: sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
```

## Verification Report

**Change**: panel-v1b-fase-4 - Slice 4 only (import-scores, tasks 4.1-4.8)
**Version**: docs/spec-importador-kitsu.md v1.7 (per design.md D6); delta spec sdd/panel-v1b-fase-4/spec (Engram #399), Delta for Kitsu Import capability
**Mode**: Standard (Strict TDD not signalled; RED/GREEN evidence present in apply-progress #402, independently re-derived below via injected breaks)
**Branch**: feat/panel-v1b-fase-4-import-scores, 4 commits off main@f5ab0fe (2f8d882, f441946, e21de1a, 3ddbc25)
**Scope note**: Task 5.1 (post-merge full-suite check) is out of scope by design and correctly left unchecked - not counted as a gap. Task 2.5 (deploy-time backup) belongs to slice 2, already resolved there.

### Completeness
| Metric | Value |
|--------|-------|
| Tasks total (slice 4) | 8 |
| Tasks complete | 8 |
| Tasks incomplete | 0 |

### Build and Tests Execution

Backend tests: PASSED
```text
./.venv/Scripts/python.exe -m pytest -q
600 passed, 1 warning in 9.14s   (baseline before this slice: 591; apply-progress claim of 600 (+9) confirmed)
```

Frontend: N/A for this slice. git diff main HEAD --stat shows 9 files (docs, cli.py, importer/, storage/, tests/); zero files under frontend/. No npm test or npm run build was run, per the session instruction that no frontend change was expected.

Coverage: Not configured for this project - unchanged from prior slices.

### Spec Compliance Matrix

Source: spec Engram #399, "Delta for Kitsu Import (MODIFIED capability)" section only - the one capability slice 4 touches. Panel Bookmark Score and Cover Backfill capabilities belong to slices 3 and 1, already verified there.

| Requirement | Scenario | Test | Result |
|---|---|---|---|
| ExportEntry carries my_score; export zero means unscored | A real score parses through | tests/importer/test_export.py test_the_score_is_now_carried_into_the_domain | COMPLIANT |
| ExportEntry carries my_score; export zero means unscored | An export zero becomes None, not 0 | tests/importer/test_export.py test_an_export_zero_score_becomes_none_not_zero | COMPLIANT |
| import-scores resolves MAL ids through the catalogue, writes nothing if unreachable | Catalogue unreachable writes nothing | tests/importer/test_scores.py test_catalogue_failure_writes_nothing | COMPLIANT |
| import-scores resolves MAL ids through the catalogue, writes nothing if unreachable | A resolved entry fills its matching bookmark | tests/importer/test_scores.py test_import_scores_reports_one_of_each_outcome (id 1) | COMPLIANT |
| import-scores fills only NULL scores, never overwrites | A hand-edited score survives a re-run | tests/importer/test_scores.py test_import_scores_reports_one_of_each_outcome (id 3) plus tests/storage/test_repositories.py test_set_bookmark_score_returns_false_and_changes_nothing_on_an_already_scored_row | COMPLIANT |
| import-scores fills only NULL scores, never overwrites | A second run on the same file fills zero | tests/importer/test_scores.py test_a_second_run_on_the_same_file_fills_zero | COMPLIANT |
| An entry with no matching manga is an ordinary skip | Unmatched entry is skipped, not an error | tests/importer/test_scores.py test_import_scores_reports_one_of_each_outcome (id 5, not_in_database) | COMPLIANT |
| Dry-run reports file-only counts before any I/O | Dry-run makes no network or database call | NONE FOUND | UNTESTED (CRITICAL) |

Compliance summary: 7/8 scenarios compliant, 1 UNTESTED.

### Correctness (Static Evidence)
| Requirement | Status | Notes |
|---|---|---|
| set_bookmark_score: one UPDATE, AND my_score IS NULL in WHERE, returns bool from cursor.rowcount | Implemented | manga_tracker/storage/repositories.py:533-553 |
| import_scores never inserts (mangas/bookmarks) | Implemented | manga_tracker/importer/scores.py:39-92 - no INSERT statement anywhere in the module |
| import_scores resolves every entrys id (not just scored), matching the ~38-request figure | Implemented | manga_tracker/importer/scores.py:58-63; consistent with docs/spec-panel-v1b.md (the ~38 requests a Kitsu figure for the full 218-entry file) |
| _cmd_import_scores reads/reports the file before any connection or catalogue construction | Implemented, correctly ordered | manga_tracker/cli.py:190-208 (read_export then _report_score_composition then dry-run early-return, all before connect()/KitsuCatalogue construction) - confirmed both by inspection and by the injected-break test below |
| _cmd_import_scores never calls _bootstrap | Implemented | manga_tracker/cli.py:175-221 - no reference to _bootstrap, ensure_site, or ManganatoClient |
| --dry-run returns file-only counts and states so explicitly | Implemented, but UNTESTED | manga_tracker/cli.py:201-207 prints the file-counts-not-resolved-matches message - see Spec Compliance Matrix |
| Score 0 becomes None at parse time | Implemented | manga_tracker/importer/export.py:138-151, _score() returns score or None |
| importer/scores.py imports only catalogue.contracts plus storage.repositories, never catalogue.kitsu | Implemented | confirmed by source inspection and by tests/test_architecture.py passing (600/600 includes this file) |

### Coherence (Design)
| Decision | Followed? | Notes |
|---|---|---|
| D6 - fill-only-NULL enforced in SQL, never a Python read-then-write | Yes | Verified by source inspection AND by an independent injected-break reproduction (see below) - the apply agents claim about which test discriminates the two shapes is CONFIRMED, not merely trusted |
| D6 - ordering: file read/reported before connection/network | Yes in code, but the guarantee itself is UNTESTED | Confirmed correct by inspection; confirmed UNPROTECTED by an injected-break test that violated the ordering and the full 600-test suite stayed green |
| D6 - categories call left unmodified (fetch_categories unconditional) | Yes | importer/scores.py calls catalogue.resolve() once per run over every entrys id, no new parameter added to CatalogueClient |
| D7 (mirrored, not re-verified) | N/A this slice | Migration 3 belongs to slice 2, already merged and verified there |

### Independent Verification of the Discrimination Claim (highest-value check)

Claim made by the apply agent: an already-scored-row returns-False-changes-nothing assertion cannot discriminate a SQL-only guard from a Python read-then-write guard, because a naive read-then-write short-circuits after its own SELECT on that exact input, costing one execute() call either way. The discriminating scenario is the fill/success path, where a read-then-write structurally needs two execute() calls.

Verified independently, not taken on trust:

1. Temporarily replaced set_bookmark_score with a Python read-then-write implementation (SELECT current my_score, decide in Python, UPDATE without AND my_score IS NULL).
2. Ran pytest tests/storage/test_repositories.py tests/importer/test_scores.py -q: 1 failed, 14 passed. The failure was exactly test_set_bookmark_score_fills_an_unscored_bookmark_in_one_statement (asserted len(execute_calls) == 1, got 2: SELECT plus UPDATE).
3. Ran test_set_bookmark_score_returns_false_and_changes_nothing_on_an_already_scored_row alone against the same broken implementation: it passed, confirming this specific test gives false confidence and cannot discriminate the two shapes, exactly as claimed.
4. Reverted with git checkout -- manga_tracker/storage/repositories.py; re-ran both files: 15 passed.

Verdict on the claim: TRUE, independently reproduced. D6 is correctly guarded in SQL and the fill-path test is what actually proves it.

### Injected-Break Verification (mandatory guard-breaking)

Five guards broken on purpose, one at a time, each reverted with git checkout before the next; full suite re-confirmed green (600/600) after every revert.

| # | Break | Command | Result | Reverted and re-green? |
|---|---|---|---|---|
| 1 | set_bookmark_score rewritten as Python read-then-write (SELECT plus conditional UPDATE, no AND my_score IS NULL) | pytest tests/storage/test_repositories.py tests/importer/test_scores.py -q | 1 failed, 14 passed - test_set_bookmark_score_fills_an_unscored_bookmark_in_one_statement caught it (2 execute() calls, expected 1); the already-scored test passed regardless (false confidence) | Yes - git checkout, re-run: 15/15 passed |
| 2 | export.py _score(): return score or None changed to return score (the export 0 sentinel no longer folds to None) | pytest tests/importer/test_export.py tests/importer/test_scores.py -q | 4 failed, 22 passed: test_an_export_zero_score_becomes_none_not_zero, test_import_scores_reports_one_of_each_outcome, test_an_export_zero_score_never_overwrites_or_counts_as_with_score, test_a_second_run_on_the_same_file_fills_zero | Yes - git checkout, re-run: 26/26 passed |
| 3 | import_scores: replaced the fill-only-NULL call with an unconditional update_panel_bookmark(my_score=entry.my_score), forcing an overwrite on an already-scored row | pytest tests/importer/test_scores.py tests/storage/test_repositories.py -q | 2 failed, 13 passed: test_import_scores_reports_one_of_each_outcome (already_scored count wrong), test_a_second_run_on_the_same_file_fills_zero (idempotency broken) | Yes - git checkout, re-run: 15/15 passed |
| 4 | import_scores: on a manga absent from the database, INSERT a new mangas plus bookmarks row instead of counting not_in_database and skipping | pytest tests/importer/test_scores.py -q | 2 failed, 3 passed: test_import_scores_reports_one_of_each_outcome (not_in_database count wrong, a row got created), test_a_second_run_on_the_same_file_fills_zero (the newly inserted row is now already scored on the second run) | Yes - git checkout, re-run: 5/5 passed |
| 5 | _cmd_import_scores: moved connect(config.db_path) and KitsuCatalogue(UrllibJsonTransport()) construction to BEFORE read_export / _report_score_composition / the dry-run check, violating the read-the-file-first ordering | full suite: pytest -q | 0 failed - 600/600 passed, unchanged. Nothing in the suite exercises _cmd_import_scores CLI wiring at all; the ordering guarantee that design D6 explicitly calls out as load-bearing is entirely unprotected | Yes - git checkout, re-run: 600/600 passed |

Break #5 is reported plainly as a finding about test coverage, not a pass: an uncaught structural regression in a command that will run against the real production database and the real Kitsu API.

Tree confirmed clean after all five reverts except the pre-existing, out-of-scope M .gitignore.

### Independent Checks

- No real network, anywhere: confirmed. tests/conftest.py block_network_sockets monkeypatches socket.socket.connect globally, raising RuntimeError on any real connection attempt; every test in tests/importer/test_scores.py uses FakeCatalogue, a duck-typed double, never KitsuCatalogue/UrllibJsonTransport. Full suite passes with sockets blocked. No CRITICAL here.
- D6 in the SQL, not in Python: confirmed - manga_tracker/storage/repositories.py:549-553 is one conn.execute(...) call with AND my_score IS NULL in the WHERE clause, returning cursor.rowcount greater than 0. Independently reproduced above.
- import_scores never inserts: confirmed by source inspection (no INSERT in importer/scores.py) and by injected-break #4 above (forcing an insert broke two tests).
- CLI verb mirrors _cmd_import_kitsu: confirmed by source inspection - same read-report-then-connect ordering, direct KitsuCatalogue(UrllibJsonTransport()) construction, no _bootstrap call anywhere in _cmd_import_scores. The ordering itself is UNTESTED (see Spec Compliance Matrix and injected-break #5) - code is correct, protection against regression is absent.
- The doc edit (docs/spec-importador-kitsu.md v1.6 to v1.7): the four pins were read directly, not trusted.
  - spec-modelo-de-datos.md header reads Version 1.9 - MATCHES pin.
  - spec-cliente-fuente-descubrimiento.md header reads Version 1.9 - MATCHES pin.
  - spec-seed-manual.md header reads Version 2.4 - MATCHES pin.
  - manganato-fuente-actual.md header reads Version 1.4 - MATCHES pin.
  All four confirmed current; the claim that the four pins are exact and none is stale is TRUE. Changelog paragraph (line 5) explicitly names the reversal of decision 5, the migration 3 column, and the import-scores subcommand. Decisiones discutibles item 5 is marked SUPERADO en v1.7 following the documents own existing convention (matches referencia-repo-viejo.md pattern), original reasoning kept, not deleted. Pendientes abiertos my_score bullet is struck through and closed with a pointer to import-scores. Prose throughout is Spanish, neutral professional register, consistent with the rest of the document voice.
- Language contract: confirmed. All new code identifiers, docstrings, comments, print statements (CLI output), and commit messages are English. Domain terms (my_score, kitsu_id, manga_mangadb_id) appear verbatim, untranslated, in both code and the Spanish doc prose. No product-facing string was introduced by this slice (the CLI is an operator tool, not the Telegram digest).
- tests/test_architecture.py: passed as part of the full 600. importer/scores.py imports manga_tracker.catalogue.contracts (allowed) and manga_tracker.storage.repositories (allowed - importers forbidden set is only catalogue.kitsu, catalogue.transport, sources.manganato; storage is NOT forbidden), never catalogue.kitsu directly.
- The ~38-request figure: import_scores resolves every export entrys id (scored or not) in one catalogue.resolve() call - confirmed by test_import_scores_resolves_the_whole_file_in_one_catalogue_call. This is consistent with docs/spec-panel-v1b.md, which documents ~38 requests a Kitsu for import-scores against the full 218-entry file (about 19 resolution plus about 19 categories) - not a silent cost increase, the number was already committed to that doc in slice 1.

### Issues Found

CRITICAL (1):
1. Spec scenario "Dry-run makes no network or database call" (requirement "Dry-run reports file-only counts before any I/O", spec Engram #399) is UNTESTED - no test anywhere invokes import-scores --dry-run (or the CLI verb _cmd_import_scores at all). Confirmed empirically: injected-break #5 (moved the DB connection and catalogue construction before the file read/dry-run check, directly violating this requirement) left the full 600-test suite entirely green. The implementation IS correct today (verified by source inspection), but nothing protects it from regressing. Blocks a clean archive per the sdd-verify decision gate: a spec scenario with no passing covering test is CRITICAL.

WARNING (1):
1. Beyond the one untested spec scenario, the entire import-scores CLI verb (_cmd_import_scores, and its argparse wiring in build_parser()) has zero test coverage of any kind - no test for --file default path, missing-file handling, malformed-export handling, or catalogue-unreachable abort message at the CLI layer, unlike import-kitsu (10+ dedicated tests in tests/test_cli.py) and cache-covers (4 dedicated tests). The underlying import_scores() function is well-tested at the module level (5 tests, task 4.8); only the CLI glue is unprotected. Recommended fix: a tests/test_cli.py battery for import-scores mirroring import-kitsu, which would also close the CRITICAL above.

SUGGESTION: None.

### Verdict

FAIL (blocked by 1 CRITICAL; the WARNING is the same underlying gap and is discharged by the same fix)

Slice 4 (tasks 4.1-4.8) is functionally complete and correctly implements design D6 end to end: the fill-only-NULL guard is genuinely SQL-only (independently reproduced, not taken on the apply agents word), import_scores never inserts, the doc pins are genuinely current, no test reaches the real network, and the language/domain-term contract holds throughout. The backend suite is green at 600/600 (+9 over baseline), and four of five injected breaks were caught cleanly by existing tests.

The one CRITICAL is narrow and mechanical to close: the CLI-level dry-run-costs-nothing guarantee - the same class of guarantee import-kitsu --dry-run already has a dedicated test for - has no covering test for import-scores, and a real ordering regression (exactly the kind task 4.6 own docstring warns about) would ship undetected. This is a missing test, not a code defect; the recommended next step is sdd-apply to add the CLI-level test(s) described in the WARNING (which also discharges the CRITICAL), not to redesign or rewrite any shipped behavior.

---

## Fix Validation - Scoped Correction (commit 388d309)

**Scope**: single bounded validation of the corrective pass that closed the CRITICAL and WARNING from the FAIL verdict above. Not a fresh full review; the settled findings above (D6 read-then-write, export 0 to None, never-overwrites, never-inserts, the four doc pins) were not re-litigated.

```yaml
schema: gentle-ai.verify-result/v1
verdict: pass
blockers: 0
critical_findings: 0
warnings: 0
suggestions: 1
requirements: 5/5
scenarios: 8/8
test_command: ./.venv/Scripts/python.exe -m pytest -q
test_exit_code: 0
```

**Corrective commit**: 388d309 - "test(cli): add import-scores battery, closing the dry-run coverage gap", on top of b88f501 (this report). Test-only diff (see item 3).

### 1. CRITICAL - closed

Reproduced the injected break independently on the corrected tree, not taken on trust: moved connect(config.db_path) and KitsuCatalogue(UrllibJsonTransport()) construction in _cmd_import_scores to BEFORE read_export / _report_score_composition / the dry-run check - the exact same break as injected-break #5 above.

Command: ./.venv/Scripts/python.exe -m pytest -q tests/test_cli.py

Result: 4 failed, 25 passed (previously 0 failed against this same break, per injected-break #5 above). Failing tests:
- test_import_scores_dry_run_reports_file_counts_and_builds_nothing
- test_import_scores_reads_the_export_before_opening_anything
- test_import_scores_rejects_a_missing_export_before_creating_anything
- test_import_scores_reports_a_malformed_export_instead_of_a_traceback

Representative failure (the exploding double, raised from inside _cmd_import_scores at the relocated connect(...) call):
```
tests\test_cli.py:598: in test_import_scores_rejects_a_missing_export_before_creating_anything
    assert main(["import-scores", "--file", str(missing)]) == 1
manga_tracker\cli.py:190: in _cmd_import_scores
    conn = connect(config.db_path)
tests\test_cli.py:332: in _explode
    raise AssertionError("this run must construct nothing and open nothing")
```

Reverted with git checkout -- manga_tracker/cli.py; full suite re-confirmed green: 606 passed, 1 warning.

Verdict: CLOSED. The dry-run/ordering guarantee now has a covering test that fails when the guarantee is violated.

### 2. WARNING - closed, with one residual SUGGESTION

The battery covers the four CLI wiring shapes the FAIL report named and mirrors import-kitsu's battery at each: default --file path, missing file, malformed file, unreachable-catalogue-writes-nothing. It adds a fifth test (a direct ordering pin via a shared call-order list) that import-kitsu's own battery does not have as a direct test - only as an injected-break finding.

One gap remains relative to import-kitsu: import-kitsu's battery includes a CLI-level happy-path test (test_import_kitsu_loads_what_it_can_and_writes_the_rest_to_the_pending_list) exercising the real success path end-to-end through the CLI. import-scores's new battery has no analogous test where a real, unmocked import_scores() reaches a temp database and writes a score through main(["import-scores", ...]) - every one of the 6 new tests either mocks import_scores itself, returns before it is called, or exercises only the abort path.

This is not a coverage hole in the sense that matters for regressions: the underlying import_scores() function already has 5 passing tests at the module level (tests/importer/test_scores.py, task 4.8, COMPLIANT in the Spec Compliance Matrix above), including the fill/success case, and the CLI wiring for the success path is a single "report = import_scores(...); return 0" with no further logic to protect. Recorded as a SUGGESTION, not a blocker.

Verdict: CLOSED (the WARNING as stated in the FAIL report is discharged). One SUGGESTION recorded for a future pass.

### 3. Production behaviour unchanged

git diff b88f501 388d309 --stat:
```
 tests/test_cli.py | 144 ++++++++++++++++++++++++++++++++++++++++++++++++++++++
 1 file changed, 144 insertions(+)
```
Only tests/test_cli.py changed: 144 insertions, 0 deletions, 0 files under manga_tracker/. No production code touched.

### 4. No real network reachable from the new tests

All 6 new tests inspected individually:
- test_import_scores_defaults_to_the_mounted_volume_path never calls main().
- test_import_scores_dry_run_reports_file_counts_and_builds_nothing, ..._reads_the_export_before_opening_anything, ..._rejects_a_missing_export_before_creating_anything, ..._reports_a_malformed_export_instead_of_a_traceback: connect / KitsuCatalogue / import_scores are monkeypatched to exploding or tracking doubles, or the code returns before either is constructed.
- test_import_scores_reports_an_unreachable_catalogue_and_writes_nothing: KitsuCatalogue is wired to a FakeCatalogue via _wire; the real KitsuCatalogue / UrllibJsonTransport classes are never instantiated.

tests/conftest.py's autouse block_network_sockets fixture (patches socket.socket.connect to raise) is also active across the whole suite as a structural backstop.

Verdict: no test reaches, or can reach, kitsu.io.

### 5. Hollow-test check - the two tests that stay green under the break

test_import_scores_defaults_to_the_mounted_volume_path never calls main(); it only exercises build_parser().parse_args(...), so it cannot be sensitive to _cmd_import_scores's internal ordering by construction. Not hollow - it targets a different layer (argparse defaults) and was never meant to catch this break.

test_import_scores_reports_an_unreachable_catalogue_and_writes_nothing wires a FakeCatalogue(error=CatalogueTransient(...)) and does not mock connect. Re-run against the injected break confirmed it still passes: with the break, connect() and the (faked) KitsuCatalogue are both constructed earlier, but the outcome is identical either way - catalogue.resolve() still raises before any write, the temp database still ends up empty, and the abort message is still printed. The break moves WHEN the real sqlite file is opened, not WHETHER a write happens, so this test's assertions (exit code 1, abort message, empty mangas/bookmarks tables) hold regardless of ordering. That is a legitimate reason, not decoration: this test targets the catalogue-abort behaviour, not the ordering guarantee, and the ordering guarantee is now separately and directly pinned by test_import_scores_reads_the_export_before_opening_anything (which DOES fail under the break, per item 1).

Verdict: the stated reason for the 2 non-discriminating tests is legitimate; not decoration.

### 6. Regression check

Full suite: ./.venv/Scripts/python.exe -m pytest -q -> 606 passed, 1 warning (600 baseline + 6 new import-scores CLI tests).
tests/test_architecture.py: 6 passed.
Tree clean after every revert except the pre-existing, out-of-scope " M .gitignore".

Verdict: no regression.

### Fix-Validation Verdict

PASS. Both the CRITICAL and the WARNING from the original FAIL verdict above are closed by commit 388d309. Production behaviour is unchanged (tests-only diff, 144 insertions in tests/test_cli.py, 0 deletions). No test reaches the real network. The two tests that stay green under the injected break have a legitimate, independently verified reason to do so. One non-blocking SUGGESTION recorded: add a CLI-level happy-path test exercising a real import_scores() write through main(["import-scores", ...]), mirroring import-kitsu's ..._loads_what_it_can_and_writes_the_rest_to_the_pending_list.

Recommended next step: sdd-archive.
