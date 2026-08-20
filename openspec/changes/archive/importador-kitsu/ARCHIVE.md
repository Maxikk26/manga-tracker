# Archive report — importador-kitsu

Closed **retroactively on 2026-08-20**. All 34/34 implementation tasks were already
checked and the work shipped long before this folder was moved here. This report exists
to close the SDD cycle that was left open, not to describe work in flight.

## Why this archive is retroactive, and what that costs

**There is no `verify-report.md` for this change, and none is being invented here.**
The `sdd-verify` phase was never run. The cycle went proposal → design → tasks → apply
and then stopped: the code was merged, deployed, and used, and nobody closed the loop.
The evidence that the change works is therefore operational rather than a verify pass:

- The `import-kitsu` command ran against the real production database and loaded the
  Kitsu export. `CLAUDE.md` records the result — 229 mangas and 229 bookmarks, of which
  **227 came from the Kitsu import** and two were added by hand on 2026-08-05.
- The import is what closed **V1a done-criterion 4**. `README.md` records the V1a phase
  row as `Fase 3 — import de Kitsu | ✅ corrió contra la base real`, and V1a was declared
  done on 2026-08-10.
- The import also populated the `onhold_sweep` population: 72 bookmarks in `on_hold`
  where there had been zero, which is what made the first full Sunday sweep on
  2026-08-09 meaningful.
- `openspec/changes/archive/v1a-heart-phase/ARCHIVE.md` (closed 2026-08-05) already lists
  "the Kitsu importer with its catalogue behind a contract" among the things that shipped
  into production.

Two consequences worth stating plainly rather than glossing:

1. **No independent verification of the spec-to-code match was ever performed.** Task
   evidence in `tasks.md` is self-reported by the apply phase — thorough (Phases 3, 4 and
   5 each carry a mutation-testing pass with the mutations named and the one real finding
   recorded), but self-reported. Anything a verify pass would have caught, it did not catch.
2. **`apply-progress.md` is itself stale and is being preserved as-is.** It documents only
   Phase 1 and lists Phases 2-5 under "Remaining Tasks", while `tasks.md` has all 34 tasks
   checked with per-phase evidence. The progress file was never updated after the first
   work unit. It is left byte-identical because an archived artifact is a record of what
   was written, not a place to retrofit a better history.

## What shipped

The Kitsu importer and the catalogue contract behind it — V1a phase 3 ("backfill"),
implementing `docs/spec-importador-kitsu.md`:

- **`manga_tracker/catalogue/`** — `contracts.py` (`CatalogueEntry`, the batch-only
  `CatalogueClient.resolve(external_ids)` Protocol, its own `Response`/`Transport`,
  `CatalogueTransient`/`CatalogueUnexpected`), `transport.py` (confined stdlib
  `urllib.request` transport), `kitsu.py` (`KitsuCatalogue`: batches of 12 against
  `page[limit]=20`, mandatory `include=item`, a separate `/manga?include=categories`
  call for genres, ordered `title_candidates`).
- **`manga_tracker/importer/`** — `export.py`, `matching.py`, `reconcile.py`,
  `pending.py`, `run.py`: XML read, status mapping, ordered slug candidates with both
  apostrophe variants, sitemap-membership matching, chapter-count verification, load
  order, and the seed-loader-compatible pending CSV.
- **`fetch_known_slugs()`** on the source contract, implemented inside
  `sources/manganato/` — the sitemap is source knowledge and never leaves that package.
- **`import-kitsu`** CLI subcommand in `cli.py`, the only place the concretes
  (`catalogue.kitsu`, `catalogue.transport`, `sources.manganato`) are wired.
- **Architecture rules** — `catalogue` and `importer` entries in `DIRECTIONAL_RULES`,
  the widened `urllib.request` `CONFINEMENT_RULES` set, both new concretes in
  `CONCRETE_IMPLEMENTATIONS`, and `test_boundary_check_flags_an_injected_violation`
  proving every one of them fires against a real file layout.

## Specs merged

Three delta specs, of which **two** were merged into `openspec/specs/` by this archive:

1. **`openspec/specs/catalogue/spec.md`** — new capability, copied verbatim from
   `specs/catalogue/spec.md`. 6 requirements: batch-only resolution contract, batching
   under the catalogue's page limit, `title_candidates` ordered and catalogue-opaque,
   `alt_titles`/`synopsis`/`total_chapters` without extra requests, mandatory
   `include=item` with a test that catches its absence, and the confined-transport
   package boundary.
2. **`openspec/specs/kitsu-import/spec.md`** — new capability, copied verbatim from
   `specs/kitsu-import/spec.md`. 13 requirements: manual invocation, the three-key
   reconciliation order, the never-mutate-a-`origin='seed'`-bookmark rule, status mapping
   with the terminal short-circuit, `last_read_at` as midnight UTC and terminal-only, the
   bookmark invariants (`origin='kitsu_import'`, `progress_is_approx=1`), chapter-count
   verification, catalogue-agnostic candidate generation, source failures routing to
   pending without aborting the run, an unrecognized `my_status` as a hard error, the
   seed-loader-compatible pending CSV, re-run safety by constraint, and the importer
   package boundary.

