# Design: `my_score`, the scores backfill and the terminal covers (`panel-v1b-fase-4`)

Contract: `docs/spec-panel-v1b.md` v1.6 → **v1.7 here**. Proposal: `proposal.md`. File map: `exploration.md` (trusted, not restated).
Data model: `docs/spec-modelo-de-datos.md` v1.9. Placement: `docs/decision-arquitectura-v1b.md` v1.2.
Owner decisions of 2026-08-25 (un-scoring allowed, fill-only-NULL, no heatmap cap) are authoritative.

## Technical Approach

Three independent mechanisms, one shared column. Nothing new is invented: migration 3 copies migration 2, the
score rides the `UNSET` sentinel that `PATCH` already uses for its two other fields, `import-scores` copies
`_cmd_import_kitsu`'s ordering, and the terminal covers are the existing cover loop with its expensive half
removed. Per PAN §195 this phase ships **the data and its editing**, and spends zero visual decisions.

```
migration 3 ──► bookmarks.my_score INTEGER (NULL = unscored)
                        │
      ┌─────────────────┼─────────────────────┐
      │                 │                     │
  import-scores    PATCH /api/bookmarks   list payload
  (cli → importer/     (web → repo)        (repo SELECT)
   scores.py)              │                     │
      │ Kitsu /mappings    │ UNSET = absent      └─► BookmarkCard
      │ ~38 req            │ None  = clear
      └─ UPDATE ... WHERE my_score IS NULL

cache-covers ──┬─ non-terminal statuses ─► backfill_covers        (mapped;  ≤2 req)
               └─ terminal statuses ─────► backfill_stored_url_covers (≤1 req, no slug in scope)
```

## Architecture Decisions

### D1 — `my_score: null` means *clear*; absence is the sentinel that already exists

The mechanism is **`model_fields_set` at the boundary and `repositories.UNSET` below it**. `None` is a legal
*value* on this field for its whole journey, so no layer may test it for presence.

| Layer | Code | Note |
|---|---|---|
| Pydantic | `my_score: int \| None = Field(default=None, ge=0, le=10)` | `int`, so `7.5` is a 422 |
| Route | `my_score=patch.my_score if "my_score" in fields else UNSET` | byte-for-byte the shape of the two lines above it (`app.py:233-234`) |
| Repository | `if my_score is not UNSET: assignments.append("my_score = ?")` | `None` binds as SQL NULL |

`UNSET = object()` (repositories.py:41) already carries the comment that settles this: *"None cannot play that
role because it is a real value."* It was written for `last_chapter_read`, where `web` then forbids null anyway;
`my_score` is the first field where the sentinel is load-bearing all the way down.

| Alternative | Why rejected |
|---|---|
| `if my_score is not None:` in the repository | **This is the bug the phase exists to avoid.** Un-scoring becomes silently unreachable: the PATCH returns 200, the score is unchanged, and nothing logs. It is the reflex reading and it must be refused in a comment, not just in code. |
| A `clear_score: bool` companion field | Two fields for one edit; `{"my_score": null}` is already unambiguous once presence is read from `model_fields_set`. |
| Sentinel string (`"__clear__"`) on the wire | Puts a magic value in a public JSON contract to avoid a mechanism the codebase already ships. |

### D2 — The presence validator gains *no* clause for `my_score`, and says why

`_check_presence` (app.py:167-175) rejects an explicit null for both existing fields. `my_score` gets the
empty-body check and **nothing else** — that omission is the decision, and an asymmetry a reader will "fix" by
reflex. The divergence has a reason and it belongs in the docstring: progress feeds the trigger,
`reading_history` and the digest, so nulling it destroys unrecoverable history; a score feeds nothing but the
list, so a mistyped one must be clearable without opening SQLite.

Two stale statements to correct in the same edit — CLAUDE.md's rule, not tidiness. The class docstring
("progress and/or status, at least one… neither may be null when present") and the error string
`"the body must carry last_chapter_read and/or status"` are both wrong the moment this field exists.

### D3 — TypeScript: `{ my_score: number | null }`, never an optional property

