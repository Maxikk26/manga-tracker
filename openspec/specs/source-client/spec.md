# Source Client Specification

## Purpose

The manganato source client is the only module that knows manganato's URLs, HTML, JSON endpoint, ad filtering, and anti-bot handling. It MUST NOT know which mangas matter, when to notify, or what is in the database (spec-cliente-fuente-descubrimiento.md §"Separación en dos capas"). It exposes multiple network operations plus auxiliary helpers.

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

The client MUST classify every failure into exactly one of three categories: not-found (404 or a false-success response), transient (timeout, connection error, 5xx, Cloudflare block — for `fetch_manga_details` this includes a 403 or 429 response, per spec-cliente-fuente-descubrimiento.md:65), or unexpected (well-formed response with the wrong shape, or a `fetch_manga_details` response with any other non-200 status) (spec-cliente-fuente-descubrimiento.md §"Taxonomía de errores").

#### Scenario: 404 classified as not-found

- GIVEN `fetch_chapters` receives a 404 or a false-success payload
- WHEN the client classifies the failure
- THEN it returns not-found

#### Scenario: Unexpected shape is logged with the offending fragment

- GIVEN a response parses without a transport error but is missing an expected field
- WHEN the client classifies the failure
- THEN it returns unexpected and logs the relevant response fragment

#### Scenario: Details response with 403, 429, or 5xx is transient

- GIVEN `fetch_manga_details` receives a response whose status is 403, 429, or in the 5xx range
- WHEN the client classifies the response
- THEN it raises `Transient`, matching spec-cliente-fuente-descubrimiento.md:65 ("transitorio": timeout, conexión, 5xx, bloqueo de Cloudflare) — the two out-of-scope causes of a 403 (source throttling vs. Cloudflare) remain undistinguished, per the open item at spec-cliente-fuente-descubrimiento.md:301

#### Scenario: Details response with any other non-200, non-404 status is unexpected

- GIVEN `fetch_manga_details` receives a response whose status is neither 200, 404, nor a transient status (403, 429, or 5xx)
- WHEN the client classifies the response
- THEN it raises `Unexpected`

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

`fetch_manga_details` MUST be implemented per the §8 contract but MUST NOT be called by any detection mechanism; it exists solely as a cover-URL fallback (spec-cliente-fuente-descubrimiento.md §"Operación 3"). It MUST raise `NotFound` on a 404 response, `Transient` on a 403, 429, or 5xx response, and `Unexpected` on any other non-200 response, and MUST NOT return a `MangaDetails` built from a non-200 response body.

#### Scenario: Never invoked during detection

- GIVEN a `feed_check` or `active_sweep` run in progress
- WHEN detection executes
- THEN `fetch_manga_details` is not called

#### Scenario: A details 403 never produces a 200 preview

- GIVEN `POST /api/mangas/preview` calls `fetch_manga_details` and the source responds 403
- WHEN the intake layer receives the raised `Transient`
- THEN `/api/mangas/preview` answers 503 via `_source_error` ("La fuente no respondió. Espera un momento y vuelve a intentar."), never 200 with an empty title

### Requirement: Chapter URL construction is a client operation, no request

The auxiliary chapter-URL builder MUST accept a slug and chapter number and return a pattern-built URL without making a network request, and callers MUST treat the result as an unverified guess (spec-cliente-fuente-descubrimiento.md §"Operação auxiliar").

#### Scenario: URL built without a request

- GIVEN a slug and a chapter number
- WHEN the builder is called
- THEN it returns a URL synchronously with zero network calls

### Requirement: fetch_known_slugs exposes sitemap-backed membership

The source client MUST expose `fetch_known_slugs() -> Sequence[str]`, returning every slug published in manganato's sitemap (`/sitemap.xml` → 10 `sitemap-comic-N.xml` shards, reachable via `robots.txt`); sitemap parsing and shard-URL knowledge MUST stay inside `sources/manganato/` — no other package MUST know what a sitemap is (KIT §"La resolución no sondea la fuente").

#### Scenario: Full slug set returned

