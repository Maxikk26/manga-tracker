# Tasks: V1a heart phase

> **Size-budget note**: this artifact exceeds the generic 530-word guidance from the `sdd-tasks` skill. Deliberate, disclosed deviation — the change already carries an accepted size exception (`delivery_strategy: exception-ok`, ~880-1500 line forecast, six work units), and the orchestrator's instructions enumerated ~15 mandatory items (AST rules, 9 fixtures, CHECK-constraint traps, D11/D14, unverified-claims checks) that must each land as an explicit task. Compressing further would have dropped required items, mirroring the same disclosed deviation already recorded on `sdd/v1a-heart-phase/spec`.

## Review Workload Forecast

| Field | Value |
|---|---|
| Estimated changed lines | ~880-1500 (per accepted proposal/scope-decision forecast) |
| 400-line budget risk | High |
| Chained PRs recommended | No |
| Suggested split | size-exception single PR; the 6 work-unit commits below double as optional manual slices the user can assemble into separate PRs from commit history |
| Delivery strategy | exception-ok |
| Chain strategy | size-exception |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: size-exception
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | Source client + project scaffolding | PR 1 | `uv run pytest tests/sources/ tests/test_architecture.py -q` | `uv run python -c "from manga_tracker.sources.manganato.client import build_chapter_url; print(build_chapter_url('one-piece', 145))"` (no network) | Delete `manga_tracker/sources/**`, `pyproject.toml`, `uv.lock`, `tests/**` — nothing else depends on it |
| 2 | Schema + connection factory | PR 2 | `uv run pytest tests/storage/ -q` | `uv run python -c "from manga_tracker.storage.db import connect; connect(':memory:')"` (bootstraps schema, no network) | Delete `manga_tracker/storage/**`, `data/.gitkeep` — independent of unit 1's public API |
| 3 | Seed loader + composition root | PR 3 | `uv run pytest tests/seed/ -q` | `uv run python -m manga_tracker seed --file seed-plantilla.csv --dry-run` | Delete `manga_tracker/seed/**`, `cli.py`, `config.py`, `logging_setup.py`, `.env.example`, `seed-plantilla.csv` — needs units 1+2 present but removable without touching them |
| 4 | Discovery core + `feed_check` + `active_sweep` | PR 4 | `uv run pytest tests/discovery/ -q` | `uv run python -m manga_tracker run-job feed_check` (requires configured env + live source — real bring-up command) | Delete `manga_tracker/discovery/**`, `manga_tracker/notifier/contracts.py` — needs units 1+2, independent of unit 5's concrete sender |
| 5 | Telegram digest emitter | PR 5 | `uv run pytest tests/notifier/ -q` | `uv run python -m manga_tracker test-telegram` | Delete `manga_tracker/notifier/telegram.py` — independent of units 1-4 beyond the `DigestSender` contract |
| 6 | Scheduler + Docker | PR 6 | `uv run pytest tests/scheduler/ -q` | `docker compose up` then `uv run python -m manga_tracker run` | Delete `scheduler.py`, `Dockerfile`, `docker-compose.yml` — removes deployment only, no application code touched |

Threat matrix: N/A per design (no routing/shell/subprocess/VCS/PR-automation boundary in this change) — no separate RED-test-per-threat-case is required beyond the tests already listed below.

## Phase 1: Source client + project scaffolding (Unit 1)

*Stands alone: zero DB dependency, testable first against trimmed fixtures.*

