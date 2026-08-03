# Tasks: Kitsu importer (`importador-kitsu`)

> **Size-budget note**: this artifact exceeds the generic 530-word `sdd-tasks` guidance, following the same disclosed-deviation precedent as `sdd/v1a-heart-phase/tasks`. 22 requirements across 3 spec files and 8 design decisions (D1-D8) each need a named evidence task; compressing further would drop required traceability or evidence naming.
>
> **Version-pin note**: `docs/spec-importador-kitsu.md` is now **v1.3**; `design.md` and the three `specs/*/spec.md` files were written against v1.2. Both v1.3 closures — protecting `manual`-origin bookmarks alongside `seed`, and aborting the whole import on a failed sitemap shard — are already correctly anticipated by design D3 and by task 3.6 below. This is a stale pin, not a reopened decision (task 4.6 bumps it), consistent with this repo's own "a stale pin is a defect" rule.

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | ~1000-1800 (proposal's own risk register estimated ~900-1400 for a smaller task list; this breakdown adds the v1.3 abort-on-shard-failure path and the manual-origin regression test) |
| 400-line budget risk | High |
| Chained PRs recommended | No |
| Suggested split | size-exception single PR; the 5 work-unit commits below double as optional manual slices the user can assemble into separate PRs from commit history |
| Delivery strategy | single-pr |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High

**Override note**: `delivery_strategy: single-pr` formally maps to "Decision needed before apply: Yes" per the guard rules. Session preflight already recorded `size:exception` as accepted by the owner, which is the cached decision this guard exists to capture — so it is recorded resolved (`No`) rather than re-asked.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | Catalogue contract + confined transport + Kitsu client | PR 1 | `uv run pytest tests/catalogue/ -q` | `uv run python -c "from manga_tracker.catalogue.kitsu import KitsuCatalogue; from manga_tracker.catalogue.transport import UrllibJsonTransport; print(KitsuCatalogue(UrllibJsonTransport()).resolve(['146982']))"` (real, live Kitsu API, no DB) | Delete `manga_tracker/catalogue/**`, `tests/catalogue/**` — nothing else depends on it yet |
| 2 | `fetch_known_slugs` + manganato sitemap parsing | PR 2 | `uv run pytest tests/sources/test_sitemap.py -q` | `uv run python -c "from manga_tracker.sources.manganato.client import ManganatoClient; from manga_tracker.sources.manganato.transport import CurlCffiTransport; print(len(ManganatoClient(CurlCffiTransport()).fetch_known_slugs()))"` (real, ~1-2.5 min, expect ~91k) | Delete `manga_tracker/sources/manganato/sitemap.py`, revert `contracts.py`/`client.py` — independent of unit 1 |
| 3 | Importer pure core + loader + reconciliation writers | PR 3 | `uv run pytest tests/importer/test_export.py tests/importer/test_matching.py tests/importer/test_reconcile.py tests/importer/test_run.py -q` | N/A — needs unit 4's `cli.py` wiring to invoke end to end; this unit's proof is its own unit + integration tests against temp sqlite + fake clients (design's stated Testing Strategy) | Delete `manga_tracker/importer/{export,matching,reconcile,run}.py` + tests; revert `repositories.py`'s reconciliation additions — needs units 1+2's contracts to type-check but not their concretes |
| 4 | `cli.py` wiring + pending CSV + doc follow-through | PR 4 | `uv run pytest tests/importer/test_pending.py tests/test_cli.py -k kitsu -q` | `uv run python -m manga_tracker import-kitsu --file manga-tracker-data/kitsu-manga.xml` (real bring-up: live Kitsu + live manganato sitemap/fetch_chapters + real DB write) | Delete `manga_tracker/importer/pending.py`, revert `cli.py`'s `import-kitsu` subcommand — needs units 1-3 present but is glue only |
| 5 | Architecture rule proof (D8) | PR 5 | `uv run pytest tests/test_architecture.py -q` | N/A — static AST/import analysis, no runtime scenario | Revert `tests/test_architecture.py`'s new rules + injected-violation test — pure test-file change |

### Requirement aliases (traceability)

| Alias | Requirement | Alias | Requirement |
|---|---|---|---|
| CAT-1 | Batch-only resolution contract | IMP-7 | Chapter-count verification |
| CAT-2 | Batching under the page limit | IMP-8 | Candidate generation catalogue-agnostic |
| CAT-3 | `title_candidates` ordered/opaque | IMP-9 | Source failures → pending, never abort |
| CAT-4 | `alt_titles`/synopsis/`total_chapters` | IMP-10 | Unrecognized `my_status` is a hard error |
| CAT-5 | `include=item` mandatory, test-caught | IMP-11 | Pending CSV seed-loader compatible |
| CAT-6 | Confined transport, own boundary | IMP-12 | Re-run safety by constraint |
| IMP-1 | Manual invocation, file-plus-API | IMP-13 | Importer package boundary |
| IMP-2 | Reconciliation: 3 keys in order | SRC-1 | `fetch_known_slugs` sitemap membership |
| IMP-3 | Seed-origin bookmark never mutated | SRC-2 | No delay exemption for sitemap shards |
| IMP-4 | Status mapping + terminal short-circuit | SRC-3 | Existing `Response` shape is sufficient |
| IMP-5 | `last_read_at` midnight UTC, terminal-only | | |
| IMP-6 | Bookmark invariants | | |

## Phase 1: Catalogue contract + confined transport + Kitsu client (Unit 1)

*Stands alone: no DB, no importer, no `sources` dependency.*

- [x] 1.1 Create `manga_tracker/catalogue/contracts.py`: `CatalogueEntry` frozen dataclass, `CatalogueClient` Protocol exposing only `resolve(external_ids) -> Sequence[CatalogueEntry]` (CAT-1), own `Response`/`Transport`, `CatalogueTransient`/`CatalogueUnexpected`. No dependency on `manga_tracker.sources`.
- [x] 1.2 Create `manga_tracker/catalogue/transport.py` (D1): `UrllibJsonTransport(*, sleeper=time.sleep)` on stdlib `urllib.request`; no delay before the first call, deterministic 1.0s from the 2nd, one retry on 429/5xx; no `rng`.
- [x] 1.3 Create `manga_tracker/catalogue/kitsu.py`: `resolve()` chunks all ids at `BATCH_SIZE=12` (CAT-2); `/mappings?...&include=item&page[limit]=20` per chunk plus a separate `/manga?include=categories` call for genres (CAT-4); builds ordered `title_candidates` (`titles.en → abbreviatedTitles → canonicalTitle → titles.en_jp`) with no catalogue-specific name escaping the file (CAT-3); `total_chapters` is `None` when absent, never `0` (CAT-4); `assert BATCH_SIZE < PAGE_LIMIT`.
- [x] 1.4 In `kitsu.py`, raise `CatalogueUnexpected` when `relationships.item` has `links` but no `data` or `included` is empty (missing-`include=item` signature, CAT-5), and when a batch returns exactly `page[limit]` resources (possible truncation, CAT-2).
- [x] 1.5 Write `tests/catalogue/test_transport.py`: fake urllib call; asserts no delay before the first request, deterministic delay via injected `sleeper` (no real wait) from the 2nd, one retry on 429/500 then propagate.
- [x] 1.6 Write `tests/catalogue/test_kitsu.py` + fixtures `tests/fixtures/kitsu_mappings_ok.json`, `kitsu_mappings_missing_include.json`, `kitsu_categories.json`: 12-id batch resolves every mapped id, unmapped ids observable not dropped (CAT-1); missing-`include=item` fixture raises `CatalogueUnexpected` (CAT-5); a `page[limit]`-sized response raises `CatalogueUnexpected` (CAT-2); candidate order + empty-list-is-valid (CAT-3); `total_chapters is None` when absent (CAT-4).
- [x] 1.7 Extend `tests/test_architecture.py`: `CONFINEMENT_RULES["urllib.request"]` becomes `frozenset({"notifier/telegram.py", "catalogue/transport.py"})`; add `catalogue -> {storage, discovery, notifier, seed, sources}` to `DIRECTIONAL_RULES` and `catalogue` to the leaf-package set (D8, CAT-6). Evidence: `uv run pytest tests/test_architecture.py -q` green with `catalogue/` present (the injected-violation proof for this rule lands in Phase 5). Manually proven this attempt: 3 temporary violation files injected one at a time (`catalogue -> storage` import, a 2nd catalogue file importing `urllib.request`, a catalogue file importing `curl_cffi`) — each made `tests/test_architecture.py` fail with the expected message, then was deleted and the suite confirmed green again before committing.

## Phase 2: `fetch_known_slugs` + manganato sitemap parsing (Unit 2)

*Stands alone: extends the existing source-client contract, no importer dependency.*

- [ ] 2.1 Add `fetch_known_slugs(*, progress=None) -> frozenset[str]` to `manga_tracker/sources/contracts.py`'s `SourceClient` Protocol (SRC-1, SRC-3 — no new `Response`/`Transport` field).
- [ ] 2.2 Create `manga_tracker/sources/manganato/sitemap.py`: fetches `/sitemap.xml`, extracts the 10 shard URLs, fetches each sequentially through `CurlCffiTransport` with no delay exemption (SRC-2), parses each from `Response.text` via `ET.fromstring` (D7), unions all `<url>` slugs into one `frozenset[str]`; reports `progress(unit, total)` before each shard, never the word "shard" (D4); a shard exhausting retries raises via the existing `Transient`/`Unexpected` taxonomy rather than returning a partial set (SRC-1).
- [ ] 2.3 Modify `manga_tracker/sources/manganato/client.py`: `fetch_known_slugs` delegates to `sitemap.py`.
- [ ] 2.4 Add trimmed fixtures `tests/fixtures/sitemap_index.xml` (3 shard entries) and `tests/fixtures/sitemap_shard.xml` (a handful of `<url>` entries).
- [ ] 2.5 Write `tests/sources/test_sitemap.py` against a fake `Transport` double + stubbed `sleeper` (no real network, no real wait): full slug set is the union across shards, no duplicates; 2nd-through-10th shard fetch each preceded by a delay call (`len(sleeper.calls) == shards - 1`, SRC-2); a shard whose fake transport raises after its retries propagates `Unexpected`/`Transient` rather than returning a truncated set (SRC-1's RED case, proven before Phase 3 relies on it); a malformed shard body raises `Unexpected` naming the first 200 chars (D7 style).
- [ ] 2.6 Confirm `sitemap.py` needs no new `CONFINEMENT_RULES` entry (it reuses `CurlCffiTransport`, already confined to `sources/manganato/`). Evidence: `uv run pytest tests/test_architecture.py -q` green with `sitemap.py` present.

## Phase 3: Importer pure core + loader + reconciliation writers (Unit 3, needs 1+2)

*Pure modules (export/matching/reconcile) are fully unit-testable with no I/O; `run.py` is the only orchestration layer.*

- [ ] 3.1 Create `manga_tracker/importer/export.py`: parses the MAL-format XML via `ET.fromstring` (D7); status map with unmapped `my_status` as a hard error naming the value (IMP-10); `last_read_at` midnight-UTC of `my_finish_date` only when terminal and present, `NULL` otherwise, with a `0000-00-00` sentinel guard (IMP-5).
- [ ] 3.2 Create `manga_tracker/importer/matching.py` (pure): NFKD normalizer; two slug variants per candidate (apostrophe dropped/hyphenated, IMP-8); iterates `title_candidates` in order, first present-in-known-slugs wins, no later candidate tried; `is_suspect(my_read_chapters, newest_chapter)` predicate (IMP-7).
- [ ] 3.3 Create `manga_tracker/importer/reconcile.py` (pure): ordered three-key policy over plain values — kitsu_id / slug / normalized-title — with the exactly-one guardian on key 3 (IMP-2).
- [ ] 3.4 In `manga_tracker/storage/repositories.py`, add `find_manga_by_kitsu_id`, `list_manga_titles`, and Kitsu writers: enrich `mangas` (backfilling `kitsu_id` when key 2/3 resolved it); bookmark writer — INSERT when absent, UPDATE only when existing `origin='kitsu_import'`, `seed`/`manual` never touched (D3, IMP-3, and v1.3's explicit extension to `manual`). `write_seed_backfill` stays untouched.
- [ ] 3.5 Create `manga_tracker/importer/run.py`: per entry, inside one `db.transaction(conn)`, `fetch_chapters` → verify (IMP-7) → reconcile+write, so a suspect match leaves zero rows (D5); terminal entries skip the slug lane, zero requests (IMP-4); `NotFound`/`Unexpected`/`Transient`/zero-chapters per entry → pending, continue to next entry, never abort the run (IMP-9); `[i/total] 'Title' ...` with `flush=True` before each `fetch_chapters` call (D4).
- [ ] 3.6 In `run.py`, call `fetch_known_slugs()` once before matching any entry; if it raises, propagate and abort the whole run with zero rows written anywhere — do NOT route it to per-entry pending. This is KIT v1.3's new rule: a lost shard is ~10k missing slugs, and catching it per-entry would silently push real titles to pending as if absent from the source.
- [ ] 3.7 Write `tests/importer/test_export.py`: status map happy path + hard-error case naming the value (IMP-10); midnight-UTC for a real finish date, `NULL` for terminal-no-date, `NULL` for every non-terminal case regardless of date fields (IMP-5, all 3 scenarios); `0000-00-00` treated as absent.
- [ ] 3.8 Write `tests/importer/test_matching.py`: normalization on KIT's two documented real title pairs; both apostrophe variants tried; first match wins, no later candidate tried (IMP-8); `is_suspect(264, 30) is True`, `is_suspect(264, 300) is False` (IMP-7); `my_read_chapters == 0` never trips suspect.
- [ ] 3.9 Write `tests/importer/test_reconcile.py`: seed row with `kitsu_id IS NULL` + matching slug reconciles by key 2, return value carries the backfill (IMP-2 scenario 1); 2 normalized-title candidates → `ambiguous`, never merged (IMP-2 scenario 2); a row already carrying `kitsu_id` matches by key 1 alone, keys 2-3 not evaluated — asserted by call count on the plain-value lookups (IMP-2 scenario 3).
- [ ] 3.10 Write `tests/importer/test_run.py` against temp sqlite (real schema) + fake `CatalogueClient`/`SourceClient`: `origin='seed'` bookmark byte-identical after load (IMP-3); same for `origin='manual'` (v1.3 extension); an `origin='kitsu_import'` bookmark whose progress changed on re-import DOES fire one `reading_history` row (v1.3's "only path reading_history gets populated" — the positive case IMP-12 alone doesn't prove); a suspect match (IMP-7) leaves zero new rows anywhere and appears in pending; a completed entry loads with no `manga_sites` row, zero requests (IMP-4); a 404 on the matched slug → pending with resolved title, entry N+1 still processes (IMP-9); a `fetch_known_slugs` failure aborts the whole run with zero rows written (task 3.6); re-running the same export twice adds no duplicate row in any of the four tables and fires no `reading_history` event beyond the one legitimate case above (IMP-12, both scenarios).
- [ ] 3.11 Extend `tests/test_architecture.py`: add `importer -> {catalogue.kitsu, catalogue.transport, sources.manganato}` to `DIRECTIONAL_RULES` and `importer` to the leaf-package set (D8, IMP-13). Evidence: `uv run pytest tests/test_architecture.py -q` green with `importer/` present (injected-violation proof lands in Phase 5).

## Phase 4: `cli.py` wiring + pending CSV + doc follow-through (Unit 4, needs 1-3)

- [ ] 4.1 Create `manga_tracker/importer/pending.py` (D6): writes `manga-tracker-data/kitsu-pendientes.csv` (argument-overridable), header exactly `title,url,last_chapter_read,status`, `url` always empty, `csv.writer(..., newline="")`, UTF-8, `lineterminator="\n"`; status column emits only `seed/loader.py`'s five `VALID_STATUSES` (IMP-11).
- [ ] 4.2 Modify `manga_tracker/cli.py`: register `import-kitsu` — the sole place `catalogue.kitsu.KitsuCatalogue`, `catalogue.transport.UrllibJsonTransport`, `sources.manganato.client.ManganatoClient`/`transport.CurlCffiTransport` are constructed and wired into `importer.run.run_import(...)`; default path `data/kitsu-manga.xml`; prints per-phase progress banners (D4) before resolution, sitemap fetch, and the load loop.
- [ ] 4.3 Verify with `git check-ignore --stdin` that the default `data/kitsu-pendientes.csv` path stays out of version control (exit 0 — ignored, like every other file under `data/`), confirming D6's "must not join the template's re-inclusion rule."
- [ ] 4.4 Write `tests/importer/test_pending.py` (D6's two "no new code" tests): a freshly generated pending CSV run through unmodified `seed.loader.load_seed` reports one `... has no extractable slug` error per row and writes nothing; the same file with `url` filled loads cleanly through the same unmodified loader (IMP-11).
- [ ] 4.5 Extend `tests/test_cli.py` with `test_import_kitsu_*`: no `--file` argument reads `data/kitsu-manga.xml` (IMP-1 scenario 1); an unreachable catalogue (fake client raising `CatalogueTransient`) writes zero `mangas`/`bookmarks` rows, reports the failure, not a partial run (IMP-1 scenario 2).
- [ ] 4.6 Update `README.md` §19 and `docs/manganato-fuente-actual.md` §18 (Spanish prose): correct "Kitsu aporta la metadata pesada" to say the metadata arrives from the catalogue API at import time, not the export file (KIT §"Lo primero"). Bump the version-pin references in `design.md` and `specs/{catalogue,kitsu-import,source-client}/spec.md` from v1.2 to **v1.3** — a pin correction only, per this project's "stale pin is a defect" rule; no decision reopened.

## Phase 5: Architecture rule proof (Unit 5, closes D8 across Phases 1-3)

- [ ] 5.1 Parameterize `tests/test_architecture.py`'s scanners into `_directional_violations(pkg_root)` / `_confinement_violations(pkg_root)`, reused by both the real-package assertions and the injected-violation test below (D8).
- [ ] 5.2 Add `catalogue.kitsu` to `CONCRETE_IMPLEMENTATIONS` (D8).
- [ ] 5.3 Write `test_boundary_check_flags_an_injected_violation`: a throwaway `tmp_path` tree with 3 probes — `catalogue/probe.py` importing `manga_tracker.storage.db`, `importer/probe.py` importing `manga_tracker.catalogue.kitsu`, `catalogue/probe2.py` importing `curl_cffi` — asserting `_directional_violations`/`_confinement_violations` report all 3 by name. Retro-proves every rule Phases 1 and 3 added actually fires against real file layout, not just that the rule string can match (this repo's documented failure mode: a prefix that could never match while the suite stayed green).
- [ ] 5.4 Run `uv run pytest tests/test_architecture.py -q` as the final regression gate: all directional rules (incl. the 2 new ones), all confinement rules (incl. the widened `urllib.request` set), `CONCRETE_IMPLEMENTATIONS`, and the injected-violation test pass together against the real `manga_tracker/catalogue/` and `manga_tracker/importer/` packages.