- GIVEN the 10 sitemap shards are reachable
- WHEN `fetch_known_slugs` completes
- THEN it returns the combined set of slugs from all 10 shards

#### Scenario: A shard fetch exhausts retries

- GIVEN one shard fails on both attempts under the standard retry policy
- WHEN `fetch_known_slugs` runs
- THEN it reports the failure via the existing error taxonomy rather than returning a silently incomplete set

### Requirement: No delay exemption for sitemap shards

`fetch_known_slugs` MUST apply the same sequential-fetch, 5-15s-delay-from-the-second-request policy as every other source-client operation; it MUST NOT special-case the sitemap as delay-free (KIT §"Corrección a la v1.0").

#### Scenario: Ten shard fetches include nine delays

- GIVEN 10 shard requests are issued
- WHEN they execute
- THEN the 2nd through 10th are each preceded by a random 5-15s delay, with none exempted

### Requirement: Existing Response shape is sufficient, no contract change

`fetch_known_slugs` MUST parse shard XML from `Response.text`; the `Transport`/`Response` contract MUST NOT gain a `content: bytes` field or any other new field to support this operation (KIT §"Lo que sí se verificó").

#### Scenario: Shard XML parses from text

- GIVEN a shard response whose `Response.text` contains the shard's XML, including an encoding declaration in its header
- WHEN it is parsed
- THEN every `<url>` entry is extracted without touching a `content: bytes` field

### Requirement: fetch_cover joins the SourceClient Protocol

The `SourceClient` Protocol (`manga_tracker/sources/contracts.py`) MUST declare `fetch_cover(cover_url: str) -> bytes`, matching the concrete implementation's signature. The `Referer` knowledge required by the source's image hosts MUST stay inside `sources/manganato/` — the Protocol only declares the shape.

#### Scenario: Protocol-typed caller can fetch a cover

- GIVEN a caller holds a `SourceClient`-typed reference, not the concrete class
- WHEN it calls `fetch_cover(cover_url)`
- THEN it receives the image bytes without importing `sources.manganato`

#### Scenario: Existing concrete behavior is unchanged

- GIVEN `ManganatoClient.fetch_cover` already sets the organic `Referer` the image hosts require
- WHEN the Protocol gains the method's signature
- THEN no behavior of the concrete implementation changes — only its type is now declared on the interface

### Requirement: fetch_cover follows the existing error taxonomy

`fetch_cover`, as declared on the Protocol, MUST raise the same `NotFound` / `Transient` / `Unexpected` categories used by every other source-client operation; no new exception type is introduced for cover fetching.

#### Scenario: Transient failure on cover fetch

- GIVEN the cover host times out
- WHEN `fetch_cover` is called through a Protocol-typed reference
- THEN it raises `Transient`, the same category the rest of the client uses

### Requirement: An empty or whitespace-only title is unwritable

The manga-add write path MUST reject a `title` that is empty or contains only whitespace before any row is written to `mangas`, so a title lost to a details failure (or any other cause) cannot reach production data. `confirm()` does not re-fetch the ficha and trusts the `title` `preview()` already echoed, so this gate MUST sit at validation, not rely on a successful `fetch_manga_details` call happening again.

#### Scenario: Confirm rejects an empty title

- GIVEN a `POST /api/mangas` request whose `title` is empty or only whitespace
- WHEN the request is validated
- THEN it is rejected and no row is written to `mangas`

#### Scenario: A well-formed title is unaffected

- GIVEN a `POST /api/mangas` request whose `title` is a normal non-empty string
- WHEN the request is validated
- THEN validation passes and the existing write path proceeds unchanged

## References

- spec-cliente-fuente-descubrimiento.md v1.4, v1.9
- manganato-fuente-actual.md v1.2
- docs/spec-importador-kitsu.md v1.3
- openspec/changes/importador-kitsu/specs/source-client/spec.md (ADDED delta 1)
- openspec/changes/panel-v1b-fase-3/specs/source-client/spec.md (ADDED delta 2)
- openspec/changes/failure-visibility/specs/source-client/spec.md (ADDED delta 3)