- [x] 1.1 Create `pyproject.toml` with direct deps `curl-cffi>=0.13,<0.15` (D11 cap), `beautifulsoup4`, `APScheduler` 3.x; `pytest` dev-only; generate and version `uv.lock`. **Deviation**: pinned `curl-cffi>=0.15` instead — see 1.4.
- [x] 1.2 Verify D11 holds: `uv sync` then `uv pip list` confirms no `rich`/`markdown-it-py`/`mdurl`/`Pygments` entered the closure. Holds for `<0.15`; does not hold for the actually-shipped pin (see 1.4).
- [x] 1.3 Verify Unverified claim #2 (design): pinned `curl-cffi` with `impersonate="chrome"` (targets 131/124) gets a clean 200 from the canonical manganato host. Confirmed live: 200, both named targets present.
- [x] 1.4 Check Unverified claim #3: no open libcurl-impersonate advisory against the pinned version at pin time. **FALSE** — GHSA-qw2m-4pqf-rmpp (SSRF, HIGH, CWE-918) open on 0.13.x/0.14.x, fixed only in 0.15.0. Per D11's own rule an advisory outranks the cap: cap lifted to `>=0.15`.
- [ ] 1.5 Create package skeleton: `manga_tracker/__main__.py`, `cli.py`, `config.py`, `logging_setup.py`, `clock.py` (stubs; composition wiring lands in unit 3). Deferred: only directories + `__init__.py` created this slice (200-line ceiling; these stubs are unit 3's per design's own work-unit ownership).
- [x] 1.6 Create `manga_tracker/sources/contracts.py`: `Response` dataclass, `Transport` Protocol, `FeedItem`, `Chapter`, `MangaDetails`, `SourceClient` Protocol, `NotFound`/`Transient`/`Unexpected`.
- [x] 1.7 Create `manga_tracker/sources/manganato/transport.py`: curl-cffi call normalized into `Response`; confine `curl_cffi` import to this file only.
- [ ] 1.8 Create `manga_tracker/sources/manganato/parsing.py`: SRC §2/§4 selectors; ad filter via `any(c.startswith("js-banner-") for c in el.get("class", []))` (not a CSS `^=` match — that only fires when the banner class is first); confine `bs4` import to this file only.
- [ ] 1.9 Create `manga_tracker/sources/manganato/client.py`: `fetch_latest_feed` (ad-filter-first; zero real items → Unexpected, not empty), `fetch_chapters` (numeric+UTC passthrough; empty array → success per D14), `fetch_manga_details` (fallback-only, never called by detection), `build_chapter_url(slug, num)` (no request; `float(n)` coercion so `80`, `'80.0'`, `145.0`→`chapter-145`, `45.5`→`chapter-45-5` all format correctly), `BASE_URL` export.
- [ ] 1.10 Implement request policy: injected `sleeper`/`rng`, random 5-15s delay between consecutive requests, 30s timeout, exactly one retry **after a 30s wait** on Transient only, never >2 attempts/item/run, organic `Referer` on the JSON call, no retry on NotFound. Partial: delay/timeout/retry-wait/attempt-cap done in `transport.py`; Referer-construction and NotFound-awareness need `client.py` (unit 1 remainder).
- [ ] 1.11 Create `tests/conftest.py`: autouse session fixture patching `socket.socket.connect` to raise (blocks manganato and Telegram alike); injected `Transport`/`sleeper`/`rng` fixtures. Partial: socket-blocking fixture done; injected fixtures wait on client tests (unit 1 remainder).
- [ ] 1.12 Create the 9 trimmed fixtures under `tests/fixtures/`: `feed_page.html` (4 real + 1 `hidden` + 1 `js-banner-*`), `feed_page_ads_only.html`, `feed_page_structure_changed.html`, `feed_item_no_number.html`, `chapters_ok.json` (incl. `45.5`/`chapter-45-5`, `.000000Z`), `chapters_false_success.json`, `chapters_missing_array.json`, `chapters_empty.json`, `manga_details.html`.
- [ ] 1.13 Write `tests/sources/test_parsing.py`: happy path, ad filter, ordering, slug extraction, `data-src` preference, zero-real-items → Unexpected, container renamed → Unexpected, unparseable chapter text dropped + logged (run continues).
- [ ] 1.14 Write `tests/sources/test_client.py`: taxonomy (404/`success:false`→NotFound, missing array→Unexpected, **empty array→success, zero chapters**, timeout/5xx/CF-403→Transient, wrong shape→Unexpected); policy (1 retry after 30s wait, ≤2 attempts, no retry on NotFound, 30s timeout forwarded, `Referer` set, no delay before the isolated feed call).
- [ ] 1.15 Write `tests/sources/test_build_chapter_url.py`: parametrized `80`, `'80.0'`, `145.0`, `45.5`; assert zero requests made.
- [x] 1.16 Create `tests/test_architecture.py` with rule 1 (`sources/**` imports nothing from storage/discovery/notifier/seed) and the `curl_cffi`/`bs4` confinement half of rule 5. Went further: implemented all 5 rules now (see 2.9/3.13/4.12/5.9/6.12) since the directional/confinement checks don't need the target packages' production files to exist.