**`specs/source-client/spec.md` was deliberately NOT merged.** Its three requirements
(`fetch_known_slugs` exposes sitemap-backed membership, no delay exemption for sitemap
shards, existing `Response` shape is sufficient) are **already present** in
`openspec/specs/source-client/spec.md`, folded in when `panel-v1b-fase-3` was archived on
2026-08-20. That archive's `ARCHIVE.md` says so explicitly and warns whoever closes this
change not to merge the delta a second time: `openspec/specs/` was empty at the time and
fase 3's own `source-client` delta sat on top of this one, so a spec carrying only the
fase-3 additions would have been incoherent. Verified before writing this report — the
merged spec carries all three requirement headings verbatim and cites this change's delta
in its `## References`. Merging again would have duplicated them.

## The two owner decisions the proposal blocked on

Both were required before unit 4 could land, and both were resolved rather than defaulted:

- **Seed/Kitsu reconciliation key.** Resolved as three keys in strict order —
  `mangas.kitsu_id`, then the resolved slug via `manga_sites.source_key`, then an exact
  normalized-title match that fires only on exactly one candidate. Zero or multiple
  candidates are reported for manual review, never guessed. A match via key 2 or 3
  backfills the missing `kitsu_id`.
- **`my_finish_date` normalization.** Resolved as midnight UTC (`00:00:00Z`) of
  `my_finish_date`, written to `bookmarks.last_read_at` **only** for terminal statuses
  and only when the date is present; `NULL` in every other case.

## Recorded deviations

- **Transient classification site.** A persistent 429/5xx surviving the catalogue
  transport's one retry is turned into `CatalogueTransient` at the `kitsu.py` call site
  rather than inside the transport, mirroring `CurlCffiTransport`'s existing asymmetry
  (the transport raises only on a genuine network-level failure; a repeated bad status
  code is handed back as data for the caller to classify). The design was silent on
  this; the choice matches the existing precedent.
- **`catalogue.transport` added to `CONCRETE_IMPLEMENTATIONS`** alongside
  `catalogue.kitsu`, one name beyond design D8's literal list. Same rule class: it is a
  concrete, `importer` is already forbidden from naming it, and the spec's "one line in
  `cli.py`" promise covers the transport as much as the client.
- **A third scanner, `_composition_root_violations(pkg_root)`**, was parameterized in
  Phase 5 beyond the task's literal text, because the composition-root rule was the one
  boundary with no vacuity guard at all and this change widened what it protects.
- **The live-API smoke check was never run** in the apply environment. Task evidence
  records it as `N/A`: the sandbox blocked network egress, so all logic was exercised
  against a scripted fake transport instead. The real run happened later, in production,
  when the owner ran `import-kitsu` against the actual export.

## Where the truth lives now

`docs/` — as always. `docs/spec-importador-kitsu.md` is the contract this change
implemented; `docs/spec-modelo-de-datos.md` owns `bookmarks.origin`,
`progress_is_approx` and `last_read_at`; `docs/spec-seed-manual.md` owns the CSV format
the pending list has to match. Read those, not this folder.

The two capability specs merged by this archive live at `openspec/specs/catalogue/spec.md`
and `openspec/specs/kitsu-import/spec.md`.

## Artifacts in this folder

| Artifact | Path | Note |
|---|---|---|
| Proposal | `proposal.md` | Scope, the five work units, the two blocking owner decisions |
| Design | `design.md` | D1-D8 and CAT-1..6 |
| Tasks | `tasks.md` | 34/34 checked, with per-phase mutation evidence for Phases 3, 4 and 5 |
| Apply progress | `apply-progress.md` | **Stale — Phase 1 only.** Preserved as written |
| Specs (delta) | `specs/catalogue/spec.md`, `specs/kitsu-import/spec.md`, `specs/source-client/spec.md` | The first two merged here; the third merged by `panel-v1b-fase-3` |
| Verification report | — | **Does not exist.** See the first section |

## Follow-up carried forward

- **Verification debt.** This change never got an independent verify pass and never will
  — the code is a year of production runs old in behaviour terms and re-verifying it
  against a paper contract now would prove less than the production data already does.
  Recorded so nobody later reads the missing file as an oversight in the record rather
  than an oversight in the process.
- **Near-duplicate slugs.** Verification by chapter count cannot distinguish a genuine
  match from a near-duplicate title whose chapter count happens to be compatible. Already
  accepted in `docs/spec-importador-kitsu.md` §"Pendientes abiertos"; unchanged here.
