# Data Model Specification

## Purpose

SQLite schema for manga-tracker V1a: 7 tables plus 1 trigger, created complete on first boot (spec-modelo-de-datos.md §"Propósito y principios", §"Las 7 tablas").

## Requirements

### Requirement: Complete schema on first boot

The system MUST create all 7 tables (`mangas`, `sites`, `manga_sites`, `bookmarks`, `reading_history`, `chapter_history`, `job_runs`) and the single trigger on first boot, even though only part of the schema is actively populated in this phase (spec-modelo-de-datos.md §"Propósito y principios").

#### Scenario: Fresh database bootstrap

- GIVEN no database file exists
- WHEN the application starts for the first time
- THEN all 7 tables and the trigger exist, and `sites` contains exactly one row for manganato

### Requirement: Foreign key enforcement

Every connection MUST enable SQLite foreign key enforcement, which is off by default (spec-modelo-de-datos.md §"Convenciones globales").

#### Scenario: FK violation rejected

- GIVEN a connection is open
- WHEN an insert into `manga_sites` references a non-existent `manga_id`
- THEN the insert is rejected by foreign key enforcement

### Requirement: Timestamps are UTC, always

Every `*_at` column MUST store a full ISO 8601 UTC timestamp; the database MUST NOT store local time, and local-time conversion MUST happen only in a presentation layer, applied before any calendar-day grouping (spec-modelo-de-datos.md §"Convenciones globales").

#### Scenario: Source timestamp stored unmodified

- GIVEN the source's JSON endpoint returns a UTC timestamp
- WHEN it is written to `chapter_history.source_published_at`
- THEN it is stored exactly as received, with no timezone conversion

### Requirement: reading_history trigger fires only on UPDATE

The single trigger on `bookmarks` MUST fire only after an UPDATE that changes `last_chapter_read` to a different value, and MUST NOT fire on INSERT, so bulk seed and any future Kitsu import never generate synthetic reading events (spec-modelo-de-datos.md §5, trigger note).

#### Scenario: Manual progress edit captured

- GIVEN a bookmark's `last_chapter_read` is updated to a new value
- WHEN the UPDATE commits
- THEN a `reading_history` row is inserted with the new and previous values

#### Scenario: Bulk seed insert generates no event

- GIVEN the seed loader inserts a new `bookmarks` row with `last_chapter_read` already set
- WHEN the INSERT commits
- THEN no `reading_history` row is created

#### Scenario: Downward correction is kept as honest data

- GIVEN a bookmark is updated from chapter 50 to chapter 40
- WHEN the trigger fires
- THEN the resulting `reading_history` row records `chapter_num=40`, `previous_chapter_num=50`, and is not discarded

### Requirement: chapter_history idempotency

`chapter_history` MUST enforce uniqueness on (`manga_site_id`, `chapter_num`); inserting an already-registered chapter MUST be silently ignored rather than erroring (spec-modelo-de-datos.md §6).

#### Scenario: Reprocessing does not duplicate

- GIVEN a chapter is already registered in `chapter_history`
- WHEN the same chapter is detected again by any mechanism
- THEN no duplicate row is inserted and no error is raised

### Requirement: consecutive_failures column semantics

`manga_sites.consecutive_failures` MUST be non-nullable and default to 0; it exists to support the dead-slug counter whose behavior is defined by chapter-detection (spec-modelo-de-datos.md §3 `manga_sites`).

#### Scenario: Column present with correct default

- GIVEN a new `manga_sites` row is created
- WHEN no explicit value is given
- THEN `consecutive_failures` is 0

## References

- spec-modelo-de-datos.md v1.6