## Phase 2: Schema + connection factory (Unit 2)

*Stands alone: `ensure_schema` takes no arguments — testable with no client and no `cli.py`.*

- [ ] 2.1 Create `manga_tracker/storage/schema.sql`: 7 tables (`mangas`, `sites`, `manga_sites`, `bookmarks`, `reading_history`, `chapter_history`, `job_runs`) + the single UPDATE-only `reading_history` trigger; all `CREATE ... IF NOT EXISTS`.
- [ ] 2.2 In `schema.sql`, set CHECK constraints: `job_runs.job_name` allows `feed_check`, `active_sweep`, `onhold_sweep` (onhold_sweep out of scope this phase but required now to avoid migrating a populated DB later); `chapter_history.detected_via` allows `feed`, `active_sweep`, `onhold_sweep`, `seed_backfill`.
- [ ] 2.3 In `schema.sql`, add the closed index set: `bookmarks(status)`, `job_runs(job_name, started_at)`, `reading_history(manga_id, read_at)`, `reading_history(read_at)`, UNIQUEs on `sites(name)`, `mangas(kitsu_id)`, `manga_sites(manga_id, site_id)`, `manga_sites(site_id, source_key)`, `bookmarks(manga_id)`, `chapter_history(manga_site_id, chapter_num)`.
- [ ] 2.4 Add `manga_sites.consecutive_failures`: non-nullable, default 0.
- [ ] 2.5 Create `manga_tracker/storage/db.py`: `connect(path)` sets `PRAGMA foreign_keys=ON`, WAL + `busy_timeout` at bootstrap, then calls `ensure_schema(conn)` before returning; `ensure_schema(conn)` runs `schema.sql` standalone (no other args, independently testable); `transaction(conn)` context manager. (`ensure_site` lands in unit 3 with its first caller, per the no-helper-before-caller rule.)
- [ ] 2.6 Create `manga_tracker/storage/repositories.py`: parameterized query helpers for `mangas`/`manga_sites`/`bookmarks`/`chapter_history`/`job_runs` used by seed and discovery — no slug or user value ever interpolated into SQL.
- [ ] 2.7 Create `data/.gitkeep` so the mount point exists before any run.
- [ ] 2.8 Write `tests/storage/test_schema.py` against a real DB in `tmp_path`: FK violation raises (proves the pragma); trigger fires on UPDATE and NOT on INSERT; downward `last_chapter_read` correction kept as honest data; `chapter_history` re-insert on the same `(manga_site_id, chapter_num)` is a silent no-op; every DM index exists.
- [x] 2.9 Extend `tests/test_architecture.py`: add rule 3 (`storage/**` imports nothing from sources/discovery/notifier/seed) and the `sqlite3`-confined-to-`storage/` half of rule 5. Done in unit 1 (see 1.16 note).

## Phase 3: Seed loader + composition root (Unit 3, needs 1+2)

*Stands alone: first executable path; standalone test suite passes without units 4-6.*

