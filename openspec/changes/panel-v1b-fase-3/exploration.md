# Exploration — panel-v1b-fase-3 (add-manga form)

Change: `panel-v1b-fase-3` · Explored: 2026-08-19 · Branch: `feat/add-manga-form` (from main @ bafefed)

Goal: implement fase 3 of the V1b web panel — add a manga by pasting its manganato URL, with a preview shown before anything is written.

## 1. Spec — fase 3

**`docs/spec-panel-v1b.md`** (v1.1, 2026-08-18). Fase 3 is not one section; it is spread across five:

- **spec-panel-v1b.md:85** — the endpoint row: `POST /api/mangas`, fase 3, "Alta: URL de manganato + estado + capítulo inicial. Valida el slug vía `catalogue`; crea manga, `manga_site` y bookmark con `origin='manual'`".
- **spec-panel-v1b.md:86** — `DELETE /api/bookmarks/{id}` **must not exist**. Baja = `status='dropped'`; deletion would destroy `reading_history`.
- **spec-panel-v1b.md:95** — screen 3: a form with URL, initial status, chapter. "El resultado del matching se muestra **antes de confirmar**" → the paste-URL→preview→confirm flow is spec'd only at that level of detail.
- **spec-panel-v1b.md:34-37** — the boundary, extended: `web` must not reach the source even indirectly; the add operation validates the slug **through `catalogue`/`importer`**, and that layer touches the client. "El panel pide 'agrega esto', no 'descarga esto'." Explicitly requires adding the rule to `DIRECTIONAL_RULES` in `tests/test_architecture.py` and **proving it by injecting a violation**.
- **spec-panel-v1b.md:128** — the add operation already visits the ficha to validate, so **the same operation caches the cover** while it's there. No periodic job.
- **spec-panel-v1b.md:144** — done criterion: "Un manga agregado desde el panel queda con mapeo válido y entra al barrido diario siguiente sin intervención."
- **spec-panel-v1b.md:16** — cost: fase 3 = **1 request per add**.
- **spec-panel-v1b.md:177** — the `status_changed_at` follow-up, verbatim: the add must stamp it at bookmark creation, because a new row does know the date of its initial status.

