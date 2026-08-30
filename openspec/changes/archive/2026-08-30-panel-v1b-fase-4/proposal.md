# Proposal: `my_score`, the scores backfill and the terminal covers (`panel-v1b-fase-4`)

V1b fase 4, the last functional phase before the design pass. **`docs/spec-panel-v1b.md` v1.6 is the contract** — this proposal shapes the work and corrects the contract where measurement contradicts it; it does not restate it. File-level detail lives in `exploration.md` and is not repeated here.

`execution_mode: auto · artifact_store: hybrid · delivery_strategy: auto-chain · review_budget_lines: 800`

| Alias | Document |
|---|---|
| PAN | `docs/spec-panel-v1b.md` v1.6 → **v1.7 in this delivery** (§171-175 `my_score`, §150-169 portadas de terminales, §186 fase 4, §195 la regla del dato y su forma, §232 el pendiente del tope) |
| DM | `docs/spec-modelo-de-datos.md` v1.9 (§Versionado del esquema — la migración 3 ya está reservada para `my_score`; sin deriva) |
| KIT | `docs/spec-importador-kitsu.md` — su **decisión 5** (`my_score` deliberadamente fuera del dominio) es la que esta entrega revierte |

## Intent

Two datasets exist in production and the panel cannot see either.

The owner's **218 Kitsu scores** have been dead since the import: KIT decision 5 deliberately dropped `my_score` on the floor, and V1b promised to pick it back up. And **66 bookmarks — every terminal one** — fall back to initials in a list the owner navigates *by cover*, even though all 66 already carry a `cover_url` pointing at the one CDN that serves without a `Referer`.

Neither is a redesign problem. PAN §195 fixes the rule this phase obeys: **fase 4 ships the data and its editing by the plainest route available, and spends zero visual decisions on it.** Schema, a CLI and files on disk are not what a design pass rewrites; where the score sits on the card is, and that belongs to fase 5.

## Scope

### In scope — four pieces

| # | Deliverable | Implements |
|---|---|---|
| 1 | **Migración 3**: `bookmarks.my_score INTEGER`, 0-10, NULL = sin puntuar. `SCHEMA_VERSION` 2 → 3, mirroring migration 2's shape exactly (guarded by `PRAGMA table_info`, no backfill). Disk-based migration tests, never `:memory:` | PAN §173, DM |
| 2 | **`import-scores`**, one-off CLI: fills `my_score` from the export, **only where it is NULL** | PAN §174, KIT |
| 3 | **Portadas de los 66 terminales**: a second candidate query with no `manga_sites` join and a thinner discovery loop. No new client method | PAN §150-169 |
| 4 | **`my_score` de punta a punta**: visible in the list, editable and **clearable** through the existing `PATCH /api/bookmarks/{id}` | PAN §175 |
| 5 | Doc follow-through: PAN → v1.7, KIT changelog note (see Risks) | CLAUDE.md |

### Out of scope

- **El tope del heatmap. Decidido: no hay tope.** The owner decided this on 2026-08-21 ("puedo convivir con ello", recorded as D7 in the fase-2 archive) and reaffirmed it on 2026-08-25. **PAN v1.6 assigned it to fase 4 in error, and the error is the orchestrator's** — v1.7 says so plainly and closes §232 as *decided*, not as pending. This piece leaves the phase entirely: fase 4 is **four** pieces, not five.
- **Every visual decision about the score** — placement, size, colour, whether unscored looks different. PAN §195, fase 5.
- Any request to manganato. Any re-mapping of a terminal. Any touch of `consecutive_failures`. PAN §169 authorises exactly one door: downloading an image from a public CDN whose address was already stored.
- A DB-level `CHECK (my_score BETWEEN 0 AND 10)` — see Approach.
- `DELETE`. Editing manga metadata. Re-sync to Kitsu. Etapa 2 del clic en la portada (PAN §230 — it is its own delivery because one of its two exits is a migration).

## Capabilities

### New

- **`panel-bookmark-score`**: migration 3 and the column's semantics (NULL = unscored, 0-10 integer), the `PATCH` contract *including clearing*, and the field's presence in the list payload.
- **`cover-backfill`**: the two cover routes, their populations, candidate queries, cost models and idempotency, and the rule that the thin route never asks the source. This capability has no spec today — the mapped route shipped 2026-08-18 outside SDD — so the new spec covers both routes, with the terminal one as the delta being built.

### Modified

- **`kitsu-import`**: `ExportEntry` gains `my_score` (reverses KIT decision 5), plus a second one-off verb that resolves MAL id → Kitsu id → `mangas.kitsu_id` and fills only NULLs. It never creates a row.
- **`catalogue`**: **only if** design elects a categories-skip for score-only resolution (see cost table). Unchanged otherwise — say "None" in the spec phase if design declines it.
- `source-client`: **not modified.** `fetch_cover` already works for Kitsu URLs; that is how 212 of today's covers were downloaded.

