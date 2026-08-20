# Tasks: Failure Visibility

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ~280-340 (additions + deletions) |
| 400-line budget risk | Medium |
| Chained PRs recommended | No |
| Suggested split | Single PR, three sequential work units (own commits) |
| Delivery strategy | auto-chain |
| Chain strategy | pending (not needed — under budget) |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Medium

Rationale: three isolated edits (SQL fragment, status-class branch, Pydantic
constraint), each under ~50 changed lines of production code, plus tests and
docs. No schema/migration, no frontend. Doc-pin sweep is many small edits
across files, not many changed lines. Session preflight sets an 800-line
budget with auto-chain — this forecast is well under it, so no chaining or
owner decision is required before apply.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Heartbeat detection-health signal (`FINISHED_WITH_EVIDENCE`) | Single PR, commit 1 | `uv run pytest -q tests/discovery/test_heartbeat.py tests/discovery/test_runs.py tests/scheduler/test_registration.py` | `uv run manga-tracker run-job heartbeat` against a DB with an in-flight `active_sweep` row | Revert `discovery/runs.py`, `discovery/heartbeat.py`, `scheduler.py` + their tests; `sweep_is_overdue`/`_last_successful_run_at` return to prior literals |
| 2 | Details-403 classification (`fetch_manga_details`) | Single PR, commit 2 | `uv run pytest -q tests/sources/test_client.py tests/sources/test_transport.py` | `POST /api/mangas/preview` against a stubbed 403 transport, confirm 503 | Revert `client.py` branch + `tests/sources/test_client.py` additions; `Unexpected`-on-any-non-200 restored |
| 3 | Empty title unwritable at the HTTP boundary | Single PR, commit 3 | `uv run pytest -q tests/web/test_add_manga_api.py` | `POST /api/mangas` with `title: "   "` against the running app, confirm 422 and zero rows | Revert `MangaAddRequest.title` constraint + its tests; `min_length=1`-only behavior restored |

Docs travel with the code they describe (per `CLAUDE.md` and `work-unit-commits`):
unit 1 carries the `spec-bot-telegram.md` bump, unit 2 carries the
`spec-cliente-fuente-descubrimiento.md` bump + the required D2/line-9
rewrite + the 7-pin sweep, unit 3 has no doc of its own (covered by unit 2's
"empty title" requirement text, already written).

## Phase 1: Heartbeat detection-health signal