- [ ] 3.1 Add `ensure_site(conn, name, base_url)` to `manga_tracker/storage/db.py`: `ON CONFLICT(name) DO UPDATE SET base_url=excluded.base_url, updated_at=?` (not `INSERT OR IGNORE` — must refresh a stale host per SRC §9 playbook).
- [ ] 3.2 Create `manga_tracker/config.py`: `load_config()` reads `os.environ` into frozen dataclasses; collects and reports ALL missing/invalid vars in one failure; `seed` subcommand does not require `TELEGRAM_BOT_TOKEN`.
- [ ] 3.3 Create `manga_tracker/logging_setup.py`: stdlib `logging`, one stdout `StreamHandler`, plain text UTC, `LOG_LEVEL` env; handler-level filter defaulting `job_name`/`run_id` to `-` outside a run.
- [ ] 3.4 Create `manga_tracker/cli.py` (the only composition root): argparse entrypoint wiring `run`, `seed`, `test-telegram`, `run-job {feed_check,active_sweep}`; every invocation opens a connection (`ensure_schema`) and calls `ensure_site(conn, "manganato", client.BASE_URL)`.
- [ ] 3.5 Create `.env.example` documenting every env var `config.py` consumes.
- [ ] 3.6 Create `manga_tracker/seed/loader.py`: validate-all-rows-then-report before any write; blocking errors vs non-blocking warnings (e.g. `reading` with no chapter); slug extracted from the segment after `/manga/` (tolerates www/trailing slash/query/fragment) from either ficha or chapter URL; `last_chapter_read` taken only from its CSV column.
- [ ] 3.7 In `loader.py`, implement per-row load via `storage.repositories`: create/find `mangas` → create `manga_sites` (slug + canonical reconstructed URL) → `fetch_chapters` sets `latest_chapter_num`/url/at + `last_checked_at`, writes `chapter_history` with `detected_via=seed_backfill` → create `bookmarks` (`origin=seed`, `progress_is_approx=0`).
- [ ] 3.8 In `loader.py`, implement D14 for seed: a well-formed empty `chapters` array reports the row and discards it completely (no `mangas`/`manga_sites`/`bookmarks`) — same treatment as a 404 row.
- [ ] 3.9 In `loader.py`, implement re-run safety: reuse existing manga/mapping by slug, update bookmark from file, rely on `chapter_history` UNIQUE for idempotency, never fabricate a `reading_history` event when progress is unchanged.
- [ ] 3.10 Create `seed-plantilla.csv` at the repo root (header + example rows) — exact name required by `.gitignore`'s re-inclusion rule.
- [ ] 3.11 Write `tests/seed/test_loader.py`: every SEED error/warning, slug extraction across ficha/chapter/www/trailing-slash/query/fragment, progress never derived from URL, re-run idempotency, zero-chapter slug reported and discarded whole, not-found/unexpected row fully discarded.
- [ ] 3.12 Write `tests/storage/test_ensure_site.py`: `ensure_site` refreshes `base_url` on conflict.
- [x] 3.13 Extend `tests/test_architecture.py`: add the `seed/**` half of rule 4 (may import `sources.contracts` but never `sources.manganato`). Done in unit 1 (see 1.16 note).
- [ ] 3.14 Verify with `git check-ignore --stdin`: `seed-plantilla.csv` is versioned, `data/seed.csv` and the DB file are ignored.

## Phase 4: Discovery core + `feed_check` + `active_sweep` (Unit 4, needs 1+2)

*Stands alone against a fake `DigestSender` — precedes unit 5.*

