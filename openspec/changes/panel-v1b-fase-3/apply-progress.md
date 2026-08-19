# Apply Progress: `panel-v1b-fase-3`

## Slice 1 — Protocol, `intake` skeleton, architecture rule (PR 1, ~395 lines forecast)

Status: **done**. Tasks 1.1–1.5 complete. Slices 2 and 3 not started.

### Completed tasks

- [x] 1.1 `fetch_cover(cover_url: str) -> bytes` added to the `SourceClient` Protocol (`manga_tracker/sources/contracts.py`).
- [x] 1.2 New `manga_tracker/intake/` package: `contracts.py` with `MangaIntake` Protocol (`preview`, `confirm`), frozen `AddPreview` (incl. `publication_status_text`) and `AddResult` dataclasses, `InvalidUrl` and `AlreadyTracked(title, status)` exceptions. `tests/intake/test_contracts.py` added (7 tests: frozen dataclasses, publication_status_text passthrough, optional fields, zero-chapters/uncached-cover legality, `AlreadyTracked` attributes).
- [x] 1.3 `tests/test_architecture.py`: `DIRECTIONAL_RULES["web"]` widened to all of `sources`/`notifier`/`discovery`/`catalogue`/`importer`/`seed` plus the exempted concrete `intake.pasted_url`; new `DIRECTIONAL_RULES["intake"]` forbids the concrete source client and reaching into `web`; both packages added to the forbidden sets of `sources`/`notifier`/`storage`/`catalogue`.
- [x] 1.4 Four new probes in `test_boundary_check_flags_an_injected_violation` (`intake/probe.py`, `web/probe2.py`, `web/probe3.py`, `web/probe4.py` — the last one the spec-mandated verbatim case); expected sorted-violation list grew 3 → 7 entries; `intake.pasted_url` added to `CONCRETE_IMPLEMENTATIONS`.
- [x] 1.5 `docs/spec-panel-v1b.md` §16 cost row corrected (fase 3: 1 → 3 requests per add); version bumped 1.1 → 1.2 (2026-08-19); changelog entry added; open-pendings note added recording the three-PR stacked delivery and that the endpoint does not exist yet. Stale `v1.1` pins in `docs/runbook-desarrollo-local.md` and `docs/runbook-deploy.md` corrected to `v1.2` per CLAUDE.md's stale-pin rule.

### Files changed

| File | Action | What was done |
|------|--------|---------------|
| `manga_tracker/sources/contracts.py` | Modified | Added `fetch_cover(cover_url: str) -> bytes` to `SourceClient` Protocol |
| `manga_tracker/intake/__init__.py` | Created | Empty package marker (matches existing `catalogue/__init__.py` convention) |
| `manga_tracker/intake/contracts.py` | Created | `MangaIntake` Protocol, `AddPreview`/`AddResult` frozen dataclasses, `InvalidUrl`/`AlreadyTracked` exceptions |
| `tests/intake/test_contracts.py` | Created | 7 tests covering frozen dataclasses and `AlreadyTracked` |
| `tests/test_architecture.py` | Modified | Widened `web` rule, new `intake` rule, four new forbidden-set memberships, four new probes, 7-entry violation list, `intake.pasted_url` in `CONCRETE_IMPLEMENTATIONS` |
| `docs/spec-panel-v1b.md` | Modified | §16 cost row correction, version 1.1 → 1.2, changelog entry, open-pendings note |
| `docs/runbook-desarrollo-local.md` | Modified | Pin `spec-panel-v1b.md` v1.1 → v1.2 |
| `docs/runbook-deploy.md` | Modified | Pin `spec-panel-v1b.md` v1.1 → v1.2 |
| `openspec/changes/panel-v1b-fase-3/{proposal,design,exploration,tasks}.md`, `specs/**/spec.md` | Created (first commit) | SDD planning artifacts, committed on this branch per CLAUDE.md's "branch is a unit of delivery" rule |

