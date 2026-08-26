# Cover Backfill Specification

## Purpose

Covers how the panel backfills cover images to disk without ever hotlinking a source URL (PAN §Portadas, §Portadas de los terminales): the existing mapped route (shipped 2026-08-18, non-terminal statuses, up to two source requests per manga) and the terminal route this phase adds (completed/dropped statuses, downloads an already-known `cover_url`, no `manga_sites` lookup, no request to manganato ever). `GET /api/covers/{manga_id}` serves either route's output identically and is unchanged by this phase.

## Requirements

### Requirement: The mapped route stays scoped to non-terminal, mapped bookmarks

The system MUST keep the existing candidate query for `cache-covers`' default population — an `INNER JOIN` on `manga_sites`, restricted to `reading`, `want_to_read`, `on_hold` — unchanged. It MAY call the source (`fetch_manga_details` to learn `cover_url` when missing, then `fetch_cover`), at most two requests per manga, one skipped if already known.

#### Scenario: Default run costs at most two requests per manga
- GIVEN a mapped, non-terminal bookmark with no cached cover and no known `cover_url`
- WHEN `cache-covers` runs with no `--status`
- THEN it issues at most one request to learn `cover_url` and one to download it

### Requirement: The terminal route never asks the source

The system MUST expose a second candidate query and download loop, scoped to `completed`/`dropped` bookmarks, that MUST NOT join or query `manga_sites`, MUST NOT call any method that requests manganato (`fetch_manga_details`, `fetch_chapters`, or any slug resolution), and downloads only a `cover_url` already stored on the `mangas` row.

#### Scenario: A terminal bookmark's cover downloads with zero manganato requests
- GIVEN a `completed` bookmark whose `mangas` row already carries a Kitsu `cover_url` and no cached file exists
- WHEN the terminal route runs
- THEN the image is downloaded from that URL and zero requests reach manganato

### Requirement: Terminal eligibility is decided by data, never by mapping presence

The terminal candidate query MUST select by status alone (`completed`/`dropped`) and MUST NOT filter on whether a `manga_sites` row exists; whether a given candidate is downloadable MUST be decided per row by whether `cover_url` is present, never assumed from status. A terminal bookmark that later gains a `manga_sites` mapping remains eligible for exactly this route — the mapped route's population stays non-terminal only, so mapping presence alone MUST NOT move a terminal row between routes or drop it from both.

#### Scenario: A newly-mapped terminal bookmark is still covered by the terminal route
- GIVEN a `completed` bookmark that has gained a `manga_sites` row (e.g., re-mapped) and still carries a known `cover_url`
- WHEN cover backfill runs
- THEN it is downloaded by the terminal route, not the mapped one, and still issues zero manganato requests

#### Scenario: A terminal bookmark with no known cover_url is skipped, not escalated
- GIVEN a terminal bookmark whose `cover_url` is NULL
- WHEN the terminal route processes it
- THEN it is logged and skipped — never routed to the source-calling mapped route, regardless of any mapping

### Requirement: Both routes share idempotency and the serving endpoint

Both routes MUST write to a `.part` file and rename on completion, so an interrupted run loses nothing already paid for, and a second run MUST only cost what remains uncached. `GET /api/covers/{manga_id}` MUST require no code change: it serves any cached file by `manga_id` regardless of which route wrote it.

#### Scenario: A second run of the terminal route is free
- GIVEN all 66 terminal covers are already cached
- WHEN the terminal route runs again
- THEN zero requests are issued and the run reports zero downloads

### Requirement: The terminal route is reachable through the existing `cache-covers` CLI

`cache-covers --status completed` and `--status dropped` MUST invoke the terminal route for their candidates instead of returning zero rows, replacing today's silent success with correct, request-free behaviour. This adds no new CLI verb.

#### Scenario: `--status completed` now does real work
- GIVEN 28 `completed` bookmarks with known `cover_url` and no cached file
- WHEN `cache-covers --status completed` runs
- THEN 28 files are cached and the report reflects real downloads, not the previous zero-row success

## References
- docs/spec-panel-v1b.md v1.6 §Portadas (fase 4), §Portadas de los terminales (fase 4)
- openspec/changes/panel-v1b-fase-4/proposal.md