- [x] 1.1 In `manga_tracker/discovery/runs.py`, add `FINISHED_WITH_EVIDENCE = "finished_at IS NOT NULL AND IFNULL(items_checked, 0) > 0"` near `open_run`, with a one-line comment pointing to the ambiguity `open_run` creates.
- [x] 1.2 RED: in `tests/discovery/test_heartbeat.py`, add a test asserting an in-flight `feed_check`/`active_sweep` row (`status='ok'`, `finished_at` NULL) is excluded from `last_successful_run_at` — must fail against today's query.
- [x] 1.3 RED: add a test for a row whose `finished_at` never closes (simulate a killed process) — same exclusion, independent of age.
- [x] 1.4 RED: add a test for a finished row with `items_checked = 0` — excluded.
- [x] 1.5 RED: add a test confirming a qualifying row (`finished_at` set, `items_checked > 0`) still reports its `started_at`.
- [x] 1.6 GREEN: in `manga_tracker/discovery/heartbeat.py`, rewrite `_last_successful_run_at`'s query to interpolate `runs.FINISHED_WITH_EVIDENCE` instead of `status = 'ok'` alone; run 1.2-1.5 to green. Leave `_last_onhold_sweep` untouched (keeps its own literal, no `items_checked` clause).
- [x] 1.7 GREEN: in `manga_tracker/scheduler.py`, replace `sweep_is_overdue`'s inline `"finished_at IS NOT NULL AND IFNULL(items_checked, 0) > 0"` with `runs.FINISHED_WITH_EVIDENCE`; keep its own `status IN ('ok', 'partial')` clause local. Existing `tests/scheduler/test_registration.py` / `tests/discovery/test_active_sweep.py` coverage for `sweep_is_overdue` must stay green unmodified.
- [x] 1.8 Break each guard on purpose, one at a time, then restore it and confirm the target test fails each time before the fix and passes after (record what failed and how, per `CLAUDE.md`): (a) drop `IFNULL(items_checked, 0) > 0` from the fragment — the zero-item test (1.4) must fail; (b) drop `finished_at IS NOT NULL` — the in-flight (1.2) and killed-run (1.3) tests must fail; (c) point the fragment at `"1=1"` — confirm both `heartbeat.py` and `scheduler.py` call sites fail their respective tests, proving the constant is load-bearing in each, not merely defined.
- [x] 1.9 `uv run pytest -q` full suite green; confirm `tests/test_architecture.py` needs no new rule (per design D1 — `scheduler.py` is top-level, only `CONCRETE_IMPLEMENTATIONS` constrains it, a SQL constant is not a concrete).
- [x] 1.10 Doc bump `docs/spec-bot-telegram.md`: v1.6 → v1.7, changelog entry stating the heartbeat now requires finished + non-empty evidence (not `status='ok'` alone), and that an equal-or-older timestamp after deploy is truthful output, not a regression — do not invent a "nunca" string; `notifier/telegram.py:92-96` already renders the null case as "ninguna todavía" and needs no code change. Update dependency pin in this file's own header if it changed (it did not — `one-pager-v1a.md` stays v1.14).
- [x] 1.11 Fix stale pins to `spec-bot-telegram.md`: `docs/runbook-mantenimiento.md:3` and `docs/one-pager-v1a.md:170` (both reference the v1.6 pin — bump to v1.7).
- [x] 1.12 Update `docs/runbook-mantenimiento.md` with a short post-deploy heartbeat expectation note (Spanish): the first post-deploy "Última detección exitosa" reading may be equal or slightly older than before, which is the fix working, not a fault.

## Phase 2: Details-403 classification

- [x] 2.1 Confirm `openspec/changes/failure-visibility/specs/source-client/spec.md` already reflects the D2-corrected taxonomy (403/429/5xx → `Transient`, other non-200 → `Unexpected`) — it does, per the 2026-08-20 amendment; no further spec edit needed here. Note this explicitly in the PR body so the reviewer does not re-flag the design's now-resolved "blocking before apply" item.
- [x] 2.2 RED: in `tests/sources/test_client.py`, add a test that `fetch_manga_details` raises `Transient` on a 403 response.
- [x] 2.3 RED: add a test that `fetch_manga_details` raises `Transient` on a 500 response.
- [x] 2.4 RED: add a test that `fetch_manga_details` raises `Unexpected` on some other non-200, non-404 status (e.g. 418) that is not in `TRANSIENT_STATUS_CODES`.
- [x] 2.5 GREEN: in `manga_tracker/sources/manganato/client.py`, import `TRANSIENT_STATUS_CODES` from `manga_tracker.sources.manganato.transport` and rewrite `fetch_manga_details`: `404` → `NotFound`; status in `TRANSIENT_STATUS_CODES` → `Transient`; any other non-200 → `Unexpected`; keep 200 → `parse_manga_details(...)` unchanged. Do not touch `transport.py` or `fetch_cover`.
- [x] 2.6 Break the guard on purpose: comment out the 403/`Transient` branch, confirm test 2.2 (and the 503-preview test in 2.9) fail, then restore it — record the result.
- [x] 2.7 Check the pinned-set interaction the design calls out: run `tests/sources/test_transport.py::test_the_transient_status_set_is_exactly_the_documented_one` (or its actual name at :582-590) unmodified and confirm it stays green — this change adds no member to `TRANSIENT_STATUS_CODES`, it only reuses it.
- [x] 2.8 Guard: temporarily add `404` to `TRANSIENT_STATUS_CODES` in a scratch/local edit, confirm the transport pin test fails, then discard the edit — record the result (proves the pin is load-bearing, not decorative).
- [x] 2.9 RED→GREEN integration: in `tests/web/test_add_manga_api.py`, add/confirm a test that `POST /api/mangas/preview` returns 503 via `_source_error` (not 200 with an empty title) when the stubbed intake's `fetch_manga_details` raises `Transient` from a 403.
- [x] 2.10 `uv run pytest -q` green for `tests/sources/` and `tests/web/`.
- [x] 2.11 Doc bump `docs/spec-cliente-fuente-descubrimiento.md`: v1.8 → v1.9, changelog entry for the details-403 classification fix and the pre-existing `fetch_cover` divergence (deliberately out of scope, unchanged).
- [x] 2.12 **Required, not optional**: rewrite the closing sentence of the bullet at `docs/spec-cliente-fuente-descubrimiento.md:9` ("La clasificación no cambia: el 403 sigue llegando como dato y sigue volviéndose 'inesperado'"), in neutral Spanish, scoped explicitly to `fetch_cover` — it currently contradicts "403 es transitorio en la taxonomía de esta spec" eleven words earlier in the same bullet. This lives in Non-Normative Notes; do not treat it as skippable prose.
- [x] 2.13 Fix all 7 stale pins to `spec-cliente-fuente-descubrimiento.md` (v1.8 → v1.9): `docs/medicion-ventana-feed.md:3`, `docs/spec-bot-telegram.md:3`, `docs/runbook-deploy.md:3`, `docs/spec-seed-manual.md:3`, `docs/spec-importador-kitsu.md:3`, `docs/one-pager-v1a.md:169`, prose at `docs/manganato-fuente-actual.md:169`.

