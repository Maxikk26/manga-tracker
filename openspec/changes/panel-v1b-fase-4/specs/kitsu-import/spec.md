# Delta for Kitsu Import

## ADDED Requirements

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
- docs/spec-importador-kitsu.md (decision 5, reversed by this change)
- docs/spec-panel-v1b.md v1.6 §171-175
- openspec/changes/panel-v1b-fase-4/proposal.md