**Pinned dependencies** (spec-panel-v1b.md:3): `one-pager-v1a.md` v1.14, `spec-modelo-de-datos.md` v1.9, `decision-arquitectura-v1b.md` v1.2. Error format is fixed at **spec-panel-v1b.md:77**: `{"detail": ...}` (FastAPI's). No error taxonomy for the add is specified — that is an open design point.

**Other docs touching the add flow:**

- **docs/spec-modelo-de-datos.md:291** — same `status_changed_at` follow-up, stated as data-model law.
- **docs/spec-modelo-de-datos.md:140** — `bookmarks.origin` CHECK is `seed | kitsu_import | manual`; `origin` is "de dónde nació este bookmark", and `manual` is the value the Kitsu importer must never overwrite.
- **docs/spec-modelo-de-datos.md:139** — `progress_is_approx`: hand-typed progress always writes 0.
- **docs/spec-seed-manual.md** is the closest existing spec for the *same flow* offline (paste URL → validate slug → fetch chapters → write) including its full validation list; worth mining for the error cases fase 3 needs.
- **docs/decision-arquitectura-v1b.md:17,32** — only fixes `web → storage`; it does not describe the add.
- **openspec/**: `openspec/changes/panel-v1b-fase-1/` contains only `verify-report.md`; `openspec/specs/` is empty. No fase-3 SDD change existed before this one.

## 2. Client contract — `sources/manganato/`

Module-level free functions plus a class wrapping them; the class binds two as staticmethods (client.py:60-61).

- **`extract_slug(url: str) -> str | None`** — `manga_tracker/sources/manganato/client.py:43`. Pure, no request. Returns None when the path has no `manga` segment or nothing after it. Tolerates `www`, trailing slash, query, fragment; ignores any segment after the slug (a chapter URL yields the slug). **Raises nothing.**
- **`ManganatoClient.fetch_manga_details(slug: str) -> MangaDetails`** — client.py:72. One GET to `{BASE_URL}/manga/{slug}`. Raises `NotFound` on 404 (client.py:76). Parsing failures come out of `parse_manga_details`. `MangaDetails` = `sources/contracts.py:58-67`: `title: str`, `cover_url: str | None`, `publication_status_text: str | None`, `last_updated_text: str | None` (frozen dataclass; **no slug/url on it**).
- **`ManganatoClient.fetch_chapters(slug: str, *, limit: int = 50) -> list[Chapter]`** — client.py:105. One GET to `{BASE_URL}/api/manga/{slug}/chapters` with an organic Referer. Failure categories: **`NotFound`** on HTTP 404 (client.py:116) *and* on `success: false` (client.py:124); **`Unexpected`** on non-JSON body (client.py:121) and on a well-formed payload missing `data.chapters` (client.py:128). Returns newest-first. `Chapter` = contracts.py:49-55: `chapter_num: float`, `url: str`, `published_at: str | None` (raw UTC ISO-8601, never reparsed).
- **`Transient`** (contracts.py:74) is raised by the **transport**, not these methods — timeout / connection error / 5xx / Cloudflare after its retry. The three categories are `NotFound` / `Transient` / `Unexpected` at contracts.py:70-79.
- Also relevant: **`build_manga_url(slug)`** client.py:38 (canonical ficha URL — callers must ask for it, never assemble it), **`fetch_cover(cover_url) -> bytes`** client.py:79 (the `Referer` knowledge; needed for spec-panel-v1b.md:128), **`build_chapter_url`** client.py:25.
- The Protocol every consumer types against: **`SourceClient`** at `manga_tracker/sources/contracts.py:82-113` — it includes `build_manga_url` and `extract_slug` deliberately, because a URL shape is source knowledge the AST test cannot police.

## 3. Catalogue / importer boundary

**`manga_tracker/catalogue/`** = the external metadata catalogue only. `contracts.py` (Response/Transport/`CatalogueEntry`/`CatalogueTransient`/`CatalogueUnexpected`/`CatalogueClient` protocol with a single batch `resolve()`), `kitsu.py` (`KitsuCatalogue.resolve(external_ids)`, kitsu.py:79), `transport.py`. **It knows nothing about manganato slugs** — it cannot validate a URL. Note the naming trap: spec-panel-v1b.md:85 says "valida el slug vía `catalogue`", but slug validation is `sources`+`importer` work; `catalogue` is Kitsu.

**`manga_tracker/importer/`** = contract-only Kitsu import: `export.py` (XML reader), `matching.py` (`normalize`, `slug_variants`, `find_slug(title_candidates, known_slugs)`, `is_suspect`), `reconcile.py` (`reconcile(*, find_by_kitsu_id, find_by_slug, find_by_title)`), `pending.py` (`write_pending`), `run.py`.

**There is no existing "add one manga by URL" function anywhere in catalogue/ or importer/.** The two functions that create manga + manga_site + bookmark are:

1. **`manga_tracker/importer/run.py:157` `_write_entry(conn, entry, catalogue_entry, *, slug, url, chapters, site_id)`** — all four tables in one `db.transaction` (run.py:167). Calls `repo.write_manga_from_catalogue` (run.py:193), `repo.write_source_mapping` (run.py:210), `repo.write_kitsu_bookmark` (run.py:214). Bookmark **`origin='kitsu_import'`** (`IMPORT_ORIGIN`, repositories.py:21), `progress_is_approx=1`, `detected_via='seed_backfill'`; refuses to touch a bookmark whose origin isn't its own (repositories.py:213). Public entry point is `run_import(export_path, conn, catalogue: CatalogueClient, client: SourceClient, *, site_id) -> ImportReport` (run.py:61). **Does not set `status_changed_at`.**
2. **`manga_tracker/seed/loader.py:196` `_load_row(conn, row, client: SourceClient, *, site_id) -> bool`** — the closest analogue to fase 3 and the model to copy: `client.extract_slug(row["url"])` → `client.fetch_chapters(slug)` → discard on `(NotFound, Unexpected)` (loader.py:200) or **zero chapters** (loader.py:203) → `repo.write_seed_backfill(conn, existing, title, site_id, slug, client.build_manga_url(slug), chapters, status, last_read, now)`. Public entry: `load_seed(csv_path, conn, client, *, site_id, dry_run=False) -> bool` (loader.py:160). Bookmark **`origin='seed'`** hardcoded in SQL, `progress_is_approx=0`, `detected_via='seed_backfill'`, and it **commits for itself** (repositories.py:231-271). **Does not set `status_changed_at`.**
   - Reusable validation helpers live here: `_validate_row` (loader.py:45), `_slug_owner_error` (loader.py:76, uses `repo.find_slug_owner`), duplicate-slug detection (loader.py:122).

**Consequence for fase 3:** a **new** writer is needed — no existing repository function writes `origin='manual'` for bookmarks, and none stamps `status_changed_at` at INSERT. `seed` is a top-level package with the exact directional shape web needs (`test_architecture.py:16`: `seed: {sources.manganato, notifier.telegram}`), and `importer` (`test_architecture.py:24`) may import `storage` and `sources.contracts` but never `sources.manganato`.

Relevant repository primitives already available: `find_manga_site_by_slug` (repositories.py:44), `find_slug_owner` (repositories.py:51), `find_manga_site_for_manga`, `write_manga_from_catalogue` (repositories.py:~110), `write_source_mapping` (repositories.py:156), `CHAPTER_HISTORY_LIMIT=50` (repositories.py:41).

## 4. Directional test

**`tests/test_architecture.py`**. Mechanism: **AST import parsing, not runtime import**. `_imports(path, pkg_root)` (test_architecture.py:80) walks `ast.Import`/`ast.ImportFrom`, resolving relative imports against the file's own package so `from ..sources.manganato import x` cannot evade a rule. `_internal()` (test_architecture.py:108) strips the `manga_tracker.` prefix; `_matches()` (test_architecture.py:104) does exact-or-dotted-prefix matching. `_directional_violations(pkg_root)` (test_architecture.py:132) keys the rule table on the **first path segment** of each file.

Rule for the panel — **`test_architecture.py:27`**:

```python
"web": {"sources.manganato", "notifier.telegram"},
```

**Forbidden today:** `manga_tracker.sources.manganato*`, `manga_tracker.notifier.telegram*`. **Allowed today:** `sources.contracts`, `storage`, `catalogue`, `importer`, `seed`, `discovery` — so the fase-3 rule the spec demands (spec-panel-v1b.md:37) is genuinely missing and must be added, plus a probe.

Four tests enforce it: `test_directional_boundaries` (:181), `test_directional_rules_actually_fire` (:199, guards against a vacuously-passing table), **`test_boundary_check_flags_an_injected_violation`** (:214, builds a throwaway manga_tracker-named tree of deliberate violations under tmp_path — the web probe is at **:238**, `web/probe.py` importing `notifier.telegram`, and asserts the exact violation list at :256-260), and `test_only_the_composition_root_wires_layers_together` (:186). Also `test_source_vocabulary_stays_inside_its_own_client` (:273) — `VOCABULARY_RULES` (:74) bans the words "sitemap"/"shard" outside `sources/manganato/`, a **string**-level check that will scan any new web/importer file.

Composition root: `COMPOSITION_ROOT = {"cli.py", "__main__.py"}` (:48), `CONCRETE_IMPLEMENTATIONS` (:59). `_composition_root_violations` only globs **top-level** `*.py` (:167).

## 5. Web / API layer

**Single-file app, no routers.** `manga_tracker/web/app.py:85` `create_app(db_path: str, frontend_dist: Path | None = None) -> FastAPI` — endpoints registered as closures inside the factory, statics mounted last (`_SPAStaticFiles` at :67, mount at :148, so `/api` wins). Wired from **`manga_tracker/cli.py:282` `_cmd_panel`** → `uvicorn.run(create_app(config.db_path), host="0.0.0.0", port=config.panel_port)` (cli.py:287). **This is the injection point for fase 3**: `create_app` will need a `SourceClient` parameter, because `web` may not name `ManganatoClient` (cli.py:39 already imports it for other commands).

**Patterns to follow:**

- Connection per request: `connect(db_path)` in a `try/finally: conn.close()` (app.py:94-98, :103-116).
- Enum from storage so the two can't drift: `BookmarkStatus = Enum(..., BOOKMARK_STATUSES, type=str)` (app.py:40) → FastAPI answers **422** for anything off-enum, in query params and bodies alike.
- Request model: `BookmarkPatch` (app.py:43) — `ConfigDict(extra="forbid")`, `Field(ge=0)`, and a `@model_validator(mode="after")` using `model_fields_set` to distinguish absent from null (app.py:56-64).
- Timestamp helper `_utc_now()` (app.py:81) — `%Y-%m-%dT%H:%M:%SZ`, the one format every writer emits (duplicated at cli.py:158).
- Response = the repository dict, re-read after the write: `return get_panel_bookmark(conn, bookmark_id)` (app.py:114). No response models declared.
- 404 via `HTTPException(status_code=404, detail=...)` (app.py:113, :136).
- Cover serving + cache headers at app.py:118-146 (relevant to spec-panel-v1b.md:128).

**The write endpoint's storage side:** `update_panel_bookmark(conn, bookmark_id, *, last_chapter_read=UNSET, status=UNSET, now) -> bool` — **`manga_tracker/storage/repositories.py:335`**. Wraps everything in `transaction(conn)` (:358), builds the assignment list dynamically (:367-379), stamps `status_changed_at` **only on a real transition** (:377-379), mirrors the trigger's WHEN clause in Python (`trigger_fired`, :384) and corrects the captured `reading_history` row to `origin='panel'` using a pre-UPDATE `MAX(id)` ceiling (:389-402) — never `last_insert_rowid()`. `UNSET` sentinel at :32.

**Frontend (`frontend/src/`), React 19 + Vite:**

- API client: **`frontend/src/api/bookmarks.ts`** — `ApiError` class (:4), `readDetail()` pulls FastAPI's `detail` (:6), `fetchBookmarks()` (:15), `patchBookmark(id, patch)` returning `void` (:31). Spanish user-facing messages; network failure and non-`ok` are distinguished.
- Types: **`frontend/src/domain/types.ts`** — `BOOKMARK_STATUSES` const tuple (:1), `Bookmark` interface mirroring the wire dict, `BookmarkPatch` as a **union** of single-field objects (:31, "sent one at a time").
- Container: **`frontend/src/containers/BookmarkListContainer.tsx`** — owns fetch/filter/PATCH. `load(initial)` callback (:23) with a distinct message for "save succeeded, refresh failed" (:34-38). **Refresh pattern after a write: `await patchBookmark(...)` then `await load(false)` — full refetch, server stays the source of truth for derived fields** (:52-53, comment at :10-15). `savingIds: ReadonlySet<number>` for per-row disable (:20, :50, :61-65). Client-side filter + `sortBookmarksForTab` (:89-96), tab counts memoized (:81).
- Components: `App.tsx` (bare shell, `<main className="app">` + header + container — **where an "add manga" button/route would go**), `components/StatusTabs.tsx` (buttons over `BOOKMARK_STATUSES`), `components/BookmarkGrid.tsx` (layout only, pure), `components/BookmarkCard.tsx`, `components/InlineNumberEdit.tsx` (click-to-edit; Enter/blur commits, Escape cancels, no-op on unchanged value; focus-before-select at :26-28). Single stylesheet `frontend/src/styles.css`.
- **There is no modal, no dialog, and no `<form>` element anywhere in `frontend/src/`** (grep-verified). Fase 3's form/preview is greenfield. There is also no router — the add screen needs either a modal or a hand-rolled view switch (`_SPAStaticFiles` already supports client-side routes surviving refresh, app.py:67-78).

## 6. Test patterns

**Backend.** `pyproject.toml`: `pytest>=8`, `httpx>=0.27` (dev-only, for `TestClient`), `addopts = "--import-mode=importlib"` (required — two suites share basenames).

- `tests/conftest.py` — autouse fixture monkeypatching `socket.socket.connect` to raise; **no test may touch a real socket**, fakes are injected.
- `tests/web/conftest.py:15` — **overrides that fixture by name** to allow loopback only (`127.0.0.1`/`::1`/`localhost`), because on Windows asyncio's proactor loop builds its self-pipe via `socketpair()`. Any new web test file inherits this.
- `tests/web/test_panel_api.py` — the model to copy. **Not in-memory: a real SQLite file** at `tmp_path / "panel.db"` (`db_path` fixture :34), `client` fixture passing `frontend_dist=tmp_path / "no-dist"` so the real build can't leak in (:38). Helpers `_site(conn)` (:44) and `_bookmark(conn, site_id, title, *, ...)` returning `(manga_id, bookmark_id)` (:52) insert raw SQL directly. `BOOKMARK_KEYS` set (:22) pins the wire shape. Assertions read both the JSON body **and** the DB row (e.g. :193-199, :223-236). Status-code assertions inline: `assert client.patch(...).status_code == 200`.
- **The user_version / migration caveat:** `tests/storage/test_migrations.py:1` — "Schema migrations, tested against databases on **DISK** rather than `:memory:`". Reason (commit 5bb2cf3): `CREATE TABLE IF NOT EXISTS` in `schema.sql` does **nothing** to an existing table — every column needs **both** a `schema.sql` declaration *and* a numbered `MIGRATIONS` entry. `manga_tracker/storage/db.py:15` `SCHEMA_VERSION = 2`; `_migrate` (db.py:75) loops `range(user_version + 1, SCHEMA_VERSION + 1)` committing `user_version` after each step; `ensure_schema` sets it directly only when the DB was **born empty** (db.py:107-113). `connect(path)` (db.py:116) bootstraps the schema, which is why the web tests need no migration setup. Tests fabricate pre-migration states with `PRAGMA user_version = 0/1` (test_migrations.py:38, :153, :220). **Fase 3 needs no migration** — it writes existing columns only.

**Frontend.** Vitest + jsdom + React Testing Library + `user-event`. Config in `frontend/vite.config.ts`: `environment: "jsdom"`, `globals: true` (for RTL auto-cleanup), `setupFiles: ["src/test/setup.ts"]`, and **`env: { TZ: "America/Caracas" }`** pinned so date assertions aren't machine-dependent. `src/test/setup.ts` registers jest-dom matchers. `src/test/fixtures.ts` — `makeBookmark(overrides)`, wire-shaped, with a comment explaining why the timestamp format must match the backend exactly.

**The 53 tests** (17+8+3+9+16): `components/BookmarkCard.test.tsx` (17), `components/InlineNumberEdit.test.tsx` (8), `containers/BookmarkListContainer.test.tsx` (3), `domain/formatDate.test.ts` (9), `domain/sortBookmarks.test.ts` (16). The container test stubs `fetch` with `vi.fn()` returning real `Response` objects built from JSON (`jsonResponse`/`stubFetch`, BookmarkListContainer.test.tsx:32-40) and uses a realistic 3-row payload including a nulls-everywhere row. Scripts: `npm test` = `vitest run`; `npm run build` = `tsc --noEmit && vite build`.

## 7. `status_changed_at` — where it is stamped

**Application code only. There is no trigger for it.**

- Column: `manga_tracker/storage/schema.sql:53` (`status_changed_at TEXT`, nullable, no default), plus migration 2 at `manga_tracker/storage/db.py:51-66`.
- The **only** write in the entire codebase: **`manga_tracker/storage/repositories.py:377-379`**, inside `update_panel_bookmark`, guarded by `if status != current_status`. Grep-confirmed: no other production line assigns it.
- The schema's single trigger (`reading_history_capture_progress`, schema.sql:99) writes `reading_history` only, with `origin` defaulting to `'manual'` — it never touches `status_changed_at`.
- Both existing INSERT paths leave it NULL: `write_seed_backfill` (repositories.py:262) and `write_kitsu_bookmark` (repositories.py:206). Migration 2 deliberately does **not** backfill (db.py:54-62).
- Commit **5bb2cf3** closes with: *"Follow-up left open: bookmarks created from the add-manga form (fase 3) know their status date at creation and should stamp it."*

**So fase 3's new writer must set `status_changed_at = now` in its bookmark INSERT** — format `%Y-%m-%dT%H:%M:%SZ` (fixed-width UTC; the frontend tab ordering compares these as **strings**, sortBookmarks.ts:19, and a SQLite-style space instead of `T` breaks the sort silently — spec-panel-v1b.md:69). And `origin='manual'`, `progress_is_approx=0`.
