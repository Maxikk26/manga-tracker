# Catalogue Specification

## Purpose

A confined-transport contract for resolving external catalogue metadata (title, alt titles, synopsis, genres, cover, publication status, chapter count) from a MyAnimeList id. Kitsu is today's implementation; the contract keeps a future catalogue swap to one new module plus one `cli.py` line (docs/spec-importador-kitsu.md v1.2 §"La frontera del catálogo").

## Requirements

### Requirement: Batch-only resolution contract

`CatalogueClient.resolve(external_ids)` MUST accept a batch of ids and return a list of `CatalogueEntry`; the contract MUST NOT expose a single-id resolution method (KIT §"El contrato").

#### Scenario: Batch resolves multiple ids in one call
- GIVEN 12 external ids
- WHEN `resolve` is called once
- THEN one call returns an entry for every id the catalogue maps

#### Scenario: An id with no mapping is observable, not dropped
- GIVEN a batch of 12 where 2 ids have no catalogue mapping
- WHEN `resolve` completes
- THEN the caller can identify which 2 ids produced no entry

### Requirement: Batching stays under the catalogue's page limit

The Kitsu implementation MUST request batches small enough that the API's per-page result limit cannot silently truncate mappings (measured: batch size 12 against `page[limit]=20`) (KIT §"Resolución").

#### Scenario: Batch of 12 loses nothing to pagination
- GIVEN 12 ids, each with exactly one mapping
- WHEN the batch resolves
- THEN 12 entries return

#### Scenario: A regression widening the batch is test-caught
- GIVEN a batch at or above the page limit, resolved against a fixture with more mappings than the limit
- WHEN the test runs
- THEN it fails on the missing entries, not silently in production

### Requirement: title_candidates is ordered and catalogue-opaque

`CatalogueEntry.title_candidates` MUST be a pre-ordered list ready for direct slug matching; no catalogue-specific field name (e.g. `abbreviatedTitles`, `canonicalTitle`) MUST appear anywhere outside the catalogue package (KIT §"title_candidates es la pieza que justifica la frontera").

#### Scenario: Consumer matches without knowing source field names
- GIVEN a resolved entry
- WHEN a consumer iterates `title_candidates`
- THEN it tries them in order with no reference to `abbreviatedTitles` or `canonicalTitle`

#### Scenario: Empty candidate list is valid, not an error
- GIVEN an entry with no usable title fields
- WHEN `title_candidates` is read
- THEN it is an empty list, treated as "no match possible", not a crash

### Requirement: alt_titles, synopsis and total_chapters populate without extra requests

`resolve()` MUST populate `alt_titles` and `synopsis` from the same `/manga` request used for title; genres MUST come from one additional `/manga?include=categories` call per batch (`include=item,item.categories` returns HTTP 400); `total_chapters` MUST be the catalogue's reported count when present and `None` — never `0` — when absent (KIT §"La frontera del catálogo").

#### Scenario: total_chapters absent stays null
- GIVEN an entry where the catalogue omits its chapter-count field
- WHEN the entry is built
- THEN `total_chapters` is `None`, not `0`

#### Scenario: Genres require the categories call
- GIVEN a batch resolved with `include=item` only
- WHEN genres are requested
- THEN a second `/manga?include=categories` call supplies them, not the first response

### Requirement: include=item is mandatory and its absence is test-caught

The Kitsu client MUST always send `include=item`; a regression dropping it MUST be caught by a test asserting non-zero resolution against a fixture, not discovered via a production run returning HTTP 200 with zero entries resolved (KIT §"Resolución").

#### Scenario: Missing include=item is caught before deploy
- GIVEN a code change omitting `include=item`
- WHEN the batch-resolution test runs
- THEN it fails because zero entries resolve

### Requirement: Confined transport, own package boundary

The catalogue MUST use its own transport module (`catalogue/transport.py`), MUST NOT let `curl_cffi` appear anywhere else under `catalogue/`, and MUST NOT import `storage`, `discovery`, `notifier`, `seed`, or `sources` (KIT §"El catálogo necesita su propio transporte confinado").

#### Scenario: Catalogue transport is confined
- GIVEN `catalogue/kitsu.py` needs an HTTP call
- WHEN implemented
- THEN it goes through `catalogue/transport.py`, and an architecture test fails if `curl_cffi` appears elsewhere in `catalogue/`

#### Scenario: Catalogue never imports storage or sources
- GIVEN any file under `manga_tracker/catalogue/`
- WHEN its imports are inspected
- THEN none of `storage`, `discovery`, `notifier`, `seed`, `sources` appear

## References

- docs/spec-importador-kitsu.md v1.2
- docs/spec-modelo-de-datos.md v1.7
