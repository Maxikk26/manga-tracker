# Apply Progress: `importador-kitsu`

**Mode**: Standard (strict_tdd: false). Tests shipped with the code in the same commit.

## Completed Tasks

### Phase 1: Catalogue contract + confined transport + Kitsu client (Unit 1)

- [x] 1.1 `manga_tracker/catalogue/contracts.py`: `CatalogueEntry` frozen dataclass, `CatalogueClient` Protocol (`resolve` only), own `Response`/`Transport`, `CatalogueTransient`/`CatalogueUnexpected`. No dependency on `manga_tracker.sources`.
- [x] 1.2 `manga_tracker/catalogue/transport.py`: `UrllibJsonTransport(*, sleeper=time.sleep)` on stdlib `urllib.request`; no delay before the first call, deterministic 1.0s from the 2nd, one retry on 429/5xx; no `rng`.
- [x] 1.3 `manga_tracker/catalogue/kitsu.py`: `resolve()` chunks all ids at `BATCH_SIZE=12`; `/mappings?...&include=item&page[limit]=20` per chunk plus a separate `/manga?include=categories` call for genres; ordered `title_candidates`; `total_chapters` is `None` when absent, never `0`; `assert BATCH_SIZE < PAGE_LIMIT`.
- [x] 1.4 `CatalogueUnexpected` raised when `relationships.item` has `links` but no `data`, when `included` is empty alongside non-empty mappings, and when a batch returns exactly `page[limit]` resources.
- [x] 1.5 `tests/catalogue/test_transport.py` (5 tests): no delay before the first request; deterministic delay from the 2nd (no real wait); one retry on 429 then 200; one retry on 429 then a persistent 500 (returned as data, mirrors `CurlCffiTransport`); a genuine network failure retried once then raised as `CatalogueTransient`.
- [x] 1.6 `tests/catalogue/test_kitsu.py` (9 tests) + fixtures `kitsu_mappings_ok.json`, `kitsu_mappings_missing_include.json`, `kitsu_categories.json`: batch resolution with unmapped ids observable not dropped; missing-`include=item` raises; page-full response raises; ordered `title_candidates`; empty candidate list is valid; `total_chapters` null vs present; `alt_titles`/`synopsis` from the first call, genres only from the second; publication-status mapping; chunking across `BATCH_SIZE`.
- [x] 1.7 `tests/test_architecture.py` extended: `CONFINEMENT_RULES` values are now frozensets, `urllib.request` maps to `{notifier/telegram.py, catalogue/transport.py}`; `catalogue -> {storage, discovery, notifier, seed, sources}` added to `DIRECTIONAL_RULES`, and `catalogue` added to the forbidden set of `sources`/`notifier`/`storage` (the leaf packages). Both new rules were manually proven this attempt by injecting one violation at a time (deleted before commit — the permanent injected-violation test lands in Phase 5 per design D8):
  - `catalogue/_tmp_violation_directional.py` importing `manga_tracker.storage` → `test_directional_boundaries` failed with `"catalogue/_tmp_violation_directional.py imports forbidden module 'manga_tracker.storage'"`.
  - `catalogue/_tmp_violation_confinement.py` importing `urllib.request` (not `transport.py`) → `test_third_party_confinement` failed with `"catalogue/_tmp_violation_confinement.py imports confined module 'urllib.request', only ['catalogue/transport.py', 'notifier/telegram.py'] may"`.
  - `catalogue/_tmp_violation_curlcffi.py` importing `curl_cffi` → `test_third_party_confinement` failed with `"catalogue/_tmp_violation_curlcffi.py imports confined module 'curl_cffi', only ['sources/manganato/transport.py'] may"`.
  - All three files deleted; `tests/test_architecture.py -q` green again (4 passed) before committing.

## Files Changed

