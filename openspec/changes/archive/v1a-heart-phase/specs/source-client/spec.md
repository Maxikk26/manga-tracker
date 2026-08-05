# Source Client Specification

## Purpose

The manganato source client is the only module that knows manganato's URLs, HTML, JSON endpoint, ad filtering, and anti-bot handling. It MUST NOT know which mangas matter, when to notify, or what is in the database (spec-cliente-fuente-descubrimiento.md §"Separación en dos capas"). It exposes three network operations plus one no-request helper.

## Requirements

### Requirement: Structural boundary

The source client MUST expose only manganato-facing behavior and MUST NOT read or write any database table, reading-list state, or notification decision.

#### Scenario: Client called without DB context

- GIVEN a source-client operation is invoked with only a slug and/or limit
- WHEN the operation runs
- THEN it returns normalized data without touching any table

### Requirement: Request policy

The client MUST issue all requests sequentially with zero concurrency, MUST wait a random 5-15s delay between consecutive requests within a sweep, MUST apply a 30s timeout per request, MUST retry exactly once on a transient failure, and MUST NOT attempt more than two total attempts for the same item in a run (spec-cliente-fuente-descubrimiento.md §"Política de request").

#### Scenario: Transient failure retried once

- GIVEN a request to `fetch_chapters` times out
- WHEN the client retries
- THEN it makes exactly one additional attempt and reports failure if that attempt also fails, without a third attempt

#### Scenario: Sequential execution

- GIVEN a sweep processes multiple mappings
- WHEN requests are issued
- THEN no two requests execute concurrently and each consecutive pair is separated by a random 5-15s delay

### Requirement: Error taxonomy

The client MUST classify every failure into exactly one of three categories: not-found (404 or a false-success response), transient (timeout, connection error, 5xx, Cloudflare block), or unexpected (well-formed response with the wrong shape) (spec-cliente-fuente-descubrimiento.md §"Taxonomía de errores").

#### Scenario: 404 classified as not-found

- GIVEN `fetch_chapters` receives a 404 or a false-success payload
- WHEN the client classifies the failure
- THEN it returns not-found

#### Scenario: Unexpected shape is logged with the offending fragment

- GIVEN a response parses without a transport error but is missing an expected field
- WHEN the client classifies the failure
- THEN it returns unexpected and logs the relevant response fragment

### Requirement: Ad filter runs first, always

`fetch_latest_feed` MUST discard any item carrying a `hidden` attribute or a class starting with `js-banner-` before any other parsing step, and MUST treat zero remaining items as an error, not an empty list (spec-cliente-fuente-descubrimiento.md §"Operación 1"; manganato-fuente-actual.md §2).

#### Scenario: Ad items discarded before parsing

- GIVEN the feed page contains real items mixed with `hidden` and `js-banner-*` items
- WHEN `fetch_latest_feed` parses the page
- THEN ad items are discarded first and only real items are returned

#### Scenario: Zero real items is an error

- GIVEN ad filtering removes every item on the page
- WHEN `fetch_latest_feed` completes
- THEN it reports an unexpected error, not an empty list

### Requirement: fetch_chapters passthrough

`fetch_chapters` MUST return the source's numeric chapter number and UTC ISO 8601 timestamp unchanged, MUST NOT paginate beyond the configured limit (default 50), and MUST classify a 404 or false-success response as not-found (spec-cliente-fuente-descubrimiento.md §"Operación 2").

#### Scenario: Numeric and timestamp passthrough

- GIVEN the JSON endpoint returns `chapter_num: 45.5` and `updated_at` in UTC
- WHEN `fetch_chapters` parses the response
- THEN both values are returned unchanged, with no reparsing

### Requirement: fetch_manga_details is fallback-only

`fetch_manga_details` MUST be implemented per the §8 contract but MUST NOT be called by any detection mechanism; it exists solely as a cover-URL fallback (spec-cliente-fuente-descubrimiento.md §"Operación 3").

#### Scenario: Never invoked during detection

- GIVEN a `feed_check` or `active_sweep` run in progress
- WHEN detection executes
- THEN `fetch_manga_details` is not called

### Requirement: Chapter URL construction is a client operation, no request

The auxiliary chapter-URL builder MUST accept a slug and chapter number and return a pattern-built URL without making a network request, and callers MUST treat the result as an unverified guess (spec-cliente-fuente-descubrimiento.md §"Operación auxiliar").

#### Scenario: URL built without a request

- GIVEN a slug and a chapter number
- WHEN the builder is called
- THEN it returns a URL synchronously with zero network calls

## References

- spec-cliente-fuente-descubrimiento.md v1.2
- manganato-fuente-actual.md v1.2
