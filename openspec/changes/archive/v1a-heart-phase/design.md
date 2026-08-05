# Design: V1a heart phase (`v1a-heart-phase`)

Implements `openspec/changes/v1a-heart-phase/proposal.md`.

**Revision 2** — corrected after fresh-context validation. Three factual claims in revision 1 were false (a musl-wheel disqualification, a dependency count, and three APScheduler mechanics). All ten decisions survived; the reasons behind D5 and D9 did not. Everything this document asserts about a third-party runtime is now either attributed to a verification someone performed, or listed under *Unverified claims* with the command that settles it.

**Doc pins** — OP = `docs/one-pager-v1a.md` v1.5 · DM = `spec-modelo-de-datos.md` v1.6 · CD = `spec-cliente-fuente-descubrimiento.md` v1.2 · BOT = `spec-bot-telegram.md` v1.1 · SEED = `spec-seed-manual.md` v2.1 · SRC = `manganato-fuente-actual.md` v1.2.

The detection rule is **not restated here** — it is CD Parte B §"La regla de detección" plus `CLAUDE.md` §"Rules that are easy to get wrong". This document decides only *how it is housed*.

## Technical approach

One installable package, one composition root, **three direct dependencies (9 installed packages)**. Every open item resolves toward the stdlib unless a dependency buys something the stdlib cannot. The client/discovery boundary is enforced by an executable import-direction test, not a comment.

The design premise is the failure mode named in `docs/referencia-repo-viejo.md`: at <20 active titles and ~44 requests/day, every added moving part is a liability. Each rejection below names the antipattern it avoids.

### Dependency budget

**3 direct dependencies · 13 installed packages.** D11 originally capped `curl-cffi <0.15` to hold this at 9; that cap was **reversed by a security advisory** — see D11.

| Direct dep | Bought | Pulls in | Rejected instead |
|---|---|---|---|
| `curl-cffi >=0.15` | Chrome impersonation (decided platform, OP) | `cffi` (**the only C extension in the image**), `pycparser`, `certifi` | Playwright — forbidden by OP |
| `beautifulsoup4` | 1:1 mapping from SRC §2/§4 CSS selectors to code | `soupsieve`, `typing_extensions` | `lxml`+`cssselect`, `selectolax`, `parsel` — a *second* compiled extension for speed we never need |
| `APScheduler` (3.x) | In-process scheduling (decided platform, OP) | `tzlocal` | host cron — forbidden by OP; APScheduler 4.x — still pre-stable |
| OS pkg `tzdata` | `zoneinfo` data — a functional requirement (D9), not polish | — | shipping without it and discovering at the first digest |

Full closure with the cap: `curl_cffi`, `cffi`, `pycparser`, `certifi`, `beautifulsoup4`, `soupsieve`, `typing_extensions`, `APScheduler`, `tzlocal`. Dev deps: `pytest` only.

**Not introduced**: `requests`/`httpx`, `python-telegram-bot`/`aiogram`, SQLAlchemy/Alembic, `python-dotenv`, `click`/`typer`, `structlog`, `pydantic-settings`. No linter or formatter is chosen here — no doc decided one; ask when it matters.

## Architecture decisions

D1–D10 match the ten open items handed to this phase. D11 and D14 were raised by validation.

