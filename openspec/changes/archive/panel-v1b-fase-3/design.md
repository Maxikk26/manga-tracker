# Design: add a manga from the panel (`panel-v1b-fase-3`)

Contract: `docs/spec-panel-v1b.md` v1.1. Proposal: `proposal.md`. File map: `exploration.md` (trusted, not restated).
Owner product decisions of 2026-08-19 are authoritative and override the proposal's assumption table.

## Technical Approach

A new top-level package **`manga_tracker/intake/`** owns the add flow end to end. `web` gains two endpoints
that call it and translate its typed failures into Spanish HTTP errors; it never names a source module again.
The panel says *"agrega esto"* (PAN §36) because the sequencing — slug → ficha → duplicate gates → chapters
→ one transaction → cover — lives entirely outside `web`.

```
browser ── POST /api/mangas/preview ──► web/app.py ──► intake.preview(conn, url)
                                            │                 │ extract_slug (0 req)
                                            │                 │ duplicate gates (0 req)
                                            │                 └─ fetch_manga_details (1 req)
           POST /api/mangas ─────────────► web/app.py ──► intake.confirm(conn, ...)
                                            │                 │ gates again, in-transaction
                                            │                 │ fetch_chapters (1 req)
                                            │                 │ repo.write_manual_add  ← one transaction
                                            │                 └─ fetch_cover (1 req, failure tolerated)
                                            └── 201 get_panel_bookmark(conn, bookmark_id)
```

## Architecture Decisions

### D1 — A service layer, not a raw `SourceClient` in `create_app`

