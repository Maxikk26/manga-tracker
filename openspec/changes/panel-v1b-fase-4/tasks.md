# Tasks: `my_score`, scores backfill, terminal covers (`panel-v1b-fase-4`)

Contract: `design.md` (authoritative — decisions D1-D8 not re-decided here). Four-slice cut is
pre-confirmed by the orchestrator; not re-opened.

## Review Workload Forecast — whole change

| Field | Value |
|---|---|
| Estimated changed lines | ≈1315 (±20%), design forecast |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | 4 slices, stacked-to-main |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

Dependency diagram (each PR bases on the previous branch; retargets to `main` once its parent merges;
owner merges one at a time from the GitHub UI):

```
main
 └─ PR1 feat/panel-v1b-fase-4-terminal-covers   (~440)
     └─ PR2 feat/panel-v1b-fase-4-migration-3    (~130)
         └─ PR3 feat/panel-v1b-fase-4-my-score   (~430)
             └─ PR4 feat/panel-v1b-fase-4-import-scores (~430)
```

### Suggested Work Units

| Unit | Goal | PR / branch (base) | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | Terminal covers, no schema touch | PR1 `feat/panel-v1b-fase-4-terminal-covers` (base `main`) | `uv run pytest tests/discovery/test_covers.py tests/storage -q` | `cli.py cache-covers --status completed dropped --dry-run` against a homelab DB copy | Revert commit; cached files under `data/covers/` recoverable at one request each |
| 2 | Migration 3 alone | PR2 `feat/panel-v1b-fase-4-migration-3` (base PR1 branch) | `uv run pytest tests/storage/test_migrations.py -q` | `docker compose up -d` against a throwaway v2 DB copy, confirm `user_version`=3 | `range(4,3)` walk is empty (no-op) per design D7; `DROP COLUMN` only via the pre-deploy backup |
| 3 | `my_score` end to end | PR3 `feat/panel-v1b-fase-4-my-score` (base PR2 branch) | `uv run pytest tests/web/test_panel_api.py tests/storage -q && cd frontend && npm test` | Manual `curl` PATCH against a dev container: set/clear/absent-key | Revert commit; v2 code ignores the column, no data loss |
| 4 | `import-scores` | PR4 `feat/panel-v1b-fase-4-import-scores` (base PR3 branch) | `uv run pytest tests/importer/test_scores.py tests/importer/test_export.py -q` | `cli.py import-scores --dry-run` against the real `kitsu-manga.xml` copy | `UPDATE bookmarks SET my_score=NULL WHERE ...`; `reading_history` untouched |

---

## Slice 1 — Terminal covers (~440 lines), branch `feat/panel-v1b-fase-4-terminal-covers`, base `main`

**Foundation**
- [x] 1.1 `storage/repositories.py`: add `TERMINAL_STATUSES = frozenset({"completed","dropped"})` beside `BOOKMARK_STATUSES` (D8)
- [x] 1.2 `storage/repositories.py`: add `list_stored_url_cover_candidates(conn, *, statuses)` — no `manga_sites` join, returns `(manga_id, title, cover_url)`, unfiltered on `cover_url`

**Core**
- [x] 1.3 `discovery/covers.py`: add `backfill_stored_url_covers(...)` as sibling of `backfill_covers`, plus `CoverBackfillReport.no_url: list[str]`; never calls `fetch_manga_details`
- [x] 1.4 `cli.py`: `cache-covers` splits requested `--status` set across both routes; prints two populations + total; `--limit` applies per route, not merged; `--dry-run` prints two blocks