```ts
export type BookmarkPatch =
  | { last_chapter_read: number }
  | { status: BookmarkStatus }
  /** `null` clears the score (D1). NOT `my_score?: number`: JSON.stringify
   *  DROPS keys whose value is undefined, so an optional property would send
   *  `{}` and earn a 422 instead of clearing anything. `null` survives. */
  | { my_score: number | null };
```

`patchBookmark` (`api/bookmarks.ts:33`) serializes with `JSON.stringify` and needs no change; the union is what
makes the un-scoring path expressible at all.

### D4 — `InlineNumberEdit` gains `max?` and `onClear?`, not a widened `onCommit`

| Option | Tradeoff |
|---|---|
| Widen to `onCommit: (value: number \| null) => void` | **Breaking.** `strict: true` (tsconfig.json:17) implies `strictFunctionTypes`, so the existing `(value: number) => void` handler stops being assignable and `BookmarkCard` must handle a null it may not legally send. |
| `clearable?: boolean` + widened commit | Same variance problem, plus a boolean that changes a callback's contract. |
| **`onClear?: () => void`** ✅ | Strictly additive. Its **absence** is what encodes "this field cannot be cleared", so `last_chapter_read` keeps line 41's blank-blur no-op unchanged and needs no new branch. |

`max?: number` is validated exactly as `min` already is (`parsed < 0` gains `|| (max !== undefined && parsed > max)`)
and is forwarded to the `<input max=…>`. Integer enforcement stays client-side-optional: the server's `int` field
is the guard that makes the contract sound, the input attribute is UX.

### D5 — The cover route: permission selects the route, data selects the cost

**"The 66 terminals are exactly the 66 unmapped" is true today and is not an invariant.** PAN §161 explains
*why* today's rows are that way — sweeps never visit a terminal, so they never learned a slug — and that
explanation says nothing about the panel marking a mapped `reading` manga `completed` in one click. The
predicate must not encode the coincidence.

Two independent facts per row, and only one of them picks a route:

| Fact | Role |
|---|---|
| bookmark status is terminal | **Permission.** Route A can spend a source lookup; a terminal may not. This is what dispatches. |
| `cover_url IS NULL` | **Cost.** Decides whether servicing the row needs a slug at all — inside whichever route runs. |

A mapped terminal therefore needs no special case: with a known `cover_url` it is downloaded like any other row
(the download asks the source nothing), and with a NULL one it is **skipped and counted**, despite owning a
slug, because using it would be a detection-shaped request PAN §169 does not authorise.

The zero-manganato guarantee is **structural, not behavioural**: `list_stored_url_cover_candidates` has no
`manga_sites` join, so `source_key` is never in the thin loop's scope and `fetch_manga_details` is not callable
there even by mistake. That is PAN §163's "no hay slug con el que hacerlas aunque alguien quisiera", made
mechanical.

The rule the design draws, stated once so a manganato-hosted terminal cover is not a live question later:
**a terminal bookmark may not spend a request that asks the source a question** (details, chapters, feed). An
image GET against an address already in the database asks nothing and cannot advance, renumber or notify.

`--status` dispatch, from the requested set:

| Requested statuses | Route | Population | Requests/manga |
|---|---|---|---|
| non-terminal (default: reading, want_to_read, on_hold) | `backfill_covers` — unchanged | `list_cover_candidates` (INNER JOIN `manga_sites`) | 0-2 |
| terminal (`completed`, `dropped`) | `backfill_stored_url_covers` — new | `list_stored_url_cover_candidates` (no join) | 0-1 |

Bare `cache-covers` still costs ~0 requests: the default set is entirely non-terminal, so the second route never
runs (owner assumption 5 — an existing habit must not silently change price).

**Known gap, deliberately not closed here:** an *unmapped non-terminal* row with a stored `cover_url` is reachable
by neither route. Its population is **zero today** — 170 mapped, 66 unmapped, all 66 terminal (PAN §161) — by the
very coincidence above. The same click that breaks the clean cut creates this gap's first row. Recorded as a
follow-up; widening Route A to a LEFT JOIN is a behaviour change to a shipped command and is out of scope.