- [ ] 4.1 Create `manga_tracker/notifier/contracts.py`: `DigestLine` dataclass, `DigestSender` Protocol (`send_digest(lines) -> bool`, all-or-nothing) — discovery builds lines without importing the concrete sender.
- [ ] 4.2 Create `manga_tracker/discovery/detection.py`: the shared rule, implemented once — (1) seal `last_checked_at` always; (2) bookmark-state gate: `completed`/`dropped` stop here, no history, no update; (3) compare vs `latest_chapter_num` (strictly lower ⇒ log only, never write backward; lower-or-equal ⇒ done); (4) `chapter_history` INSERT OR IGNORE regardless of notification; (5) branch: `on_hold` updates immediately and silently, active accumulates with `latest_chapter_num` untouched until send succeeds.
- [ ] 4.3 Create `manga_tracker/discovery/links.py`: link resolution hierarchy — (1) real URL of the first unread chapter from `chapter_history` if registered, (2) `build_chapter_url` pattern guess, (3) newest chapter's URL.
- [ ] 4.4 Create `manga_tracker/discovery/runs.py`: opens/closes one `job_runs` row per run (`status` ok/error/partial, counts, `error_summary`); overlap guard (no new run of the same `job_name` while one is open; startup only logs a warning, never mutates open rows); opens exactly **one `sqlite3` connection inside the job function, on the worker thread** (never module-level, never `check_same_thread=False`).
- [ ] 4.5 Create `manga_tracker/discovery/feed_check.py`: one `fetch_latest_feed` call, match by (site, `source_key`), `detected_via=feed`, `source_published_at` always null.
- [ ] 4.6 Create `manga_tracker/discovery/active_sweep.py`: daily loop over `reading`/`want_to_read` mappings with a slug (excluding paused mappings), `fetch_chapters` per mapping with the injected delay, compares only the newest via the shared rule, `detected_via=active_sweep`, writes the full response (up to 50) idempotently; implement D14 — an empty `chapters` array is a **success** (seals `last_checked_at`, resets `consecutive_failures`, logs "slug alive, zero chapters", nothing else happens).
- [ ] 4.7 In `active_sweep.py`, implement the dead-slug counter: `consecutive_failures` +1 on NotFound only, reset to 0 on ANY success (including D14's zero-chapter success), mapping at ≥5 skipped with zero request consumed.
- [ ] 4.8 Wire notify-before-update across `feed_check.py`/`active_sweep.py`: accumulate active-manga candidates, call `DigestSender.send_digest`; success advances `latest_chapter_*` for every included mapping and closes `job_runs` ok; failure advances nothing, closes `partial`; zero candidates = no send.
- [ ] 4.9 Write `tests/discovery/test_detection.py` against a fake `DigestSender`: notify-before-update regression (failing send ⇒ no `latest_chapter_num` moved, `job_runs.status='partial'`, `chapter_history` still written); lower number ⇒ logged, never backwards; terminal bookmarks consume zero requests and write no `chapter_history` row.
- [ ] 4.10 Write `tests/discovery/test_active_sweep.py`: `consecutive_failures` +1 on not-found only, reset on any success including zero-chapter, skipped at ≥5.
- [ ] 4.11 Write `tests/discovery/test_runs.py`: overlap guard behavior; one connection per run opened on the worker thread.
- [x] 4.12 Extend `tests/test_architecture.py`: add the `discovery/**` half of rule 4 (may import `sources.contracts`/`notifier.contracts` but never `sources.manganato`/`notifier.telegram`). Done in unit 1 (see 1.16 note).

## Phase 5: Telegram digest emitter (Unit 5, input contract independent — buildable beside 4)

*Stands alone: `notifier/**` has no DB/source knowledge, tested against the `DigestLine` contract only.*

- [ ] 5.1 Verify Unverified claim #5: confirm Telegram's current 4096-char limit and whether `disable_web_page_preview` or `link_preview_options` is the accepted preview-suppression parameter at implementation time.
- [ ] 5.2 Create `manga_tracker/notifier/telegram.py`: plain HTTPS `sendMessage` via `urllib.request`; confine `urllib.request` to this file only; startup token/chat-id validation fails fast before any send.
- [ ] 5.3 In `telegram.py`, implement digest formatting: HTML (not Markdown), one manga per line blank-line separated, alphabetical by title, chapter numbers shown as-is (decimals included), null progress omits "vas por el" and links to newest chapter, overlong titles truncated with ellipsis, `html.escape()` every interpolated field.
- [ ] 5.4 In `telegram.py`, disable link previews on every send (missing from rev 1 and from the `telegram-digest` spec artifact — now restored per design).
- [ ] 5.5 In `telegram.py`, implement all-or-nothing size split: exceeding the char limit splits into multiple messages without cutting a manga's line; success only if ALL parts send.
- [ ] 5.6 In `telegram.py`, implement send retry/rate-limit handling: 429 → wait `retry_after`, retry once; other failure → retry once after a brief wait, then report failure to discovery; never log the request URL or raw response (bot token is in the URL path).
- [ ] 5.7 Add `test-telegram` manual verification-message mode to `cli.py`; must not run automatically.
- [ ] 5.8 Write `tests/notifier/test_telegram.py`: HTML escaping, alphabetical order, blank-line separation, decimals verbatim, null-progress variant, long-title truncation with ellipsis, link previews disabled on every send, split never cuts a manga line, all-or-nothing success, 429 `retry_after` then one retry, no message when zero novelties.
- [x] 5.9 Extend `tests/test_architecture.py`: add rule 2 (`notifier/**` imports nothing from storage/sources/discovery/seed) and the `urllib.request`-confined-to-`notifier/telegram.py` half of rule 5. Done in unit 1 (see 1.16 note).

## Phase 6: Scheduler + Docker (Unit 6, deployment only)

*Stands alone: removes deployment wiring only, no application code touched.*

- [ ] 6.1 Verify Unverified claim #4: read `EVENT_JOB_ERROR`/`EVENT_JOB_MISSED`/max-instances event constant names off the installed `apscheduler.events`.
- [ ] 6.2 Create `manga_tracker/scheduler.py`: `BlockingScheduler`, in-memory jobstore, default executor explicitly `ThreadPoolExecutor(max_workers=1)`; confine `apscheduler` import to this file only.
- [ ] 6.3 Register `feed_check` (`IntervalTrigger(hours=1)`) and `active_sweep` (`CronTrigger(hour, minute)` in local tz, `ACTIVE_SWEEP_HOUR=3` default); both `max_instances=1`; misfire grace 300s (feed) / 3600s (sweep); no run at process start.
- [ ] 6.4 Wrap each job function so an unhandled exception is caught, closes `job_runs` as `error` with `error_summary`, `logger.exception`; add a scheduler-level error listener as backstop.
- [ ] 6.5 Add `run` and `run-job {feed_check,active_sweep}` subcommands to `cli.py` invoking `scheduler.py`.
- [ ] 6.6 Write `tests/scheduler/test_registration.py`: asserts trigger types, `max_instances`, misfire values, and `max_workers=1` explicitly present — without starting the scheduler.
- [ ] 6.7 Create `Dockerfile`: `python:3.12-slim-bookworm`, multi-stage (uv-pinned build → runtime copies `/app/.venv`), `uv sync --frozen --no-dev`, OS `tzdata`, non-root fixed UID, `PYTHONUNBUFFERED=1`, no HEALTHCHECK.
- [ ] 6.8 At first image build, verify `cffi` resolves to a prebuilt wheel, not an sdist (inspect the build log / `pip show cffi` inside the image).
- [ ] 6.9 Verify Unverified claim #1: `docker run --rm python:3.12-slim-bookworm python -c "import zoneinfo; zoneinfo.ZoneInfo('America/Caracas')"` confirms the tz database is present once the `tzdata` OS package is installed.
- [ ] 6.10 Create `docker-compose.yml`: mounts `data/` as a volume, log-driver rotation configured, deploy note documenting the post-restart `run-job active_sweep` mitigation (~47h worst-case latency after an off-window restart).
- [ ] 6.11 Document the non-root UID's one-time `chown` of `./data` (SQLite needs directory write permission in every journal mode, not just WAL).
- [x] 6.12 Extend `tests/test_architecture.py`: add the `apscheduler`-confined-to-`scheduler.py` half of rule 5 — all 5 AST rules now complete and enforced. Done in unit 1 (see 1.16 note).
- [ ] 6.13 End-to-end bring-up per design rollout: `seed` → `test-telegram` → `run-job feed_check` → `run-job active_sweep` → `run`; confirms OP success criteria 1-3.