## Phase 3: Empty title unwritable

- [ ] 3.1 RED: in `tests/web/test_add_manga_api.py`, add a test that `POST /api/mangas` with `title: ""` returns 422 and writes zero rows to `mangas`.
- [ ] 3.2 RED: add a test that `title: "   "` (whitespace-only) also returns 422 and writes zero rows — this is the case `min_length=1` alone would miss.
- [ ] 3.3 RED: add a test that a normal non-empty title still validates and reaches the existing write path unchanged (no behavior regression).
- [ ] 3.4 GREEN: in `manga_tracker/web/app.py`, change `MangaAddRequest.title: str` to `Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]` (import `Annotated` from `typing`, `StringConstraints` from `pydantic`). Note in a code comment that `strip_whitespace=True` also normalizes the stored title (matches the `TRIM(title)` production audit) — call this out as a real write-path behavior change, not a side effect to gloss over.
- [ ] 3.5 Break the guard on purpose: temporarily drop `strip_whitespace=True` (keep `min_length=1`), confirm test 3.2 fails with a written row, then restore it — record the result.
- [ ] 3.6 `uv run pytest -q tests/web/test_add_manga_api.py` green.

## Phase 4: Owner prerequisite and CLAUDE.md check (not implementer tasks)

- [ ] 4.1 **Owner action, NOT completable by the implementer.** Record in the PR body as an explicit archive prerequisite: run `SELECT id, title FROM mangas WHERE TRIM(title) = '';` against production before archiving this change. Status: UNRUN — this account has no `docker` socket permission and `data/` in the checkout is empty. Expect zero rows; any row is a pre-existing empty-title add from the sibling defect, remediation is owner-decided and out of scope here.
- [ ] 4.2 Judge whether `CLAUDE.md` §"Request policy" or §"Rules that are easy to get wrong" goes stale from this change. Conclusion to record: **no update needed** — no new job_name, no new traffic class, no change to the detection rule, retry policy, or `fetch_cover`'s divergent 403 handling; the heartbeat and client changes are read-and-raise only, not policy changes.

## Phase 5: Final verification

- [ ] 5.1 `uv run pytest -q` — full backend suite green (532+ tests plus additions).
- [ ] 5.2 `npm test` from `frontend/` — confirm untouched; no frontend files are modified by this change (no UI surface consumes `fetch_manga_details`'s exception classes directly, and `MangaAddRequest` validation surfaces as an existing 422 the frontend already handles).
- [ ] 5.3 Confirm `docs/` pin sweep is complete: grep for the old version numbers (`spec-bot-telegram.md.*v1\.6`, `spec-cliente-fuente-descubrimiento.md.*v1\.8`) across `docs/` and `one-pager-v1a.md` and confirm zero remaining stale hits outside changelog history.