### D6 — `import-scores`: the fill-only-NULL rule is enforced in SQL, not in Python

`set_bookmark_score` issues **one** statement:

```sql
UPDATE bookmarks SET my_score = ?, updated_at = ? WHERE manga_id = ? AND my_score IS NULL
```

and reports `cursor.rowcount` so the caller can separate *filled* from *already scored*. A read-then-write in
Python would be a real TOCTOU, not a theoretical one: the panel container serves the same SQLite file, and the
owner can be typing a score in the browser while the import runs. One conditional statement closes it; WAL plus
`busy_timeout=5000` (db.py:121-122) handles the lock.

Ordering copies `_cmd_import_kitsu` (cli.py:80-93): read and report the file **before** a connection, before the
network. `--dry-run` returns there with **file-only counts** and says so in words — accuracy would cost the same
~38 requests as the real run, which is just the run without the write (owner assumption 2).

Two more placements:

- **Score 0 → NULL at parse time**, in `export.py::_entry`, because it is a fact about the file format
  (PAN §174): the export writes 0 for "never rated". The importer must never see a 0 it has to interpret. The
  panel's vocabulary is different and both are right — a 0 typed into the card is a deliberate score and reaches
  the column through `PATCH`, which the importer never touches.
- **`catalogue` stays unmodified.** `KitsuCatalogue.resolve()` runs `_fetch_categories` unconditionally
  (kitsu.py:123); skipping it would halve ~38 requests to ~19 and save ~19 seconds, **once**, at the price of a
  new parameter on the shared `CatalogueClient` Protocol that every implementation must honour forever. Declined.
  Counter-argument recorded: a `CatalogueUnexpected` from a categories call the run does not need would abort it
  — harmless, since resolution precedes every write and re-running is safe.

`import-scores` is the first subcommand that touches the catalogue and never the source: it must **not** call
`_bootstrap` (which builds a `ManganatoClient` and writes the `sites` row). It constructs
`KitsuCatalogue(UrllibJsonTransport())` and nothing else.

### D7 — Migration 3 mirrors migration 2, including the trap its test fixture sets

`_migration_3_bookmarks_my_score`: `PRAGMA table_info(bookmarks)` guard, one `ALTER TABLE … ADD COLUMN
my_score INTEGER`, **no backfill**, `SCHEMA_VERSION = 3`, `MIGRATIONS[3]`. `schema.sql` gains the column too —
for databases born empty only; `ensure_schema` does nothing to an existing table (db.py:91-106).

The fixture is textual and therefore constrains the schema file: `_build_pre_migration_3_database` strips the
literal `"    my_score INTEGER,\n"`. So the declaration must sit **on its own line with no trailing comment**
(explanatory comments go above it, as `status_changed_at` does at schema.sql:49-53), and
`test_migrating_from_zero_applies_all_three_migrations_in_order` must strip this line too — it currently strips
only migration 1's and 2's, so a database at `user_version 0` would otherwise be built already carrying the
column.

**No DB-level `CHECK (my_score BETWEEN 0 AND 10)`** — settled in the proposal, restated because the schema is
where a reader will look for it: `last_chapter_read` validates in Pydantic only, and a CHECK added later is a
table rebuild on a populated database.

### D8 — `TERMINAL_STATUSES` gets one home and a parity test

`frozenset({"completed", "dropped"})` already exists twice (`web/app.py:76`, `importer/export.py:31`) and this
change needs it in `cli.py` and `discovery/covers.py`. It lands in `storage/repositories.py` beside
`BOOKMARK_STATUSES`, which already owns the status vocabulary and is importable from everywhere. The two
existing copies stay — pulling `storage` (and `sqlite3` with it) into the pure XML parser is a worse trade — and
a ~8-line test asserts all three sets are equal, the same tactic fase 3 used for the status-label mirror. The set
can only grow through a `bookmarks.status` CHECK migration, so the duplication is bounded.

## Interfaces / Contracts

