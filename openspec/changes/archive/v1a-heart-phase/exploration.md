# Exploration — V1a heart phase (`v1a-heart-phase`)

Phase: `sdd-explore`. Date: 2026-07-28. Artifact store: hybrid (mirrors Engram `sdd/v1a-heart-phase/explore`).

The repository has zero application code. Everything below is derived from the eight documents in `docs/`, which are the source of truth.

## Scope per the one-pager

`docs/one-pager-v1a.md` §"Fases internas de V1a", phase 1 ("Fase corazón"): SQLite schema + manual seed (<20 titles) + source client + detection cron + Telegram digest + Docker deploy. Milestone: the first real notification. Phase 1 is not shared with any other phase.

Cross-checked against the phase-2 definition ("Fase red de seguridad" = `active_sweep` + `onhold_sweep` + heartbeat), the phase-1 "detection cron" reads as **`feed_check` only** — the hourly, explicitly non-guaranteeing mechanism — and not `active_sweep`, which the same document designates as the primary detection mechanism. This is an unresolved scope boundary, recorded as Gap 7 below.

## Build inventory

| # | Component | Specified by |
|---|---|---|
| 1 | SQLite schema: 7 tables + 1 UPDATE-only trigger; FK enforcement must be enabled per connection | `spec-modelo-de-datos.md` v1.6 |
| 2 | Source client: `fetch_latest_feed`, `fetch_chapters`, `fetch_manga_details`, plus chapter-URL construction. No DB dependency by design | `spec-cliente-fuente-descubrimiento.md` v1.2 Parte A; `manganato-fuente-actual.md` v1.2 §2–5, §8 |
| 3 | Detection rule / discovery core: seal `last_checked_at` → compare → record `chapter_history` → branch by bookmark state. One rule, shared by all three mechanisms | same spec, Parte B |
| 4 | `feed_check` job | same spec, §"Mecanismo 1" |
| 5 | Notify-before-update orchestration: accumulate → single digest → success advances state, failure advances nothing | same spec, §"Orden de operaciones"; model handoff 1 |
| 6 | Seed loader CLI | `spec-seed-manual.md` v2.1 |
| 7 | Telegram digest emitter (message 1 only; heartbeat and dead-slug notices fire only from phase-2 sweeps) | `spec-bot-telegram.md` v1.1 |
| 8 | Docker deploy | one-pager §"Decisiones de plataforma cerradas" |
| 9 | APScheduler wiring | one-pager §Scheduler (corrected in v1.4 — see Traps) |

## Dependency order and slicing

Topological order: source client (no DB dependency, testable against trimmed fixtures) → schema → seed loader (needs both) → discovery core + `feed_check` + notify glue → digest emitter → scheduler + Docker last.

Honest changed-line forecast, uncalibrated because no code exists yet, tests included:

| Slice | Estimate |
|---|---|
| Source client + parsing + error handling + tests | 250–400 |
| Schema (DDL + connection/pragma helper) | 100–200 |
| Seed loader | 150–250 |
| Discovery core + `feed_check` + notify glue | 150–250 |
| Digest emitter | 150–250 |
| Scheduler + Docker + entrypoint + env validation | 80–150 |
| **Total** | **≈ 880–1500** |

That is roughly 2–4× the cached 400-line review budget, and it conflicts with the cached `single-pr` delivery strategy independently of library choices.

## Gaps — enumerated, deliberately not resolved

Per `README.md` §"Cómo se trabaja aquí" and `CLAUDE.md`, a gap the specs do not cover is asked, not filled by default judgment.

Closed since this exploration ran: test runner (pytest) and dependency/environment management (uv), both recorded in one-pager v1.4.

Still open, product/scope — require a decision:

7. **Phase-1/phase-2 boundary for the shared detection core.** No document says whether phase 1 builds the core generically (ready for all three `detected_via` values, including dead-slug tracking) or feed-only minimal. This changes phase-1 scope and line count. It also means the phase-1 milestone rides solely on a mechanism the specs call non-guaranteeing: with a 60-minute interval against a measured 41-minute window there is a structural ~19-minute blind spot and roughly two-thirds peak capture. No document states whether that is accepted specifically for phase-1 bring-up.
8. **Bot message scope for phase 1**: ship all three message types now, or the digest only, given heartbeat and dead-slug notices only ever fire from phase-2 sweeps.

Still open, technical — appropriate for `sdd-design` to decide with recorded rationale:

1. HTML/DOM parsing library not named anywhere (selectors are specified; the library is not).
2. Telegram transport/library not named.
3. DB access layer not named (raw `sqlite3` vs an ORM).
4. Schema bootstrap mechanism: what runs the one-time DDL and inserts the single `sites` row, and when relative to the seed loader.
5. APScheduler job registration specifics: trigger type, missed-run-on-restart behaviour.
6. Application entrypoint/CLI shape: at least three invocation modes are implied (scheduler process, seed loader, Telegram test-send utility) and no document unifies them.
9. Env-var loading mechanism, and whether a `.env.example` template is expected.
10. Logging implementation: the correlation convention is decided, the mechanism is not.
11. Docker base image and Python version not pinned.
12. Required test fixtures and cases for the source client not enumerated.

## Traps

Every entry in `CLAUDE.md` §"Rules that are easy to get wrong" was verified line by line against the underlying specs. All check out with no discrepancies: notify-before-update, `chapter_history` written regardless of notification, the shared one-rule detection sequence, terminal-state zero-requests with silent `on_hold`, the UPDATE-only trigger with honest negative-delta corrections, the feed non-guarantee, ad-filter-first with zero-items-as-error, UTC-always with timezone applied before calendar-day aggregation, the request policy, and the dead-slug threshold.

Two inconsistencies were found inside `one-pager-v1a.md` v1.3 itself. Both are corrected in v1.4:

- **Stale self-tracking list.** §"Documentos siguientes" reported the data-model spec as v1.4 (actual v1.6), the client/discovery spec as v1.0 (actual v1.2), the bot spec as still pending and blocking the heart phase (actual: closed at v1.1), and the seed spec as v2.0 (actual v2.1). Taken literally it would have wrongly suggested the bot spec still blocked heart-phase start.
- **Stale scheduler section.** §"Decisiones de plataforma cerradas" said "los dos jobs (detección cada 3-4h, barrido semanal)", contradicting, inside the same version, the three-mechanism table, the 1-hour feed interval fixed in that very version, and the three-value CHECK constraint on `job_runs.job_name`. The done-criteria list carried the same two-job framing and omitted `active_sweep`, the designated primary mechanism.

A third, minor: `CLAUDE.md` said `docs/` held seven documents; the actual count is eight. Corrected.

## Next

`sdd-propose`, once gaps 7 and 8 and the delivery-strategy conflict are decided by the user.
