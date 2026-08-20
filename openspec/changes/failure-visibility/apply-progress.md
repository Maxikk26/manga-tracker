# Apply Progress: Failure Visibility

**Status**: 35/36 tasks complete. Task 4.1 (owner-only production audit) is
intentionally UNRUN — see below. Ready for `sdd-verify`.

**Branch**: `fix/failure-visibility`, off `main` @ `eabfe30`.

## Commits (one PR, four commits — SDD artifacts + three work units)

1. `ada7972` — `docs(sdd): add failure-visibility proposal, design, and specs`
2. `e9d89ad` — `fix(discovery): require finished, non-empty evidence for detection health`
3. `8827a37` — `fix(sources): classify a details 403/429/5xx as transient, not unexpected`
4. `4932de9` — `fix(web): reject an empty or whitespace-only manga title`

## Phase 1 — Heartbeat detection-health signal (all done)

- Added `FINISHED_WITH_EVIDENCE = "finished_at IS NOT NULL AND IFNULL(items_checked, 0) > 0"` in `manga_tracker/discovery/runs.py`, next to `open_run`.
- `heartbeat.py::_last_successful_run_at` and `scheduler.py::sweep_is_overdue` both interpolate it instead of repeating the literal. `_last_onhold_sweep` untouched.
- 4 new unit tests in `tests/discovery/test_heartbeat.py` (in-flight, killed-mid-sweep, zero-item, qualifying row).
- **Guard-break evidence** (task 1.8):
  - (a) Dropped `IFNULL(items_checked, 0) > 0` → `test_last_successful_run_at_excludes_a_finished_run_that_examined_nothing` failed (`'2026-07-25T03:00:00Z' is not None`). Restored → passed.
  - (b) Dropped `finished_at IS NOT NULL` → both `test_last_successful_run_at_excludes_an_in_flight_run` and `..._excludes_a_run_killed_mid_sweep_left_open_forever` failed. Restored → passed.
  - (c) Set fragment to `"1=1"` → failed 3 heartbeat tests AND 3 scheduler/active-sweep tests (`test_a_sweep_that_examined_nothing_does_not_satisfy_the_catch_up_window`, `test_an_unfinished_sweep_does_not_satisfy_the_catch_up_window`, `test_reaping_releases_a_run_row_left_open_by_a_dead_process`), proving the constant is load-bearing at both call sites. Restored → full suite green.
- `tests/test_architecture.py` needs no new rule — confirmed green (6/6), matching design D1.
- Docs: `spec-bot-telegram.md` v1.6→v1.7 (changelog + post-deploy expectation), stale pins fixed in `runbook-mantenimiento.md:3` and `one-pager-v1a.md:170`, post-deploy note added to `runbook-mantenimiento.md`.

## Phase 2 — Details-403 classification (all done)

