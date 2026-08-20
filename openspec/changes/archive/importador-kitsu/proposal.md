# Proposal: Kitsu importer (`importador-kitsu`)

V1a phase 3 ("backfill"), closing done-criterion 4. **`docs/spec-importador-kitsu.md` v1.1 is the contract** — this proposal shapes the work, it does not restate the decisions.

| Alias | Document |
|---|---|
| KIT | `docs/spec-importador-kitsu.md` v1.1 |
| DM | `docs/spec-modelo-de-datos.md` v1.7 |
| SEED | `docs/spec-seed-manual.md` v2.3 |
| CD | `docs/spec-cliente-fuente-descubrimiento.md` v1.4 |

## Intent

218 Kitsu entries live only in an export file. The DB holds only what the seed loader typed by hand. Until the backfill runs there is no history to detect against and no dataset for V1b statistics — and that data is not reconstructible later.

## Scope

### In scope

| # | Deliverable | Implements |
|---|---|---|
| 1 | `catalogue/contracts.py` — `CatalogueEntry`, `CatalogueClient.resolve(external_ids)` | KIT §El contrato |
| 2 | `catalogue/kitsu.py` — batches of 12, mandatory `include=item`, separate categories call | KIT §Resolución |
| 3 | `fetch_known_slugs()` on the source contract, implemented in `sources/manganato/` (sitemap is source knowledge) | KIT §La resolución no sondea |
| 4 | `importer/` — XML read, status map, ordered candidates + normalization, membership match, chapter-count verification, load, pending CSV | KIT §El archivo…§La lista de pendientes |
| 5 | Repository writes for `origin = kitsu_import`, `progress_is_approx = 1`, and the seed-protection rule | DM `bookmarks.origin` |
| 6 | `import-kitsu` CLI subcommand — the only place concretes are wired | KIT §Dónde vive |
| 7 | `DIRECTIONAL_RULES` + `CONCRETE_IMPLEMENTATIONS` extended for `catalogue` and `importer` | KIT §Dónde vive |
| 8 | Doc follow-through: README §19 and `manganato-fuente-actual.md` §18 still say metadata arrives with the file | KIT §Lo primero |

### Out of scope

Anime. Scheduler changes. Sitemap as a detection mechanism (closed against). A `mal_id` or `my_score` column. Filling `url` in the pending CSV — that is manual by design.

## Capabilities

### New

- `catalogue-client`: the catalogue contract, batch resolution, ordered `title_candidates`, Kitsu as one implementation.
- `kitsu-importer`: XML parsing, status mapping, slug matching, verification, load order, pending-list output, re-run safety.

### Modified

- `source-client`: gains `fetch_known_slugs()`. Its spec lives in the unarchived `openspec/changes/v1a-heart-phase/specs/source-client/spec.md`; `openspec/specs/` is still empty, so the delta targets that file.

## Approach

Five work units, each one reviewable commit with its tests:

1. Catalogue contract + Kitsu client + `catalogue` boundary rules. No DB, no importer.
2. `fetch_known_slugs` + manganato sitemap parsing, tested against a trimmed shard fixture.
3. Importer pure core — parse, map, candidates, match, verify. No I/O, so fully unit-testable.
4. Load + pending CSV + repository writes + `importer` boundary rules.
5. CLI wiring and doc follow-through.