| # | Decision | Rejected | Rationale |
|---|---|---|---|
| **D1** | `beautifulsoup4` on the stdlib `html.parser` backend | `lxml`+`cssselect`, `selectolax`, `parsel`, hand-rolled `html.parser` | Two documented selector sets over ~155 KB once an hour. Pure Python, so it adds no compiled extension beyond the `cffi` curl-cffi already requires. `soupsieve` (bundled) consumes SRC's selectors verbatim — **verified: all eight selectors from SRC §2/§4 parse and match unchanged** — keeping the SRC §9 domain-change playbook a copy-paste job. Hand-rolling a selector layer is more code and more bugs than the dep it avoids. |
| **D2** | Plain HTTPS `sendMessage` via stdlib `urllib.request` | `python-telegram-bot`, `aiogram`, `requests`, reusing `curl_cffi` | BOT §"Qué NO hace el bot en V1a": emit-only, zero incoming updates. A bot framework ships an async runtime and update-polling machinery for one POST per run — the `Parallelism: 10` antipattern in a new costume. `requests` = a dependency for one POST. `curl_cffi` is the *source layer's* anti-bot transport; borrowing it couples the notifier to source-layer choices and buys nothing (Telegram has no Cloudflare). **OP item 8 calls the bot "(polling)"; the bot spec contradicts it — see doc defect 1.** |
| **D3** | Raw stdlib `sqlite3` + one connection factory + hand-written SQL in thin repository modules | SQLAlchemy Core / ORM, SQLModel, peewee | DM: schema closed, no migrations, ~7 fixed query shapes (DM §"Consultas operativas clave"), `updated_at` explicitly the data-layer's job. An ORM's payoff is model churn, which does not exist here; its cost is a second schema definition that can drift from `schema.sql`. Decisive: V1a edits progress by hand in DB Browser and the `reading_history` trigger fires DB-side — no Python-side session can see either. |
| **D4** | Two separate bootstrap steps: `ensure_schema(conn)` runs `storage/schema.sql` (DDL only, no external input) from the connection factory on every open; `ensure_site(conn, name, base_url)` upserts the single `sites` row and is called only by `cli.py` | DDL as Python strings, per-repository `CREATE TABLE`, Alembic/yoyo, bootstrap only in the seed loader, bootstrap only at scheduler start, **bootstrap wholly in `cli.py`** | One SQL file is diffable against DM in one read — that *is* the review activity. Splitting the two steps is what makes the factory placement compose: `ensure_schema` takes no arguments, so `repositories.py` and unit 2's tests (which land before `cli.py` exists) can open a DB without storage ever importing the client. Idempotent-on-open removes ordering entirely: whichever entrypoint runs first on a fresh volume creates the DB, so the seed loader stays "invocable a mano, fuera del scheduler" (SEED) **and** the scheduler boots on a wiped volume with no hand-run step. *Bootstrap wholly in `cli.py`* was the closest rival and satisfies the ordering argument equally; it lost because a path that forgets `ensure_schema` fails at first query rather than never existing, and unit 2 must be testable before `cli.py` exists. A migration framework holding one migration is the enterprise version of `executescript`. |
| **D5** | `BlockingScheduler`, in-memory jobstore, default executor **explicitly** `ThreadPoolExecutor(max_workers=1)`; `feed_check` = `IntervalTrigger(hours=1)`, `active_sweep` = `CronTrigger(hour=H, minute=M)` in the configured local tz; both `max_instances=1`; misfire grace 300 s (feed) / 3600 s (sweep); no run at process start | `BackgroundScheduler`+`while True`, SQLAlchemy jobstore, cron trigger for the feed, a DB-based overlap guard, run-on-start | **`max_workers=1` is not a default and must be written down** — APScheduler 3.x's default executor is `ThreadPoolExecutor(max_workers=10)`, so zero concurrency is a configuration fact only because the config says so. With one worker, an hourly `feed_check` firing mid-sweep cannot open a second connection to manganato. `max_instances=1` is exactly CD §"Solapamiento" (skip + log). Interval vs cron follows the specs' own words: the feed has a measured *interval*, the sweep a wall-clock *appointment*. Missed-run behaviour: see *Scheduler mechanics*. No run-on-start: no document asks for one, `run-job` covers bring-up, and a crash-loop would otherwise fire ~20 requests per restart. |
| **D6** | One entrypoint `python -m manga_tracker <cmd>` on stdlib `argparse` subparsers: `run`, `seed`, `test-telegram`, `run-job {feed_check,active_sweep}` | separate scripts, Makefile targets, `click`/`typer` | One entrypoint means one place where env validation, logging setup and DB bootstrap happen; three scripts means three copies of that wiring and a path that can silently skip it — the structural ancestor of the commented-out cron. `argparse` covers 4 subcommands with a handful of flags; a CLI framework here is a dependency with no payoff. `run-job` is the operational replacement for run-on-start (you cannot wait an hour to test a feed check). |
| **D7** | `config.py` reads `os.environ` into frozen dataclasses via one `load_config()`; **no** dotenv library; versioned `.env.example`; each subcommand validates only the config it needs | `python-dotenv`, `pydantic-settings`, one global config validated wholesale | Docker Compose reads `env_file:` natively and `uv run --env-file .env` covers local dev — dotenv would be a dependency for a job two existing tools already do. `.gitignore` already re-includes `.env.example`, so the template is expected. Validation collects *all* missing/invalid vars and fails once with the full list (BOT §"Configuración y token": fail immediately with a clear log message). Per-subcommand scoping is deliberate: `seed` never sends a message, so demanding `TELEGRAM_BOT_TOKEN` to load a CSV would over-reach a spec that is about the scheduler process. |
| **D8** | stdlib `logging`, one `StreamHandler` to **stdout**, plain text, UTC timestamps, level from `LOG_LEVEL`; correlation via a per-run `logging.LoggerAdapter` passed down the call chain; the source client takes its logger as an argument | `structlog`/JSON, a `contextvars`+`Filter` auto-stamp, a log file | The consumer is a human running `docker logs` on a mini-PC; there is no aggregator to parse JSON, and DM already assigns the structured role to `job_runs` (SQL). Passing the adapter makes "this runs inside a job run" visible in signatures instead of ambient; a `contextvars` filter loses correlation in any helper that logs from another context. Injecting the logger lets the client log unexpected-response fragments (CD taxonomy) without knowing what `job_runs` is. UTC in logs so log lines and DB timestamps line up during the DM diagnosis flow. |
| **D9** | `python:3.12-slim-bookworm`, multi-stage (uv-pinned build stage → runtime copies `/app/.venv`), `uv sync --frozen --no-dev`, OS `tzdata`, non-root fixed UID, `PYTHONUNBUFFERED=1`, no `HEALTHCHECK` | Alpine/musl, single-stage, `latest` uv, root user, HTTP healthcheck | Glibc slim is the **lower-risk default, not a compatibility requirement**: it is the base CPython's own images use, so it is the most-tested surface for a manylinux wheel set, and `cffi` — the one C extension here — is what any wheel/sdist question is actually about. **Alpine is not disqualified**: curl-cffi 0.15.0 publishes `musllinux_1_2` wheels for x86_64 and aarch64, so Alpine would install a prebuilt wheel too. It is simply the less-travelled option with no upside for this deployment. 3.12 over 3.13/3.14: nothing in the code needs a newer feature and this runs unattended for years, where the widest-tested interpreter beats the newest. `--no-dev` honours OP ("pytest no viaja al contenedor"). No healthcheck: there is no port to probe and the weekly heartbeat is the designed liveness signal (phase 2). |
| **D10** | 9 trimmed fixtures in `tests/fixtures/` + parametrized cases, all behind an injected transport; an autouse session fixture blocks real sockets | committing `samples/`, `responses`/`vcrpy`/`requests-mock` | `samples/` is gitignored (~155 KB per feed page, all re-downloadable). Trimmed fixtures keep the failure message readable and the diff reviewable. A cassette library records HTTP for a transport we own the seam of; the seam is cheaper. |
| **D11** *(added by validation; **cap REVERSED at apply time** — see the note at the end of this row)* | `curl-cffi >=0.15`. The cap `<0.15` was decided here and then lifted | uncapped `>=0.15`, uncapped latest, a uv `override-dependencies` hack to strip `rich` | curl-cffi 0.15.0 declares `rich` **unconditionally** (no `extra ==` marker), dragging `rich`, `markdown-it-py`, `mdurl` and `Pygments` — a Markdown renderer and a syntax highlighter — into a headless scraper image. `<=0.14.0` declared only `cffi` + `certifi`, keeping the closure at 9 instead of 13. D2 rejected `requests` for one POST and D8 rejected `structlog` for want of a consumer; four never-imported presentation packages fail the same standard, so the cap is consistency, not thrift. **The cap is a preference, not a wall** — lift it immediately for (a) an impersonation target the pinned version lacks, per the SRC §9 playbook, or (b) any libcurl advisory affecting the pinned build. Both outrank closure size. An `override-dependencies` trick is exactly the cleverness this project's failure mode warns against. **REVERSED 2026-07-28, by trigger (b) of this row's own rule.** `GHSA-qw2m-4pqf-rmpp` / `CVE-2026-33752` is an open HIGH-severity redirect-based SSRF with TLS-impersonation bypass, affecting every release below 0.15.0 and fixed in 0.15.0. This client follows redirects against a third-party site, so the exposure is real. The pin is `>=0.15` and the closure is 13. The reasoning above is kept because it still governs any future reconsideration: if the advisory is ever resolved on a lower-closure branch, or `curl-cffi` drops `rich`, revisit. Security outranks closure size. Method note: 0.14.0 had been verified against the live source (19 Chrome targets, feed 200, no challenge) — that confirmed it **worked**, not that it was **safe**. Pinning a network library requires an advisory-database check, not just a successful request. |

