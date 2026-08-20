```yaml
schema: gentle-ai.verify-result/v1
evidence_revision: sha256:117dbdb118f8ba7bb8a5ae7ee566737c392dbe47ce842bba102f23eb90851adb
verdict: fail
blockers: 1
critical_findings: 1
requirements: 4/5
scenarios: 14/15
test_command: uv run pytest -q && cd frontend && npm test
test_exit_code: 0
test_output_hash: sha256:ded14e959a3bec374d4ff9e5c36f2d90b361a06e4e95928e403f57a231b33b7d
build_command: cd frontend && npm run build
build_exit_code: 0
build_output_hash: sha256:23cc79d44337b1f8f57435ca47892641b65cb90cb78f3c931e4d2a45f2bc845e
```

## Verification Report

**Change**: failure-visibility
**Branch**: `fix/failure-visibility`, 5 commits `ada7972..7c7b950` on `main` @ `eabfe30`
**Version**: heartbeat-report spec.md (new), source-client spec.md delta (amended 2026-08-20)
**Mode**: Standard (strict_tdd: false)

### Completeness

| Metric | Value |
|--------|-------|
| Tasks total | 36 |
| Tasks complete | 35 |
| Tasks incomplete | 1 (4.1 — owner-only production audit, correctly left unchecked, no fabricated result) |

### Build & Tests Execution

**Build**: ✅ Passed
```text
$ cd frontend && npm run build
tsc --noEmit && vite build
✓ 44 modules transformed, built in 948ms
```

