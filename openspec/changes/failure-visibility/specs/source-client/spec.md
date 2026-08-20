# Delta for Source Client

## MODIFIED Requirements

### Requirement: Error taxonomy

The client MUST classify every failure into exactly one of three categories: not-found (404 or a false-success response), transient (timeout, connection error, 5xx, Cloudflare block — for `fetch_manga_details` this includes a 403 or 429 response, per spec-cliente-fuente-descubrimiento.md:65), or unexpected (well-formed response with the wrong shape, or a `fetch_manga_details` response with any other non-200 status) (spec-cliente-fuente-descubrimiento.md §"Taxonomía de errores").
(Previously: this requirement said nothing about what a details response other than 200/404 classifies as; `fetch_manga_details` let a 403 fall through unclassified)

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

### Requirement: fetch_manga_details is fallback-only

`fetch_manga_details` MUST be implemented per the §8 contract but MUST NOT be called by any detection mechanism; it exists solely as a cover-URL fallback (spec-cliente-fuente-descubrimiento.md §"Operación 3"). It MUST raise `NotFound` on a 404 response, `Transient` on a 403, 429, or 5xx response, and `Unexpected` on any other non-200 response, and MUST NOT return a `MangaDetails` built from a non-200 response body.
(Previously: raised `NotFound` only on 404; every other non-200 status — 403 included — fell through to `parse_manga_details`, which returned `MangaDetails(title="", cover_url=None, ...)`)

#### Scenario: Never invoked during detection

- GIVEN a `feed_check` or `active_sweep` run in progress
- WHEN detection executes
- THEN `fetch_manga_details` is not called

#### Scenario: A details 403 never produces a 200 preview

- GIVEN `POST /api/mangas/preview` calls `fetch_manga_details` and the source responds 403
- WHEN the intake layer receives the raised `Transient`
- THEN `/api/mangas/preview` answers 503 via `_source_error` ("La fuente no respondió. Espera un momento y vuelve a intentar."), never 200 with an empty title

## ADDED Requirements

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

## Non-Normative Notes

- Doc bump: `spec-cliente-fuente-descubrimiento.md` v1.8 → v1.9; stale pins to fix: `medicion-ventana-feed.md:3`, `spec-bot-telegram.md:3`, `runbook-deploy.md:3`, `spec-seed-manual.md:3`, `spec-importador-kitsu.md:3`, `one-pager-v1a.md:169`, prose at `manganato-fuente-actual.md:169`.
- Scope boundary preserved: distinguishing a source-throttling 403 from a Cloudflare 403 by cause stays the declared-open item at spec-cliente-fuente-descubrimiento.md:301; this change does not resolve it.
- Pre-existing divergence, deliberate and out of scope: `fetch_cover` (`manga_tracker/sources/manganato/client.py:79-111`) raises `Unexpected` on any `status != 200`, so it still classifies a 403 as `Unexpected` while this requirement classifies a details 403 as `Transient`. Correct as-is: a missing cover thumbnail is an ordinary 403 (spec-cliente-fuente-descubrimiento.md:9, "un estado ordinario, no un fallo que valga 30 segundos"), confirming it measured 43.9s, which is why `fetch_cover` alone runs with `retry=False`. Reclassifying it as `Transient` could invite the retry the spec deliberately removed. This change does not touch `fetch_cover`.
- Required doc task (part of the v1.9 bump, not optional): `spec-cliente-fuente-descubrimiento.md:9`'s closing sentence — "La clasificación no cambia: el 403 sigue llegando como dato y sigue volviéndose 'inesperado'" — reads as a general taxonomy rule but actually describes only `fetch_cover`'s own behavior, and it sits in the same bullet as "403 es transitorio en la taxonomía de esta spec," which says the opposite for the general case. That self-contradiction is what produced this defect. Rewrite the sentence, in neutral Spanish, so it is scoped explicitly to the cover operation.

## References

- spec-cliente-fuente-descubrimiento.md v1.8 (pending v1.9)
- manga_tracker/sources/manganato/client.py — fetch_cover (deliberately divergent non-200 classification, see Non-Normative Notes)
- manga_tracker/web/app.py — `MangaAddRequest`/`_source_error`
- manga_tracker/intake/pasted_url.py — `confirm()` docstring on the trusted title