## Approach

Four work units, each one reviewable commit with its tests. Unit 1 gates 2 and 4; unit 3 is independent of all of them.

1. **Migración 3** — the column, `SCHEMA_VERSION` 3, a third block in `test_migrations.py` mirroring migration 2's: literal-line strip fixture, pre-migration-3 builder, "gains the column and keeps rows", "does not invent a value", fresh-DB stamp, and the "migrating from zero applies N migrations" count.
2. **`my_score` de punta a punta** — repository select/update, Pydantic field, `types.ts`, `InlineNumberEdit` gains an **additive `max` prop**, `BookmarkCard` renders it plainly. Simplest of the three PATCH fields: `my_score` has **zero trigger interaction** — the trigger's `WHEN` guard is on `last_chapter_read`, so a score-only UPDATE inserts nothing into `reading_history`.
3. **`import-scores`** — mirrors `_cmd_import_kitsu`'s shape: read and report the file before touching a connection or the network.
4. **Portadas de los terminales** — new candidate query, thin loop in `discovery/covers.py`, wired from `cli.py`. `GET /api/covers/{manga_id}` needs **zero** changes; it serves any cached file by `manga_id` regardless of which route wrote it.

### Three decisions taken here, and their reasons

**The panel CAN un-score, and `last_chapter_read` cannot** (owner, 2026-08-25). The divergence is deliberate and needs its reason on the record: progress feeds the trigger, `reading_history` and the digest, so nulling it back out destroys history that is not recoverable — which is why `web/app.py` forbids it. A score feeds **nothing**. Nothing reads it but the list. So a mistyped score must be clearable without opening SQLite, and refusing that would be a rule copied for symmetry rather than for a reason.

**`import-scores` never overwrites a non-NULL `my_score`** (owner, 2026-08-25). A score edited by hand in the panel beats a re-run of the import. Same philosophy as `write_kitsu_bookmark`'s origin-based protection: the human's deliberate act outranks a bulk re-read of a file.

**No DB-level CHECK on `my_score`** (orchestrator). This schema has no precedent for range CHECKs — `last_chapter_read` validates in Pydantic only (`Field(ge=0)`). Consistency beats a one-off constraint, and a CHECK added later is a table rebuild on a populated database.

### The two cover paths stay distinct — and the CLI question

**Do not merge them into one branchy function** (orchestrator). The routes have genuinely different cost models: the thin one costs **0-1** requests per manga and never calls `fetch_manga_details`; the mapped one costs up to 2. One function serving both would carry a branch whose two sides share nothing but a loop.

**The CLI surface is the smaller question, and the recommendation is to extend `cache-covers`** rather than add a verb. Three reasons, and one real objection:

- `--status` is *already* the flag that replaces the default population (PAN §136). Today `cache-covers --status completed` returns **zero rows** and reports success — a silent wrong answer, which is worse than an error. Extending the verb converts that silence into the correct behaviour; a dedicated verb leaves the trap armed forever.
- The dispatch is on **data, not on a user choice**: no mapping ⇒ no slug ⇒ nothing to ask the source. The operator should not have to know which verb matches which row.
- One `--dry-run`, one `--limit`, one idempotency story, one cost table.
- **The objection**, and it is real: two cost models under one verb make `--dry-run` output ambiguous unless it reports the two populations separately, and a single `--limit` then spans both. Design owns that output shape. It is a reporting problem, not a reason for a second verb.

### Cost, measured and honest

| Pieza | Requests | A quién | Política | Reloj |
|---|---|---|---|---|
| Migración 3 | 0 | — | — | un `ALTER`, instantáneo |
| `import-scores` | **~38** | Kitsu `/mappings` + `/categories` | transporte de `catalogue`, cortesía 1,0 s | ~40 s |
| Portadas terminales | **66** | `media.kitsu.app` | `BATCH_POLICY`, 5-15 s, secuencial | **~6-17 min** |
| `my_score` en el panel | 0 | — | — | — |
| **Total** | **~104** | **cero a manganato** | | |