**Tests**: ✅ 543 backend passed / ✅ 101 frontend passed (independently re-run, not trusted from apply's report)
```text
$ uv run pytest -q
543 passed, 1 warning in 8.66s

$ npm test (frontend/)
Test Files  10 passed (10)
Tests  101 passed (101)
```
Confirms apply's claimed 543 backend (532 baseline + 11 new) and 101 frontend exactly — no discrepancy.

**Coverage**: not measured — threshold 0 per config.yaml, no coverage tool configured. ➖ Not available.

### Spec Compliance Matrix

| # | Requirement | Scenario | Test | Result |
|---|---|---|---|---|
|1| Last successful run requires finished, non-empty evidence | In-flight run excluded | `tests/discovery/test_heartbeat.py::test_last_successful_run_at_excludes_an_in_flight_run` | ✅ COMPLIANT |
|2| " | Killed mid-sweep run excluded | `..._excludes_a_run_killed_mid_sweep_left_open_forever` | ✅ COMPLIANT |
|3| " | Zero-item run excluded | `..._excludes_a_finished_run_that_examined_nothing` | ✅ COMPLIANT |
|4| " | Qualifying row reported | `..._reports_a_qualifying_row` | ✅ COMPLIANT |
|5| " | No qualifying run ever → None, truthful | `test_heartbeat_renders_without_crashing_when_no_run_has_ever_succeeded` (pre-existing) | ✅ COMPLIANT |
|6| onhold_sweep excluded from detection health | onhold success never substitutes | `test_heartbeat_reports_the_onhold_sweep_without_ever_counting_it_as_detection` (pre-existing) | ✅ COMPLIANT |
|7| " | onhold failures don't inflate degraded_run_count | none found | ❌ UNTESTED — CRITICAL, see Issues |
|8| Error taxonomy | 404 → not-found | `tests/sources/test_client.py::test_fetch_chapters_not_found` (pre-existing) | ✅ COMPLIANT |
|9| " | Unexpected shape logged | `test_fetch_chapters_missing_array_is_unexpected` (pre-existing) | ✅ COMPLIANT |
|10| " | 403/429/5xx → Transient | `test_fetch_manga_details_403_is_transient`, `..._500_is_transient` (new) | ✅ COMPLIANT |
|11| " | Other non-200 → Unexpected | `test_fetch_manga_details_other_non_200_is_unexpected` (418, new) | ✅ COMPLIANT |
|12| fetch_manga_details is fallback-only | Never invoked during detection | no explicit assertion; enforced indirectly — `FakeClient` in `test_active_sweep.py`/`test_feed_check.py` does not implement `fetch_manga_details`, so a real call would raise `AttributeError` and fail every existing sweep test (pre-existing) | ✅ COMPLIANT (indirect, real runtime enforcement) |
|13| " | A details 403 never produces a 200 preview | `test_fetch_manga_details_403_is_transient` (client raises `Transient` on 403) + `tests/web/test_add_manga_api.py::test_a_details_403_never_produces_a_200_preview_with_an_empty_title` (endpoint returns 503 given `Transient`) | ✅ COMPLIANT (split across two unit tests, each covering one half of the GIVEN/WHEN/THEN; see WARNING for the narrower "single true end-to-end" gap) |
|14| Empty title unwritable | Confirm rejects empty title | `test_empty_title_is_422_and_writes_nothing`, `test_whitespace_only_title_is_422_and_writes_nothing` (new) | ✅ COMPLIANT |
|15| " | Well-formed title unaffected | `test_a_normal_title_still_validates_and_reaches_the_write_path` (new) | ✅ COMPLIANT |

**Compliance summary**: 14/15 scenarios compliant, 1 CRITICAL (UNTESTED, #7).

### Correctness (Static Evidence)

| Requirement | Status | Notes |
|---|---|---|
| `FINISHED_WITH_EVIDENCE` scoped to evidence conditions only, not status | ✅ Implemented | Verified by reading `runs.py`, `heartbeat.py`, `scheduler.py`: heartbeat keeps its own `status = 'ok'`, scheduler keeps its own `status IN ('ok','partial')`, only the shared fragment is `finished_at IS NOT NULL AND IFNULL(items_checked, 0) > 0` |
| `_last_onhold_sweep` uses its own literal | ✅ Implemented | `heartbeat.py:76-79` — own query, `finished_at IS NOT NULL` only, no `items_checked`, does not import/reuse `FINISHED_WITH_EVIDENCE` |
| onhold_sweep excluded from `last_successful_run_at` and `degraded_run_count` | ✅ Implemented (static evidence only for the second half) | `DETECTION_JOBS = ("feed_check", "active_sweep")` drives both queries; `onhold_sweep` is never in that tuple. `last_successful_run_at` half has runtime test coverage; `degraded_run_count` half does not (CRITICAL finding #7) |
| `fetch_manga_details` classification: 404→NotFound, 403/429/5xx→Transient, other→Unexpected | ✅ Implemented | `client.py:83-90`, reuses `TRANSIENT_STATUS_CODES` from `transport.py`, never builds `MangaDetails` from a non-200 body |
| `fetch_cover` untouched, `retry=False` intact | ✅ Confirmed unchanged | `client.py:117-126` — still `status != 200 → Unexpected`, `retry=False` on the transport call |
| `transport.py` unchanged, `TRANSIENT_STATUS_CODES` unchanged | ✅ Confirmed | `git diff` on `transport.py` is empty; `test_transport.py:582-590` pin test passes unmodified |
| Empty/whitespace title unwritable | ✅ Implemented | `web/app.py` — `Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]`, with a code comment calling out the `strip_whitespace` normalization as a real write-path behavior change |
| No schema/migration change | ✅ Confirmed | `git diff` touches no schema file; nothing writes `job_runs.job_name`; `SCHEMA_VERSION` untouched (no hit in diff) |

### Coherence (Design)

| Decision | Followed? | Notes |
|---|---|---|
| D1 — one named SQL fragment, not a helper | ✅ Yes | `FINISHED_WITH_EVIDENCE` constant, interpolated at both call sites, no parameterized helper introduced |
| D2 — status-class classification, corrected per docs/ | ✅ Yes | Matches `docs/spec-cliente-fuente-descubrimiento.md:65` (403/429/5xx = transitorio); spec.md was already amended before apply (task 2.1's note is accurate) |
| D3 — blast radius confined to `client.py` | ✅ Yes | `transport.py` diff is empty; both `fetch_manga_details` callers (`intake/pasted_url.py:49`, `discovery/covers.py:105`) already catch all three exception classes |
| D4 — dead-slug counter untouched | ✅ Yes | `consecutive_failures` logic lives only in `fetch_chapters`/`active_sweep`; `covers.py` and `intake` never touch it |
| D5 — two gates, not three (client + HTTP boundary, no `confirm()` gate) | ✅ Yes | No new gate added inside `intake.confirm()` |
| D6 — existing transport pin test unaffected | ✅ Yes | `test_the_transient_status_set_is_exactly_the_documented_one` passes unmodified, no member added |
| Doc bump v1.6→v1.7 (bot), v1.8→v1.9 (client) with changelog | ✅ Yes | Both changelog entries present and worded per design |
| Required line-9 rewrite scoped to `fetch_cover` | ✅ Yes | Confirmed: now reads "Esta clasificación es propia de `fetch_cover`..." — no longer contradicts the taxonomy statement 11 words earlier |
| All 9 stale pins fixed | ✅ Yes | Verified each of the 9 listed files/lines individually via diff |
| 6 historical mentions left untouched | ✅ Yes | Verified each of the 6 listed locations individually; all are changelog/historical prose referencing old version numbers on purpose |
| No "nunca" string invented; null case truthful | ✅ Yes | `notifier/telegram.py` untouched (no diff hit); `docs/runbook-mantenimiento.md` post-deploy note explicitly frames an equal-or-older timestamp as the fix working, not a regression |
| Commits conventional, no AI/Co-Authored-By attribution | ✅ Yes | All 5 commit messages inspected directly; none carry `Co-Authored-By` or AI attribution |
| Doc prose neutral Spanish, no voseo | ✅ Yes | `rg` scan of all `docs/*.md` diff hunks for `creá|decime|pará|tenés|sos|vos|dale` — zero hits |

### Issues Found

**CRITICAL**:
1. **Spec scenario "onhold_sweep failures do not inflate degraded_run_count" has no covering test at runtime.** `heartbeat-report/spec.md` is a NEW full spec introduced by this change, and this scenario is one of its normative MUST-level scenarios. No test in the suite inserts an `onhold_sweep` row with `status='error'` and asserts `degraded_run_count` excludes it — I confirmed this by grepping every test file for `degraded_run_count`/`status.*error` combinations against `onhold_sweep`; none exist. The behavior is correct today by static construction (`_degraded_run_count`'s query filters `job_name IN (?, ?)` against `DETECTION_JOBS = ("feed_check", "active_sweep")`, which never includes `onhold_sweep`), and this is pre-existing, unchanged-by-this-fix behavior per the design's own note — but the newly-authored spec document asserts it as a MUST with zero regression coverage, which is exactly the gap this verify phase exists to catch. A future refactor of `_degraded_run_count` (or a widened `DETECTION_JOBS`) would break this silently. **This is genuinely low real-world risk** (nothing in this PR touches that query's filtering) but is a real spec/test-completeness gap by the skill's own compliance rule ("a spec scenario is compliant only when a covering test passed at runtime"). **Closing it costs one test**: insert an `onhold_sweep` row with `status='error'` inside the 7-day window and assert `degraded_run_count == 0`.

**WARNING**:
1. **The "details 403 → 503" scenario is proven correct only across two separate unit tests, never one true end-to-end integration test.** Every test in `tests/web/test_add_manga_api.py` uses `FakeIntake`, which never calls the real `ManganatoClient`; `tests/intake/test_pasted_url.py` proves `PastedUrlIntake.preview()` propagates `Transient` unmodified, using its own fake client; `tests/sources/test_client.py` proves the real `ManganatoClient` raises `Transient` on 403. Each segment is solidly unit-tested and the seams between them are simple, documented pass-throughs (`# 1 req; NotFound/Transient/Unexpected propagate`) with no logic to hide a defect, which meaningfully lowers the risk — I judge the scenario itself COMPLIANT (both halves of its GIVEN/WHEN/THEN are independently proven), so this does not count against the scenario totals above. But `tests/test_cli.py`'s DI-wiring tests for `_cmd_panel` also monkeypatch `ManganatoClient` to a stub (`lambda *a, **k: "the-client"`), so nothing in the suite proves the *identity* of the wired object graph combined with its *behavior*, end-to-end, in one place. Apply's own deviation note (task 2.6) frames this purely as "an architectural fact of the test double, not a bug" — that is true for what it claims, but it understates that this leaves the real wiring path with zero direct regression coverage. Closing it: one integration test building the real app via `create_app(db_path, PastedUrlIntake(ManganatoClient(fake_transport)))` (no `FakeIntake`), asserting a stubbed 403 `Transport` response produces an HTTP 503, not 200 or 502.
2. **Archive prerequisite still outstanding.** Task 4.1 (`SELECT id, title FROM mangas WHERE TRIM(title) = ''` against production) is correctly left unchecked with no fabricated result — this account has no `/var/run/docker.sock` permission and `data/` is empty in this checkout. Not a defect in the change itself, but archiving without the owner running that query (or explicitly accepting the risk) would silently skip the one check confirming the sibling defect never wrote a bad row to production.

**SUGGESTION**: None beyond the test additions named above.

### Additional Verification Notes (from the explicit checklist)

- Item 1 (FINISHED_WITH_EVIDENCE scope): confirmed — heartbeat keeps its own `status = 'ok'`, scheduler keeps its own `status IN ('ok','partial')`.
- Item 2 (`_last_onhold_sweep` own literal): confirmed, no shared-fragment reuse.
- Item 3 (onhold_sweep excluded from both figures): code confirmed correct; test coverage confirmed for `last_successful_run_at`, missing for `degraded_run_count` — see CRITICAL #1.
- Item 4 (four heartbeat scenarios have real tests): confirmed, all four new tests exist and pass.
- Item 5 (`fetch_manga_details` classification): confirmed exactly as specified.
- Item 6 (`fetch_cover` untouched): confirmed, `retry=False` intact, still raises `Unexpected` on any non-200.
- Item 7 (`transport.py`/`TRANSIENT_STATUS_CODES` unchanged, pin test intact): confirmed, empty diff on `transport.py`.
- Item 8 (test exists for details-403): confirmed, 3 new tests (403, 500, 418).
- Item 9 (empty-title guard + `strip_whitespace` comment): confirmed, code comment present and explicit about the normalization side effect.
- Item 10 (guard-break evidence real, not boilerplate): confirmed — every guard-break entry in apply-progress.md names the exact test, the exact before/after behavior, and a literal assertion failure message (e.g. `'2026-07-25T03:00:00Z' is not None`). Real evidence, not boilerplate.
- Item 11 (task 2.6 deviation judgment): judged COMPLIANT for scenario coverage (both halves independently proven) but flagged as WARNING #1 for the missing true end-to-end wiring test — a more precise reading than apply's "architectural fact, not a bug" framing, which is correct on the narrow claim but understates the residual risk.
- Item 12/13 (doc versions + changelogs): confirmed both bumps and both changelog entries.
- Item 14 (9 stale pins fixed): confirmed individually, all 9.
- Item 15 (6 historical mentions untouched): confirmed individually, all 6.
- Item 16 (required line-9 rewrite): confirmed, correctly scoped to `fetch_cover`, neutral Spanish, no self-contradiction remains.
- Item 17 (heartbeat truthful-null claim, no "nunca" invented): confirmed.
- Item 17b (task 4.1 correctly unrun): confirmed, no fabricated result — see WARNING #2.
- Item 18 (no schema/migration, `SCHEMA_VERSION` untouched): confirmed.
- Item 19 (commits conventional, no AI attribution): confirmed.
- Item 20 (CLAUDE.md staleness): agree with apply's judgment — no new `job_name`, traffic class, retry policy, or detection-rule change; nothing in CLAUDE.md's "Request policy" or "Rules that are easy to get wrong" sections references heartbeat evidence semantics or `fetch_manga_details` classification, so nothing there goes stale from this change.

### Verdict

**FAIL** — narrowly, on one CRITICAL finding: the newly-written `heartbeat-report/spec.md` declares a scenario ("onhold_sweep failures do not inflate degraded_run_count") with zero runtime test coverage. This does not reflect a defect in the three actual fixes this change makes: all of them (heartbeat false-positive evidence, details-403 misclassification, empty-title write path) are correctly implemented, match the spec/design exactly, and are backed by real, independently-verified test runs (543 backend + 101 frontend, both green, exactly matching apply's reported numbers). The fix is one test (see CRITICAL #1). Recommended path: either add that one test in a short follow-up apply pass, or the owner explicitly accepts the residual risk (structurally low, since the exclusion is enforced by an unmodified job-name tuple) and waives this finding before archiving — alongside resolving the already-known task 4.1 production-audit prerequisite.