```python
# storage/repositories.py
TERMINAL_STATUSES = frozenset({"completed", "dropped"})

def update_panel_bookmark(conn, bookmark_id, *, last_chapter_read=UNSET, status=UNSET,
                          my_score=UNSET, now: str) -> bool:
    """... my_score: UNSET = absent, None = CLEAR IT, int = set it.
    `is not UNSET`, never `is not None` — None is a legal value here (design D1)."""

def set_bookmark_score(conn, manga_id: int, my_score: int, *, now: str) -> bool:
    """Fill an unscored bookmark. Returns False when it already had one — the
    guard is in the WHERE clause, not in Python (design D6)."""

def list_stored_url_cover_candidates(conn, *, statuses: tuple[str, ...]
                                     ) -> list[tuple[int, str, str | None]]:
    """(manga_id, title, cover_url) for these statuses. NO manga_sites join:
    this route may not ask the source, so it never holds a slug. Not filtered
    on cover_url — the caller reports the NULLs it skips."""
```

```python
# discovery/covers.py — sibling of backfill_covers, not a branch inside it
def backfill_stored_url_covers(*, db_path, client, cache_dir, statuses,
                               limit=None, now_fn) -> CoverBackfillReport: ...
# CoverBackfillReport gains: no_url: list[str]  (skipped: nothing to download and
# nowhere this route is allowed to ask)

# importer/scores.py — new module; run.py untouched
@dataclass(frozen=True)
class ScoreImportReport:
    total: int; with_score: int; resolved: int
    filled: int; already_scored: int; unresolved: int; not_in_database: int

def import_scores(export_path, conn, catalogue: CatalogueClient) -> ScoreImportReport:
    """Resolve every id in one catalogue call (chunked at 12), then fill NULLs.
    Never creates a row: an entry whose manga is absent is an ordinary skip."""
```

```python
# importer/export.py — reverses KIT decision 5
my_score: int | None   # export scale 0-10; a 0 in the file becomes None (PAN §174)
```

## File Changes

| File | Action | Description |
|---|---|---|
| `manga_tracker/storage/schema.sql` | Modify | `my_score INTEGER,` on its own line in `bookmarks` (D7) |
| `manga_tracker/storage/db.py` | Modify | `SCHEMA_VERSION = 3`, `_migration_3_bookmarks_my_score`, `MIGRATIONS[3]` |
| `manga_tracker/storage/repositories.py` | Modify | `my_score` in `_PANEL_BOOKMARK_SELECT` + `_panel_bookmark_row`; `my_score=UNSET` in `update_panel_bookmark`; `set_bookmark_score`; `list_stored_url_cover_candidates`; `TERMINAL_STATUSES`. Also: the `"59 of 229 in production"` comment (line ~407) is stale — PAN §161 measured 66 of 236 on 2026-08-25 |
| `manga_tracker/web/app.py` | Modify | `BookmarkPatch.my_score`, docstring + error string corrected (D2), one line in `patch_bookmark`. `GET /api/covers/{manga_id}` **unchanged** |
| `manga_tracker/discovery/covers.py` | Modify | `backfill_stored_url_covers`, `CoverBackfillReport.no_url` |
| `manga_tracker/importer/export.py` | Modify | `ExportEntry.my_score`, `_entry` reads `<my_score>` with 0 → None |
| `manga_tracker/importer/scores.py` | Create | `import_scores` + `ScoreImportReport` |
| `manga_tracker/cli.py` | Modify | `import-scores` verb; `cache-covers` splits its requested statuses across the two routes and prints two populations |
| `frontend/src/domain/types.ts` | Modify | `Bookmark.my_score`, `BookmarkPatch` third variant (D3) |
| `frontend/src/components/InlineNumberEdit.tsx` | Modify | `max?`, `onClear?` (D4) |
| `frontend/src/components/BookmarkCard.tsx` | Modify | Second `InlineNumberEdit` for the score, plainly placed. No new CSS |
| `frontend/src/containers/BookmarkListContainer.tsx` | Modify | `onChangeScore(id, value \| null)` → `patchBookmark` |
| `docs/spec-panel-v1b.md` | Modify | → **v1.7** (see Rollout) |
| `docs/spec-importador-kitsu.md` | Modify | Changelog note: V1b reversed decision 5 |
| `tests/` | New + Modify | See below |

