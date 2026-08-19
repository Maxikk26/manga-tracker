# Proposal: add a manga from the panel (`panel-v1b-fase-3`)

V1b fase 3. **`docs/spec-panel-v1b.md` v1.1 is the contract** — this proposal shapes the work, it does not restate the decisions. File-level detail lives in `exploration.md`; it is not repeated here.

`execution_mode: auto · artifact_store: hybrid · delivery_strategy: single-pr · review_budget_lines: 800`

| Alias | Document |
|---|---|
| PAN | `docs/spec-panel-v1b.md` v1.1 (§85-86, §95, §34-37, §128, §144, §177) |
| DM | `docs/spec-modelo-de-datos.md` v1.9 (§139-140, §291) |
| SEED | `docs/spec-seed-manual.md` — the same flow, offline; its validation list is the model |

## Intent

Adding a manga today means hand-editing `data/seed.csv` and running a CLI on the homelab. The reading list therefore only grows when the owner is at a terminal, and the one route that exists writes `origin='seed'`, which the Kitsu importer is allowed to overwrite. Fase 3 makes the panel the normal way in: paste a URL, see what the source actually matched, confirm, and the manga enters the next `active_sweep` unattended (PAN §144).

## Scope

### In scope

| # | Deliverable | Implements |
|---|---|---|
| 1 | `POST /api/mangas` — two-step: preview (no write) then confirm (write) | PAN §85, §95 |
| 2 | New writer: manga + `manga_site` + bookmark in **one** transaction, `origin='manual'`, `progress_is_approx=0`, `status_changed_at` stamped at INSERT | DM §139-140, PAN §177 |
| 3 | Cover cached during the same visit, no job | PAN §128 |
| 4 | `fetch_cover` added to the `SourceClient` Protocol (it exists on the concrete client only) | PAN §34-37 |
| 5 | `create_app` takes an injected source-side dependency; wiring stays in `cli.py` | PAN §36 |
| 6 | `DIRECTIONAL_RULES` entry for `web` + **injected-violation probe** | PAN §37 |
| 7 | Frontend: add form with preview-before-confirm, Spanish copy, Vitest coverage | PAN §29, §95 |
| 8 | Doc follow-through: PAN's "1 request por alta" is wrong (see Risks) | PAN §16 |

### Out of scope

`DELETE /api/bookmarks/{id}` — **never** (PAN §86). Editing manga metadata. Bulk add. Any schema migration. A router or client-side routing library. Re-syncing to Kitsu.

## Capabilities

### New

- `panel-add-manga`: the add endpoint, the preview contract, validation and rejection cases, the `origin='manual'` write, cover-on-add.

### Modified

- `source-client`: gains `fetch_cover` on the Protocol. `openspec/specs/` is empty, so the delta targets `openspec/changes/importador-kitsu/specs/source-client/spec.md` (the newest unarchived copy).

## Approach

Four work units, each one reviewable commit with its tests:

1. Protocol + boundary: `fetch_cover` on `SourceClient`, the new `web` directional rule, the injected-violation probe.
2. The writer: one transaction, `origin='manual'`, `status_changed_at` at INSERT, duplicate-slug refusal via `find_slug_owner`.
3. The endpoint: preview and confirm, error taxonomy, cover cached on confirm.
4. The form: URL field, initial status, initial chapter, preview panel, confirm.

**Nothing is written before the owner confirms.** `extract_slug` costs zero requests; the preview costs the ficha; confirm costs the chapters endpoint (to seal `latest_chapter_num`) plus the cover image. Duplicates and malformed URLs are refused at preview, before any request is paid for.

