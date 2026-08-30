# Panel Bookmark Score Specification

## Purpose

Defines `bookmarks.my_score` (PAN §171-175): a 0-10 integer scale carried from Kitsu, NULL meaning unscored, visible in the panel's list and editable — including clearable — through the existing `PATCH /api/bookmarks/{id}`. Migration 3 is the only schema change involved. Placement, size, and colour on the card are phase 5's decision (PAN §195) and are explicitly out of scope here.

## Requirements

### Requirement: Migration 3 adds `my_score`, idempotently and without inventing a value

The system MUST add `bookmarks.my_score INTEGER` via a migration numbered 3 (`SCHEMA_VERSION` 2 → 3), following the existing migration mechanism: guarded by a column-existence check so a repeated run is a no-op, and writing NULL to every existing row — never a derived or default value.

#### Scenario: Existing database gains the column
- GIVEN a database at `user_version` 2 with populated `bookmarks` rows
- WHEN the migration runs
- THEN `bookmarks` gains `my_score`, every existing row reads NULL, and `user_version` becomes 3

#### Scenario: Re-running the migration is a no-op
- GIVEN a database already at `user_version` 3
- WHEN `ensure_schema` runs again
- THEN no error occurs and the column is not altered or duplicated

#### Scenario: A database born after this change is stamped, not migrated
- GIVEN a brand-new database file
- WHEN it is created
- THEN it already has `my_score` from `schema.sql` and is stamped `user_version` 3 directly, with no migration executed

### Requirement: `my_score` is NULL-as-unscored, integer 0-10

The system MUST treat NULL as "unscored" and MUST reject any value outside the closed integer range 0-10, including fractional values, at the API boundary.

#### Scenario: Out-of-range score is refused
- GIVEN a PATCH body with `my_score: 11`
- WHEN it is submitted
- THEN the API responds 422 and no write occurs

#### Scenario: Fractional score is refused
- GIVEN a PATCH body with `my_score: 7.5`
- WHEN it is submitted
- THEN the API responds 422 and no write occurs

### Requirement: PATCH distinguishes absent, set, and clear

`PATCH /api/bookmarks/{id}` MUST treat `my_score` as three distinct wire states: the key absent (leave the stored value untouched), the key present with an integer 0-10 (set it), and the key present with an explicit `null` (clear it to unscored). This extends, rather than copies, the existing presence-based mechanism that already distinguishes "absent" from "provided" for `last_chapter_read` — that field's validator additionally forbids a provided `null`; `my_score`'s validator MUST NOT, since un-scoring is a legitimate operation this field alone permits.

#### Scenario: Field absent leaves the score untouched
- GIVEN a bookmark with `my_score = 6`
- WHEN a PATCH body carries only `status` and no `my_score` key
- THEN `my_score` remains 6

#### Scenario: Field present and numeric sets the score
- GIVEN a bookmark with `my_score = NULL`
- WHEN a PATCH body carries `my_score: 8`
- THEN `my_score` becomes 8

#### Scenario: Field present and null clears the score
- GIVEN a bookmark with `my_score = 6`
- WHEN a PATCH body carries `my_score: null`
- THEN `my_score` becomes NULL

### Requirement: Clearing a score never writes `reading_history`

Unlike `last_chapter_read`, which the panel forbids re-nulling because it would destroy unrecoverable reading history, `my_score` MAY be set to NULL through the panel because nothing besides the list reads it. A `my_score`-only PATCH, whether setting or clearing, MUST NOT produce a `reading_history` row, since the trigger's guard fires on `last_chapter_read` alone.

#### Scenario: Un-scoring is silent to reading_history
- GIVEN a bookmark with `my_score = 4` and no pending `last_chapter_read` change
- WHEN a PATCH clears `my_score` to null
- THEN no new `reading_history` row exists after the write

### Requirement: `my_score` is visible in the list payload

`GET /api/bookmarks` MUST include `my_score` for every row, whether NULL or an integer.

#### Scenario: Unscored and scored rows both carry the field
- GIVEN a list containing both a scored and an unscored bookmark
- WHEN the list is fetched
- THEN both rows carry `my_score`, one as an integer and one as null

## References
- docs/spec-panel-v1b.md v1.7 §`my_score` (fase 4), §Fases y criterios de terminado ("El orden entre la 4 y la 5" — the data, not its form)
- docs/spec-modelo-de-datos.md v1.9 §Versionado del esquema
- openspec/changes/panel-v1b-fase-4/proposal.md