## Testing Strategy

Databases are real files on disk, never `:memory:`. Sockets are blocked by `tests/conftest.py`; every catalogue
and source call is a fake.

| Layer | File | What it must prove |
|---|---|---|
| Migration | `tests/storage/test_migrations.py` | third block mirroring migration 2's: pre-migration-3 builder at `user_version 2`, gains the column and keeps its rows, **does not invent a score** (NULL stays NULL), fresh DB is born with it, from-zero applies **three** migrations in order, and the own-line fixture guard |
| Unit | `tests/storage/` | `update_panel_bookmark(my_score=None)` writes SQL NULL; `my_score=UNSET` leaves the column untouched; a score-only edit writes **zero** `reading_history` rows; `set_bookmark_score` returns False and changes nothing on an already-scored row |
| Integration | `tests/web/test_panel_api.py` | the three-way contract: `{"my_score": 7}` sets, `{"my_score": null}` **clears**, key absent leaves it alone; `11`, `-1` and `7.5` are 422; `{}` is still 422; the list payload and the PATCH response both carry the field; clearing generates no reading event |
| Unit | `tests/importer/test_scores.py` (new) | 0 in the file → NULL; a non-NULL score is skipped, not overwritten; an unresolved id and a manga absent from the database are ordinary skips with distinct counters; a second run fills zero; a catalogue failure writes nothing |
| Regression | `tests/importer/test_export.py:160-165` | **deliberately rewritten**: asserts `my_score` is now carried *and* that 0 becomes None. The old test pinned KIT decision 5; the changelog note ships in the same commit |
| Unit | `tests/discovery/test_covers.py` | the thin route downloads with **zero** `fetch_manga_details` calls (assert the fake was never asked); a NULL `cover_url` is counted in `no_url`, never fetched; a **mapped terminal** with a known URL is downloaded and a mapped terminal without one is skipped — D5's predicate, executable; already-cached rows cost nothing |
| Unit | `tests/storage/` | `list_stored_url_cover_candidates` returns unmapped rows the INNER-JOIN query cannot see, and returns no `source_key` at all |
| Contract | `tests/` | the three `TERMINAL_STATUSES` copies are equal (D8) |
| Unit (TS) | `InlineNumberEdit.test.tsx` | `max` rejects an over-range commit; **without `onClear` a blank blur stays a no-op** (the `last_chapter_read` guarantee); with it, a blank blur calls `onClear` exactly once |
| Integration (TS) | `BookmarkCard.test.tsx`, `BookmarkListContainer.test.tsx` | the score renders `—` when null; editing sends `{my_score: n}`; clearing sends `{"my_score": null}` and **not** `{}` — assert the serialized body, since that is where `undefined` would vanish |

## Threat Matrix

| Boundary | Applicability |
|---|---|
| Routing / process integration | N/A — two argparse subcommands in-process; no subprocess, no shell |
| Shell commands / VCS / PR automation | N/A — none invoked |
| Executable-file classification | N/A — the only files written are images under `data/covers/`, through `cover_cache.write_cover`'s allow-listed suffix and int-derived filename |
| Documentation-like paths | N/A |

One boundary recorded as an **accepted risk**, weaker than fase 3's: `backfill_stored_url_covers` GETs a
`cover_url` read from the database. Its provenance is the Kitsu import or a panel add, both already trusted, and
unlike fase 3's accepted risk no client-supplied URL is involved. Failure is one wasted request.

## Migration / Rollout

**Deploy order is fixed by the dependency:** migration 3 must be live in production before `import-scores` or a
score PATCH runs. `docker compose up -d` (never `restart`) applies it on the first `connect`.

**The backup is a manual operator step, not automation.** `docs/runbook-deploy.md` §7:
`cp ~/manga-tracker-data/manga-tracker.db ~/backups/manga-tracker-$(date +%F).db`, taken before the deploy that
carries migration 3. There is one production database with 236 bookmarks and no second copy.

**Rollback.**

