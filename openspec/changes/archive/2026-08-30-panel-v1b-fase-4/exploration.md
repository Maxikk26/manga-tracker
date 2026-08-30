# Exploration — panel-v1b-fase-4 (my_score, terminal covers, heatmap cap)

Change: `panel-v1b-fase-4` · Explored: 2026-08-25 · Branch: `main` @ `4d2d555`
Spec: `docs/spec-panel-v1b.md` v1.6 (§`my_score` fase 4, §Portadas de los terminales, §Fases y criterios de terminado, §Pendientes abiertos). Data model: `docs/spec-modelo-de-datos.md` v1.9 (§Versionado del esquema already reserves migration 3 for `my_score`, no doc drift there).

> Persistence note: this file is the filesystem half of the `hybrid` artifact store. The Engram half is topic key `sdd/panel-v1b-fase-4/explore`. The exploring agent had no write tool in its toolset, so the orchestrator materialized this file from the Engram record; the two are the same content.

## 1. Migration mechanism (as it exists)

`manga_tracker/storage/db.py`: `SCHEMA_VERSION = 2` (line 15) must become 3. `MIGRATIONS = {1: ..., 2: _migration_2_bookmarks_status_changed_at}` (69-72) — migration 2 (51-66) is the exact template: `PRAGMA table_info(bookmarks)`, add the column only if absent (idempotent, guards a half-run migration), no backfill (explicitly documented as deliberate — a copied value would lie). `_migrate()` (75-88) walks `range(user_version+1, SCHEMA_VERSION+1)`, writing and committing `user_version` after EACH migration so an interruption leaves the number describing what ran. `ensure_schema()` (91-113) is the load-bearing trap CLAUDE.md warns about: `schema.sql` is all `CREATE ... IF NOT EXISTS`, so it does nothing to an existing table's columns — a column added only there never reaches production. The empty-check (`born_empty`) is what decides fresh-stamp vs migrate.

`tests/storage/test_migrations.py` tests on DISK, never `:memory:` (its own docstring: "every other test builds from nothing... A column added to schema.sql therefore passes the whole suite while doing NOTHING to a database that already exists"). Migration 3 needs the same shape as migration 2's block (137-234): a literal-line strip fixture (`MIGRATION_3_LINE = "    my_score INTEGER,\n"`), a pre-migration-3 DB builder, "gains the column and keeps rows", "does not invent a value" (NULL stays NULL — mirrors migration 2's "does not invent a pause date"), a fresh-DB test, and updating the "migrating from zero applies N migrations in order" test to 3.

Backup step is NOT code — it's `docs/runbook-deploy.md` §7 "Respaldo" (247-253): `cp ~/manga-tracker-data/manga-tracker.db ~/backups/manga-tracker-$(date +%F).db`, a manual pre-deploy operator step, not something `sdd-apply` automates.

No CHECK constraint precedent for range validation at the DB level (`last_chapter_read REAL` has none; range is Pydantic-only, `Field(ge=0)` in `web/app.py:164`). Recommend the same for `my_score` (no `CHECK (my_score BETWEEN 0 AND 10)` in schema.sql) for consistency — flagged as an option, not fully closed.

## 2. import-scores — what it must reuse, and the real finding