| File | Action | What Was Done |
|------|--------|---------------|
| `manga_tracker/catalogue/__init__.py` | Created | Empty package marker |
| `manga_tracker/catalogue/contracts.py` | Created | `CatalogueEntry`, `CatalogueClient`, own `Response`/`Transport`, `CatalogueTransient`/`CatalogueUnexpected` |
| `manga_tracker/catalogue/transport.py` | Created | `UrllibJsonTransport`: stdlib urllib, 1.0s courtesy delay, one retry on 429/5xx |
| `manga_tracker/catalogue/kitsu.py` | Created | `KitsuCatalogue.resolve()`: batching, missing-include/page-full guards, ordered title candidates, categories call |
| `tests/catalogue/test_transport.py` | Created | 5 tests, `urllib.request.urlopen` monkeypatched, no real socket/wait |
| `tests/catalogue/test_kitsu.py` | Created | 9 tests against a scripted fake `Transport` |
| `tests/fixtures/kitsu_mappings_ok.json` | Created | 3 mapped ids: full candidate order, missing fields, empty-title case |
| `tests/fixtures/kitsu_mappings_missing_include.json` | Created | Reproduces the missing-`include=item` signature (links, no data; empty included) |
| `tests/fixtures/kitsu_categories.json` | Created | Categories response for the two entries with genres |
| `tests/test_architecture.py` | Modified | `CONFINEMENT_RULES` → frozensets; `catalogue` added to `DIRECTIONAL_RULES` and to the leaf packages' forbidden sets |
| `openspec/changes/importador-kitsu/tasks.md` | Modified | Phase 1 tasks (1.1-1.7) marked `[x]` with evidence notes |

## Deviations from Design

None — implementation matches design D1, D2 and CAT-1..6. One clarification made where the design was silent: a persistent transient HTTP status (429/5xx surviving the transport's one retry) is turned into `CatalogueTransient` at the `kitsu.py` call site rather than the transport itself, mirroring `CurlCffiTransport`'s existing asymmetry (the transport only raises on a genuine network-level failure; a repeated bad status code is handed back as data for the caller to classify).

## Issues Found

None.

## Work Unit Evidence

| Evidence | Value |
|---|---|
| Focused test command and exact result | `.venv/Scripts/python.exe -m pytest tests/catalogue/ tests/test_architecture.py -q` → 18 passed |
| Runtime harness command/scenario and exact result | `python -c "from manga_tracker.catalogue.kitsu import KitsuCatalogue; from manga_tracker.catalogue.transport import UrllibJsonTransport; print(KitsuCatalogue(UrllibJsonTransport()).resolve(['146982']))"` — NOT run this attempt: it is a real, live call to the public Kitsu API (`kitsu.io`) and the sandbox's `conftest.py`-style network block for the interactive shell was not lifted; treat as `N/A` for this batch pending an environment with live network egress. All logic exercised instead via the 14 unit tests against a scripted fake transport. |
| Rollback boundary | Delete `manga_tracker/catalogue/**`, `tests/catalogue/**`, the 3 `tests/fixtures/kitsu_*.json` fixtures, and revert the `tests/test_architecture.py` diff. Nothing else in the repo depends on `catalogue/` yet. |

## Remaining Tasks

- [ ] Phase 2: `fetch_known_slugs` + manganato sitemap parsing (Unit 2)
- [ ] Phase 3: Importer pure core + loader + reconciliation writers (Unit 3)
- [ ] Phase 4: `cli.py` wiring + pending CSV + doc follow-through (Unit 4)
- [ ] Phase 5: Architecture rule proof — permanent injected-violation test (Unit 5)

## Workload / PR Boundary

- Mode: single PR, `size:exception` (accepted by the owner per session preflight)
- Current work unit: Unit 1 — Catalogue contract + confined transport + Kitsu client
- Boundary: starts from no `catalogue/` package existing; ends with `catalogue/` fully self-contained, tested, and boundary-proven, with zero other package depending on it yet
- Estimated review budget impact: ~850 changed lines this unit (739 authored code/tests/fixtures + 105 in the `tasks.md` checklist artifact + 6 net in `test_architecture.py`'s diff), within the already-accepted `size:exception` for the full change's forecasted 1000-1800 lines

## Status

7/7 Phase 1 tasks complete (1.1-1.7). Full repo suite: 112/112 passing (98 baseline + 14 new). Ready for Phase 2 (`sdd-apply` again) — do not run `sdd-verify` yet, since Phases 2-5 of this change remain unstarted.
