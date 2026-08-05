# Proposal: V1a heart phase (`v1a-heart-phase`)

Build the chain seed → detection → Telegram digest → Docker until the first real chapter notification arrives.

**Doc aliases** (source of truth; Spanish prose, cited by section):

| Alias | Document |
|---|---|
| OP | `docs/one-pager-v1a.md` v1.6 |
| DM | `docs/spec-modelo-de-datos.md` v1.6 |
| CD | `docs/spec-cliente-fuente-descubrimiento.md` v1.2 |
| BOT | `docs/spec-bot-telegram.md` v1.1 |
| SEED | `docs/spec-seed-manual.md` v2.1 |
| SRC | `docs/manganato-fuente-actual.md` v1.2 |

## Intent

The repo has zero application code; `docs/` is a closed design with nothing executing it. The previous Go attempt died over-engineered with the cron commented out (`README.md` §"Cómo se trabaja aquí"), so this change admits only work that moves the first Telegram message forward.

Success is OP §"Criterio de terminado de V1a" items 1–3. Item 4 (Kitsu) is phase 3.

## Scope

### In scope

| # | Deliverable | Implements |
|---|---|---|
| 1 | 7 tables + the single UPDATE-only `reading_history` trigger, created complete on first boot; SQLite FK enforcement enabled per connection | DM §"Las 7 tablas", §"Convenciones globales" |
| 2 | Source client: `fetch_latest_feed`, `fetch_chapters`, `fetch_manga_details`, plus the no-request chapter-URL helper. Request policy and 3-way error taxonomy. Zero DB knowledge | CD Parte A; SRC §2–§5, §8 |
| 3 | Shared detection rule, implemented **once** | CD §"La regla de detección" |
| 4 | `feed_check`, hourly | CD §"Mecanismo 1" |
| 5 | `active_sweep`, daily, **pulled forward from phase 2** — plus the `consecutive_failures` counter: increment on not-found only, reset on any success, skip mappings at ≥5 | CD §"Mecanismo 2"; §"Slugs muertos" steps 1, 2, 4 |
| 6 | Notify-before-update orchestration; `job_runs` open/close | CD §"Orden de operaciones", §"Registro de corridas" |
| 7 | Seed loader CLI + the versioned `seed-plantilla.csv` (absent from the repo today) | SEED, full doc |
| 8 | Telegram digest emitter — **message 1 only** | BOT §"Mensaje 1", §"Configuración y token" |
| 9 | APScheduler wiring for those two jobs; one container, SQLite on a volume | OP §"Decisiones de plataforma cerradas" |
| 10 | pytest + uv scaffolding, landing with work unit 1 | OP §"Decisiones de plataforma cerradas" (Tests, Dependencias) |

### Out of scope

`onhold_sweep`; heartbeat (BOT message 2); the dead-slug **notice** (BOT message 3 — the counter is in, the Telegram message is not); Kitsu importer; everything in OP §"NO entra en V1a".

**Stated consequence, not papered over**: CD §"Slugs muertos" step 4 assigns the low-frequency retry of a paused mapping to the weekly sweep. With `onhold_sweep` out, a mapping stopped at 5 consecutive not-found failures has **no automatic retry path** during the heart phase, and no Telegram notice announces it — it surfaces only in `job_runs` and stdout logs. Repair is manual slug correction. Accepted for bring-up.

## Capabilities

`openspec/specs/` is empty, so every capability is new. One per work unit.

### New Capabilities

- `source-client`: manganato client — 3 operations + chapter-URL construction, request policy, error taxonomy, ad-filter-first parsing, zero-items-as-error.
- `data-model`: SQLite schema, 7 tables, the UPDATE-only trigger, FK enforcement, first-boot bootstrap including the single `sites` row.
- `seed-loader`: CSV validate-then-load CLI, slug extraction, `seed_backfill` history seeding, safe re-run.
- `chapter-detection`: the shared detection rule, `feed_check`, `active_sweep`, notify-before-update, dead-slug counter, run recording.
- `telegram-digest`: digest formatting, link-resolution hierarchy, size split with all-or-nothing success, startup token/chat validation, manual test-send.
- `scheduler-deployment`: APScheduler registration, entrypoint, env validation, Docker image and volume.

### Modified Capabilities

None.

## Approach

Six sequenced work units in topological order. Each is one reviewable commit scope with its tests:

1. **Source client** — no DB dependency; tested against trimmed fixtures in `tests/fixtures/`. Lands the pytest/uv scaffolding.
2. **Schema** — DDL, connection/pragma helper, first-boot bootstrap.
3. **Seed loader** — needs 1 + 2. First point where the DB holds real data.
4. **Discovery core + `feed_check` + `active_sweep` + notify glue** — needs 1 + 2.
5. **Digest emitter** — input contract is independent (BOT §"Qué recibe y qué no"), so it can be built beside 4.
6. **Scheduler + Docker** — glue, last.

**Hard structural rule kept visible** (CD §"Separación en dos capas"): the client knows manganato — URLs, HTML, the JSON endpoint, ad filtering, anti-bot — and knows nothing about the database or the reading list. Discovery knows the list, the states and the notify decisions, and nothing about manganato's markup. Building a chapter URL from a slug and a number is a **client** operation; the bot asks for URLs and never assembles them.