| Option | Tradeoff |
|---|---|
| `create_app(db_path, client: SourceClient, site_id)` | Satisfies the AST rule, but `web` holds the client and sequences four source calls: that is *"descarga esto"*, against PAN §36. |
| **`create_app(db_path, intake: MangaIntake)`** ✅ | `web` imports `intake.contracts` only; the enforceable form of §36 is that `web` may not import `sources` **at all**. Mirrors `SourceClient`/`ManganatoClient` and `CatalogueClient`/`KitsuCatalogue`. |
| Put the flow in `catalogue/` (PAN §85's wording) | Impossible: `DIRECTIONAL_RULES["catalogue"]` forbids `sources` outright (test_architecture.py:19), and catalogue is Kitsu. The spec's wording is a naming trap (exploration §3). |
| Put the flow in `seed/` or `importer/` | Directional shape fits, semantics do not: `seed` is a CSV file (`load_seed(csv_path, ...)`), `importer` is a Kitsu export. An interactive two-step preview/confirm would make either mean two things. |

New package, two modules:

| Path | Contents |
|---|---|
| `manga_tracker/intake/contracts.py` | `MangaIntake` Protocol, `AddPreview`/`AddResult` frozen dataclasses, `InvalidUrl` and `AlreadyTracked(title, status)` exceptions. **No Spanish, no HTTP, no source knowledge.** |
| `manga_tracker/intake/pasted_url.py` | `PastedUrlIntake(client: SourceClient, site_id: int, cache_dir: Path)` — the only implementation. Imports `sources.contracts`, `storage.*`, `importer.matching`. |

Methods take `conn`, never open it: connection lifecycle stays the caller's, as in `load_seed` and `run_import`.
`now` is passed in by `web._utc_now()`, as `update_panel_bookmark` already does.

### D2 — Product copy lives in `web`, structured failures in `intake`

`intake` raises `AlreadyTracked(title="…", status="dropped")` — raw schema values, no Spanish; `web` composes
the sentence. Keeps the non-web layer language-neutral and keeps user-facing copy in the layer that faces the
user (CLAUDE.md: Spanish for what the product says, English for what the machine says to a developer).

Consequence, accepted deliberately: `web/app.py` gains a **Python mirror of the five Spanish status labels**
that `frontend/src/domain/statusLabels.ts:7` already holds, because the duplicate/terminal `detail` string must
name the state in Spanish for a reader who only has `detail` (spec.md:26, :34). That file says "nothing else
translates statuses", and this design breaks that claim rather than pretending otherwise — so the drift is
pinned executably instead of by comment: a test in `tests/web/` parses `statusLabels.ts` as text and asserts
the two maps are equal. Same tactic as `BookmarkStatus = Enum(..., BOOKMARK_STATUSES)` (app.py:40) and as the
string-level `VOCABULARY_RULES` scan — this repo pins cross-artifact agreement with a test, not with trust. The
set can only grow through a `bookmarks.status` CHECK migration, so the mirror is bounded at five entries.

### D3 — Duplicate detection: three gates, two of them free

`find_slug_owner` cannot see the 66 terminal Kitsu mangas (no `manga_sites` row), so slug identity is not enough.

| # | Gate | Cost | Catches |
|---|---|---|---|
| 1 | `repo.find_slug_owner(conn, site_id, slug)` | 0 req | any manga already mapped to this slug, in any state |
| 2 | pasted slug ∈ `matching.slug_variants(stored_title)` for every tracked title | 0 req | terminal Kitsu rows — the importer bound titles to slugs with exactly this function, so the inverse test has the same hit rate |
| 3 | `matching.normalize(details.title) == matching.normalize(stored_title)` | after the ficha (1 req) | the residue gate 2 misses (source title ≠ catalogue title) |

Gates 1-2 run before any request, so a duplicate is refused for free. Gate 3 runs on the preview's ficha, no
extra request. All three run again inside `confirm`'s transaction (TOCTOU); `idx_manga_sites_site_source_key`
is the last line of defence and turns a race into a clean 409, not a 500.

New read: `repo.list_tracked_titles(conn) -> list[tuple[str, str]]` — `(title, status)` joined over `bookmarks`.
Folding happens in Python because SQLite has no NFKD (repositories.py:96-98, reconciliation key 3's precedent).

### D4 — Preview→confirm continuity: echo `title` and `cover_url`

| Option | Tradeoff |
|---|---|
| Re-fetch the ficha on confirm | A 4th request and a 5-15s courtesy delay against a ~3-request budget; the title could also have changed between the two steps, making the confirmed manga not the previewed one. |
| Server-side preview cache | State in a stateless design; dies on restart mid-flow, needs a TTL and eviction. |
| **Echo both fields from the preview response** ✅ | Statelessness preserved, 3 requests. The slug is re-derived server-side from `url`, never trusted from the client. |

Trust analysis: a client-supplied **title** is exactly the seed loader's existing trust model
(`_title(row)` is hand-typed, `_slug_owner_error` is the only guard). A client-supplied **cover_url** makes the
server GET an arbitrary address — the accepted-risk note is below.

### D5 — Zero chapters: add with `latest_chapter_num` NULL (owner decision 2). **No schema change.**

`manga_sites.latest_chapter_num REAL` is nullable (schema.sql:32) and so are `latest_chapter_url` /
`latest_chapter_at`. The proof that this row shape flows through detection, which the seed loader never
produced because it discarded these rows (loader.py:203):

| Step | Evidence | Behaviour with NULL |
|---|---|---|
| Population | `active_sweep._population`, active_sweep.py:76-83 | Filters on `b.status` and `consecutive_failures` only — a NULL-latest mapping is **in** the population. |
| Prefilter | `has_moved`, prefilter.py:60-61 (docstring at :44) | `stored_at is None → True`. `latest_chapter_at` is NULL, so the mapping is **always requested**, never skipped. The docstring names this case first: "No stored timestamp: never successfully checked, so nothing to compare." |
| Detection rule | `apply_detection`, detection.py:82-88 | `if latest is not None and chapter.chapter_num <= latest` — the guard is explicitly NULL-aware. NULL falls through to the `chapter_history` insert (:90) and to `Candidate` (:109). |
| Advance | `send_and_advance`, runs.py:137-142 | Writes `latest_chapter_num` after a successful digest. The NULL is sealed by the first sweep that finds a chapter. |
| Digest math | `_accumulated_count`, runs.py:98-104 | Reads `last_chapter_read`, not `latest_chapter_num`. Unaffected. |
| Panel read | `_panel_bookmark_row`, repositories.py:299-303 | `behind` is NULL when either side is NULL — "unknowable, not zero". |
| Panel render | `BookmarkCard.tsx:62`, `:88`, `:103` | `readable` is false → cover without a link, and no `de N` suffix. Already a first-class branch. |

**Conclusion: NULL is the correct representation and needs no code change.** `0` would be a lie (it claims the
source published chapter 0) and would additionally satisfy `latest is not None`, so a source that renumbers
downward to a fraction below 1 would be silently swallowed by step 3 instead of logged.

Consequence to accept, not fix: the first sweep after such an add emits a digest line for the manga. That is
correct — a chapter really was detected for the first time.

### D6 — Cover failure on confirm never fails the add

The transaction commits first; the cover is fetched after it, outside any transaction. `NotFound`/`Transient`/
`Unexpected` are caught, logged, and reported as `AddResult.cover_cached=False`. Justification is already
written into the covers route: "404 when the image was never cached. That is an ordinary state, not an error"
(app.py:129-132), and the card has a gradient-initials fallback (BookmarkCard.tsx:42-51).

The atomic `.part`-then-`replace` write moves from `discovery/covers.py:145-150` into
**`storage/cover_cache.write_cover(cache_dir, manga_id, cover_url, image) -> Path`**, and `covers.py` calls it.
Second copy avoided rather than created; `cover_cache.py` already owns "where cover images live on disk".

### D7 — Two routes, not one flagged route

`POST /api/mangas/preview` (200, no write) and `POST /api/mangas` (201, writes). One endpoint with a
`confirm: bool` would return two unrelated shapes from one path. Both are registered before the static mount,
so `_SPAStaticFiles` never sees them (app.py:148).

### D8 — `site_id` for the panel process

`_cmd_panel` currently never calls `ensure_site`, so it has no `site_id`. It reuses `_bootstrap(config)`
(cli.py:238) which already returns `(site_id, ManganatoClient)`; its docstring ("shared by every subcommand
that runs a job") is corrected. `ensure_site` stays called from `cli.py` only (design D4/B6).

### D9 — The boundary rules, and what proves them

```python
# tests/test_architecture.py
"web":    {"sources", "notifier", "discovery", "catalogue", "importer", "seed", "intake.pasted_url"},
"intake": {"sources.manganato", "notifier", "discovery", "catalogue", "seed", "web"},
```

`web`'s set widens from `sources.manganato` to **all of `sources`**: that is the mechanically checkable form of
"el panel no llega a la fuente ni indirectamente" (PAN §37, spec.md:127). `intake.pasted_url` joins
`CONCRETE_IMPLEMENTATIONS`, and `intake` and `web` are added to the forbidden sets of
`sources`/`storage`/`notifier`/`catalogue` — those sets list every package that is not downstream, and both were
missing from all four.

What `intake` may import, stated exactly rather than as "everything not downstream": **`storage`,
`sources.contracts`, and `importer`**. Everything else is denied by the set above. `importer` stays reachable
on purpose and for one function family — `matching.normalize` / `matching.slug_variants`, pure, no I/O, no
source knowledge, already documented as shared with reconciliation key 3 (matching.py:21-33). The alternative
was a per-module denylist (`importer.run`, `importer.export`, `importer.reconcile`, `importer.pending`), which a
new module in `importer/` would escape by default — a denylist that grows silently is worse than an allowance
that is written down. Revisit only if `matching` moves to a shared home.

Four new probe files in `test_boundary_check_flags_an_injected_violation`, because a rule this repo cannot see
fail is a rule it has shipped unenforced before (test_architecture.py:199-212 exists for that reason):

| Probe | Import | Proves |
|---|---|---|
| `intake/probe.py` | `manga_tracker.sources.manganato.client` | intake names no concrete source |
| `web/probe2.py` | `manga_tracker.sources.contracts` | web cannot reach the source at all |
| `web/probe3.py` | `manga_tracker.intake.pasted_url` | web asks the service, never builds it |
| `web/probe4.py` | `manga_tracker.sources.manganato` | **spec.md:134-140, verbatim** |

`web/probe4.py` is the literal probe the spec mandates as a MUST ("a `web`-named module importing
`manga_tracker.sources.manganato`"). It is *not* dropped as redundant with `web/probe2.py`: `probe2` proves the
widened rule, `probe4` proves the rule the spec names, and a design may not silently narrow a MUST. The two
cost four lines together.

The expected-violations list at :256-260 grows from three entries to **seven**, in `sorted(rglob)` path order:

```
catalogue/probe.py, importer/probe.py, intake/probe.py,
web/probe.py, web/probe2.py, web/probe3.py, web/probe4.py
```

(`web/probe.py` sorts before `web/probe2.py` — `.` is 0x2E, `2` is 0x32.) Note also `VOCABULARY_RULES` (:74):
no new `.py` may contain the words "sitemap" or "shard".

## Interfaces / Contracts

```python
# manga_tracker/intake/contracts.py
@dataclass(frozen=True)
class AddPreview:
    slug: str
    url: str                            # canonical ficha URL, from client.build_manga_url
    title: str
    cover_url: str | None
    # spec.md:10 requires the preview to return the publication status text too.
    # Free: fetch_manga_details already carries it (contracts.py:66), so this is
    # a field passed through, not a second request. Raw source text, never
    # mapped onto mangas.publication_status — that enum is 'ongoing' /
    # 'hiatus_detected' / 'finished' (schema.sql:13-14) and inferring it from a
    # display string is not this change's business.
    publication_status_text: str | None

@dataclass(frozen=True)
class AddResult:
    manga_id: int
    bookmark_id: int
    chapters_found: int     # 0 is legal (D5)
    cover_cached: bool      # False is legal (D6)

class InvalidUrl(Exception): ...
class AlreadyTracked(Exception):
    title: str
    status: str             # raw schema value; web translates

class MangaIntake(Protocol):
    def preview(self, conn, url: str) -> AddPreview: ...
    def confirm(self, conn, *, url: str, title: str, cover_url: str | None,
                status: str, last_chapter_read: float, now: str) -> AddResult: ...
```

```python
# manga_tracker/sources/contracts.py — SourceClient gains the method the concrete already has
def fetch_cover(self, cover_url: str) -> bytes: ...
```

```python
# manga_tracker/storage/repositories.py
MANUAL_ORIGIN = "manual"

def write_manual_add(conn, *, title, site_id, slug, url, chapters, status,
                     last_chapter_read, cover_url, now) -> tuple[int, int]:
    """mangas + manga_sites + bookmark (+ chapter_history) in ONE transaction.
    origin='manual', progress_is_approx=0, status_changed_at=now.
    `chapters` may be empty: latest_chapter_* stay NULL and no history is written.
    detected_via reuses 'seed_backfill' — the CHECK at schema.sql:72 admits no 'panel'.
    last_read_at stays NULL: an initial chapter is progress, not a reading event.
    Returns (manga_id, bookmark_id)."""

def list_tracked_titles(conn) -> list[tuple[str, str]]:
    """(title, status) for every bookmarked manga — duplicate gates 2 and 3."""
```

The bookmark INSERT fires no trigger (`reading_history_capture_progress` is UPDATE-only, schema.sql:95-96),
so an add generates zero reading events, as the proposal's rollback plan assumes.

## Error Taxonomy

Body stays `{"detail": <string>}` (PAN §77). Copy is Spanish and names the next action.

| Case | Detected in | Requests spent | HTTP | `detail` |
|---|---|---|---|---|
| Body malformed, status off-enum, negative chapter | Pydantic | 0 | 422 | FastAPI's list-shaped detail (frontend already falls back on it) |
| URL yields no slug | `InvalidUrl` | 0 | 422 | `La URL no es de una ficha de la fuente. Pega el enlace que contiene /manga/…` |
| Already tracked, non-terminal (gate 1) | `AlreadyTracked` | 0 | **409** | `«{title}» ya está en tu lista, con estado {label}.` |
| Already tracked, **terminal** (`completed`/`dropped`, gates 1-3) | `AlreadyTracked` | 0 or 1 | **409** | `«{title}» ya está en tu lista, con estado {label}. Para retomarlo, cámbiale el estado desde su pestaña «{label}»; no hace falta agregarlo de nuevo.` |
| Slug unknown to the source | `NotFound` | 1 | 404 | `La fuente no tiene ningún manga con ese enlace. Revisa la URL.` |
| Timeout / 5xx / Cloudflare | `Transient` | 1 | 503 | `La fuente no respondió. Espera un momento y vuelve a intentar.` |
| Well-formed response, wrong shape | `Unexpected` | 1 | 502 | `La fuente respondió algo inesperado; probablemente cambió. Revisa los logs.` |
| Zero chapters | — | 2 | **201** | not an error (D5) |
| Cover fetch failed | — | 3 | **201** | not an error (D6) |

No `Retry-After` and no server-side retry: owner decision 4 puts the retry in the owner's hands, and the
transport already spends one retry of its own.

**The 409 is the one body with a sibling key.** `detail` is self-sufficient — it names the title, the state in
Spanish, and for a terminal row the reactivation path (spec.md:34) — because `frontend/src/api/bookmarks.ts:9`
accepts `detail` only when it is a string, so anything hidden in a dict `detail` would lose the whole message
for a curl reader *and* for the panel. On top of that the endpoint returns a `JSONResponse` carrying:

```json
{"detail": "…", "existing": {"title": "…", "status": "dropped", "terminal": true}}
```

`existing` buys the modal one affordance the sentence cannot: a **"Ver en «Abandonado»"** button that closes the
modal and switches the grid tab to that status, so "reactivation is a PATCH" is one click rather than an
instruction to go and find the card. `terminal` is computed server-side from the status so the frontend never
re-derives which two states are terminal — a rule the schema owns, not the UI.

Reactivation itself needs **no new endpoint**: `PATCH /api/bookmarks/{id}` already changes status and already
stamps `status_changed_at` on a real transition (repositories.py:377-379). This design points at it and adds
nothing, exactly as the owner decision says.

## Frontend

The button and the modal live **inside `BookmarkListContainer`**, not in `App.tsx`: confirm must refresh the
grid, and `load(false)` is already there (BookmarkListContainer.tsx:52-53). Lifting the list into `App` would
be churn for nothing.

| File | Action | Contents |
|---|---|---|
| `api/http.ts` | Create | `ApiError` (now carrying optional `existing`), `readDetail`, moved out of `bookmarks.ts` |
| `api/bookmarks.ts` | Modify | imports from `http.ts`, re-exports `ApiError` so existing importers do not churn |
| `api/mangas.ts` | Create | `previewManga(url)`, `addManga(body) -> Bookmark`; Spanish network-failure copy per the existing pattern |
| `domain/types.ts` | Modify | `MangaPreview` (incl. `publication_status_text`), `MangaAdd` request type, `ExistingManga` |
| `components/AddMangaModal.tsx` | Create | Pure: dialog chrome + `<form>` + preview panel + the duplicate affordance. All state via props |
| `containers/AddMangaContainer.tsx` | Create | url/status/chapter state, preview & confirm calls, error message, `existing` |
| `containers/BookmarkListContainer.tsx` | Modify | "Agregar manga" button beside `StatusTabs`; on success `await load(false)`, close, `setActiveStatus(added.status)`; on a 409 with `existing`, jump to that tab |
| `styles.css` | Modify | modal, backdrop, form, preview panel |

Form: URL (required, autofocused), status `<select>` over `BOOKMARK_STATUSES` with `STATUS_LABELS` defaulting
to `reading`, initial chapter (optional, `min=0`, defaults to 0). Confirm is disabled until a preview exists —
the preview *is* the matching proof PAN §95 asks for.

**The preview panel renders three things** (spec.md:10): the matched **title**, the **cover candidate**
(`<img>` straight at `cover_url`, with the same `onError` fallback branch `BookmarkCard.tsx:30` already uses —
the source's hosts 403 a hotlink, so a broken candidate must degrade, not break the modal), and the
**publication status text** verbatim from the source, as muted secondary text. Verbatim because it is source
prose, not a domain enum: translating or mapping it would invent a fact the preview is supposed to *report*.

**Duplicate rejection.** The modal shows the `detail` sentence, and when `existing` is present adds a
`Ver en «{STATUS_LABELS[existing.status]}»` button that closes the modal and switches the grid tab. For a
terminal row that is the whole reactivation path made clickable; the sentence already carries the instruction
for anyone who ignores the button.

**Modal UX decisions.** Plain `<div role="dialog" aria-modal="true">`, not `<dialog>`: `showModal` is unevenly
implemented in jsdom and the suite must stay deterministic. Escape and backdrop click close, unless a request
is in flight. Entrance `opacity 0→1` with `scale(0.96)→1` over 200ms `cubic-bezier(0.23, 1, 0.32, 1)`; exit
140ms — a modal is occasional, so it earns an animation, and `transform-origin` stays `center` because it is
not anchored to its trigger. Never `scale(0)`. Buttons take `transform: scale(0.97)` on `:active`. Under
`prefers-reduced-motion: reduce`, opacity only, no transform. The preview→confirm step change is *not*
animated: it is new data in place, and motion there would read as a second dialog.

## Testing Strategy

Sockets are blocked by `tests/conftest.py`, so every source call is a fake. `tests/web/conftest.py` re-allows
loopback for `TestClient`; new web files inherit it. Databases are real files on disk, never `:memory:`.

| Layer | File | What it must prove |
|---|---|---|
| Architecture | `tests/test_architecture.py` | the two new rules fire; **four** injected violations are reported, incl. the spec-mandated `web → sources.manganato`; the exempt file is not |
| Contract | `tests/web/` (new, ~25 lines) | the Python status-label mirror equals `frontend/src/domain/statusLabels.ts`, parsed as text (D2's drift pin) |
| Unit | `tests/intake/test_pasted_url.py` (new) | happy path writes all four tables; `AddPreview` carries title, cover candidate **and `publication_status_text`**; zero chapters → NULL latest and no history; gates 1-2 refuse with **zero** client calls; gate 3 refuses after one; `AlreadyTracked` carries the raw status for both a terminal and a non-terminal owner; `NotFound`/`Transient`/`Unexpected` propagate untranslated; cover failure leaves the add standing |
| Unit | `tests/storage/` (existing suite) | `write_manual_add`: `origin='manual'`, `progress_is_approx=0`, `status_changed_at` matches `^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$`, `detected_via='seed_backfill'`, **no `reading_history` row**, and a failure mid-transaction leaves zero rows |
| Regression | `tests/discovery/` | **the D5 proof, executable**: a mapping with NULL `latest_chapter_num`/`latest_chapter_at` is picked up by `active_sweep` — in the population, not skipped by the prefilter, recorded, notified, sealed |
| Integration | `tests/web/test_add_manga_api.py` (new) | one case per taxonomy row; the terminal 409 `detail` names the title, the Spanish state **and the reactivation instruction**, and `existing.terminal` is true; the non-terminal 409 names title + state; preview writes nothing and returns `publication_status_text`; a rejected confirm leaves zero rows in all four tables; 201 returns the `BOOKMARK_KEYS` shape |
| Unit (TS) | `api/mangas.test.ts`, `AddMangaModal.test.tsx` | error mapping and `existing` parsing; the preview panel shows title, cover and publication-status text; a failed cover candidate falls back instead of breaking; confirm disabled before preview; Escape/backdrop; busy disables everything |
| Integration (TS) | `AddMangaContainer.test.tsx`, `BookmarkListContainer.test.tsx` (+3) | preview→confirm request bodies; a terminal 409 renders the reactivation sentence and its `Ver en «…»` button switches the tab and closes the modal; after success the list refetches, the modal closes and the tab switches |

## Threat Matrix

| Boundary | Applicability |
|---|---|
| Documentation-like paths | N/A — no file classification or execution; the only file written is an image under `data/covers/` |
| Git repository selection | N/A — no VCS operation |
| Commit state | N/A |
| Push state | N/A |
| PR commands | N/A — no subprocess, no shell, no `gh` |

One boundary the matrix does not cover, recorded as an **accepted risk**: D4 makes the server GET a
client-supplied `cover_url`. `intake` rejects anything that is not `https` with a non-empty host;
`cover_cache.cache_path` already allow-lists the suffix and names the file from an int, so no path is
expressible; the fetch is outside the transaction, so the worst case is one wasted request and a junk file
that costs one request to fix. The panel has no auth by declared decision and is LAN-scoped, where any caller
can already PATCH every bookmark — this is not a new trust boundary. Re-open it if the panel is ever exposed.

A second **accepted risk**, recorded after slice 2 verification: `intake/contracts.py` re-exports the three
failure categories (`NotFound`/`Transient`/`Unexpected`) from `sources.contracts` so that `web` can catch them
without importing `sources`. Today this is a genuine re-export of source-agnostic categories, verified as such.
The channel is structural, though: the AST check inspects direct imports only, so a future re-export of genuinely
source-specific knowledge through `intake.contracts` would pass mechanically. The guard is review discipline plus
this sentence: anything re-exported from `intake.contracts` must be a source-agnostic contract, never a concrete
client symbol.

## Migration / Rollout

No schema migration. Existing columns only (D5 confirms `latest_chapter_num` is already nullable), so no
`schema.sql` + `MIGRATIONS` pair is needed and the `user_version` trap does not apply.

`docs/spec-panel-v1b.md` §16 is corrected in this delivery: fase 3 costs **3 requests per add**, not 1 —
§16 predates the cover decision of §128. Version bump + changelog + open-pendings, same branch as the code.

## Changed-Lines Forecast

| Area | ± lines |
|---|---|
| `sources/contracts.py`, `storage/cover_cache.py`, `discovery/covers.py`, `cli.py` | ~30 |
| `storage/repositories.py` | ~60 |
| `intake/` (new package) | ~195 |
| `web/app.py` (incl. the status-label mirror) | ~105 |
| Backend tests (4 files touched, 3 new) | ~530 |
| Frontend production (7 files, 4 new) | ~460 |
| Frontend tests (2 new, 2 touched) | ~275 |
| `docs/spec-panel-v1b.md` | ~11 |
| **Total** | **≈ 1635 (±20%)** |

`Decision needed before apply: Yes`
`Chained PRs recommended: Yes`
`400-line budget risk: High`

The forecast is roughly **2× the 800-line `single-pr` budget** and 4× the default 400. It exceeds the
proposal's own ~600-800 estimate because this repo's modules run ~40% comment by line and because the owner's
"always do testing" rule puts ~805 lines in tests. Recommended stack, each slice independently revertible with
its own tests green:

| Slice | Scope | ± lines |
|---|---|---|
| 1 | `fetch_cover` on the Protocol, `cover_cache.write_cover`, `write_manual_add`, `list_tracked_titles`, the two `DIRECTIONAL_RULES` entries + four probes, `docs` correction | ~395 |
| 2 | `intake/` package, the two endpoints, the status-label mirror + its parity test, `cli.py` wiring, web + intake tests | ~515 |
| 3 | Frontend: `api/http.ts`, `api/mangas.ts`, modal, container, styles, tests | ~725 |

Slice 2 is where the feature becomes usable by `curl`; slice 3 makes it usable by a browser.

## Open Questions

- [ ] **Delivery**: the cached strategy is `single-pr` at 800 lines and the forecast is ~1560. Confirm the
      three-slice stack above, or accept a `size:exception`. `sdd-tasks` must not plan one PR by default.
- [ ] Package name `intake` — chosen for the sibling shape (`seed` = bulk offline, `importer` = Kitsu,
      `intake` = one pasted URL). Rename now if it should be `library` or Spanish-domain `alta`; renaming after
      apply touches every rule table and probe.