## Scheduler mechanics (D5, corrected)

Revision 1 described a queue-and-run-late model. Verified against APScheduler 3.11.3, the real behaviour is:

| Mechanism | Actual behaviour | Consequence adopted |
|---|---|---|
| Overlap, same job | `max_instances=1` → the new run is skipped and logged | Exactly CD §"Solapamiento". Confirmed correct |
| Overlap, different jobs | The due job is submitted, queues on the single worker, and `run_job` **re-checks `misfire_grace_time` at worker pickup** — if exceeded it is **dropped** with a job-missed event, not run late | A `feed_check` due during a long sweep is discarded once the sweep exceeds 300 s |
| Restart | The in-memory jobstore recomputes `next_run_time`; nothing is persisted, so **no backlog can exist to replay** | `coalesce` is kept as an explicit no-op documenting intent, and it survives a future switch to a persistent jobstore. It is already the 3.x default; revision 1's claim that it prevents replaying 12 backlogged feed reads described a jobstore this design does not use |
| Job exception | Swallowed into `EVENT_JOB_ERROR`; it never reaches `BlockingScheduler` | The job wrapper catches, closes `job_runs` as `error` with `error_summary`, and calls `logger.exception`; a scheduler error-event listener is the backstop. **This is the 2025 attempt's exact cause of death** |

**Grace values re-derived from the corrected model.** Worst-case `active_sweep` duration, using the full CD request policy — delay ≤15 s + attempt-1 timeout 30 s + **30 s wait before the single retry** + attempt-2 timeout 30 s ≈ 105 s per mapping × <20 mappings ≈ **35 min** (typical ~4 min). A sweep can therefore overlap at most one hourly feed run.