Roughly half of `import-scores`' cost is `_fetch_categories()`, which `KitsuCatalogue.resolve()` runs unconditionally and which a score-only backfill has no use for. Design may skip it and halve the figure; that is the one branch that would make `catalogue` a modified capability.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `manga_tracker/storage/db.py` | Modified | `SCHEMA_VERSION` 3 + `_migration_3_bookmarks_my_score`. `schema.sql` gains the column too — but **only for databases born empty**; a column added there alone never reaches production. |
| `manga_tracker/storage/repositories.py` | Modified | `my_score` in the panel `SELECT`/row mapper and in `update_panel_bookmark`; `set_bookmark_score`; a terminal candidate query with **no** `manga_sites` join. |
| `manga_tracker/web/app.py` | Modified | `BookmarkPatch` gains `my_score`; `patch_bookmark` passes it through. `GET /api/covers/{manga_id}`: **unchanged**. |
| `manga_tracker/importer/export.py` | Modified | `ExportEntry` gains `my_score`. Reverses KIT decision 5. |
| `manga_tracker/discovery/covers.py` | Modified | Sibling function for the thin route. Must live here, not in `web` — `DIRECTIONAL_RULES["web"]` forbids importing `discovery` at all. |
| `manga_tracker/cli.py` | Modified | `import-scores`; `cache-covers` learns the terminal population. Composition root, as always. |
| `frontend/src/` | Modified | `types.ts`, `InlineNumberEdit` (`max` prop, additive), `BookmarkCard`. No new CSS treatment. |
| `docs/spec-panel-v1b.md` | Modified | → v1.7, two corrections (see Risks). Same branch as the code (CLAUDE.md). |
| `docs/spec-importador-kitsu.md` | Modified | Changelog note recording that V1b reversed decision 5. |
| `tests/` | New + Modified | Migration block; `import-scores` module (zero coverage today); terminal covers (zero coverage today); `my_score` in `test_panel_api.py` (zero of 25 tests touch it); the **deliberate rewrite** of `test_export.py:160-165`. |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| **`my_score: null` is ambiguous with "field absent".** The existing `BookmarkPatch` uses `None` to mean *not provided* and validates presence that way. Owner decision 3 requires `null` to mean **clear it** — so the two meanings collide on the wire, and a naive `is None` check makes un-scoring silently unreachable | **High** | The mechanism is Pydantic's `model_fields_set` / `exclude_unset`, not a `None` test. Design decides the exact shape; the existing presence-check is the precedent to **extend**, not to copy. This is the sharpest technical consequence of the un-score decision and must not be discovered during apply. |
| **"The 66 terminals are exactly the 66 unmapped" is a fact about today's data, not an invariant.** The moment the panel marks a mapped `reading` manga as `completed`, a terminal bookmark **with** a `manga_sites` row exists — and PAN §161's clean cut stops holding | **Med-High** | Route selection must key on the **data** (is `cover_url` known? is there a mapping?), not on the status. Design fixes the predicate. A terminal row with a NULL `cover_url` is log-and-skip, defensively, even though today's data is 66/66 populated. |
| **`import-scores` is not an offline file read**, contrary to PAN §174 ("matchea por `kitsu_id` ya guardado en `mangas`"). The XML carries a **MAL id**; `mangas.kitsu_id` is not in the file. Every entry resolves through `CatalogueClient.resolve()` — ~38 Kitsu requests, and **nothing runs if Kitsu is unreachable** | **High** | Correct §174 and the cost row in PAN v1.7. Harmless traffic — Kitsu's own courtesy transport, manganato's request policy does not apply here at all — but a published figure that says "one-off local" must not stay wrong. |
| **A pinned test is being rewritten on purpose.** `tests/importer/test_export.py:160-165` asserts `ExportEntry` has **no** `my_score`; it exists to pin KIT decision 5 | Med | Rewrite it deliberately, in the same commit, and add the KIT changelog note. A reversed decision with no changelog note is precisely the stale-pin defect CLAUDE.md warns about. |
| **`InlineNumberEdit` has no upper bound and does not enforce integer** (`step="any"`, `min={0}` only). Reused verbatim it silently accepts 11, 500, or 7.5 | Med | Additive `max` prop, validated the way `min` already is — backward compatible, existing caller unaffected, not a visual decision. The server-side `int` + `Field(ge=0, le=10)` is the guard that makes the contract sound; the client-side one is UX. |
| **Migration 3 lands on the one production database.** `ensure_schema` does nothing to an existing table's columns, so the migration is the only path that works — and there is no second copy | Med | The pre-deploy backup is `docs/runbook-deploy.md` §7, a **manual operator step**, not something apply automates. Say so in tasks; do not let it be assumed. |
| ~800 changed lines across four units against an 800-line budget, `auto-chain` | Med | The units are natural slice boundaries and are already ordered by dependency: 1 → {2, 3}, with 3 (covers) independent of all of them and the cleanest thing to split off first. |

## Rollback Plan