**The boundary is the point.** `title_candidates` arrives ordered, so the importer never learns `abbreviatedTitles` exists. The importer asks for a set of known slugs and never learns what a sitemap is. Only `cli.py` names `catalogue.kitsu` or `sources.manganato`. Each rule added to `DIRECTIONAL_RULES` is proven to fire by `test_directional_rules_actually_fire`, plus an injected-violation check — this repo has direct history of a boundary rule that could never match while the suite stayed green.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `manga_tracker/catalogue/` | New | Contract + Kitsu implementation. |
| `manga_tracker/importer/` | New | Contract-only consumer. |
| `manga_tracker/sources/contracts.py`, `sources/manganato/` | Modified | `fetch_known_slugs` + sitemap parsing. |
| `manga_tracker/storage/repositories.py` | Modified | `write_seed_backfill` hardcodes `origin='seed'`, `progress_is_approx=0` and upserts the bookmark unconditionally — it **must not** be reused as-is. |
| `manga_tracker/cli.py` | Modified | One subcommand. |
| `tests/test_architecture.py` | Modified | Two new rule sets. |
| `README.md`, `docs/manganato-fuente-actual.md` | Modified | Follow-through only, no new decisions. |
| Runtime behaviour | None | Nothing the scheduler runs changes. |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| **Spec gap — seed/Kitsu reconciliation key.** KIT step 1 locates `mangas` by `kitsu_id`, but seed rows have `kitsu_id = NULL`. The "never touch an `origin = seed` bookmark" rule can only fire if the entry resolves to that same row, and the only join available is the slug. Resolution order is undefined; getting it wrong silently duplicates the manga instead of enriching it | **High** | Owner decision required before unit 4. Do not resolve by default judgment. |
| **Confinement rules leave the catalogue with no HTTP path.** `curl_cffi` is confined to `sources/manganato/transport.py`, `urllib.request` to `notifier/telegram.py`. Kitsu needs its own confined transport file and a `CONFINEMENT_RULES` entry | High | Design decision in unit 1; shapes the package. |
| **Sitemap through `CurlCffiTransport` is not delay-free.** The transport sleeps 5-15s from the 2nd call onward, so KIT's "10 requests sin delay" costs ~1-2.5 min. Also unclear whether shards arrive as text or gzip — `Response` exposes only `text: str` | Med | Accept the delay or add an exemption; decide in design, not silently. |
| **Spec gap — `my_finish_date` is a date, DM requires a full UTC timestamp** for `last_read_at`. No time-of-day is specified; MAL exports also emit `0000-00-00` sentinels | Med | Owner decision; small but unrecoverable once written. |
| **DM says `alt_titles` and `synopsis` come from the catalogue; KIT's destination table omits both.** Synopsis is nearly free — the categories call already hits `/manga` | Med | Raise, do not decide. README §19 promises synopsis. |
| Verification by chapter count misses near-duplicates | Med | Accepted in KIT §Pendientes abiertos. |
| **~900-1400 changed lines vs the 800-line budget**, `single-pr` | High | Needs an accepted `size:exception` or a split at unit 3. Work-unit commits carry the review load. |
| Remote XML parsed with stdlib `iterparse` (91k URLs) | Low | One-shot operator tool; consider `defusedxml` in design. |

## Rollback Plan

No existing behaviour changes, so rollback is removal:

- Per unit: revert that commit. Units 1-3 are independently removable; 4 needs 1-3; 5 is glue.
- Whole change: delete `catalogue/` and `importer/`, revert the six modified files.
- **Data**: rows written by this change are exactly `bookmarks.origin = 'kitsu_import'` and their `mangas`/`manga_sites`/`chapter_history` descendants. Seed rows are untouched by construction, so a SQL cleanup is surgical. `reading_history` stays empty — the trigger is UPDATE-only.
- Never delete `manga-tracker-data/seed.csv` or `kitsu-manga.xml`; both are hand-held and not reconstructible.

## Dependencies

- Blocked on the two owner decisions in Risks (reconciliation key, `last_read_at` normalization) before unit 4 lands.
- `manga-tracker-data/kitsu-manga.xml` must exist locally. Never committed.
- Kitsu's public API reachable at run time. Import is file **plus** API — offline it does nothing.
- KIT pins DM v1.7, CD v1.4, SEED v2.3, SRC v1.3. All currently consistent; re-check after any bump.

## Success Criteria

- [ ] 218 entries imported; the 66 terminal ones get no `manga_sites` row and consume zero requests.
- [ ] `progress_is_approx = 1` and `origin = 'kitsu_import'` on every bookmark this creates.
- [ ] An existing `origin = 'seed'` bookmark is enriched in `mangas` and left byte-identical in `bookmarks` — regression test.
- [ ] A batch of 12 against `page[limit]=20` resolves every id; a missing `include=item` is caught by a test, not by a silent zero-resolution run.
- [ ] A slug whose newest chapter is below `my_read_chapters` is rejected to pending, not loaded.
- [ ] `kitsu-pendientes.csv` is consumed by the existing seed loader with **no new code**.
- [ ] Re-running the import inserts no duplicate manga, mapping, chapter or reading event.
- [ ] `catalogue` and `importer` boundary rules fail when a violation is injected.
- [ ] pytest passes with no network access.