- `feed_check` grace **300 s**: a feed run that has waited longer than five minutes has been waiting behind the sweep, and dropping it is correct — the only thing that can delay it that long is `active_sweep`, which is at that moment checking *every* active mapping. CD is explicit that the guarantee is the sweep's, never the feed's. Cost: up to one discarded feed run per day, fully covered by the job that displaced it.
- `active_sweep` grace **3600 s**: the guaranteeing mechanism is never dropped for a scheduling delay. In practice it never fires, because the only job that can hold the worker ahead of the sweep is a one-request feed check.
- **The honest missed-run cost is not misfire grace at all.** With an in-memory jobstore and a cron trigger, a container restarted at 04:00 gets no `active_sweep` until 03:00 the next day, pushing worst-case detection latency from ~24 h to **~47 h**. Mitigation is one documented command in the deploy notes: run `run-job active_sweep` after any restart outside the scheduled window. This is the accepted price of refusing run-on-start, and it is cheaper than a crash-loop firing ~20 requests per restart.

## Layer ownership

The boundary is architectural law (CD §"Separación en dos capas"). Every responsibility has exactly one owner.

| Responsibility | Owner | Explicitly not |
|---|---|---|
| Feed selectors, ad-filter-first, `data-src` cover preference, zero-real-items-is-an-error | source client | discovery |
| JSON chapters endpoint, organic `Referer`, false-success → not-found | source client | discovery |
| **Chapter URL construction from slug + number** (no request) | source client | notifier, discovery |
| Impersonation, 5–15 s delay, 30 s timeout, **one retry after a 30 s wait**, 3-way error taxonomy | source client transport | discovery |
| Which mappings are requested at all; terminal states consume zero requests | discovery | source client |
| Detection rule, `chapter_history` write, notify-before-update, `job_runs` | discovery | notifier |
| `consecutive_failures` counter (the client only reports the *category*) | discovery | source client |
| **Link resolution hierarchy** (`chapter_history` URL → built URL → newest) | discovery — it queries the DB and *asks* the client for the pattern URL | notifier (BOT §"Qué recibe y qué no": it receives candidate URLs already resolved) |
| Message text, HTML escaping, **link-preview suppression**, **long-title truncation with ellipsis**, 4096-char split, 429 `retry_after` | notifier | discovery |
| Schema, pragmas, transactions, `updated_at` | storage | everyone else |
| Env reading, logging setup, job registration, `ensure_site`, wiring | composition root (`cli.py` / `scheduler.py`) | libraries |

## Module layout

```
manga_tracker/
├── __main__.py          python -m manga_tracker → cli.main()
├── cli.py               argparse subcommands — THE ONLY composition root
├── config.py            frozen dataclasses from os.environ; aggregated fail-fast
├── logging_setup.py     stdout handler, run-id adapter, missing-field default filter
├── clock.py             utc_now_iso() — the single timestamp source
├── sources/
│   ├── contracts.py     Response (normalized dataclass) · Transport Protocol ·
│   │                    FeedItem · Chapter · MangaDetails · SourceClient Protocol ·
│   │                    NotFound/Transient/Unexpected   ← source-agnostic shapes
│   └── manganato/
│       ├── client.py    the 3 operations + build_chapter_url + BASE_URL
│       ├── parsing.py   SRC §2/§4 selectors — the ONLY place they appear
│       └── transport.py curl-cffi impersonation, delay, timeout, retry
├── storage/
│   ├── schema.sql       7 tables + 1 trigger + the closed index set (mirrors DM)
│   ├── db.py            connect() → pragmas + ensure_schema(); ensure_site(); transaction()
│   └── repositories.py  hand-written SQL
├── discovery/
│   ├── detection.py     THE detection rule — implemented once
│   ├── feed_check.py · active_sweep.py · runs.py · links.py
├── notifier/
│   ├── contracts.py     DigestLine · DigestSender Protocol
│   └── telegram.py      formatting + sendMessage over urllib
├── seed/loader.py       CSV validate-then-load
└── scheduler.py         APScheduler wiring
```

`Response` is a **normalized dataclass** in `sources/contracts.py` (`status: int`, `text: str`, `headers: Mapping[str, str]`), built by `transport.py` from curl-cffi's own response object. It cannot *be* curl-cffi's type: `Transport` lives in `contracts.py`, and re-exporting a vendor type from there would break the rule confining `curl_cffi` to `transport.py`. `DigestLine` and `DigestSender` live in `notifier/contracts.py` for the mirror-image reason — discovery builds the lines and must import the type without importing the sender.

**Boundary made structural, not documented** — `tests/test_architecture.py` walks the AST of the package and asserts:

1. `sources/**` imports nothing from `storage`, `discovery`, `notifier`, `seed`.
2. `notifier/**` imports nothing from `storage`, `sources`, `discovery`, `seed`.
3. `storage/**` imports nothing from `sources`, `discovery`, `notifier`, `seed` — the reverse direction D4 depends on.
4. `discovery/**` and `seed/**` may import `sources.contracts` and `notifier.contracts` (types) but never `sources.manganato` or `notifier.telegram`; the client and sender instances arrive from `cli.py`. **`seed/**` is included precisely because the seed loader calls `fetch_chapters` and would otherwise be free to import the concrete client.**
5. Third-party confinement: `curl_cffi` only in `sources/manganato/transport.py`, `bs4` only in `parsing.py`, `sqlite3` only in `storage/`, `apscheduler` only in `scheduler.py`, `urllib.request` only in `notifier/telegram.py`.

