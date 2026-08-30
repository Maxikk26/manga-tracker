# Kitsu Import Specification

## Purpose

A manually invoked, one-shot CLI utility that reads Kitsu's MyAnimeList-format XML export plus a catalogue lookup, reconciles entries against existing `mangas`/`bookmarks` rows, matches active/on-hold/want-to-read entries against manganato via sitemap membership, and loads history — closing V1a done-criterion 4 (docs/spec-importador-kitsu.md v1.3).

## Requirements

### Requirement: Manual invocation, file-plus-API nature

The importer MUST be invoked manually, outside the scheduler, reading the export path as an argument defaulting to `data/kitsu-manga.xml`; because title resolution requires the catalogue, it MUST NOT write any `mangas`/`bookmarks` row when the catalogue is unreachable (KIT §"Lo primero").

#### Scenario: Default path used with no argument
- GIVEN the importer runs with no path argument
- WHEN it starts
- THEN it reads `data/kitsu-manga.xml`

#### Scenario: Unreachable catalogue writes nothing
- GIVEN the catalogue API is unreachable
- WHEN the importer runs
- THEN no `mangas` or `bookmarks` row is written and the failure is reported

### Requirement: Reconciliation is three keys in order, first match wins

For each entry the importer MUST locate an existing `mangas` row by, in order: (1) `mangas.kitsu_id`, (2) the resolved slug via `manga_sites.source_key` for manganato, (3) an exact normalized-title match. Key 3 MUST fire only when normalization yields exactly one candidate row; zero or multiple candidates MUST be reported for manual review, never guessed. A match via key 2 or 3 MUST backfill the row's missing `kitsu_id` (KIT §"Reconciliación con las filas del seed").

#### Scenario: Seed row with no kitsu_id reconciles by slug
- GIVEN a seed-loaded `mangas` row with `kitsu_id = NULL` and a matching slug
- WHEN the Kitsu entry resolves to the same slug
- THEN the existing row is enriched and its `kitsu_id` is written; no duplicate row is created

#### Scenario: Ambiguous title match is reported, not merged
- GIVEN normalized-title matching yields 2 candidate rows
- WHEN key 3 is evaluated
- THEN the entry is reported for manual review and no row is merged

#### Scenario: Second run hits key 1 directly
- GIVEN a row already carries the `kitsu_id` written by a prior run
- WHEN the importer re-runs
- THEN key 1 matches directly and keys 2-3 are not evaluated

### Requirement: A seed-origin bookmark is never mutated

If the reconciled `mangas` row has a `bookmarks` row with `origin = 'seed'`, the importer MUST enrich only the `mangas` row and MUST NOT insert, update, or delete that `bookmarks` row (spec-modelo-de-datos.md `bookmarks.origin`; KIT §"Carga").

#### Scenario: Seed bookmark survives the import byte-identical
- GIVEN a `bookmarks` row with `origin = 'seed'`
- WHEN the same manga's Kitsu entry is loaded
- THEN `mangas` gains catalogue metadata and the `bookmarks` row is unchanged in every column

### Requirement: Status mapping and terminal short-circuit

`my_status` MUST map to `bookmarks.status` per {Reading→reading, On Hold→on_hold, Plan to Read→want_to_read, Dropped→dropped, Completed→completed}. Only the first three require a slug match; `dropped` and `completed` entries MUST get no `manga_sites` row and consume zero source requests (KIT §"Reparto por estado").

#### Scenario: Completed entry loads without a source request
- GIVEN an entry with `my_status = Completed`
- WHEN it loads
- THEN `mangas`/`bookmarks` are created/enriched and no `manga_sites` row or source request occurs

#### Scenario: Reading entry with no slug match goes to pending
- GIVEN an entry with `my_status = Reading`
- WHEN no candidate slug matches the known-slugs set
- THEN the entry is routed to pending, not loaded with a guessed slug

### Requirement: last_read_at is midnight UTC of my_finish_date, terminal-only

`bookmarks.last_read_at` MUST be set to `my_finish_date` at `00:00:00Z` only when the mapped status is terminal (`completed`/`dropped`) and `my_finish_date` is present; in every other case it MUST stay `NULL` (KIT §"El archivo").

#### Scenario: Terminal entry with a finish date gets midnight UTC
- GIVEN a completed entry with `my_finish_date = 2021-09-07`
- WHEN it loads
- THEN `bookmarks.last_read_at = "2021-09-07T00:00:00Z"`