- **Units 2, 3 and 4**: revert the commit. No data residue except cached cover files under `data/covers/`, each recoverable for one request.
- **Migration 3 is the one that is not free — but it is not dangerous either.** Verified against `db.py`: reverting the code to `SCHEMA_VERSION = 2` against a database already stamped 3 makes `_migrate()` walk `range(4, 3)`, which is **empty**. It is a no-op, not a crash. The column stays and v2 code ignores it. The destructive alternative (`DROP COLUMN` + `PRAGMA user_version = 2`) is what the pre-deploy backup is for, not a routine step.
- **Data written by `import-scores`** is exactly `bookmarks.my_score` where it was NULL, plus whatever `updated_at` the writer stamps. One `UPDATE bookmarks SET my_score = NULL` cleans it. **`reading_history` is untouched** — verified in `schema.sql`: the trigger's `WHEN` guard is `NEW.last_chapter_read IS NOT OLD.last_chapter_read`, so a score-only UPDATE fires nothing.
- **Docs**: PAN v1.7 and the KIT note are prose; reverting them is a revert.

## Dependencies

- Fases 1, 2 and 3 deployed (they are). Fase 4 is the one phase with a **real** internal dependency: pieces 2 and 4 need migration 3 (PAN §191).
- PAN pins `one-pager-v1a.md` v1.14, `spec-modelo-de-datos.md` v1.9 and `decision-arquitectura-v1b.md` v1.2 — all current, re-verified at v1.6.
- `~/manga-tracker-data/kitsu-manga.xml` must still be on the homelab.
- **Kitsu must be reachable** for `import-scores` (see Risks) and for the 66 cover downloads. Offline, both are no-ops that report and write nothing.
- Fase 5 depends on this one only in the weak sense that it will restyle what this ships. It is not blocked by it.

## Success Criteria

- [ ] `PRAGMA user_version` reads **3** in production, taken after a backup, with all 236 bookmark rows intact and `my_score` NULL on every row the import did not fill.
- [ ] `import-scores` fills the scores from the export, reports how many it filled and how many it skipped, and a **second run fills zero** — including zero overwrites of a score edited in the panel between runs.
- [ ] A score of **0** in the export becomes NULL, not zero (PAN §174).
- [ ] The 66 terminal bookmarks have a cover on disk and `GET /api/covers/{manga_id}` serves it without a fetch. **Zero requests to manganato** during the whole run, verifiable because no slug exists to make one with.
- [ ] An unscored manga can be scored from the browser, a scored one re-scored, and a mistyped one **cleared back to unscored** — all through `PATCH /api/bookmarks/{id}`, with no `reading_history` row generated by any of the three.
- [ ] A score outside 0-10, or a fractional one, is refused by the API with a 422.
- [ ] The score is visible in the list without any new visual treatment — no new colour, no new size decision, nothing fase 5 has to undo beyond moving it.
- [ ] `uv run pytest -q` green with no network access; `npm test` and `npm run build` green.
- [ ] PAN is at v1.7 with the heatmap cap recorded as **decided — no cap**, and §174 corrected to state the MAL-id resolution and its cost. KIT carries the decision-5 reversal note.

## Proposal question round

`execution_mode: auto`, so these were not asked interactively. Owner decisions on the cap, the overwrite policy and un-scoring are **settled and not reopened here**. What follows is what remains genuinely open at the product level — each changes behaviour, not mechanics. Answer before design if any assumption is wrong.

| # | Question | Assumption taken |
|---|---|---|
| 1 | **Is a hand-typed `0` a real score or the same as unscored?** The export encodes 0 as "sin nota" and PAN §174 turns it into NULL. But the panel's range is 0-10, so the owner can type a deliberate 0 meaning *terrible* | The two vocabularies are different and both are right. In the **export**, 0 means "I never rated it" → NULL. In the **panel**, 0 is a legitimate score the owner typed on purpose and is stored as 0. Clearing is `null`, not `0`. |
| 2 | **Does `--dry-run` on `import-scores` pay the ~38 requests to be accurate?** `_cmd_import_kitsu`'s dry-run returns before any I/O — but without resolution it can only count scores *in the file*, never bookmarks it *would fill* | Cheap dry-run: file-only counts, and the output says so explicitly rather than implying it counted matches. An accurate dry-run costs the same as the real run and would just be the run without the write. |
| 3 | **An export entry whose manga is not in the database at all** — an error, or an ordinary skip? | Ordinary skip, reported in the summary. `import-scores` never creates a row; that is `import-kitsu`'s job and it already ran. |
| 4 | **Do scores apply to terminal bookmarks too?** Most scored entries in a Kitsu export are `completed` | Yes, all statuses. The score is a fact about a manga the owner read, and terminals are visible in the list — that is why their covers are in this same phase. |
| 5 | **Should `cache-covers` run both populations when given no `--status`,** or keep its current default (non-terminal only) and require `--status completed dropped` to reach the 66? | Keep the current default untouched; the terminals are opt-in via `--status`. Changing the bare default would silently change what an existing habit costs, from ~0 requests to 66. |