`manga_tracker/importer/export.py`: `ExportEntry` (47-64) deliberately omits `my_score` (KIT decision 5 docstring). `_entry()` (95-129) never reads `<my_score>`. Pinned test: `tests/importer/test_export.py:160-165 test_the_score_is_not_carried_into_the_domain` asserts `ExportEntry` has no `my_score` field — this WILL need deliberate rewriting, and `docs/spec-importador-kitsu.md` decision 5 (line 64) needs a changelog note that v1b reversed it (CLAUDE.md's doc-pin/versioning convention).

**Key finding, contradicts a literal reading of the spec's "matchea por kitsu_id (ya guardado en mangas)":** `<manga_mangadb_id>` in the XML is a **MAL id**, not `mangas.kitsu_id` (export.py:57 comment "the MAL id: resolution input only, never stored"; `spec-importador-kitsu.md:56,88` — "el export trae id de MAL; el kitsu_id hay que resolverlo"). So `import-scores` is NOT a pure offline file read. It must resolve every entry through `CatalogueClient.resolve()` — a network call to Kitsu's `/mappings` endpoint (`manga_tracker/catalogue/kitsu.py:79-128`, chunked at `BATCH_SIZE=12`, kitsu.py:29) — exactly like `import-kitsu` does (`manga_tracker/importer/run.py:69`), then `repo.find_manga_by_kitsu_id(conn, catalogue_entry.catalogue_id)` (repositories.py:81-84). `KitsuCatalogue.resolve()` also unconditionally runs `_fetch_categories()` (kitsu.py:123,130-149), pure overhead for a score-only backfill (~19 mapping-chunks + ~19 category-chunks ≈ 38 Kitsu requests for 218 entries) — harmless (Kitsu's own API has its own 1.0s courtesy-delay transport, `catalogue/transport.py:35-45`, unrelated to manganato's `BATCH_POLICY`/`INTERACTIVE_POLICY`, so CLAUDE.md's Request Policy section does not apply here at all).

`bookmarks.manga_id` is UNIQUE (schema.sql:107) — manga:bookmark is 1:1, so a new repo write `set_bookmark_score(conn, manga_id, my_score, *, now)` mirroring `set_manga_cover` (repositories.py:684-691) is a simple lookup-then-UPDATE. `reconcile.py`'s three-key policy is NOT needed — that's for creating/merging manga rows during the full import; `import-scores` only ever updates an existing bookmark found by kitsu_id, never creates rows.

CLI precedent to mirror: `cli.py:70-114 _cmd_import_kitsu` — read-and-report the file BEFORE opening a connection or hitting the network, dry-run returns before any I/O.

Open question (see §7): overwrite policy when `my_score` is already non-NULL (e.g. edited by hand via the panel, then `import-scores` re-run by accident). `write_kitsu_bookmark` (repositories.py:197-231) protects non-`kitsu_import`-origin bookmarks from re-import overwrites — same philosophy might apply here but the spec doesn't say.

## 3. Second cover route for the 66 terminals

`repositories.py:652-681 list_cover_candidates` — INNER JOIN on `manga_sites`, by design and documented (664-667: "a manga with no source mapping has no slug... listing it would only produce a row the caller must skip"). Confirmed by production measurement: all 66 terminals have zero `manga_sites` rows, so `--status completed` returns 0 rows today.

`discovery/covers.py:62-151 backfill_covers` — two-step loop (learn `cover_url` via `fetch_manga_details`, then `fetch_cover`), gated by `DEFAULT_STATUSES = ("reading","want_to_read","on_hold")` (covers.py:38).

**Key finding: no new client method needed.** `ManganatoClient.fetch_cover(cover_url)` (`sources/manganato/client.py:95-127`) sends a hardcoded manganato Referer unconditionally, and the docstring + `cover_cache.py` module docstring both confirm hosts that don't check it (Kitsu's CDN) simply ignore it — this is already how 212/229 non-terminal Kitsu-sourced covers get downloaded today through this exact method. So "the second route" is a new *candidate query* (skip the `manga_sites` join entirely) plus a thinner discovery-layer loop that skips the `fetch_manga_details` step (terminals never have a slug — nothing to look up; `cover_url` is always already present, measured 66/66), not a new fetch primitive.

Structural boundary: `tests/test_architecture.py:36-44 DIRECTIONAL_RULES["web"]` forbids importing `discovery` or `catalogue` at all. So the new logic MUST live in `discovery/covers.py` (sibling function, e.g. `backfill_terminal_covers`), wired only from `cli.py` (composition root). `GET /api/covers/{manga_id}` (`web/app.py:270-298`) needs ZERO changes — it already serves any cached file by `manga_id` regardless of which route wrote it.

New repository query: e.g. `list_terminal_cover_candidates(conn)` — `SELECT m.id, m.title, m.cover_url FROM mangas m JOIN bookmarks b ON b.manga_id=m.id WHERE b.status IN ('completed','dropped')`, no `manga_sites` join. Treat a hypothetical NULL `cover_url` defensively (log-and-skip) even though today's data guarantees non-null — that guarantee is a fact about production data, not a schema constraint.

Open CLI-shape question (§7): fold into `cache-covers --status completed/dropped` (detecting terminal statuses and switching internally to the thinner path) vs. a new dedicated one-off verb. Cost model differs meaningfully (0-1 request/manga here, vs up to 2 for the mapped route), which argues for keeping the two code paths distinct regardless of CLI surface.

Cost confirmed: 66 Kitsu requests, 0 manganato requests — matches spec's §Portadas de los terminales measurement exactly.

## 4. Heatmap cap — where it lives

`repositories.py:522-573 reading_days()` is the ENTIRE local-day aggregation (server-side, `zoneinfo`, per CLAUDE.md's hard timezone-before-grouping rule). The exact site of the uncapped accumulation is lines 561-563:

```
if previous_chapter_num is not None and chapter_num > previous_chapter_num:
    bucket[0] += chapter_num - previous_chapter_num
```

No existing test constrains a single event's contribution — `tests/web/test_history_api.py:123-138` only covers the downward-correction-contributes-zero and NULL-previous-counts-as-edit cases. `GET /api/history/reading` (`web/app.py:243-253`) is the only caller; `frontend/src/domain/heatmapBuckets.ts` is explicitly reserved for fase 5 (the visual bucket/scale decision) and is the WRONG place for a cap — this is server-side computation per the spec's own framing ("Es cómputo del servidor, no presentación").

Genuinely ambiguous exactly as the spec's own pendiente says (spec-panel-v1b.md:232): cap one event's delta before summing (risks under-counting a legitimate multi-day binge collapsed into one panel edit) vs. cap the day's post-sum total vs. some signal to distinguish "correction" from "genuine binge" — the schema carries no such flag; a `reading_history` row from a panel PATCH looks identical whether it followed 1 chapter or 175. No config parameter exists yet for a cap value (compare the `PANEL_PORT`/`FEED_CHECK_MINUTES` pattern in spec-panel-v1b.md's own "Parámetros de configuración" table) — whether this is a hardcoded constant or a new config knob is unresolved.

## 5. my_score reuse in the panel UI + API contract cost

`frontend/src/components/InlineNumberEdit.tsx` (83 lines) — click-to-edit numeric field, currently wired only to `last_chapter_read` (`BookmarkCard.tsx:108-113`). Its `min={0}`/`Number.isFinite`/`parsed<0` guard (lines 43,68) is reusable, but it has **no upper bound** (`step="any"`, no `max`) — reusing it verbatim for a 0-10 score would silently accept 11, 500, etc. Needs one small additive prop (`max?`, validated the same way `min` already is) — backward compatible, existing callers unaffected, not a visual decision (no new class, no size/color choice). Doesn't enforce integer either; either add lightweight integer validation client-side or rely on the Pydantic `int` field server-side (422 on a fractional score) — recommend both for UX but the server-side guard alone is sufficient to keep the contract sound.

`DecimalInput.tsx` is a free-text unbounded-decimal draft input used only in the add-manga modal (`AddMangaModal.tsx`) — wrong shape (no click-to-edit/display toggle); `InlineNumberEdit` is the closer fit and needs less rework.

Contract changes, all mechanical: `frontend/src/domain/types.ts:11-31 Bookmark` gains `my_score: number | null`; `types.ts:34-36 BookmarkPatch` union gains a variant (see §7 re: null); `web/app.py:154-176 BookmarkPatch` (Pydantic) gains `my_score: int | None = Field(default=None, ge=0, le=10)` plus a presence-check mirroring the existing validator; `web/app.py:225-241 patch_bookmark` passes it through; `repositories.py:433-501 update_panel_bookmark` gains a `my_score=UNSET` kwarg and one more conditional assignment — simplest of the three PATCH fields since `my_score` has no trigger interaction at all (unlike `last_chapter_read`, which needs the `reading_history` origin-correction dance); `_PANEL_BOOKMARK_SELECT`/`_panel_bookmark_row` (367-415) gain the column.

Rendering location: `BookmarkCard.tsx` (75-134) has a natural plain insertion point (e.g. between title and progress line, or appended after it) with no new CSS treatment needed beyond not breaking the existing layout — matches the spec's explicit constraint (v1.6: "la fase 4 entrega el dato y su edición... y no gasta ni una decisión visual en él").

## 6. Test coverage gaps (562 tests, green, as of main@4d2d555)

- Migration: needs a 3rd block in `test_migrations.py` mirroring migration 2's (137-234) exactly.
- import-scores: ZERO existing tests (grep for `my_score`/`import_scores` across `tests/` hits only `test_export.py`'s pinned-absence test and the KIT fixture file). Needs its own test module plus CLI dry-run/report coverage mirroring `_cmd_import_kitsu`'s pattern.
- Terminal covers: ZERO coverage — no test file references `list_cover_candidates` directly at all (only exercised indirectly via `backfill_covers` in `tests/discovery/test_covers.py`); no `tests/storage/test_repositories.py` exists yet.
- Heatmap cap: ZERO coverage — no test anywhere asserts a magnitude ceiling on a single upward delta.
- my_score in panel API: ZERO coverage in `tests/web/test_panel_api.py` (25 existing test functions there, none touch `my_score`).
- Frontend: `InlineNumberEdit.test.tsx` has no `max`-prop test (prop doesn't exist yet); no `my_score` references anywhere in `frontend/src`.

## 7. Ambiguities to raise with the owner before sdd-propose

1. **Heatmap cap shape and magnitude** — explicitly left open by the spec itself (spec-panel-v1b.md:232, "para que el dueño decida... con qué forma, una vez vea el heatmap real"). Per-event delta cap vs per-day total cap vs something else; hardcoded constant vs new config parameter.
2. **import-scores overwrite policy** — does a re-run overwrite an already-edited (non-NULL) `my_score`, or only fill NULLs? No stated rule; the closest precedent (`write_kitsu_bookmark`'s origin-based protection) suggests "manual wins" but was never asked for scores.
3. **Can the panel un-score (my_score → NULL)?** The `last_chapter_read` PATCH validator explicitly forbids re-nulling progress ("NULLing progress back out is not a panel operation", web/app.py:157-159). If the same rule applies to `my_score`, a mis-typed score can never be cleared through the UI — worth a direct decision, not an assumption.
4. **CLI shape for the terminal-cover route** — fold into `cache-covers --status completed/dropped` (one verb, internal dispatch) vs. a new dedicated one-off command. Cost model and query differ meaningfully.
5. **DB-level CHECK on `my_score` (0-10)?** No precedent for range CHECKs in this schema (`last_chapter_read` has none); recommend following that precedent (Pydantic-only) but flagging since a wrong score is user-visible data, not internal bookkeeping.

## Ready for Proposal

Yes. All five pieces have a clear implementation path grounded in existing patterns; the five ambiguities above are genuine decisions for the owner (especially #1, which the spec itself defers) rather than missing research. None of them block scoping the change — sdd-propose can present them as explicit open questions inside the proposal, or the orchestrator can surface #1-#3 to the owner directly since they change API/CLI contract shape.
