# Tasks: Add a manga from the panel (`panel-v1b-fase-3`)

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ≈1635 (±20%), per `design.md` Changed-Lines Forecast |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 (~395) → PR 2 (~515) → PR 3 (~725) |
| Delivery strategy | resolved by owner: chained |
| Chain strategy | stacked-to-main, sequential |

Decision needed before apply: No — resolved: chained, stacked-to-main
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

## All 18 Tasks Complete

### Slice 1 — Protocol, `intake` skeleton, architecture rule (5 tasks, all [x])
- [x] 1.1 `fetch_cover` on SourceClient Protocol
- [x] 1.2 `intake/contracts.py` with MangaIntake Protocol, frozen dataclasses
- [x] 1.3 Widened `web` directional rule
- [x] 1.4 Four injected-violation probes
- [x] 1.5 Documentation cost-row correction

### Slice 2 — Repository writer, endpoints, wiring (7 tasks, all [x])
- [x] 2.1 `cover_cache.write_cover` atomic write
- [x] 2.2 `write_manual_add` and `list_tracked_titles`
- [x] 2.3 `PastedUrlIntake.preview()` with three gates
- [x] 2.4 `PastedUrlIntake.confirm()` with atomic write and cover fetch
- [x] 2.5 Status labels Python mirror + parity test
- [x] 2.6 `POST /api/mangas/preview` and `POST /api/mangas` endpoints
- [x] 2.7 `cli.py` wiring with dependency injection

### Slice 3 — Frontend modal, integration, Vitest (6 tasks, all [x])
- [x] 3.1 `api/http.ts` with ApiError carrying `existing`
- [x] 3.2 `api/mangas.ts` with preview and add functions
- [x] 3.3 Extended `domain/types.ts` with wire contracts
- [x] 3.4 `AddMangaModal.tsx` pure component with form and preview
- [x] 3.5 `AddMangaContainer.tsx` with state and round-trip logic
- [x] 3.6 Integration with `BookmarkListContainer.tsx`
- [x] 3.7 CSS animations and modal styling
- [x] 3.8 Full `npm run build` and `npm test` validation

---

**ARCHIVED CHANGE**: All tasks verified complete in production. See ARCHIVE.md for final state.