- `fetch_manga_details` in `manga_tracker/sources/manganato/client.py` now imports `TRANSIENT_STATUS_CODES` from `transport.py` and classifies: 404→`NotFound`, 403/429/5xx→`Transient`, any other non-200→`Unexpected`.
- 3 new unit tests in `tests/sources/test_client.py` (403, 500, 418).
- 1 new integration test in `tests/web/test_add_manga_api.py`: `test_a_details_403_never_produces_a_200_preview_with_an_empty_title` — passed immediately (the web layer's `_source_error` was already generic over `Transient`), confirming design D3's "blast radius: client.py, not web/app.py".
- **Guard-break evidence** (tasks 2.6-2.8):
  - 2.6: commented out the 403/`Transient` branch → `test_fetch_manga_details_403_is_transient` and `..._500_is_transient` failed with `Unexpected` raised instead. **Deviation from task wording**: the "503-preview test in 2.9" did NOT fail, because `tests/web/test_add_manga_api.py` fakes `intake.preview()` directly (per the file's own docstring) and never invokes the real `ManganatoClient` — an architectural fact of that test double, not a defect. Restored → all green.
  - 2.7: `tests/sources/test_transport.py::test_the_transient_status_set_is_exactly_the_documented_one` run unmodified — green (50/50 in that file), confirming no member was added to `TRANSIENT_STATUS_CODES`.
  - 2.8: temporarily added `404` to `TRANSIENT_STATUS_CODES` → the pin test failed (`Extra items in the left set: 404`). Discarded → `git diff` on `transport.py` empty, confirming exact restoration.
- Docs: `spec-cliente-fuente-descubrimiento.md` v1.8→v1.9 (changelog + rewritten line-9 sentence scoped to `fetch_cover`), 7 stale pins fixed (`medicion-ventana-feed.md`, `spec-bot-telegram.md`, `runbook-deploy.md`, `spec-seed-manual.md`, `spec-importador-kitsu.md`, `one-pager-v1a.md:169`, `manganato-fuente-actual.md:169`).

## Phase 3 — Empty title unwritable (all done)

- `MangaAddRequest.title` in `manga_tracker/web/app.py` changed to `Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]`.
- 3 new tests in `tests/web/test_add_manga_api.py`: empty title (422, zero rows), whitespace-only title (422, zero rows), normal title (201, unchanged write path).
- **Guard-break evidence** (task 3.5): dropped `strip_whitespace=True` (kept `min_length=1`) → `test_whitespace_only_title_is_422_and_writes_nothing` failed with a written row (201 instead of 422). Restored → 21/21 green in that file.

## Phase 4 — Owner prerequisite and CLAUDE.md check

- **4.1 — UNRUN, not completable by the implementer.** `SELECT id, title FROM mangas WHERE TRIM(title) = '';` was not run against production: this account has no permission on `/var/run/docker.sock` and `data/` in the checkout is empty. This is an **archive prerequisite**, not a code blocker — flag before archiving this change.
- **4.2 — done.** Judged `CLAUDE.md` §"Request policy" and §"Rules that are easy to get wrong": no update needed. No new `job_name`, no new traffic class, no change to the detection rule, retry policy, or `fetch_cover`'s divergent 403 handling. The heartbeat and client changes are read-and-raise only.

## Phase 5 — Final verification (all done)

- `uv run pytest -q`: **543 passed** (532 baseline + 11 new: 4 heartbeat + 3 client + 1 preview-integration + 3 empty-title).
- `npm test` from `frontend/`: **101 passed**, confirming the frontend is untouched (no frontend files modified by this change).
- Doc-pin sweep: `rg` for `spec-bot-telegram\.md.*v1\.6` and `spec-cliente-fuente-descubrimiento\.md.*v1\.8` across `docs/` — remaining hits are all confirmed-historical changelog prose (`runbook-mantenimiento.md:26`, `:317`; `one-pager-v1a.md:3` changelog paragraph), not missed pins.

## Diff size

189 insertions + 21 deletions across 17 production/test/doc files (SDD
planning artifacts — `proposal.md`, `design.md`, `specs/` — add another 376
lines in their own commit, not counted against the review budget). Well
under the 400-line PR budget and the 800-line session budget; no chaining
needed, matching the tasks.md forecast (Medium risk, no decision needed).

## Phase 6 — Verify remediation (outside the sdd-attempt ledger)

`sdd-verify` returned **FAIL** on one CRITICAL and raised one WARNING
(`verify-report.md`). Both are closed by two tests; no production code was
touched.

**Ledger note.** This remediation ran **OUTSIDE the `gentle-ai sdd-attempt`
ledger**, deliberately. The `failure-visibility` objective became
unadvanceable: it was rescoped with `max_attempts` equal to the carried
`cumulative_attempts`, so every ledger operation refuses in a cycle — the
budget is exhausted the moment it is consulted, and there is no ledger
transition left that could record this pass. The work is therefore recorded
here, in the change's own progress file, rather than as an attempt.

### CRITICAL #1 — onhold_sweep failures must not inflate degraded_run_count

- **Added** `tests/discovery/test_heartbeat.py::test_degraded_run_count_never_counts_an_onhold_sweep_failure`,
  and imported `_degraded_run_count` alongside the existing
  `_last_successful_run_at` import. Asserts in two steps: an `onhold_sweep`
  row closed `status='error'` inside the 7-day window reads **0**, and adding
  a degraded `feed_check` row reads **1**, not 2. The second half pins the
  *exclusion*; the empty case alone would also pass against a query that
  counts nothing at all.
- **Guard-break evidence.** Widening `DETECTION_JOBS` to
  `("feed_check", "active_sweep", "onhold_sweep")` alone fails on a binding
  error (`sqlite3.ProgrammingError: Incorrect number of bindings supplied.
  The current statement uses 3, and there are 4 supplied.`) because the
  query hardcodes `IN (?, ?)` — a failure, but not the semantic one. So the
  widening was done *faithfully*, the way a real refactor would (placeholders
  generated from `len(DETECTION_JOBS)`), and the assertion itself caught it:

  ```text
  >       assert _degraded_run_count(conn, NOW) == 0
  E       AssertionError: assert 1 == 0
  E        +  where 1 = _degraded_run_count(<sqlite3.Connection object at 0x785a19d693f0>, '2026-07-26T03:00:00Z')
  ```

  The second half was verified separately under the same widened tuple (the
  first `assert` short-circuits): it reads **2** where the test demands 1.
  Reverted → `git diff` on `manga_tracker/discovery/heartbeat.py` empty,
  10/10 green in that file.

### WARNING #1 — nothing wired a real client 403 through to the panel's 503

- **Added** `tests/web/test_add_manga_wiring.py::test_a_real_client_403_reaches_the_panel_as_a_503`,
  a **new file** rather than an addition to `tests/web/test_add_manga_api.py`.
  The reason is that file's own docstring: it states that `intake` is a fake
  there and that the file proves *only what `web` itself does*. A real-object-graph
  test inside it would contradict that contract and blur what a failure there
  means. The new file states the opposite scope explicitly.
- The graph is the production one, assembled exactly as `cli.py::_cmd_panel`
  assembles it — `FakeTransport` → real `ManganatoClient` → real
  `PastedUrlIntake` → real `create_app` — with the `Transport` double as the
  only fake, because the wire is the only thing a test may not touch. The
  architecture boundary holds: the client enters by injection, `web` still
  imports no `sources` module, and `tests/test_architecture.py` passes.
- It also asserts `transport.calls == [".../manga/throttled-manga"]`, so a
  duplicate-gate short-circuit upstream of the request cannot produce the
  same 503 and prove nothing, and asserts zero `mangas` rows written.
- **Guard-break evidence.** Commenting out the 403/`Transient` branch in
  `manga_tracker/sources/manganato/client.py::fetch_manga_details` (403 then
  falls through to the `!= 200` → `Unexpected` case):

  ```text
  >       assert response.status_code == 503
  E       assert 502 == 503
  E        +  where 502 = <Response [502 Bad Gateway]>.status_code
  ```

  Under that same break `tests/web/test_add_manga_api.py` stayed **21/21
  green**, which is precisely the gap the WARNING described — now closed.
  Reverted → `git diff` on `client.py` empty.

### Verification

- `uv run pytest -q`: **545 passed** (543 verify baseline + 2 new).
- `npm test` from `frontend/`: **101 passed** — frontend untouched, matching
  the verify baseline exactly.
- `uv run pytest -q tests/test_architecture.py`: green — the `web ↛ sources`
  directional rule is intact.
- No production file was modified: `git status` shows only the two test files.