| Piece | Reverting the commit leaves |
|---|---|
| Migration 3 | The column, and that is safe. Verified against `db.py:83`: v2 code against a database stamped 3 walks `range(4, 3)` — **empty**, a no-op, not a crash. v2 code ignores the column. `DROP COLUMN` + `PRAGMA user_version = 2` is what the backup is for, never a routine step |
| `my_score` end to end | Nothing. Scores typed in the panel survive as data v2 code does not read |
| `import-scores` | Exactly `bookmarks.my_score` where it was NULL, plus `updated_at`. `UPDATE bookmarks SET my_score = NULL` cleans it. **`reading_history` untouched** — the trigger's `WHEN` guard is on `last_chapter_read` (schema.sql:97) |
| Terminal covers | Cached files under `data/covers/`, each recoverable for one request |

**PAN → v1.7, one bump for the whole delivery**, landed with the first slice. Contents: §232 closed as
**decided — no cap** (v1.6 assigned it to fase 4 in error); §174 corrected to state the MAL-id resolution and its
~38 Kitsu requests, replacing "matchea por `kitsu_id` ya guardado"; §175 gains the un-scoring contract; §161
qualified — the clean terminal/unmapped cut describes how today's rows were created, and the panel can break it
in one click; §186 rewritten to four pieces. A bump per slice was rejected as churn: one document, one version.

## Changed-Lines Forecast

| Area | ± lines |
|---|---|
| `storage/` (schema, db, repositories) | ~110 |
| `web/app.py` | ~30 |
| `discovery/covers.py` + `cli.py` | ~150 |
| `importer/` (export, scores) | ~130 |
| Backend tests (4 touched, 2 new) | ~600 |
| Frontend production (4 files) | ~110 |
| Frontend tests (3 touched) | ~150 |
| `docs/` | ~35 |
| **Total** | **≈ 1315 (±20%)** |

`Decision needed before apply: Yes`
`Chained PRs recommended: Yes`
`400-line budget risk: High`

Above the proposal's ~800 estimate for the reason fase 3 measured and this repo repeats: modules run ~40% comment
by line, and "always do testing" puts ~750 lines in tests. `delivery_strategy: auto-chain`, budget 800.
Recommended cut — four slices, each with a clear finish, its own tests and its own rollback:

| # | Slice | Depends on | ± lines |
|---|---|---|---|
| 1 | **Terminal covers** — the new query, `backfill_stored_url_covers`, the `cache-covers` split and its two-population output, `TERMINAL_STATUSES` + parity test, PAN v1.7 | none | ~440 |
| 2 | **Migration 3** — `schema.sql`, `db.py`, the third `test_migrations.py` block | none | ~130 |
| 3 | **`my_score` end to end** — repository, Pydantic, route, `types.ts`, `InlineNumberEdit`, `BookmarkCard`, container | 2 | ~430 |
| 4 | **`import-scores`** — `export.py`, `importer/scores.py`, `set_bookmark_score`, the CLI verb, the KIT note | 2 | ~430 |

Slice 1 first because it is independent of the schema and provable in production the day it lands. Slice 2 alone
because it is the only piece that touches the production database, and a migration deserves its own review and
its own backup window — a column nothing yet reads is exactly the right size for that. Slices 3 and 4 both depend
on 2 and not on each other; 3 goes first so its tests pin the un-scoring contract before 4's fill-only-NULL rule
is written against the same column.

**`--limit` applies per route, not across the run**, and its help text says so. A single limit spanning both would
make `--limit 1` exercise whichever route happened to sort first and would make the cost of `--limit N` depend on
the status mix. `--dry-run` prints the two populations as two blocks with their own cost lines and a total, never
one merged number.

## Open Questions

- [ ] **Confirm the four-slice cut** above before `sdd-tasks` plans a single PR. `auto-chain` resolves the
      strategy but not the boundaries.
- [ ] Follow-up, not a blocker: the unmapped-non-terminal cover gap (D5). Zero rows today; worth a spec line in
      fase 5 or its own one-liner once the panel has moved a mapped manga to a terminal state.