~30 lines, `ast` + `pathlib`, zero deps. A leak becomes a failing test, which is the only kind of rule that survives.

## Data flow

```
        APScheduler (1 worker, set explicitly)        CLI: seed | test-telegram | run-job
                    │                                             │
                    ▼                                             ▼
  discovery.runs ── open job_runs row ──► run-scoped LoggerAdapter ──► stdout
        │           one sqlite3 connection opened HERE, on this worker thread
        ▼
  feed_check / active_sweep ─► SourceClient Protocol ─► manganato client ─► transport ─► manganato
        │                                       (ad filter, taxonomy, delay, 1 retry after 30 s)
        ▼
  detection.py
   1. seal last_checked_at ................................. always, on every branch below
   2. bookmark-state gate
        completed / dropped ─► STOP: no history, no update. Sweeps never request them at all
   3. compare observed vs latest_chapter_num
        lower ─► log; never write the stored value backwards
        lower or equal ─► no novelty; done
   4. chapter_history INSERT OR IGNORE ........... written regardless of any notification
   5. branch on state
        on_hold ─► update latest_chapter_* immediately and silently; never notify
        active  ─► accumulate candidate; latest_chapter_num UNTOUCHED
                        │
                        ▼
           links.py (chapter_history URL → build_chapter_url → newest)
                        ▼
           notifier ── ONE digest, previews off ──► api.telegram.org
                        │
             success ───┴─── failure
                │              │
    advance latest_chapter_*   advance NOTHING
    for every included mapping job_runs partial
    job_runs ok                next run re-detects
```

**Step 2 deliberately precedes step 4.** CD numbers the state decision *after* the history write, but CD's own terminal clause ("ni se actualiza el mapeo ni se registra historia") and `CLAUDE.md` ("a match on them updates nothing and records no history") both require a terminal match to write no history — achievable only if the gate runs first. Revision 1's diagram hung both branches off the history insert and read as the opposite. Reported as doc defect 2; not resolved here.

## File changes

| File | Action | Notes |
|---|---|---|
| `pyproject.toml`, `uv.lock` | Create | Lockfile versioned (transitive pinning, OP); `curl-cffi` pinned `>=0.15` per D11 (cap reversed) |
| `manga_tracker/**` | Create | Layout above |
| `tests/**`, `tests/fixtures/**` | Create | Fixtures versioned; `samples/` stays ignored |
| `seed-plantilla.csv` | Create | Exact name fixed by SEED; `.gitignore` re-includes it by that name |
| `.env.example`, `data/.gitkeep` | Create | Both already anticipated by `.gitignore` |
| `Dockerfile`, `docker-compose.yml` | Create | Log-driver rotation and the post-restart `run-job` note live here (DM defers deploy detail) |
| `docs/one-pager-v1a.md` | Modify (follow-through, **not by this phase**) | v1.6 should record the dependency set with the honest closure count, the Python/base-image pin, and fix "(polling)" in item 8. Per README's dependency map, then revisit the pins in DM, CD, BOT. Read-only here; reported to the coordinator |

## Interfaces / contracts

Two seams carry the whole test strategy. Both are constructor arguments, never module-level singletons.

```python
# sources/contracts.py
class Transport(Protocol):
    def get(self, url: str, *, headers: Mapping[str, str], timeout: float) -> Response: ...

# notifier/contracts.py
class DigestSender(Protocol):
    def send_digest(self, lines: Sequence[DigestLine]) -> bool: ...   # all-or-nothing
```

Non-obvious formatting rule for `build_chapter_url` (SRC §5) — integral numbers must not leak `.0`, and the input may already be a string from the CSV or JSON path:

```python
f = float(n)                      # '80.0' and 80.0 both survive; int('80.0') raises ValueError
num = int(f) if f.is_integer() else f
return f"{BASE_URL}/manga/{slug}/chapter-{str(num).replace('.', '-')}"   # chapter-145, chapter-45-5
```

`sites.base_url` (DM) is written by `ensure_site(conn, name, base_url)`, which `cli.py` calls with the client's exported `BASE_URL` — so the column holds the right value for V1b/V2 without storage ever importing the client and without a second source of truth. It upserts with `ON CONFLICT(name) DO UPDATE SET base_url = excluded.base_url, updated_at = ?` rather than `INSERT OR IGNORE`, because an ignore would silently leave a stale host in the row after a domain change under the SRC §9 playbook. No `SOURCE_BASE_URL` env override: SRC §9.bis proved sibling domains are not drop-in (403 + Cloudflare), so a config knob would advertise a domain rotation the playbook says is a client-code change.

