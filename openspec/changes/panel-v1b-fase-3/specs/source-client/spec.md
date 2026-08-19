# Delta for Source Client

Targets `openspec/changes/importador-kitsu/specs/source-client/spec.md` (newest unarchived copy; `openspec/specs/` has no `source-client` entry yet). Adds one operation to the `SourceClient` Protocol; the concrete implementation already exists (`ManganatoClient.fetch_cover`, `manga_tracker/sources/manganato/client.py:79`) — this delta closes the Protocol/implementation gap so callers (the panel's add flow) can type against the interface instead of the concrete client (PAN §34-37, §128).

## ADDED Requirements

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

## References
- docs/spec-panel-v1b.md v1.1 §34-37, §128
- manga_tracker/sources/manganato/client.py:79
- openspec/changes/importador-kitsu/specs/source-client/spec.md
