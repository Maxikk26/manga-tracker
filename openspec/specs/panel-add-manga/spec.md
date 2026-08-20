# Panel Add Manga Specification

## Purpose

Defines `POST /api/mangas` (PAN §85, §95) — the panel's route to add a manga by pasting a manganato URL: a no-write preview, then an atomic confirm that writes `mangas` + `manga_site` + `bookmark` with `origin='manual'`, caches the cover, and leaves the row ready for the next `active_sweep` (PAN §144) with no further intervention. `DELETE` never exists (PAN §86); editing metadata, bulk add, schema migration, and re-sync to Kitsu are out of scope.

## Requirements

### Requirement: Preview validates without writing
The system SHALL expose a preview operation that, given a candidate URL and optional initial status/chapter, resolves the slug and returns matched metadata (title, cover candidate, publication status text) without writing to `mangas`, `manga_site`, `bookmarks`, or `chapter_history`.

#### Scenario: Valid slug preview
- GIVEN a well-formed manganato URL with no prior mapping in the database
- WHEN preview runs
- THEN it returns the matched title and cover candidate and zero rows are written

### Requirement: Malformed URL is rejected
GIVEN a URL from which no slug segment can be extracted (per the client's `extract_slug`), preview and confirm SHALL reject it as invalid before any request is issued to the source, and SHALL write zero rows.

#### Scenario: URL has no `/manga/` segment
- GIVEN a pasted URL without a `manga` path segment
- WHEN preview runs
- THEN it rejects with a message identifying the URL as invalid, at zero source requests

### Requirement: Duplicate active slug is rejected, naming the owner
GIVEN the slug is already mapped to a `manga_sites` row whose bookmark is in a non-terminal status, preview and confirm SHALL reject the add, naming the existing title and its current status, and SHALL write zero rows.

#### Scenario: Slug already owned by a reading bookmark
- GIVEN the slug already maps to a manga bookmarked as `reading`
- WHEN confirm runs
- THEN it rejects, the message names that title and `reading`, and no new rows exist

### Requirement: Existing terminal title is rejected; reactivation is a PATCH
GIVEN the resolved manga matches (by title, normalized as `importer/matching.py` already does, or another detection the design selects) an existing manga whose bookmark is `completed` or `dropped` — including when that manga has no surviving `manga_sites` row, so slug lookup alone cannot see it — preview and confirm SHALL reject the add, naming the existing title and its terminal status, and pointing at the existing `PATCH /api/bookmarks/{id}` as the way to reactivate it. SHALL write zero rows.

#### Scenario: Re-adding a completed manga with no manga_sites row
- GIVEN a manga is `completed` and its `manga_sites` row was removed, so the slug alone does not identify it
- WHEN the owner pastes a URL that resolves to that same title
- THEN the add is rejected, naming the title and `completed`, and no rows are written

#### Scenario: Re-adding a dropped manga
- GIVEN a manga is `dropped`
- WHEN the owner pastes its URL again
- THEN the add is rejected the same way, naming the title and `dropped`

### Requirement: Unknown slug is rejected
GIVEN the source reports `NotFound` for the slug (404, or a chapters response with `success: false`), preview and confirm SHALL reject distinctly from other failure classes and SHALL write zero rows.

#### Scenario: Slug does not exist at the source
- GIVEN a syntactically valid but non-existent slug
- WHEN preview runs
- THEN it rejects as not-found and writes zero rows

### Requirement: Transient source failure requires no automatic retry
GIVEN the source call raises `Transient` (timeout, connection error, 5xx, Cloudflare, after the client's own one retry), preview and confirm SHALL reject distinctly from other failure classes, SHALL write zero rows, and SHALL NOT retry automatically — the owner presses again.

#### Scenario: Source times out mid-preview
- GIVEN the ficha request times out
- WHEN preview runs
- THEN it rejects as transient, writes zero rows, and no further request is issued without the owner acting again

### Requirement: Unexpected source response is rejected
GIVEN the source call raises `Unexpected` (well-formed response, wrong shape), preview and confirm SHALL reject distinctly from other failure classes and SHALL write zero rows.

#### Scenario: Chapters payload is missing `data.chapters`
- GIVEN the chapters endpoint returns a well-formed but malformed payload
- WHEN confirm runs
- THEN it rejects as unexpected and writes zero rows

### Requirement: Zero chapters is a successful add with a null latest_chapter_num
GIVEN a valid, resolvable slug whose chapters endpoint returns zero chapters, confirm SHALL still create `mangas`, `manga_site`, and `bookmarks` rows, with `manga_sites.latest_chapter_num` left NULL. This OVERRIDES SEED's precedent of discarding a zero-chapter row (`docs/spec-seed-manual.md`): the panel's add treats zero chapters as a legitimate state the next `active_sweep` will seal once a chapter appears, not a dead row. The resulting `manga_sites` row MUST be indistinguishable, for sweep purposes, from any other NULL-`latest_chapter_num` mapping already produced by other flows.

#### Scenario: Slug resolves but has no chapters yet
- GIVEN the ficha resolves and the chapters endpoint returns an empty list with `success: true`
- WHEN confirm runs
- THEN `mangas`, `manga_site`, and `bookmarks` rows are created, `latest_chapter_num` is NULL, and no `chapter_history` row is written
- AND the next `active_sweep` run visits this mapping like any other unsealed one

### Requirement: The manual bookmark write shape
On a successful confirm, the bookmark row SHALL carry `origin='manual'`, `progress_is_approx=0`, and `status_changed_at` stamped at INSERT time to the write's own `now`, formatted `%Y-%m-%dT%H:%M:%SZ` (the one fixed-width UTC format every writer emits, since tab ordering compares these as strings). Any `chapter_history` rows written during the same add MUST use `detected_via='seed_backfill'` — the CHECK constraint admits no `'manual'`/`'panel'` value, so the existing value is reused, not invented.

#### Scenario: Confirm stamps status_changed_at
- GIVEN confirm succeeds with initial status `want_to_read`
- WHEN the bookmark row is read back
- THEN `status_changed_at` equals the write's timestamp in `%Y-%m-%dT%H:%M:%SZ`, `origin` is `manual`, and `progress_is_approx` is `0`

#### Scenario: Chapters seeded on add reuse seed_backfill
- GIVEN chapters exist at confirm time (up to the existing 50-row limit)
- WHEN they are written to `chapter_history`
- THEN each row's `detected_via` is `seed_backfill`

### Requirement: Initial status and chapter validation
`status` MUST be one of the five existing bookmark statuses; anything else is rejected before any write. `last_chapter_read` is OPTIONAL and defaults to `0` when omitted. When provided, it MUST be `>= 0`; it is NOT validated against `latest_chapter_num` — reading ahead of what the source has detected is legitimate (PAN §50).

#### Scenario: Initial chapter omitted
- GIVEN the owner submits no initial chapter
- WHEN confirm runs
- THEN `last_chapter_read` is written as `0`

#### Scenario: Initial chapter ahead of the source
- GIVEN the source reports 5 published chapters and the owner enters `10`
- WHEN confirm runs
- THEN the write succeeds; no cross-validation rejects it

### Requirement: Cover is cached during the same confirm, no periodic job
The confirm operation, having already visited the ficha to validate the slug, SHALL fetch and cache the cover image bytes to disk in the same operation when the source reports a `cover_url`, so that `GET /api/covers/{manga_id}` serves it without a further fetch immediately after the add. When the source reports no `cover_url`, confirm SHALL still succeed; the cover endpoint answers 404 as its existing ordinary state.

#### Scenario: Cover present at the source
- GIVEN the ficha reports a `cover_url`
- WHEN confirm succeeds
- THEN the cover bytes are on disk before the response returns, and `GET /api/covers/{manga_id}` serves them without issuing a request

#### Scenario: Source has no cover
- GIVEN the ficha reports no `cover_url`
- WHEN confirm succeeds
- THEN the add still succeeds and `GET /api/covers/{manga_id}` answers 404, same as any manga awaiting `cache-covers`

### Requirement: Confirm is atomic; any rejection leaves zero rows
A confirm that fails for any reason — validation, duplicate/terminal detection, `NotFound`/`Transient`/`Unexpected`, or a failure partway through the write — SHALL leave zero new rows across `mangas`, `manga_sites`, `bookmarks`, and `chapter_history`. There is no partially-added manga.

#### Scenario: Failure after the ficha but before the write completes
- GIVEN the ficha resolves but the chapters call raises `Unexpected`
- WHEN confirm runs
- THEN the transaction is not committed and none of the four tables gain a row

### Requirement: `web` never reaches the source, directly or by sequencing it itself
`web` MUST NOT import `sources.manganato` or `notifier.telegram`, directly or transitively, for the add flow or any other. The endpoint handler in `web` MUST NOT itself sequence multiple `SourceClient`-style calls (resolve slug → fetch details/chapters → fetch cover) to build a preview or complete a confirm; that sequencing belongs to a layer other than `web` (PAN §34-37: "el panel pide agrega esto, no descarga esto"). `web` MAY hold an injected `SourceClient`-typed dependency only to pass it through to that layer.

#### Scenario: Preview request is delegated
- GIVEN a preview request reaches the `web` endpoint
- WHEN it is handled
- THEN the multi-step slug/ficha/chapters sequencing executes in a non-`web` layer, and `web` returns that layer's result unchanged

### Requirement: The boundary is proven by an injected violation
The directional-boundary check (`tests/test_architecture.py`) MUST include a case that fabricates a `web`-named module importing `manga_tracker.sources.manganato` and asserts the check flags it, so the rule is proven capable of failing rather than merely present and unexercised — mirroring the existing `notifier.telegram` probe for `web`.

#### Scenario: Fabricated web→sources.manganato import is flagged
- GIVEN a throwaway module under a `web`-named path imports `manga_tracker.sources.manganato`
- WHEN the directional-boundary check runs against it
- THEN the violation appears in the reported list

### Requirement: The add form is a modal over the grid
The add form SHALL render as a modal over the existing grid, not a separate route or view. Confirming SHALL close the modal and trigger a full refetch of the grid behind it (the container's existing refresh pattern — server stays the source of truth for derived fields). Closing the modal without confirming SHALL send no confirm request and leave the grid unchanged. All user-facing copy SHALL be in Spanish.

#### Scenario: Successful add refreshes the grid
- GIVEN the owner previews a valid URL and confirms
- WHEN confirm succeeds
- THEN the modal closes, the grid performs a full refetch, and the new manga's card appears

#### Scenario: Abandoning the preview writes nothing
- GIVEN a successful preview is shown
- WHEN the owner closes the modal without confirming
- THEN no confirm request is sent and the grid is unchanged

#### Scenario: Rejection copy names the taxonomy in Spanish
- GIVEN preview or confirm rejects with any failure class (bad URL, duplicate, terminal title, not-found, transient, unexpected, or validation)
- WHEN the response returns
- THEN the modal shows a Spanish message identifying that failure class; for duplicate/terminal rejections it names the existing title and status
- AND for a transient rejection the copy invites the owner to try again, with no automatic retry

## References
- docs/spec-panel-v1b.md v1.1 §85-86, §95, §34-37, §50, §69, §77, §128, §144, §177
- docs/spec-modelo-de-datos.md v1.9 §139-140, §291
- docs/spec-seed-manual.md v2.4 (validation-list precedent; zero-chapter handling is explicitly overridden here)
- openspec/changes/panel-v1b-fase-3/proposal.md
