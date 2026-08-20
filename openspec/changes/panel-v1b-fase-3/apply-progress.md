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

### Remaining tasks (Slice 2) — none, see below

## Slice 2 — Repository writer, `PastedUrlIntake`, endpoints, wiring (PR 2, ~515 lines forecast)

Status: **done**. Tasks 2.1–2.7 complete, on branch `feat/add-manga-endpoint`, created from `feat/intake-boundary` (slice 1, PR 1 pending merge at the time this slice started). Slice 3 not started.

### Completed tasks

- [x] 2.1 Moved the atomic `.part`-then-`replace` cover write from `discovery/covers.py` into `storage/cover_cache.write_cover(cache_dir, manga_id, cover_url, image) -> Path`; `discovery/covers.py` now calls it. `tests/storage/test_cover_cache.py` added (atomic write, directory creation, interrupted-write safety).
- [x] 2.2 Added `MANUAL_ORIGIN = "manual"`, `IntegrityError` (re-export of `sqlite3.IntegrityError`, needed so `intake` can catch it without importing `sqlite3` itself — confined to `storage/`), `write_manual_add` and `list_tracked_titles` to `storage/repositories.py`. One transaction via the existing `transaction(conn)` context manager; zero chapters leaves `latest_chapter_num`/`_url`/`_at` NULL and writes no `chapter_history`; `last_checked_at` is still stamped (the ficha and chapters endpoint really were both visited). `tests/storage/test_write_manual_add.py` added (11 tests: write shape, zero chapters, initial-chapter-ahead legality, atomicity via a forced FK violation, `list_tracked_titles`).
- [x] 2.3 Created `manga_tracker/intake/pasted_url.py` with `PastedUrlIntake.preview()`: `extract_slug` → gates 1-2 (`find_slug_owner` + `list_tracked_titles`/`matching.slug_variants`, zero requests) → `fetch_manga_details` (1 req) → gate 3 (`matching.normalize`) → `AddPreview`. `tests/intake/test_pasted_url.py` added.
- [x] 2.4 Implemented `confirm()`: re-derives the slug from the echoed `url` (design D4, never trusted from the client), re-runs gates 1-3 (gate 3 against the echoed `title`, no re-fetch), `fetch_chapters` (1 req), `write_manual_add`, then `fetch_cover` + `cover_cache.write_cover` outside the transaction with failure tolerated. Added a safety net: a unique-index race on `write_manual_add` (`IntegrityError`) is caught and turned into `AlreadyTracked` naming the actual winner (design D3's stated intent — "turns a race into a clean 409, not a 500") — plus one test forcing that exact race via a monkeypatched `find_slug_owner`. Also added, per the slice-1 verify report's SUGGESTION: `tests/sources/test_client.py::test_fetch_cover_is_reachable_through_a_sourceclient_typed_caller`, exercising `fetch_cover` through a `SourceClient`-typed helper function rather than only the concrete class.
- [x] 2.5 Added `STATUS_LABELS` (Python mirror of the 5 Spanish labels) and `TERMINAL_STATUSES` to `web/app.py`. `tests/web/test_status_labels_parity.py` parses `statusLabels.ts` as text and asserts equality, plus a 5-entry ceiling test.
- [x] 2.6 Added `MangaPreviewRequest`/`MangaAddRequest` Pydantic models, `_conflict_response` (409 with the `existing` sibling key and terminal-aware reactivation sentence), `_source_error` (422/404/503/502 mapping), and the two endpoints `POST /api/mangas/preview` / `POST /api/mangas`, registered before the static mount. `create_app` gained a required `intake: MangaIntake` parameter. `intake/contracts.py` now re-exports `NotFound`/`Transient`/`Unexpected` from `sources.contracts` so `web` can catch them without importing `sources` (the architecture rule forbids that import entirely) — these are source-agnostic categories, not manganato knowledge. `tests/web/test_add_manga_api.py` added (15 tests, one per taxonomy row plus 201-shape and zero-rows-on-rejection checks). `tests/web/test_panel_api.py`'s fixtures updated for the new `create_app` signature (a small `_UnusedIntake` stub, since that suite never touches `/api/mangas*`).
- [x] 2.7 `_bootstrap`'s docstring corrected (it now also serves `panel`, not just job-running subcommands). `_cmd_panel` now calls `_bootstrap`, constructs `PastedUrlIntake(client, site_id, cache_dir_for(...))`, and passes it into `create_app`. `tests/test_cli.py`'s panel-wiring test updated to assert an injected `PastedUrlIntake` instance reaches `create_app`. Manual smoke: started `python -m manga_tracker panel` with `DB_PATH=data/.smoke-slice2.db PANEL_PORT=8199` (a throwaway DB and a port distinct from the owner's running dev panel on :8000); `POST /api/mangas/preview` with a `/genre/action` URL returned `422` with the exact taxonomy `detail` string; `GET /api/bookmarks` returned `[]`. Process killed and the throwaway DB removed afterward; verified :8000 still answered normally throughout.

### Files changed (Slice 2)

| File | Action | What was done |
|------|--------|---------------|
| `manga_tracker/storage/cover_cache.py` | Modified | Added `write_cover` |
| `manga_tracker/discovery/covers.py` | Modified | Calls `write_cover` instead of inlining the atomic write |
| `tests/storage/test_cover_cache.py` | Created | 4 tests |
| `manga_tracker/storage/repositories.py` | Modified | Added `MANUAL_ORIGIN`, `IntegrityError` re-export, `write_manual_add`, `list_tracked_titles` |
| `tests/storage/test_write_manual_add.py` | Created | 11 tests |
| `manga_tracker/intake/pasted_url.py` | Created | `PastedUrlIntake` (`preview`, `confirm`, the three gates, race-safety net) |
| `tests/intake/test_pasted_url.py` | Created | 25 tests |
| `tests/sources/test_client.py` | Modified | Added the Protocol-typed `fetch_cover` test (slice-1 verify SUGGESTION) |
| `manga_tracker/intake/contracts.py` | Modified | Re-exports `NotFound`/`Transient`/`Unexpected` for `web` |
| `manga_tracker/web/app.py` | Modified | `STATUS_LABELS`, `TERMINAL_STATUSES`, request models, `_conflict_response`, `_source_error`, the two endpoints; `create_app` gained `intake: MangaIntake` |
| `tests/web/test_status_labels_parity.py` | Created | 2 tests |
| `tests/web/test_add_manga_api.py` | Created | 15 tests |
| `tests/web/test_panel_api.py` | Modified | `_UnusedIntake` stub for the new `create_app` signature |
| `manga_tracker/cli.py` | Modified | `_bootstrap` docstring correction, `_cmd_panel` wiring, import ordering |
| `tests/test_cli.py` | Modified | Panel-wiring test asserts an injected `PastedUrlIntake` |
| `openspec/changes/panel-v1b-fase-3/tasks.md` | Modified | Tasks 2.1–2.7 marked `[x]` |

### Commits (branch `feat/add-manga-endpoint`, off `feat/intake-boundary`)

1. `5a2776b` — `refactor(storage): move the atomic cover write into cover_cache.write_cover`
2. `f0c10e2` — `feat(storage): add write_manual_add and list_tracked_titles`
3. `d789d7a` — `feat(intake): implement PastedUrlIntake.preview with the three duplicate gates`
4. `7def7dc` — `feat(intake): implement PastedUrlIntake.confirm with the atomic write and cover fetch`
5. `4149820` — `feat(web): mirror the Spanish status labels and pin the parity to the frontend`
6. `77a4101` — `feat(web): add POST /api/mangas/preview and POST /api/mangas endpoints`
7. `ec68fdf` — `feat(cli): wire PastedUrlIntake into the panel command`

### Work Unit Evidence (Slice 2)

| Evidence | Value |
|---|---|
| Focused test command and result | `uv run pytest tests/storage tests/intake tests/web -q` → 91 passed |
| Full suite | `uv run pytest -q` → 492 passed, 1 pre-existing warning (starlette/httpx deprecation, unrelated) |
| Runtime harness | `DB_PATH=data/.smoke-slice2.db PANEL_PORT=8199 python -m manga_tracker panel`, then `curl -X POST http://127.0.0.1:8199/api/mangas/preview -d '{"url":"https://www.manganato.gg/genre/action"}'` → `422` with the exact `InvalidUrl` taxonomy message; `curl http://127.0.0.1:8199/api/bookmarks` → `[]`. Process killed, throwaway DB removed; the owner's dev panel on :8000 verified unaffected before and after. |
| Rollback boundary | Revert `manga_tracker/intake/pasted_url.py`, the two endpoints + request models + `STATUS_LABELS`/`TERMINAL_STATUSES` in `web/app.py` (and its `create_app` signature back to one arg), the `cli.py` wiring in `_cmd_panel`, `write_manual_add`/`list_tracked_titles`/`IntegrityError` in `repositories.py`, `cover_cache.write_cover` (reverting `discovery/covers.py`'s call site too), the `NotFound`/`Transient`/`Unexpected` re-export in `intake/contracts.py`, and all seven new/modified test files. Slice 1 (Protocol, `intake` skeleton, architecture rule) stays intact and unused by nothing else if this slice is rolled back. |

### Deviations from design (Slice 2)

- Design's Interfaces block doesn't specify how `web` catches `NotFound`/`Transient`/`Unexpected` given the widened rule forbidding `web` from importing `sources` at all. Resolved by re-exporting the three exception classes from `intake/contracts.py` (they are source-agnostic categories per `sources/contracts.py`'s own docstrings, not manganato knowledge) — `web` imports them from there, never from `sources` directly. This satisfies the AST-level architecture check (which inspects each file's own import statements, not transitive origins) and keeps `web`'s only import surface as `intake.contracts`, matching the design's stated intent literally.
- Added a safety net in `confirm()` for a unique-index race on `write_manual_add` (catches `IntegrityError`, re-reads the actual owner, raises `AlreadyTracked`) beyond what task 2.4's literal test list required — this is design D3's own explicit sentence ("idx_manga_sites_site_source_key is the last line of defence and turns a race into a clean 409, not a 500"), so implemented and covered by one added test rather than left as a latent 500.
- `create_app`'s signature change (`intake: MangaIntake` added) is listed under task 2.7 in `tasks.md`, but the endpoints added in task 2.6 could not be written or tested without it — implemented as part of the 2.6 commit instead, with `cli.py`'s wiring (constructing the concrete `PastedUrlIntake`) staying in the 2.7 commit as written. No behavior difference from what the tasks intended, just which commit the signature line landed in.
- `last_checked_at` is stamped in `write_manual_add` even when `chapters` is empty (design's D5 table only requires `latest_chapter_num`/`_url`/`_at` to stay NULL). Chosen because the confirm operation genuinely queried the chapters endpoint and got an authoritative empty answer — recorded as a design decision in this file rather than silently done.

### Issues found (Slice 2)

None.

## Slice 3 — Frontend modal, container integration, Vitest coverage (PR 3, ~725 lines forecast)

Status: **done**. Tasks 3.1–3.8 complete, on branch `feat/add-manga-modal`, created from `feat/add-manga-endpoint` (slice 2, PR 2 pending merge at the time this slice started). This is the last slice of the change.

### Completed tasks

- [x] 3.1 Created `frontend/src/api/http.ts`: `ApiError` (now carrying an optional `existing: ExistingManga`) and `readDetail` (now returning `{detail, existing?}`), moved out of `bookmarks.ts`. `bookmarks.ts` imports from it and re-exports `ApiError` so existing importers do not churn. `frontend/src/api/http.test.ts` added (9 tests: plain detail, `existing` parsing, a malformed `existing` ignored, unparsable body, `ApiError` carrying/omitting `existing`).
- [x] 3.2 Created `frontend/src/api/mangas.ts`: `previewManga(url)` / `addManga(body) -> Bookmark`, both routing non-ok responses through `readDetail` so a 409's `existing` survives as `ApiError.existing`; network failures map to the same Spanish-copy pattern `bookmarks.ts` already uses. `frontend/src/api/mangas.test.ts` added (6 tests: request bodies, 409 `existing` propagation for both preview and confirm, network-failure mapping).
- [x] 3.3 Extended `frontend/src/domain/types.ts`: `MangaPreview` (incl. `publication_status_text`), `MangaAdd` request type, `ExistingManga` — the typed wire contracts for `POST /api/mangas{,/preview}`, matching `web/app.py`'s actual response/request shapes (verified against the slice-2 code, not the design's prose).
- [x] 3.4 Created `frontend/src/components/AddMangaModal.tsx`: pure `<div role="dialog" aria-modal="true">` chrome (not `<dialog>`, per design — jsdom's `showModal` is uneven) + `<form>` (URL required/autofocused, status `<select>` over `BOOKMARK_STATUSES`/`STATUS_LABELS`, optional initial-chapter number input `min=0` defaulting to `0`, confirm disabled until a preview exists) + a preview panel (title, cover `<img>` with an `onError` fallback to a "Sin portada" placeholder, `publication_status_text` as muted secondary text) + the duplicate/terminal `Ver en «{label}»` affordance shown alongside the Spanish `errorMessage` when `existing` is present. Escape and backdrop-click request a close that is ignored while `previewing || confirming`; entrance (200ms) and exit (140ms) both use the design's own `cubic-bezier(0.23, 1, 0.32, 1)` curve (added as a new `--ease-modal` CSS variable, kept separate from the existing `--ease-out` token used by the cover hover), never `scale(0)`, and a `prefers-reduced-motion` block strips the transform and keeps only the opacity transition. `frontend/src/components/AddMangaModal.test.tsx` added (10 tests).
- [x] 3.5 Created `frontend/src/containers/AddMangaContainer.tsx`: owns `url`/`status`/`lastChapterRead`, the preview and confirm round-trips, `errorMessage`, and `existing`. Editing the URL after a preview (or after a rejection) clears `preview`/`existing`/`errorMessage`, so a stale preview can never be confirmed against an edited URL. `frontend/src/containers/AddMangaContainer.test.tsx` added (3 tests: preview→confirm request bodies, the terminal-409 reactivation sentence and its button calling `onViewExisting` with the raw status, and abandoning a shown preview by editing the URL sending zero confirm requests).
- [x] 3.6 Modified `frontend/src/containers/BookmarkListContainer.tsx`: added an "Agregar manga" button beside `StatusTabs` inside a new `.panel-toolbar` row, and conditionally mounts `AddMangaContainer`. On success: close the modal, `setActiveStatus(added.status)`, and fire `load(false)` for the full refetch. On the "Ver en «…»" affordance: close the modal and switch to that existing status tab, with zero confirm requests. Extended `BookmarkListContainer.test.tsx` with +3 cases (renamed `jsonResponse` to accept an optional status for the 201 case).
- [x] 3.7 Modified `frontend/src/styles.css`: the `.panel-toolbar`/`.add-manga-button` styles, and the full modal/backdrop/form/preview-panel rule set (`.modal-backdrop`, `.modal`, `.modal-field`, `.modal-error`, `.modal-view-existing`, `.modal-preview*`, `.modal-actions`, `.modal-cancel/-submit/-confirm`), plus the new `--ease-modal` token. No dedicated test file — covered by `AddMangaModal.test.tsx`'s behavior assertions (class toggling, disabled states).
- [x] 3.8 Ran `npm run build` (`tsc --noEmit && vite build`) and `npm test` end to end — both green — and `uv run pytest -q` to confirm the untouched backend suite stayed green.

### Files changed (Slice 3)

| File | Action | What was done |
|------|--------|---------------|
| `frontend/src/api/http.ts` | Created | `ApiError` (+`existing`), `readDetail` (returns `{detail, existing?}`) |
| `frontend/src/api/http.test.ts` | Created | 9 tests |
| `frontend/src/api/bookmarks.ts` | Modified | Imports `ApiError`/`readDetail` from `http.ts`, re-exports `ApiError`, updated the two `readDetail` call sites for the new return shape |
| `frontend/src/api/mangas.ts` | Created | `previewManga`, `addManga` |
| `frontend/src/api/mangas.test.ts` | Created | 6 tests |
| `frontend/src/domain/types.ts` | Modified | `MangaPreview`, `MangaAdd`, `ExistingManga` |
| `frontend/src/components/AddMangaModal.tsx` | Created | Pure dialog chrome, form, preview panel, duplicate affordance, entrance/exit animation |
| `frontend/src/components/AddMangaModal.test.tsx` | Created | 10 tests |
| `frontend/src/containers/AddMangaContainer.tsx` | Created | url/status/chapter state, preview/confirm calls, error/`existing` state |
| `frontend/src/containers/AddMangaContainer.test.tsx` | Created | 3 tests |
| `frontend/src/containers/BookmarkListContainer.tsx` | Modified | Toolbar button, conditional `AddMangaContainer` mount, success/duplicate handlers |
| `frontend/src/containers/BookmarkListContainer.test.tsx` | Modified | +3 tests (`jsonResponse` gained an optional `status` parameter) |
| `frontend/src/styles.css` | Modified | Toolbar, modal/backdrop/form/preview rules, `--ease-modal` token |
| `openspec/changes/panel-v1b-fase-3/tasks.md` | Modified | Tasks 3.1–3.8 marked `[x]` |

### Commits (branch `feat/add-manga-modal`, off `feat/add-manga-endpoint`)

1. `12026ca` — `feat(frontend): extract api/http.ts and add the add-manga wire types`
2. `bd8e2dd` — `feat(frontend): add the mangas API client (preview/confirm)`
3. `ee53487` — `feat(frontend): add the AddMangaModal component and its styles`
4. `ba1a898` — `feat(frontend): add AddMangaContainer wiring preview/confirm state`
5. `14121b8` — `feat(frontend): wire the add-manga modal into BookmarkListContainer`
6. `071e640` — `docs(tasks): mark slice 3 tasks 3.1-3.8 complete`

### Work Unit Evidence (Slice 3)

| Evidence | Value |
|---|---|
| Focused test command and result | `npm test` (Vitest) → 9 test files, 82 tests passed |
| Full frontend build | `npm run build` (`tsc --noEmit && vite build`) → clean, no type errors, `dist/` produced |
| Backend regression check | `uv run pytest -q` → 492 passed, 1 pre-existing warning (unrelated, same as slice 2) — confirms the untouched Python backend stayed green |
| Runtime harness | `npm run build` then the manual click-through described in tasks.md's work-unit table (paste URL → preview → confirm → grid refetch) was exercised indirectly via `BookmarkListContainer.test.tsx`'s new integration cases (real fetch stubs, real DOM, real state transitions) rather than a live click-through against the owner's running :8000/:5173 processes, per the environment note that those must not be restarted or interfered with. The component/container/integration test layers together already exercise every step of that path against the actual wire shapes read from `web/app.py`. |
| Rollback boundary | Revert `frontend/src/api/http.ts`, `frontend/src/api/mangas.ts` (+ their tests), the `domain/types.ts` additions, `frontend/src/components/AddMangaModal.tsx` (+ test), `frontend/src/containers/AddMangaContainer.tsx` (+ test), the `BookmarkListContainer.tsx`/`.test.tsx` edits, and the `styles.css` additions. `bookmarks.ts`'s two-line import change also reverts. Slices 1–2 (backend) keep working via `curl` with no frontend at all, exactly as tasks.md's own rollback note for this unit states. |

### Deviations from design (Slice 3)

- **No explicit "Preview"-vs-"Confirm" trigger was specified in design's Modal UX section beyond "confirm disabled until a preview exists".** Implemented the URL field inside a `<form>` whose `onSubmit` runs the preview (so Enter in the field and a visible "Vista previa" submit button both trigger it), with a separate always-visible `type="button"` "Agregar" action gated on `preview !== null`. This is an interaction-design decision the design text left open; noted rather than silently invented.
- **Closing the modal on a successful add is not animated.** The entrance/exit transition (200ms/140ms) is fully implemented for Escape/backdrop/Cancelar dismissal, but `BookmarkListContainer.handleAdded` unmounts `AddMangaContainer` immediately on success rather than routing through `AddMangaModal`'s internal exit-transition timer. Design's Modal UX decisions describe the transition mechanics generally without stating whether a successful confirm's close is animated; keeping it instant avoids an artificial 140ms delay before the grid's refetched state is visible, and keeps the success-path tests deterministic without `waitFor`/fake-timer machinery. If the owner wants the animated close on success too, `BookmarkListContainer` would route `handleAdded`'s modal-closing step through the same `onRequestClose` timer path instead of `setAddModalOpen(false)` directly.
- **The cover-fetch-failure fallback renders a text placeholder ("Sin portada")** rather than reusing `BookmarkCard`'s gradient-plus-initials treatment. The design only specifies "the same `onError` fallback branch `BookmarkCard.tsx:30` already uses" for the *mechanism* (an `onError`-driven state flag degrading gracefully), not the exact visual; a full initials-gradient treatment felt like more chrome than a transient preview panel warrants. Noted as a design judgment call, not a gap.
- **`AddMangaContainer`'s `onAdded`/`onViewExisting`/`onRequestClose` props are synchronous (`void`-returning)** even though `handleAdded` internally fires `load(false)` (async, self-contained error handling) without awaiting it from the callback boundary — matching the existing `handleChangeProgress`/`handleChangeStatus` `void applyPatch(...)` fire-and-forget pattern already in this file, rather than introducing a new async-prop convention.

### Issues found (Slice 3)

None.

### Workload / PR boundary (cumulative)

- Mode: chained PR slice (stacked-to-main), per tasks.md Review Workload Forecast
- Slice 1: PR 1 of 3, done, ~395-line forecast (branch `feat/intake-boundary`, off `main`)
- Slice 2: PR 2 of 3, done, ~515-line forecast — actual `git diff feat/intake-boundary --shortstat`: 16 files changed, 1334 insertions(+), 33 deletions(-). Materially over forecast, same root cause design.md's own Changed-Lines Forecast names for the whole change: this repo's modules run ~40% comment by line and "always do testing" puts most of the growth in tests (68 of the ~90 new test cases across this slice's 7 new/modified test files). Flagged as a risk for the orchestrator; not re-split without a new delivery decision, since the three-slice stack was already resolved by the owner before apply and re-slicing mid-slice was outside this batch's assignment.
- Slice 3: PR 3 of 3, done, ~725-line forecast — actual `git diff feat/add-manga-endpoint --shortstat`: 14 files changed, 1329 insertions(+), 26 deletions(-) (≈1355 changed lines). Same overage pattern as slice 2: of the 1321 lines touched in `frontend/src`, ~570 are the five new/modified test files (82 total Vitest cases in the suite after this slice, up from 59 before it) and the rest split across a genuinely new modal/container/API surface plus ~250 lines of CSS for the modal chrome and its animation states. Flagged as a risk for the orchestrator, same as slice 2 — not re-split mid-slice for the same reason (the three-slice stack was already an owner-resolved decision before apply).

### Status

18/18 total tasks across the full change complete (Slice 1: 5/5, Slice 2: 7/7, Slice 3: 8/8). Ready for `sdd-verify` on the whole change, or for PR 3 to open against `feat/add-manga-endpoint` (once PR 2 merges, the orchestrator rebases this branch — not done here). No further apply work remains for `panel-v1b-fase-3`.
