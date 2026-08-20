# Delta for Source Client

Targets the unarchived `openspec/changes/v1a-heart-phase/specs/source-client/spec.md` (`openspec/specs/` has no `source-client` entry yet). Adds one operation; no existing requirement changes behavior.

## ADDED Requirements

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

## References

- docs/spec-importador-kitsu.md v1.3
- docs/spec-cliente-fuente-descubrimiento.md v1.4
- openspec/changes/v1a-heart-phase/specs/source-client/spec.md
