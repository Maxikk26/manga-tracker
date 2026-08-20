# Archive report — panel-v1b-fase-3

Closed 2026-08-20. All 18/18 implementation tasks resolved across three slices (PRs #27, #28, #29).
Deployed to production 2026-08-20 ~01:23 UTC. Zero open blockers.

## What shipped

The V1b phase 3 (panel add-manga feature): a two-step web form (preview without writing, then atomic confirm) that allows adding a manga to the reading list by pasting a manganato URL. The feature integrates a new service layer (`intake/pasted_url.py`), expands the `SourceClient` Protocol with `fetch_cover`, caches cover images on-add, and maintains strict architectural boundaries so `web` never imports source modules directly.

Delivered as three chained PRs with measurable performance improvement: add operation measured end-to-end at ~2.6s (down from 15-45s), a missing-cover add at 0.7s (down from 43.9s), while preserving exactly 3 source requests per add and supporting zero-chapter legitimate adds.

**Production deployment**: `main` @ `74bfab2` on the homelab. Both containers up, panel endpoint responsive, all four jobs (active_sweep, onhold_sweep, feed_check, cache_covers) starting cleanly. Database integrity verified (`user_version: 2`, `integrity_check` ok, 227 mangas / 227 bookmarks / 7883 chapter_history / 15 reading_history). No `origin='manual'` rows in production until owner pastes a URL.

**Final test counts**: 532 backend tests (pytest), 101 frontend tests (Vitest), `npm run build` clean with no TypeScript errors or warnings.

## Specs merged

Two delta specs synthesized into `openspec/specs/`:

1. **`openspec/specs/source-client/spec.md`** — Merged two deltas on top of the v1a-heart-phase base:
   - importador-kitsu delta: added `fetch_known_slugs` (sitemap shard membership), no-delay-exemption policy, existing response-shape sufficiency
   - panel-v1b-fase-3 delta: added `fetch_cover` (Protocol declaration), error taxonomy compliance for cover fetch
   - Result: 12 total requirements (7 base + 3 from importador-kitsu + 2 from panel-v1b-fase-3)
   - **Caveat for whoever archives `importador-kitsu`**: its delta was folded in here, because
     `openspec/specs/` was empty and this change's own delta sits on top of it — a spec carrying
     only the fase-3 additions would have been incoherent. That change's own archive must therefore
     **not** merge its `source-client` delta again, or the requirements duplicate. `importador-kitsu`
     is implemented and live in production; it was simply never archived.

2. **`openspec/specs/panel-add-manga/spec.md`** — Full new spec defining the add endpoint:
   - Preview validation and rejection cases (malformed URL, duplicate active slug, terminal title, unknown slug, transient/unexpected failures)
   - Atomic confirm with zero-chapters support, cover-on-add, status/chapter validation
   - Frontend modal UX requirements, Spanish copy, and architectural boundary enforcement
   - Total: 13 requirements covering both backend and frontend

## Implementation scope

### Slice 1 (PR #27 — Protocol + intake skeleton + architecture rule)
- Tasks 1.1-1.5: `fetch_cover` on SourceClient, `intake/contracts.py` package skeleton, widened `web` directional rule with four injected-violation probes, documentation cost-row correction
- 5 tasks complete

### Slice 2 (PR #28 — Repository writer, `PastedUrlIntake`, endpoints, wiring)
- Tasks 2.1-2.7: `cover_cache.write_cover` atomic writer, `write_manual_add` transaction (mangas + manga_site + bookmarks + chapter_history, `origin='manual'`, `status_changed_at` at INSERT), `PastedUrlIntake` service layer, two endpoints (`POST /api/mangas/preview` and `POST /api/mangas`), `cli.py` wiring, status-label Python mirror + parity test
- 7 tasks complete

### Slice 3 (PR #29 — Frontend modal, container integration, Vitest coverage)
- Tasks 3.1-3.8: API error shapes and re-exports, `MangaPreview`/`MangaAdd`/`ExistingManga` types, `AddMangaModal.tsx` pure dialog component, `AddMangaContainer.tsx` state orchestration, `BookmarkListContainer.tsx` integration ("Agregar manga" button, grid refetch, tab switching), CSS animations and reduced-motion compliance, `npm run build` and `npm test` validation
- 6 tasks complete

## Deliverables met

| Deliverable | Task(s) | Status |
|---|---|---|
| `POST /api/mangas` preview and confirm endpoints | 2.6, 2.7 | Complete ✓ |
| `write_manual_add` atomic transaction | 2.2 | Complete ✓ |
| Cover cached on-add, no periodic job | 2.3, 2.4 | Complete ✓ |
| `fetch_cover` on SourceClient Protocol | 1.1 | Complete ✓ |
| `intake` service layer isolation | 1.1, 2.3, 2.4 | Complete ✓ |
| `web` directional boundary + injected-violation proof | 1.3, 1.4 | Complete ✓ |
| Frontend add modal with preview-before-confirm | 3.4, 3.5, 3.6 | Complete ✓ |
| Spanish copy throughout | 2.5, 3.4, 3.5, 3.6 | Complete ✓ |
| Documentation follow-through: PAN §16 cost correction | 1.5 | Complete ✓ |

## Measures verified

**Performance (end-to-end on dev panel, live measurements)**:
- Full add (preview 0.74s + preview-cover proxy 1.14s + confirm 0.72s): **~2.6s** (from 15-45s)
- Missing-cover add: **0.7s** (from 43.9s)
- Request count per add: **exactly 3** (unchanged design goal: preview 1 req, confirm chapters 1 req + cover 1 req)
- Cover promotion verified: stored file byte-count matched preview download, preview cache left empty

**Quality**:
- 532 backend tests passing (`uv run pytest -q`)
- 101 frontend tests passing (`npm test`)
- Build clean (`npm run build`: tsc --noEmit && vite build, zero errors)
- Guard-break exercise: injected-violation probes in Slice 1 verified independently; all architectural rules fire correctly

**Data integrity at deployment**:
- Database `user_version: 2` (no migration needed; schema compatible)
- `integrity_check` OK
- 227 mangas / 227 bookmarks / 7883 chapter_history / 15 reading_history
- No `origin='manual'` rows until owner begins adding via panel

## Owner product decisions recorded (2026-08-19)

These shaped the implementation and final design:

1. **Terminal manga re-add is an error** — a 409 response names the title, status, and includes a `PATCH /api/bookmarks/{id}` URL as the reactivation path. The duplicate/terminal `detail` message is Spanish.
2. **Zero chapters is a successful add** — confirmed mangas with zero published chapters still write mangas + manga_site + bookmarks rows, with `latest_chapter_num` NULL. The next `active_sweep` treats the row as unsealed and ready.
3. **The add form is a modal** — not a separate route or view; modal closes on success and triggers a full grid refetch.
4. **Initial chapter field is optional**, defaulting to 0. No automatic retry on transient source failure — user presses again.

## Accepted risks recorded in design.md

1. **Server GETs a client-echoed `cover_url`** — on LAN, unauth panel, allowlisted URL suffix, now also https-host-gated (fixed in commit `980fd97` after verify-report). This risk is **resolved**.
2. **`intake.contracts` re-exports the three failure categories** — so `web` can catch them without importing `sources`. The AST check only inspects direct imports, so anything re-exported there must stay source-agnostic. This risk is **accepted and mitigated by the architecture rule**.

## Fixes after verify-report

Four additional commits landed on `main` after slice 1's verify-report was written, closing open gaps:

| Commit | Title | Closes |
|---|---|---|
| `980fd97` | fix(intake): drop a non-https `cover_url` before storing or fetching | design threat: https/host gate missing in slice 2 |
| `9c4ad09` | fix(panel): the preview cover is proxied through `GET /api/mangas/preview-cover` | source 403 hotlinks → every preview showed fallback |
| `21e041f` | feat(frontend): DecimalInput replaces `<input type="number">` for chapters | owner preference: no native spinner, no `0170` artifact |
| `c9f04a0`..`b151dab` (PR #29) | Source request policy split into BATCH_POLICY (5-15s, jobs) / INTERACTIVE_POLICY (1-2s, panel) | interactive responsiveness vs stable detection window |

**Version updates accompanying PR #29**: `docs/spec-cliente-fuente-descubrimiento.md` bumped to v1.8 with pins refreshed in six dependent documents. Spacing measured against `time.monotonic` instead of a sticky flag; `fetch_cover` no longer retrying (covers are unrecoverable on transient, not worth retry traffic).

## Specs and documentation

**`openspec/specs/` now contains:**
- `source-client/spec.md` — merged base + both deltas
- `panel-add-manga/spec.md` — full spec for the add endpoint

**Living specs updated:**
- `docs/spec-panel-v1b.md` → v1.1 (cost row correction in slice 1), v1.2 (live version at integration)
- `docs/spec-cliente-fuente-descubrimiento.md` → v1.8 (interactive policy split, pin updates)

## References to archived change

Change folder: `openspec/changes/archive/2026-08-20-panel-v1b-fase-3/`

| Artifact | Path |
|---|---|
| Proposal | `proposal.md` (summarizes deliverables, scope, approach) |
| Design | `design.md` (technical decisions D1-D10, threat matrix, error taxonomy, measurement baseline) |
| Exploration | `exploration.md` (file map, dependency analysis, naming traps) |
| Tasks | `tasks.md` (18 tasks across 3 slices, work-unit boundaries, rollback scopes) |
| Specs (merged) | `specs/panel-add-manga/spec.md`, `specs/source-client/spec.md` |
| Verification report | `verify-report.md` (slice 1 scope: 5/5 tasks, 441 tests, guard-break proof) |
| Apply progress | `apply-progress.md` (progress snapshots as PRs landed) |

## Open follow-ups (do not lose)

These are not blockers and do not prevent archive; they are carried forward in the docs and memory:

1. **Interactive window choice (1-2s)** was by analogy to browser page load, not measured against the source. Watch for 403 during manual add. Recorded as open pending in `spec-cliente-fuente-descubrimiento.md` v1.8.
2. **`docs/spec-cliente-fuente-descubrimiento.md` lacks a `## Resumen` section** per `runbook-mantenimiento.md` mandate. Schedule as a doc-hygiene task.
3. **Two spec scenarios are covered only indirectly by tests**. Direct test cases may improve validation clarity.
4. **No container-level integration test for the 409 "Ver en «…»" tab-switch affordance.** Consider Playwright/Selenium for future UI integration coverage.

## Traceability

All observations and artifacts are linked by their SDD topic keys and observation IDs in Engram:

| Artifact | Topic Key | Status |
|---|---|---|
| Proposal | `sdd/panel-v1b-fase-3/proposal` | Archived |
| Specification | `sdd/panel-v1b-fase-3/spec` | Archived |
| Design | `sdd/panel-v1b-fase-3/design` | Archived |
| Tasks | `sdd/panel-v1b-fase-3/tasks` | Archived |
| Verify Report | `sdd/panel-v1b-fase-3/verify-report` | Archived |
| Archive Report | `sdd/panel-v1b-fase-3/archive-report` | This document |

---

**The V1b heart phase is complete.** The panel can now add, edit reading progress (in phase 4: sync to Kitsu), and see the digest. All three detection mechanisms (feed, active_sweep, onhold_sweep) and both input routes (seed and panel) are live in production.