### Commits (branch `feat/intake-boundary`, off `main`)

1. `de6ae82` — `docs(openspec): add panel-v1b-fase-3 SDD artifacts`
2. `dba82b1` — `feat(sources): declare fetch_cover on the SourceClient protocol`
3. `bc5d0c0` — `feat(intake): add MangaIntake contracts and package skeleton`
4. `bbfb8df` — `test(architecture): widen the web/intake boundary and prove it`
5. `8ebd123` — `docs(panel-v1b): correct fase 3's cost row to 3 requests per add`
6. (pending) — `docs(tasks): mark slice 1 tasks 1.1-1.5 complete`

### Work Unit Evidence

| Evidence | Value |
|---|---|
| Focused test command and result | `uv run pytest tests/test_architecture.py tests/intake tests/discovery/test_covers.py -q` → 39 passed |
| Full suite | `uv run pytest -q` → 441 passed, 1 pre-existing warning (starlette/httpx deprecation, unrelated) |
| Runtime harness | N/A — no runnable endpoint yet; this slice is structural only (Protocol + contracts + architecture rule), per the tasks.md work-unit table |
| Rollback boundary | Revert `manga_tracker/sources/contracts.py`'s `fetch_cover` addition, `manga_tracker/intake/`, `tests/intake/`, the `tests/test_architecture.py` rule/probe additions, and the `docs/` correction commit. Nothing downstream depends on any of it yet — `intake.pasted_url` (Slice 2) does not exist, so the widened `web` rule and the `intake` rule currently have no real importer to break. |

### Deviations from design

- Design's own "Suggested Work Units" / "Changed-Lines Forecast" tables describe Slice 1 as including `cover_cache.write_cover`, `storage.write_manual_add`, and `storage.list_tracked_titles`. The authoritative `tasks.md` Slice 1 section (tasks 1.1–1.5, the literal work assignment) does **not** include those — they are tasks 2.1/2.2 in Slice 2. Followed `tasks.md` as the binding task list; no repository writer code was added in this slice. Flagging this discrepancy between design's forecast table and tasks.md's actual assignment for whoever picks up Slice 2.
- Added two one-line pin corrections outside the literal task 1.5 file list (`docs/runbook-desarrollo-local.md`, `docs/runbook-deploy.md`) to keep `spec-panel-v1b.md`'s version pin consistent, per CLAUDE.md's explicit stale-pin rule ("a stale pin is what let `daily_sweep` survive... through v1.0"). Minimal, mechanical, no other content touched.

### Issues found

None.

### Remaining tasks (Slice 2, not started)

- [ ] 2.1 `storage/cover_cache.write_cover` + `discovery/covers.py` update
- [ ] 2.2 `storage/repositories.py`: `write_manual_add`, `list_tracked_titles`
- [ ] 2.3 `intake/pasted_url.py`: `preview()`
- [ ] 2.4 `intake/pasted_url.py`: `confirm()`
- [ ] 2.5 `web/app.py` status-label mirror + parity test
- [ ] 2.6 `web/app.py`: `POST /api/mangas/preview`, `POST /api/mangas`
- [ ] 2.7 `create_app`/`cli.py` wiring

### Workload / PR boundary

- Mode: chained PR slice (stacked-to-main), per tasks.md Review Workload Forecast
- Current work unit: Slice 1 (PR 1 of 3)
- Boundary: starts from `main` (branch was identical to main), ends with Slice 1 fully green and tasks 1.1–1.5 marked done
- Estimated review budget impact: `git diff main --shortstat` reported below; within the ~395-line Slice 1 forecast

### Status

5/5 Slice 1 tasks complete (18/... total tasks across the full change). Ready for `sdd-verify` on Slice 1, or for PR 1 to open against `main`. Slice 2 (`feat/intake-boundary` follow-up branch, stacked on this one) is the next recommended work.