`schema.sql` carries **7 tables + the one UPDATE-only trigger + the closed index set** — DM makes the indexes part of the closed schema: `bookmarks(status)`, `job_runs(job_name, started_at)`, `reading_history(manga_id, read_at)`, `reading_history(read_at)`, plus the UNIQUEs on `sites(name)`, `mangas(kitsu_id)`, `manga_sites(manga_id, site_id)`, `manga_sites(site_id, source_key)`, `bookmarks(manga_id)` and `chapter_history(manga_site_id, chapter_num)`. All `IF NOT EXISTS`.

**CHECK-constraint trap**: `job_runs.job_name` must allow `onhold_sweep`, and `chapter_history.detected_via` must allow `onhold_sweep` *and* `seed_backfill`, even though `onhold_sweep` is out of scope for this change. These values live inside CHECK constraints, so adding them once the database is populated means a migration — the exact cost DM §"Nota sobre los nombres" warns about. `STRICT` tables are not used: DM does not ask for them, and V1a edits by hand in DB Browser where affinity coercion is a feature.

## Work units → commits

Six commits, topological, each standing alone with its tests. The user slices PRs from this history, so scope hygiene per commit is the deliverable. **Rule: no repository function or helper lands before its caller** — speculative plumbing is how the previous attempt grew an apparatus without a heart.

| # | Commit scope | Lands | Stands alone because |
|---|---|---|---|
| 1 | `feat(source)`: manganato client, 3 operations + `build_chapter_url` | `pyproject.toml`, `uv.lock`, `tests/conftest.py` socket guard, fixtures, `sources/**`, `test_architecture.py` | Zero DB dependency; fixtures only |
| 2 | `feat(storage)`: schema bootstrap + connection factory | `schema.sql`, `db.py` (`connect`, `ensure_schema`, `transaction`), `data/.gitkeep` | `ensure_schema` takes no arguments, so its tests need no client and no `cli.py` |
| 3 | `feat(seed)`: CSV seed loader | `seed/loader.py`, `seed-plantilla.csv`, `storage.ensure_site` **with its first caller**, plus `cli.py`/`config.py`/`logging_setup.py`/`.env.example` | First executable path, so the CLI skeleton and the `sites` row land here. Needs 1+2 |
| 4 | `feat(discovery)`: detection rule + `feed_check` + `active_sweep` | `discovery/**` incl. `links.py`, dead-slug counter, `job_runs`, `notifier/contracts.py` | Tested against a fake `DigestSender`, so it precedes unit 5 |
| 5 | `feat(notifier)`: Telegram digest emitter | `notifier/telegram.py`, `test-telegram` subcommand | Input contract is independent (BOT §"Qué recibe y qué no") |
| 6 | `feat(scheduler)`: APScheduler wiring + Docker | `scheduler.py`, `run`/`run-job`, `Dockerfile`, compose, deploy notes | Deployment only; reverting it removes deployment, nothing else |

`test_architecture.py` lands in unit 1 and gains a rule as each package appears, so no boundary is ever unguarded for the life of a commit.

## Testing strategy

**How tests never reach the real source** — three layers: (a) the client's `Transport` is injected, and `curl_cffi` is importable from exactly one module (asserted by the architecture test); (b) an autouse session fixture in `tests/conftest.py` patches `socket.socket.connect` to raise, so any accidental real transport fails loudly for manganato *and* Telegram; (c) the delay `sleeper` and `rng` are injected, so the suite asserts the 5–15 s policy and the 30 s pre-retry wait without waiting.

**Fixtures (9)**: `feed_page.html` (4 real items + 1 `hidden` + 1 `js-banner-*`), `feed_page_ads_only.html`, `feed_page_structure_changed.html`, `feed_item_no_number.html`, `chapters_ok.json` (5 chapters incl. `45.5` / `chapter-45-5` and a `.000000Z` timestamp), `chapters_false_success.json`, `chapters_missing_array.json`, `chapters_empty.json`, `manga_details.html`.