**The boundary is the point.** `web` names no concrete client; only `cli.py` does. The rule is proven by injecting a violation, because this repo has direct history of a boundary rule that could never match while the suite stayed green.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `manga_tracker/web/app.py`, `cli.py` | Modified | Endpoint + the one wiring line. |
| `manga_tracker/sources/contracts.py` | Modified | `fetch_cover` on the Protocol. |
| `manga_tracker/storage/repositories.py` | Modified | New writer. No existing function writes `origin='manual'`, and none stamps `status_changed_at` at INSERT — `write_seed_backfill` and `write_kitsu_bookmark` must **not** be reused as-is. |
| Layer that owns the add flow | New | Placement is an open question (see below). |
| `tests/test_architecture.py` | Modified | One rule set + one probe. |
| `frontend/src/` | New | First `<form>`, first modal-or-view-switch in the codebase. |
| `docs/spec-panel-v1b.md` | Modified | Cost row correction. Same branch as the code (CLAUDE.md). |
| Schema | None | Existing columns only. |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| **The cost figure in PAN §16 is wrong.** The add costs **three** requests (ficha for the preview, chapters to seal `latest_chapter_num`, image for the cover), not one. §16 predates the cover decision of §128 | **High** | Correct the spec row in this delivery; do not silently ship a 3× overrun against a published figure. |
| **`chapter_history.detected_via` CHECK admits only `feed`/`active_sweep`/`onhold_sweep`/`seed_backfill`.** A `'panel'` value makes every insert violate the constraint; widening it is a table rebuild | High | Reuse `seed_backfill`. `bookmarks.origin` is where `manual` belongs; the two columns are different vocabularies. |
| **Duplicate detection by slug alone is insufficient.** The 66 terminal Kitsu mangas have no `manga_sites` row, so `find_slug_owner` cannot see them and a re-add creates a second `mangas` row for a title already in the DB | Med | `importer/matching.py` already normalizes titles. Decide in design whether the preview also warns on a title match. |
| **Injecting `SourceClient` into `create_app` may read against PAN §36** ("el panel pide *agrega esto*, no *descarga esto*"). It satisfies the AST rule, but `web` then sequences the source calls itself | Med | Design decides: raw `SourceClient` vs a service protocol with `preview()`/`confirm()`. Raise, do not decide by default. |
| Error taxonomy is unspecified — PAN §77 fixes only `{"detail": ...}` | Med | Intent: `NotFound` / `Transient` / `Unexpected` / duplicate / no chapters each map to a distinct, actionable response. Exact codes belong to design. |
| Confirm needs the preview's `cover_url`; echoing it back trusts client input, re-fetching the ficha costs a fourth request | Med | Design decides. `cache_path` already allow-lists the suffix, so a hostile URL cannot choose a filename. |
| ~600-800 changed lines against an 800-line budget, `single-pr` | Med | Work-unit commits carry the review load; unit 4 is the split point if the forecast climbs. |

## Rollback Plan

No existing behaviour changes, so rollback is removal.

- Per unit: revert that commit. Units 1-2 are independently removable; 3 needs both; 4 is the UI.
- Whole change: revert the modified files. `create_app`'s new parameter must default or be dropped in the same revert, or `_cmd_panel` breaks.
- **Data**: rows this change writes are exactly `bookmarks.origin = 'manual'` and their `mangas`/`manga_sites`/`chapter_history` descendants — a surgical SQL cleanup. `reading_history` is untouched: the trigger is UPDATE-only, so an add generates no reading event, by design.
- Cached covers written by an add are files under `data/covers/`; deleting one costs one request to recover.

## Dependencies

- Fase 1 deployed (it is). Fase 2 is **not** a prerequisite: PAN §147 already broke the strict phase order for covers, and this proposal does not reopen it.
- PAN pins `spec-modelo-de-datos.md` v1.9 and `decision-arquitectura-v1b.md` v1.2 — both current.
- The source must be reachable at add time. Offline, the form can only fail; there is no queue.

## Success Criteria

- [ ] A manga added from the browser has a valid mapping and is picked up by the next `active_sweep` with no intervention (PAN §144).
- [ ] Its bookmark carries `origin='manual'`, `progress_is_approx=0`, and a non-null `status_changed_at` in `%Y-%m-%dT%H:%M:%SZ`.
- [ ] A rejected add (bad URL, duplicate slug, unknown slug, zero chapters) leaves **zero** rows in all four tables.
- [ ] The preview is shown before any write, and abandoning it writes nothing.
- [ ] The cover is on disk after the add; `GET /api/covers/{manga_id}` serves it without a fetch.
- [ ] The `web` boundary rule fails when a violation is injected.
- [ ] `uv run pytest -q` green with no network access; `npm test` and `npm run build` green.

## Proposal question round

`execution_mode: auto`, so these were not asked interactively. Each one changes the product, not the mechanics — answer before design if any assumption is wrong.

| # | Question | Assumption taken |
|---|---|---|
| 1 | A URL for a manga already in the DB as `completed`/`dropped` — is that an error, or "reactivate this"? | Error with a message naming the existing title. Reactivation is `PATCH`, which already exists. |
| 2 | A slug whose chapters endpoint returns **zero** chapters — reject, or add with `latest_chapter_num` null? | Reject, following SEED's precedent: a mapping that detects nothing is a dead row. |
| 3 | Is the initial chapter mandatory, or does it default to 0 for a manga the owner has not started? | Optional, defaults to 0. Nothing validates it against `latest_chapter_num` (PAN §50: reading ahead is legitimate). |
| 4 | On a `Transient` failure mid-preview, does the form retry itself or ask the owner to press again? | Owner presses again. Silent retries multiply requests against a source with a 5-15s delay policy. |
| 5 | Where does the form live — a modal over the grid, or its own view? | Undecided; both are greenfield (no modal, no router, no `<form>` exists today). |