**Tests — traps first**
- [x] 1.5 RED/GREEN `tests/discovery/test_covers.py`: thin route downloads with **zero** `fetch_manga_details` calls (assert the fake was never asked)
- [x] 1.6 `tests/discovery/test_covers.py`: NULL `cover_url` counted in `no_url`, never fetched; mapped terminal with a known URL downloads, mapped terminal with none is skipped (D5 predicate, executable)
- [x] 1.7 `tests/discovery/test_covers.py`: already-cached rows cost nothing
- [x] 1.8 `tests/storage/`: `list_stored_url_cover_candidates` returns unmapped rows the INNER-JOIN query cannot see, and no `source_key` at all
- [x] 1.9 New contract test: the three `TERMINAL_STATUSES` copies (`web/app.py`, `importer/export.py`, `storage/repositories.py`) are equal (D8)
- [x] 1.10 Fix the stale `"59 of 229 in production"` comment near `storage/repositories.py:407`

**Docs — one bump, landed here to avoid per-slice version churn**
- [x] 1.11 `docs/spec-panel-v1b.md` → v1.7: close §232 heatmap cap as **decided — no cap**; correct §174 to state the MAL-id resolution and its ~38 Kitsu requests, replacing "matchea por kitsu_id ya guardado"; §175 gains the un-scoring contract; qualify §161 (the clean terminal/unmapped cut describes today's rows, not an invariant); rewrite §186 to four pieces
- [x] 1.12 Same PAN v1.7 edit, record as a follow-up (not fixed here): an unmapped non-terminal row with a stored `cover_url` is reachable by neither cover route (D5 gap) — zero rows today

## Slice 2 — Migration 3 (~130 lines), branch `feat/panel-v1b-fase-4-migration-3`, base PR1 branch

- [ ] 2.1 `storage/schema.sql`: add `my_score INTEGER,` on `bookmarks`, on its own line, no trailing comment (fixture trap, D7)
- [ ] 2.2 `storage/db.py`: `SCHEMA_VERSION = 3`, `_migration_3_bookmarks_my_score` mirroring migration 2 (`PRAGMA table_info` guard, one `ALTER TABLE`, no backfill), `MIGRATIONS[3]`
- [ ] 2.3 RED/GREEN `tests/storage/test_migrations.py`: third block mirroring migration 2's — literal-line strip fixture, pre-migration-3 builder at `user_version 2`, "gains the column and keeps rows", "does not invent a score" (NULL stays NULL), fresh DB stamped 3 directly, re-run is a no-op
- [ ] 2.4 Update `test_migrating_from_zero_applies_all_three_migrations_in_order`: strip the migration-3 line too (today it strips only 1 and 2) and assert **three** migrations — the exact trap: skipping this builds a `user_version 0` DB that already carries the column
- [ ] 2.5 Confirm the production backup (`docs/runbook-deploy.md` §7) is taken before this slice deploys — manual operator step, not automated

## Slice 3 — `my_score` end to end (~430 lines), branch `feat/panel-v1b-fase-4-my-score`, base PR2 branch

**Repository**
- [ ] 3.1 `storage/repositories.py`: add `my_score` to `_PANEL_BOOKMARK_SELECT` + `_panel_bookmark_row`
- [ ] 3.2 `storage/repositories.py`: `update_panel_bookmark` gains `my_score=UNSET`; `if my_score is not UNSET: assignments.append("my_score = ?")` — comment stating `None` is a legal value here, never test for it (D1)
- [ ] 3.3 RED/GREEN `tests/storage/`: `update_panel_bookmark(my_score=None)` writes SQL NULL; `my_score=UNSET` leaves the column untouched; a score-only edit writes **zero** `reading_history` rows. Write the assertion so it fails if `is not UNSET` is swapped for `is not None`

**API**
- [ ] 3.4 `web/app.py`: `BookmarkPatch.my_score: int | None = Field(default=None, ge=0, le=10)`; `_check_presence` gains **no** null-rejection clause for `my_score` (D2); fix the stale class docstring and error string, both currently implying only progress/status exist
- [ ] 3.5 `web/app.py patch_bookmark`: `my_score=patch.my_score if "my_score" in fields else UNSET` — byte-for-byte shape of the two existing lines
- [ ] 3.6 `tests/web/test_panel_api.py`: three-way contract — `{"my_score":7}` sets, `{"my_score":null}` clears, key absent leaves it alone; `11`, `-1`, `7.5` are 422; `{}` still 422; list payload and PATCH response both carry the field; clearing writes no `reading_history` row

**Frontend**
- [ ] 3.7 `frontend/src/domain/types.ts`: `Bookmark.my_score: number | null`; `BookmarkPatch` third variant `{ my_score: number | null }` — **not** `my_score?: number` (D3: `JSON.stringify` drops `undefined` keys)
- [ ] 3.8 `frontend/src/components/InlineNumberEdit.tsx`: additive `max?: number` (validated like `min`) and `onClear?: () => void` — **not** a widened `onCommit` (D4: `strictFunctionTypes` breaking-change trap); `onClear`'s absence keeps `last_chapter_read`'s blank-blur no-op unchanged
- [ ] 3.9 `frontend/src/components/BookmarkCard.tsx`: second `InlineNumberEdit` for the score, plainly placed — no new CSS, class, size or colour decision (hard constraint)
- [ ] 3.10 `frontend/src/containers/BookmarkListContainer.tsx`: `onChangeScore(id, value | null)` → `patchBookmark`
- [ ] 3.11 `InlineNumberEdit.test.tsx`: `max` rejects an over-range commit; without `onClear` a blank blur stays a no-op; with it, a blank blur calls `onClear` exactly once
- [ ] 3.12 `BookmarkCard.test.tsx`, `BookmarkListContainer.test.tsx`: score renders `—` when null; editing sends `{my_score:n}`; clearing sends `{"my_score":null}` and **not** `{}` — assert the serialized `JSON.stringify` body, not the mock call

## Slice 4 — `import-scores` (~430 lines), branch `feat/panel-v1b-fase-4-import-scores`, base PR3 branch

**Parse-time fix + doc, same commit**
- [ ] 4.1 `importer/export.py`: `ExportEntry.my_score: int | None`; `_entry()` parses `<my_score>`, converts `0` → `None` at parse time
- [ ] 4.2 Rewrite `tests/importer/test_export.py:160-165` (was `test_the_score_is_not_carried_into_the_domain`): assert `my_score` is now carried and `0` becomes `None`
- [ ] 4.3 `docs/spec-importador-kitsu.md`: changelog note — V1b reversed decision 5 — in the same commit as 4.1/4.2

**Repository + module**
- [ ] 4.4 `storage/repositories.py`: `set_bookmark_score(conn, manga_id, my_score, *, now)` — one statement, `UPDATE bookmarks SET my_score=?, updated_at=? WHERE manga_id=? AND my_score IS NULL`, returns `cursor.rowcount`; fill-only-NULL enforced in the WHERE clause, never a Python read-then-write (D6, TOCTOU)
- [ ] 4.5 Create `importer/scores.py`: `ScoreImportReport` dataclass + `import_scores(export_path, conn, catalogue)` — resolves every id in one chunked-at-12 catalogue call, then fills NULLs; never creates a row

**CLI**
- [ ] 4.6 `cli.py`: `import-scores` verb mirroring `_cmd_import_kitsu` — read/report the file before a connection or the network; constructs `KitsuCatalogue(UrllibJsonTransport())` directly, never `_bootstrap`; `--dry-run` returns file-only counts and states so explicitly

**Tests — traps first**
- [ ] 4.7 RED/GREEN `tests/storage/`: `set_bookmark_score` returns `False` and changes nothing on an already-scored row — written to fail if the guard moves into Python
- [ ] 4.8 `tests/importer/test_scores.py` (new): `0` in file → `NULL`; non-NULL score skipped, not overwritten; unresolved id and manga absent from DB are ordinary skips with distinct counters; second run fills zero; catalogue failure writes nothing

## Final
- [ ] 5.1 After every slice merges: `uv run pytest -q` and (`cd frontend && npm test && npm run build`) green