| Layer | What | Approach |
|---|---|---|
| Unit — parsing | feed happy path, ad filter, strict ordering, slug extraction, `data-src` preference | `feed_page.html` |
| Unit — parsing | zero real items after filter → **unexpected error, not an empty list** | `feed_page_ads_only.html` |
| Unit — parsing | feed container missing/renamed → unexpected | `feed_page_structure_changed.html` |
| Unit — parsing | one item with unparseable chapter text → dropped + logged, run continues | `feed_item_no_number.html` |
| Unit — parsing | chapters happy path incl. decimal + microsecond timestamp | `chapters_ok.json` |
| Unit — taxonomy | `success:false` → NotFound · missing `data.chapters` → Unexpected · **empty array → success with zero chapters (D14)** | `chapters_false_success.json`, `chapters_missing_array.json`, `chapters_empty.json` |
| Unit — details | cover, source title, `<li>` labels | `manga_details.html` |
| Unit — taxonomy | 404 → NotFound · timeout/5xx/CF-403 → Transient · well-formed-wrong-shape → Unexpected | fake transport |
| Unit — policy | exactly one retry on transient **after a 30 s wait** (≤2 attempts/item/run); **no retry on not-found**; 30 s timeout forwarded; `Referer` = manga page on the JSON call; no delay before the isolated feed call | fake transport call log |
| Unit — URL | `build_chapter_url` parametrized (`80`, `'80.0'`, `145.0`→`chapter-145`, `45.5`→`chapter-45-5`) **and asserts zero requests** | parametrize |
| Unit — storage | FK violation raises (proves the pragma); trigger fires on UPDATE and **not** on INSERT; downward correction recorded with negative delta; `chapter_history` re-insert is a silent no-op; every DM index exists; `ensure_site` refreshes `base_url` on conflict | real DB in `tmp_path` |
| Unit — seed | every blocking error and warning from SEED; slug extraction across ficha/chapter/`www`/trailing-slash/query/fragment; **progress never derived from URL**; re-run idempotency; **zero-chapter slug reported and discarded whole (D14)** | fixtures + `tmp_path` DB |
| Unit — notifier | HTML escaping of source titles, alphabetical order, blank-line separation, decimals verbatim, null-progress variant, **long title truncated with ellipsis**, **link previews disabled on every send**, 4096 split never cutting a manga line, all-or-nothing, 429 `retry_after` honoured then one retry | fake sender/transport |
| Integration | **notify-before-update regression**: failing send ⇒ no `latest_chapter_num` moved, `job_runs.status='partial'`, `chapter_history` still written | fake sender + real DB |
| Integration | lower observed number ⇒ logged and never written backwards | real DB |
| Integration | terminal bookmarks consume zero requests **and write no `chapter_history` row** | transport call log + real DB |
| Integration | `consecutive_failures`: +1 on not-found only, reset on any success **including a zero-chapter success**, mapping skipped at ≥5 | real DB |
| Config | scheduler registration asserts trigger types, `max_instances`, misfire values and **`max_workers=1` explicitly present** — without starting the scheduler | inspect job/executor objects |

## Consequences that bite

| Gotcha | Handling |
|---|---|
| A CSS `[class^="js-banner-"]` selector matches the raw untokenized attribute string (W3C Selectors 4), so it fires only when the banner class is *first*; CSS has no per-token prefix operator | Filter ads in Python — `any(c.startswith("js-banner-") for c in el.get("class", []))`. This is the only correct implementation, not a workaround |
| **`sqlite3` connections default to `check_same_thread=True`**, and every job runs on an executor worker thread while `BlockingScheduler` holds the main thread | **One connection per run, opened inside the job function on that worker thread** and closed at run end. Do not share a module-level connection; do not set `check_same_thread=False`, which permits real cross-thread sharing with no lock |
| The Telegram URL embeds the bot token in its path | Never log the request URL or the raw send response; log method + status only |
| Source titles flow into a Telegram **HTML** message | `html.escape()` every interpolated field. BOT chose HTML to keep escaping tractable, not to skip it |
| SQLite needs write permission on the **directory**, not just the file, in *every* journal mode — WAL writes `-wal`/`-shm`, rollback-journal mode writes `-journal` | Non-root fixed UID + a documented one-time `chown` of `./data`. Not a WAL-specific consequence |
| A log record emitted outside a run has no `run_id`, so a formatter referencing it raises | Handler-level filter defaults `job_name`/`run_id` to `-` |
| Docker buffers stdout, so `docker logs` looks dead | `PYTHONUNBUFFERED=1` |
| An "overlap guard = an open `job_runs` row exists" would deadlock the job permanently after one crash (DM keeps `finished_at IS NULL` as diagnostic data) | Guard is APScheduler `max_instances=1`; startup only **logs a warning** listing open rows, never mutates them |
| `max_instances=1` is **process-local**, so a `docker exec … run-job active_sweep` can overlap a scheduled sweep and issue concurrent requests | Named residue, not guarded: the DB alternative deadlocks (above) and the trigger is a deliberate human action. `job_runs` shows the open run |
| An unhandled job exception is swallowed into `EVENT_JOB_ERROR` and never reaches `BlockingScheduler` — the exact death of the 2025 attempt | Job wrapper catches, closes `job_runs` as `error` with `error_summary`, `logger.exception`; scheduler error-event listener as backstop |
| WAL kept (`.gitignore` already anticipates `*.db-wal`) so a future V1b reader does not fight the writer | Set once at bootstrap, plus `busy_timeout`. Timestamps stay TEXT — no `PARSE_DECLTYPES` |

## Unverified claims (check before relying on them)

Revision 1 labelled an assumption a "verification rule". These are the claims this document cannot settle from here, each with the command that does.