#### Scenario: Terminal entry without a finish date stays null
- GIVEN a dropped entry with no `my_finish_date`
- WHEN it loads
- THEN `bookmarks.last_read_at` is `NULL`

#### Scenario: Non-terminal entry never gets a value
- GIVEN a Reading entry
- WHEN it loads
- THEN `bookmarks.last_read_at` is `NULL` regardless of any date field on the entry

### Requirement: Bookmark invariants for every entry this importer writes

Every `bookmarks` row created by this importer MUST have `origin = 'kitsu_import'`, `progress_is_approx = 1`, and `last_chapter_read` taken only from `my_read_chapters` (KIT §"Carga").

#### Scenario: Progress is flagged approximate
- GIVEN any entry loaded by this importer
- WHEN its bookmark is inspected
- THEN `progress_is_approx = 1` and `origin = 'kitsu_import'`

### Requirement: Chapter-count verification rejects impossible matches

A matched slug MUST be verified before acceptance: if `my_read_chapters` exceeds the newest chapter number `fetch_chapters` reports for that slug, the match MUST be discarded and the entry routed to pending instead of loaded (KIT §"Verificación").

#### Scenario: Progress ahead of the source rejects the match
- GIVEN a candidate slug whose newest chapter is 30
- WHEN the entry's `my_read_chapters` is 264
- THEN the match is discarded and the entry goes to pending

#### Scenario: Progress within range accepts the match
- GIVEN a candidate slug whose newest chapter is 300
- WHEN the entry's `my_read_chapters` is 264
- THEN the match is accepted and loading proceeds

### Requirement: Candidate generation is catalogue-agnostic

Slug candidates MUST be generated by iterating the catalogue's `title_candidates` in order, and for each name producing two normalized slug variants (apostrophes dropped, apostrophes hyphenated); the importer MUST NOT reference any catalogue-specific field name (KIT §"Candidatos, en orden").

#### Scenario: Apostrophe variants both get tried
- GIVEN a candidate title `"villain's return"`
- WHEN slugs are generated
- THEN both `villains-return` and `villain-s-return` are tried against the known-slugs set

#### Scenario: First matching candidate wins, in order
- GIVEN candidate 1 has no match and candidate 2 matches a known slug
- WHEN matching runs
- THEN candidate 2's slug is used and no later candidate is tried

### Requirement: Source failures route to pending, never abort the run

An entry whose matched slug returns not-found, transient, or unexpected from `fetch_chapters`, or resolves to zero chapters, MUST be reported and routed to pending with its already-resolved title; the run MUST continue processing remaining entries even after a transient failure, unlike the seed loader's abort-on-transient behavior — retrying 136 entries once per re-run is cheap, an aborted 34-minute run is not (KIT §"Carga").

#### Scenario: A 404 on the matched slug does not stop the run
- GIVEN entry N's `fetch_chapters` call returns not-found
- WHEN the importer processes entry N
- THEN entry N is written to pending with its resolved title, and entry N+1 still processes

#### Scenario: A transient failure does not abort the run
- GIVEN entry N's `fetch_chapters` call raises a transient error after its retry
- WHEN the importer processes entry N
- THEN entry N is written to pending and entry N+1 still processes, rather than the run stopping

### Requirement: An unrecognized my_status is a hard error, not a silent skip

If an entry's `my_status` is not one of the five mapped values, the importer MUST fail loudly for that entry (hard error) rather than silently skipping it or guessing a default status (KIT §"Reparto por estado", by extension of the project's error-taxonomy convention).

#### Scenario: Unmapped status halts that entry with a visible error
- GIVEN an entry with `my_status = "Rewatching"` (not one of the five mapped values)
- WHEN the importer processes it
- THEN it reports a hard error naming the unrecognized value, and does not load the entry under a guessed status

### Requirement: Pending CSV is seed-loader compatible with no new code

The pending list MUST be written to `manga-tracker-data/kitsu-pendientes.csv` with columns `title, url, last_chapter_read, status`, matching the seed template's format, with `url` left empty for manual completion; it MUST be loadable by the existing seed loader without any loader code change (KIT §"La lista de pendientes").

#### Scenario: Pending file loads through the unmodified seed loader
- GIVEN a `kitsu-pendientes.csv` with `url` filled in by hand
- WHEN the seed loader runs against it
- THEN it loads with no changes to the seed loader's code

### Requirement: Re-running the import is safe by constraint, not by care