**Deferred to `sdd-design`, with recorded rationale — not decided here**: HTML parsing library, Telegram transport, DB access layer, schema bootstrap mechanism, APScheduler registration specifics (trigger type, missed runs, overlap guard), entrypoint/CLI shape unifying the three invocation modes, env-var loading and `.env.example`, logging setup, Docker base image and Python version, source-client fixture set.

**Spec gaps needing a user decision**: none found beyond the list above. The three product decisions the specs left open — `active_sweep` phasing, bot message scope, size gating — were resolved by the user before this proposal.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| Application package | New | Client, schema, discovery, bot, scheduler. Layout is a design decision. |
| `tests/`, `tests/fixtures/` | New | pytest suite; trimmed source fixtures. No test touches the live source. |
| `pyproject.toml`, `uv.lock` | New | uv-managed, lockfile versioned for transitive pinning. |
| `Dockerfile` (+ compose) | New | One container, `data/` mounted, log driver owns rotation (DM §"Estrategia de logging"). |
| `seed-plantilla.csv` | New | Name fixed by SEED; `.gitignore` already re-includes it by that exact name. |
| `data/.gitkeep` | New | `.gitignore` already anticipates it; keeps the volume mount point on clone. |
| `docs/one-pager-v1a.md` | Modified | Phase boundary moved — see Dependencies. |
| Existing behaviour | None | There is none. |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Notify-before-update implemented in the wrong order → a lost alert | Med | Regression test: a failed send advances nothing and closes the run `partial`. A duplicated alert is acceptable, a lost one is not. |
| Paused mapping has no retry until phase 2 | Med | Accepted, stated above. Manual slug fix; visible in `job_runs`. |
| Client/discovery boundary leaks | Med | Hard structural rule above; URL construction stays in the client. Review each unit against CD §"Separación en dos capas". |
| Source markup or endpoint changes mid-build | Low | Blast radius is the client alone (SRC §9 playbook); fixtures keep parser tests offline. |
| ~880–1500 changed lines vs the 400-line review budget | High | Accepted: `delivery_strategy` is `exception-ok`. Commit hygiene carries the weight instead — one reviewable unit per commit, tests alongside, because the user slices PRs from the commit history. |
| Milestone depends on a real upstream publication | Med | `active_sweep` in scope caps detection latency at ~24h (OP §"Arquitectura de descubrimiento"); `feed_check` alone would not. |

## Rollback Plan

No prior code exists, so rollback is deletion, not a revert of behaviour:

- Per unit: revert that unit's commit. Units 1–3 and 5 are independently removable; 4 depends on 1 + 2; 6 removes deployment only.
- Whole change: delete the new files and directories listed in Affected Areas. `docs/` and `.gitignore` are the only pre-existing files touched.
- Local state: delete `data/manga-tracker.db` (unversioned, rebuildable from the seed CSV). **Never delete `data/seed.csv`** — hand-typed and not reconstructible.

## Dependencies

- No code dependency. All five specs are closed and their version pins are currently consistent.
- `data/seed.csv` must exist locally before any end-to-end run. It is not in the repo and must not be committed.
- Telegram bot token and chat id as env vars; the process must fail fast at startup if either is missing (BOT §"Configuración y token").
- **Doc follow-through — RESOLVED.** Pulling `active_sweep` into phase 1 left OP §"Fases internas de V1a" stale, still assigning it to phase 2. Closed in OP v1.5, which records the new phase boundary with its rationale and the dead-slug consequence; OP v1.6 then added the dependency set and the runtime/base-image pin. Pins of DM, CD and BOT were re-checked and cascaded per `README.md` §"Mapa de dependencias entre documentos" after each bump. CD also went to v1.3 to fix an internal contradiction the design phase surfaced, and SEED to v2.2 for the empty-chapters rule.

## Success Criteria

- [ ] Seed loader populated the DB from `data/seed.csv` with correct slug and progress (OP criterion 1).
- [ ] `feed_check` and `active_sweep` run unattended in Docker under APScheduler (OP criterion 2, minus `onhold_sweep`).
- [ ] At least one real new-chapter notification arrived and was verified correct (OP criterion 3).
- [ ] A failed Telegram send leaves every `latest_chapter_num` untouched and closes the run `partial`.
- [ ] `chapter_history` is written regardless of notification; re-running a detection inserts no duplicates.
- [ ] A number lower than the stored `latest_chapter_num` is logged and never written backwards.
- [ ] Terminal bookmarks (`completed`, `dropped`) consume zero requests and update nothing.
- [ ] `consecutive_failures` increments only on not-found, resets on any success, and skips a mapping at ≥5.
- [ ] pytest passes with no network access.
- [ ] `git check-ignore --stdin` confirms `seed-plantilla.csv` is versioned and `data/seed.csv` is ignored.

## Next step

`sdd-spec` and `sdd-design` can run in parallel. Design owns the deferred technical decisions listed under Approach.
