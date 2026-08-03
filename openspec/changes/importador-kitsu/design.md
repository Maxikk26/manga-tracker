# Design: Kitsu importer (`importador-kitsu`)

Contract: `docs/spec-importador-kitsu.md` **v1.2**, which closed all five gaps the proposal raised. Nothing here is blocked on the owner.

## Technical Approach

Two new top-level packages behind contracts, wired only by `cli.py`. `catalogue/` gets its own confined transport: it is a documented batch API, not a scraped site, so it borrows neither `curl_cffi` nor manganato's courtesy policy. `importer/` is a contract-only consumer — it never learns that `abbreviatedTitles` or a sitemap exist. Sitemap parsing lands in `sources/manganato/sitemap.py` behind a new `fetch_known_slugs()` on the source contract.

## Architecture Decisions

### D1 — Catalogue transport: stdlib `urllib.request`, injected `sleeper`, fixed 1s

Rejected: reusing `CurlCffiTransport` (puts manganato's module and its 5-15s rule inside the catalogue); a second `curl_cffi` file (impersonation is anti-bot machinery Kitsu does not need). Chosen: `catalogue/transport.py` on `urllib.request` — stdlib, no new dependency, and `notifier/telegram.py` is the precedent for exactly this kind of documented HTTPS JSON call.

Same seam as `CurlCffiTransport`: `UrllibJsonTransport(*, sleeper=time.sleep)`, `get(url, *, headers, timeout) -> Response`, no delay before the first call, one retry on 429/5xx. **No `rng`** — jitter exists to look human; Kitsu needs politeness, not disguise, so the delay is a deterministic 1.0s (~21s total against a 13-37 min import). Tests inject a fake transport and `sleeper=lambda _: None`, so the socket block in `conftest.py` stays satisfied.

`CONFINEMENT_RULES` values become frozensets; `urllib.request` maps to `{notifier/telegram.py, catalogue/transport.py}`. The other three keep single-element sets, so nothing loosens.

### D2 — `resolve` batches internally; page-full fails loud

`resolve(external_ids)` takes **all** ids and chunks at 12 inside `kitsu.py`, because 12 is derived from Kitsu's `page[limit]=20` and the importer must not carry another catalogue's page limit. Unresolvable ids are absent from the result; the importer diffs requested against returned.

Two silent failures get RED-tested guards. A `/mappings` payload whose `relationships.item` has `links` but no `data`, or an empty `included`, raises `CatalogueUnexpected` — that is the missing-`include=item` signature (HTTP 200, zero resolved). A batch returning exactly `page[limit]` resources may be truncated → `CatalogueUnexpected`; plus a module-level `assert BATCH_SIZE < PAGE_LIMIT`.

`catalogue/contracts.py` defines its own `Response`, `Transport`, `CatalogueTransient`, `CatalogueUnexpected`: duplicating a three-field dataclass is cheaper than a shared HTTP package both layers depend on, and distinct exception names keep `sources.contracts.Unexpected` unambiguous at the importer's call sites.

### D3 — Reconciliation: queries in `storage`, ordered policy in `importer/reconcile.py`

`importer` may import `storage` (precedent: `seed/loader.py`); the ban is on `catalogue.kitsu` and `sources.manganato`, neither of which reconciliation needs. `site_id` and `slug` arrive as plain values, as they already do for `load_seed`.

`repositories.py` gains `find_manga_by_kitsu_id`, `list_manga_titles` and the Kitsu writers; `find_manga_site_by_slug` is reused as key 2. Key 3 cannot run in SQL — SQLite has no NFKD — so titles are normalized in Python with the **same** normalizer the slug candidates use, and the exactly-one guardian applies there. Keeping the ordered policy pure makes the highest-risk rule unit-testable with no DB.

`write_seed_backfill` is neither reused nor modified: it hardcodes `origin='seed'`, `progress_is_approx=0` and upserts unconditionally. Bookmark rule: INSERT when absent; UPDATE only when the existing `origin = 'kitsu_import'`; `seed` and `manual` are never touched. Protecting `manual` too goes beyond the spec's letter and cannot violate it.

### D4 — Progress: announce before the request, in every phase

The seed loader's rule, extended. A banner per phase with its expected cost, then `[i/total] 'Title' ...` with `flush=True` **before** each `fetch_chapters` call. The sitemap's 1-2.5 silent minutes gets the same treatment via an optional `progress: Callable[[int, int], None] | None` on `fetch_known_slugs`, reporting "unit n of m", never "shard" — no source knowledge escapes. Unannounced silence is what got a real bring-up killed with Ctrl+C.

### D5 — Verification precedes every write for that entry

§Carga lists what to write, not that partial writes survive. Reordered: `fetch_chapters` → verify → steps 1-4 inside one `db.transaction(conn)`. A suspect match (`my_read_chapters` > newest chapter) therefore leaves **zero** rows and goes to pending with its resolved title. `my_read_chapters = 0` makes the check vacuous — accept. Zero chapters, `NotFound`, `Unexpected` **and `Transient`** are caught per entry and sent to pending; the seed loader lets `Transient` abort, which is wrong at 136 entries and 34 minutes when re-running is cheap and safe.

### D6 — Pending CSV is the seed template, byte-compatible

Header exactly `title,url,last_chapter_read,status`, `url` empty by design, `csv.writer` with `newline=""`, UTF-8, `lineterminator="\n"`. Default `data/kitsu-pendientes.csv` (argument-overridable) — under `data/`, already covered by `.gitignore`, and it must **not** join the template's re-inclusion rule. The status map emits only the loader's five `VALID_STATUSES`. Two tests make "no new code" executable: the fresh file through `load_seed` reports one error per row, all `url ... has no extractable slug`, and writes nothing; the same file with urls filled loads.

### D7 — Stdlib XML, no `defusedxml`

CPython's `ElementTree` does not expand undefined entities and fetches no external DTD, closing billion-laughs for this parser; a new dependency is not proportionate for a one-shot operator tool hitting a `robots.txt`-declared endpoint. v1.2 verified `ET.fromstring` parses a shard straight from `Response.text`. A parse failure raises `Unexpected` with the first 200 chars, matching `client.py`'s source-changed style. Reversal if this ever runs unattended: swap in `defusedxml`.

### D8 — Every new boundary rule proven by an injected violation

Extend `DIRECTIONAL_RULES` with `catalogue -> {storage, discovery, notifier, seed, sources}` and `importer -> {catalogue.kitsu, catalogue.transport, sources.manganato}`; add `catalogue`/`importer` to the leaf sets (`sources`, `notifier`, `storage`); add `catalogue.kitsu` to `CONCRETE_IMPLEMENTATIONS`.

`test_directional_rules_actually_fire` proves only that a prefix *string* can match — it would not catch a walker that never reaches the new files, and **this repo has direct history of a rule keyed on the wrong prefix that could never match while the suite stayed green.** So parameterize the scanners as `_directional_violations(pkg_root)` / `_confinement_violations(pkg_root)` and add `test_boundary_check_flags_an_injected_violation`, which builds a throwaway tree in `tmp_path` with `catalogue/probe.py` importing `manga_tracker.storage.db`, `importer/probe.py` importing `manga_tracker.catalogue.kitsu`, and `catalogue/probe2.py` importing `curl_cffi`, then asserts all three are reported. This retro-covers the existing rules. A rule that does not appear here is not enforced.

## Data Flow

    kitsu-manga.xml ─→ importer.export ──218 entries──┐
    CatalogueClient.resolve(152 ids) ─────150 entries──┤  catalogue/kitsu.py → catalogue/transport.py
    SourceClient.fetch_known_slugs() ─────91k slugs────┤  sources/manganato/sitemap.py
                                                       ↓
                        importer.matching (ordered candidates → membership)
                                    ┌──────────────┴──────────────┐
                                 matched                       unmatched
                                    ↓                              │
                          fetch_chapters → verify ──suspect───────→│
                                    ↓ ok                           ↓
                importer.reconcile (3 keys) → storage         importer.pending
                    one transaction per entry              kitsu-pendientes.csv

The 66 terminal entries bypass the slug lane: `mangas` + `bookmarks` only, zero requests.

## File Changes

| File | Action | Description |
|---|---|---|
| `manga_tracker/catalogue/contracts.py` | Create | `CatalogueEntry`, `CatalogueClient`, `Response`, `Transport`, two exceptions. No dependencies. |
| `manga_tracker/catalogue/transport.py` | Create | D1; only catalogue file importing `urllib.request`. |
| `manga_tracker/catalogue/kitsu.py` | Create | Batches of 12, `include=item`, separate categories call, ordered `title_candidates`. |
| `manga_tracker/importer/export.py` | Create | XML parse, status map (unknown = hard error), midnight-UTC `last_read_at` with `0000-00-00` guard. |
| `manga_tracker/importer/matching.py` | Create | NFKD normalizer, candidates, apostrophe pair, verification predicate. Pure. |
| `manga_tracker/importer/reconcile.py` | Create | D3 policy. Pure. |
| `manga_tracker/importer/pending.py` | Create | D6. |
| `manga_tracker/importer/run.py` | Create | Orchestration, transactions, progress output. |
| `manga_tracker/sources/manganato/sitemap.py` | Create | Index + 10 shards → `frozenset[str]`. |
| `manga_tracker/sources/contracts.py` | Modify | `fetch_known_slugs(*, progress=None) -> frozenset[str]`. |
| `manga_tracker/sources/manganato/client.py` | Modify | Delegates to `sitemap.py`. |
| `manga_tracker/storage/repositories.py` | Modify | Reconciliation queries + Kitsu writers; `write_seed_backfill` untouched. |
| `manga_tracker/cli.py` | Modify | `import-kitsu`; sole composition root. |
| `tests/test_architecture.py` | Modify | D8. |
| `README.md` §19, `docs/manganato-fuente-actual.md` §18 | Modify | Metadata arrives from the API, not the file. |

## Interfaces

```python
@dataclass(frozen=True)
class CatalogueEntry:
    external_id: str; catalogue_id: str; title: str
    title_candidates: Sequence[str]      # ORDERED; catalogue knowledge
    alt_titles: Sequence[str]; synopsis: str | None; genres: Sequence[str]
    cover_url: str | None; total_chapters: int | None
    publication_status: str              # 'ongoing' | 'finished'

class CatalogueClient(Protocol):
    def resolve(self, external_ids: Sequence[str]) -> Sequence[CatalogueEntry]: ...
```

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit | Normalizer, candidate order, apostrophe pair, verification predicate, status map, midnight-UTC date, three-key policy + ambiguous-title guardian | Pure, no I/O |
| Unit | Kitsu batching, missing-`include` guard, page-full guard, transport delay/retry | Fake `Transport`, stub `sleeper` |
| Unit | Sitemap index + shard parse; malformed shard → `Unexpected` | Trimmed fixtures |
| Integration | Load order, rollback on suspect match, `origin='seed'` bookmark byte-identical, re-run adds no duplicate row and no `reading_history` event | Temp sqlite, fake client |
| Integration | Pending CSV consumed by `load_seed` unchanged | D6's two tests |
| Architecture | Every new rule fires on an injected violation | D8 |

New fixtures: Kitsu mappings payload, the same without `include`, a categories payload, trimmed sitemap index + shard, small export XML.

## Threat Matrix

N/A — no shell, subprocess, VCS/PR automation, executable-file classification, or process integration; `import-kitsu` is in-process argparse dispatch. The one adjacent surface, untrusted remote XML, is decided in D7 with stated failure behaviour and a test.

## Migration / Rollout

No migration. Every column this writes exists in `schema.sql`, and `origin='kitsu_import'` / `detected_via='seed_backfill'` are already in their CHECK constraints. Nothing the scheduler runs changes.

## Open Questions

None. v1.2 closed the reconciliation key, `last_read_at`, `alt_titles`/`synopsis`, the catalogue transport, and the sitemap delay.