| Claim | Check |
|---|---|
| `python:3.12-slim-bookworm` ships no `zoneinfo` tz database, so OS `tzdata` is required | `docker run --rm python:3.12-slim-bookworm python -c "import zoneinfo; zoneinfo.ZoneInfo('America/Caracas')"` — if it raises, the `tzdata` install is load-bearing. The *requirement* is not in doubt: BOT renders local time and D5's cron hour is local |
| The capped `curl-cffi` 0.14.x exposes the impersonation target SRC §9.bis verified | Install the pinned version, confirm a clean 200 from the canonical host with `impersonate="chrome"`, and confirm the Chrome targets SRC names (131, 124) are available. **If not, lift the cap — that outranks closure size** |
| ~~Whether 0.14.x's bundled libcurl-impersonate carries open advisories~~ | **RESOLVED 2026-07-28: it does.** `GHSA-qw2m-4pqf-rmpp` / `CVE-2026-33752`, HIGH, fixed in 0.15.0. D11's cap reversed as a result. |
| APScheduler 3.x constant names for the listener (`EVENT_JOB_ERROR`, `EVENT_JOB_MISSED`, and a max-instances event) | Read them off the installed `apscheduler.events` before wiring. The *behaviours* are verified; the exact symbol set is not |
| Telegram's 4096-char limit, and whether `disable_web_page_preview` is still accepted alongside `link_preview_options` | Bot API changelog at implementation time. BOT requires previews off; the parameter that achieves it is an implementation detail |

## Threat matrix

**N/A — no routing, shell, subprocess, VCS/PR-automation or executable-file-classification boundary exists.** Row by row: *Documentation-like paths* N/A (no file-type classification or execution of repo content); *Git repository selection* N/A (no VCS invocation); *Commit state* N/A; *Push state* N/A; *PR commands* N/A — commits are the orchestrator's, and the application never calls `git` or `gh`.

The real untrusted-input surface is different and is handled above: source HTML/JSON → Telegram HTML (escape), secret-in-URL (never log), and SQL (always parameterized — never interpolate a slug, even though slugs look safe).

## Migration / rollout

No migration: no prior code, no prior database. Rollback is **deletion**, not a behaviour revert — per unit, revert that commit (1–3 and 5 removable independently, 4 needs 1+2, 6 removes deployment only). Whole change: delete the created paths; `docs/one-pager-v1a.md` is the only pre-existing file the change touches, and this phase does not touch it. Local state: delete `data/manga-tracker.db` (rebuildable from the seed CSV). **Never delete `data/seed.csv`** — hand-typed, not reconstructible, and `git clean -xdf` would take it.

Bring-up order after unit 6: `seed` → `test-telegram` → `run-job feed_check` → `run-job active_sweep` → `run`. Each step is observable before the next, which is the point of D6. After any restart outside the scheduled window, `run-job active_sweep` — see the ~47 h note.

## D14 — empty `data.chapters`, at both consumers *(decided during the corrective pass)*

The client returns an empty list: the response has the expected shape, so it is not "unexpected" under CD's taxonomy, and it is not a 404, so it is not "no encontrado".

- **Seed loader** (user decision): report the row and discard it completely — no `mangas`, no `manga_sites`, no `bookmarks` — matching SEED's existing "prefiero corregir y re-correr que arrastrar una fila coja".
- **Detection / `active_sweep`** (decided here; previously implied and therefore unsafe): the call is a **success**, so it **resets `consecutive_failures`** per CD ("Cualquier respuesta exitosa lo devuelve a cero"). `last_checked_at` is still sealed, no chapter is observed, nothing else happens, and one log line records "slug alive, zero chapters". Consequence, stated rather than hidden: a live slug that never publishes is polled once a day forever and the dead-slug counter never fires for it. At one request per day that cost is negligible, and the alternative — counting it as not-found — would redefine a counter CD scopes strictly to "no encontrado" and could pause a perfectly valid mapping.

## Open questions

- [ ] `openspec/changes/v1a-heart-phase/proposal.md` still pins OP at v1.4 while the file is v1.5 — by this project's own rule a stale pin is a defect; fix on next touch.
- [ ] Exact `ACTIVE_SWEEP_HOUR` default (a config value, not a design decision). `3` local proposed as "madrugada".

## Doc defects reported to the coordinator (read-only here)

1. **`one-pager-v1a.md` v1.5 §"SÍ entra en V1a" item 8** calls the bot "**(polling)**", which `spec-bot-telegram.md` §"Qué NO hace el bot en V1a" directly contradicts ("No recibe comandos… no hay polling de mensajes entrantes"). The conflict rule resolves it in the bot spec's favour, so D2 stands; the v1.6 bump should fix the word.
2. **`spec-cliente-fuente-descubrimiento.md` §"La regla de detección"** orders the `chapter_history` write (step 3) before the bookmark-state decision (step 4), while step 4's own terminal clause forbids writing history for terminal states. Implementable as written only by gating first; worth an explicit note in CD.
3. **`telegram-digest/spec.md`** (SDD spec artifact) dropped two hard BOT requirements: link-preview suppression (BOT §"Resolución del enlace", last line) and long-title truncation with ellipsis (BOT §"Reglas de contenido"). Both are now in this design's ownership row and test list.