Re-running the importer MUST NOT create duplicate `mangas`, `manga_sites`, `chapter_history`, or `bookmarks` rows, relying on `mangas.kitsu_id` UNIQUE, `manga_sites (site_id, source_key)` UNIQUE, and `chapter_history (manga_site_id, chapter_num)` UNIQUE; the bulk insert MUST NOT fire a `reading_history` event, since that trigger is UPDATE-only (KIT §"Re-ejecución").

#### Scenario: Second run on the same file is a no-op for existing rows
- GIVEN the importer already loaded an entry
- WHEN the same file is imported again unchanged
- THEN no duplicate row appears in any of the four tables

#### Scenario: Bulk import fires zero reading_history events
- GIVEN a fresh database and the full 218-entry export
- WHEN the import completes
- THEN `reading_history` remains empty

### Requirement: Importer package boundary

`manga_tracker/importer/` MUST NOT import `catalogue.kitsu`, `catalogue.transport`, or `sources.manganato` directly; only `cli.py` may wire those concrete implementations into the importer (KIT §"Dónde vive").

#### Scenario: Boundary violation fails the architecture test
- GIVEN a hypothetical edit adding `import catalogue.kitsu` inside `importer/`
- WHEN the architecture test suite runs
- THEN it fails, naming the offending import

### Requirement: ExportEntry carries `my_score`; the export's zero means unscored

`ExportEntry` MUST carry `my_score` parsed from the Kitsu export, reversing the prior decision to omit it. The export encodes "never rated" as 0; the importer MUST translate that to `None`, not `0` — the export's zero and the panel's own storable zero mean different things at the two ends of this pipeline.

#### Scenario: A real score parses through
- GIVEN an export entry with `my_score = 8`
- WHEN it is parsed
- THEN `ExportEntry.my_score == 8`

#### Scenario: An export zero becomes None, not 0
- GIVEN an export entry with `my_score = 0`
- WHEN it is parsed
- THEN `ExportEntry.my_score is None`

### Requirement: `import-scores` resolves MAL ids through the catalogue, and writes nothing if it is unreachable

The system MUST provide a one-off CLI command, `import-scores`, that resolves each export entry's MAL id to `mangas.kitsu_id` through the same catalogue resolution `import-kitsu` uses, before any bookmark write. If the catalogue is unreachable, it MUST write nothing and MUST report the failure.

#### Scenario: Catalogue unreachable writes nothing
- GIVEN the Kitsu catalogue API is unreachable
- WHEN `import-scores` runs
- THEN no `bookmarks.my_score` value changes and the failure is reported

#### Scenario: A resolved entry fills its matching bookmark
- GIVEN an export entry whose MAL id resolves to a `mangas` row with `my_score = NULL`
- WHEN `import-scores` runs
- THEN that row's `my_score` is set from the export

### Requirement: `import-scores` fills only NULL scores, never overwrites

A bookmark whose `my_score` is already non-NULL MUST be left unchanged by `import-scores`, regardless of what the export reports for it, and MUST be counted as skipped rather than filled.

#### Scenario: A hand-edited score survives a re-run
- GIVEN a bookmark with `my_score = 7`, set by the owner through the panel
- WHEN `import-scores` runs again with an export reporting `9` for that manga
- THEN the stored score remains 7 and the run reports it as skipped, not overwritten

#### Scenario: A second run on the same file fills zero
- GIVEN `import-scores` already filled every resolvable entry once
- WHEN it runs again unchanged
- THEN it fills zero scores, including zero overwrites

### Requirement: An entry with no matching manga is an ordinary skip

An export entry whose resolved `kitsu_id` matches no existing `mangas` row MUST be reported as an ordinary skip; `import-scores` MUST NOT create a `mangas` or `bookmarks` row.

#### Scenario: Unmatched entry is skipped, not an error
- GIVEN an export entry resolves to a `kitsu_id` absent from `mangas`
- WHEN `import-scores` processes it
- THEN it is reported as skipped and no row is created

### Requirement: Dry-run reports file-only counts before any I/O

`import-scores --dry-run` MUST return before opening a database connection or making a catalogue request, reporting counts derived only from the export file's content, and MUST state explicitly that these are file counts, not resolved matches.

#### Scenario: Dry-run makes no network or database call
- GIVEN `import-scores --dry-run` is invoked
- WHEN it runs
- THEN it reports scored-entry counts from the file alone, with no catalogue request and no database write

## References

- docs/spec-importador-kitsu.md v1.3 (decision 5 reversed by panel-v1b-fase-4)
- docs/spec-modelo-de-datos.md v1.7
- docs/spec-seed-manual.md v2.3
