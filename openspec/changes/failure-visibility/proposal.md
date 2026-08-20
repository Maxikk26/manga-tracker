# Proposal: Failure Visibility

## Intent

One root class: **a failure that does not show**, in the owner's only two windows.

- **Heartbeat reports unverified health.** `heartbeat.py:28-34` accepts `status='ok'`, but `open_run` inserts that status with `finished_at` NULL (`runs.py:22-26`), so a run merely in flight — or one killed mid-sweep, whose row stays open forever — reads as the last successful detection. This is exactly the "healthy-looking heartbeat on six days of dead feed and sweep" that `spec-bot-telegram.md:103,128` says the message exists to expose.
- **A details 403 reports success.** `client.py:75-77` maps only 404; a 403 body reaches `parse_manga_details`, which returns `title=""` (`parsing.py:70`). `POST /api/mangas/preview` answers **200 with an empty title**.
- **Escalation (not previously named):** `confirm()` does not re-fetch the ficha (`pasted_url.py:97`) and `AddConfirm.title` has no `min_length` (`web/app.py:93`), so that empty title is **writable into production data**.

## Scope

### In Scope
- `_last_successful_run_at` requires finished evidence — reusing the shape already present twice: `heartbeat.py:77`, `scheduler.py:315-320`.
- `fetch_manga_details` classifies non-200 like its siblings (`client.py:106`, `:129`).
- Regression tests for both untruthful outputs. None exist today: `tests/sources/test_client.py:87-100` covers 200/404 only.
- Doc version bumps plus the full pin sweep (`runbook-mantenimiento.md:110`).

### Out of Scope
- Telling an interactive-pacing 403 from a Cloudflare 403. `spec-cliente-fuente-descubrimiento.md:301` stays **open**: the policy class is not visible where classification happens (`cli.py:250-267`).
- Dead-slug notice for `on_hold` — recorded decision (`runbook-mantenimiento.md:313`).
- Any new `job_name` (a CHECK rebuild on a populated DB).

### Preserved by design
`onhold_sweep` stays excluded from `last_successful_run_at` and `degraded_run_count` (`heartbeat.py:22`, `notifier/contracts.py:51-52`).

## Open decision — blocks the spec phase

What does "última detección exitosa" mean? `CLAUDE.md` and `config.yaml` `rules.proposal` forbid deciding this by default judgment.

| # | Semantics | Consequence |
|---|---|---|
| a | `+ finished_at IS NOT NULL` | Fixes the in-flight and killed-run cases. A sweep that examined nothing still counts. |
| b | **(recommended)** also `IFNULL(items_checked,0) > 0` | Full `sweep_is_overdue` shape; both conditions were **observed** suppressing a real catch-up (`scheduler.py:298-313`). Verified safe: `feed_check` closes `items_checked=len(items)` and zero items raises `Unexpected` (`feed_check.py:75`), so a healthy feed run always counts. |
| c | `MAX(detected_at) FROM chapter_history` | **Changes the message's meaning.** At ~1 chapter/day, legitimate silence would read as no detection. Also contradicts the spec's own wording, "última corrida de detección exitosa" (`spec-bot-telegram.md:101`) — a *run*, not a detection. Needs a label change at `notifier/telegram.py:118`. |

Under (a)/(b) the Spanish label stays true and is untouched.

## Capabilities

### New Capabilities
- `heartbeat-report`: what the weekly message may claim, and what counts as evidence for each claim.

### Modified Capabilities
- `source-client`: `Requirement: Error taxonomy` and `Requirement: fetch_manga_details is fallback-only` — every non-200 details response classifies.

## Approach

Two SQL conditions and one status branch. **No new state, flag, verb, table, or parallel mechanism** — each fix reuses a shape this codebase already applies elsewhere and deletes a special case. Net additions are tests and docs.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `manga_tracker/discovery/heartbeat.py` | Modified | `_last_successful_run_at` query only |
| `manga_tracker/sources/manganato/client.py` | Modified | `fetch_manga_details` non-200 branch |
| `tests/sources/test_client.py`, heartbeat tests | Modified | Assert both current lies |
| `docs/spec-bot-telegram.md` (v1.6), `docs/spec-cliente-fuente-descubrimiento.md` (v1.8) | Modified | Spanish prose, neutral register |

## Docs extended, and the pins each bump stales

| Bump | Stale pins to fix |
|---|---|
| `spec-bot-telegram.md` → v1.7 | `runbook-mantenimiento.md:3`, `one-pager-v1a.md:170` |
| `spec-cliente-fuente-descubrimiento.md` → v1.9 | `medicion-ventana-feed.md:3`, `spec-bot-telegram.md:3`, `runbook-deploy.md:3`, `spec-seed-manual.md:3`, `spec-importador-kitsu.md:3`, `one-pager-v1a.md:169`, prose at `manganato-fuente-actual.md:169` |

Treat a stale pin as a defect (`CLAUDE.md`); four were shipped last time this was skipped (`runbook-mantenimiento.md:115`).

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Owner picks (c); spec/design redone | Med | Decision gate above, before the spec phase |
| Heartbeat reads "nunca" after the fix — truthful, but looks like a regression | Low | Note it in the doc bump: it means no finished detection run exists |
| 403 now surfaces as 502/503 on a working add flow | Low | Match `fetch_cover`'s existing classification; test both codes |
| Pin sweep missed | Med | Run `runbook-mantenimiento.md:110` and paste the output |

## Rollback Plan

Both fixes are read-and-raise: no schema change, no migration, no backfill. Revert the commit, then `docker compose build && docker compose up -d` (never `restart`).

**Rows written:** none by either fix. The heartbeat is read-only and opens no `job_runs` row (`spec-bot-telegram.md:118`). The 403 fix *prevents* a write — it stops an empty-title manga row. Reverting restores the old queries against unmodified production data; nothing needs undoing. Before shipping, confirm no empty-title row already landed: `SELECT id FROM mangas WHERE TRIM(title) = ''`.

## Dependencies

None external. Both defects are one change: two ~15-line slices sharing one review frame, well inside the 1500-line budget. Splitting would duplicate the framing for no reviewer gain.

## Success Criteria

- [ ] A `job_runs` row with `finished_at` NULL is never reported as the last successful detection.
- [ ] A details 403 raises a classified error; `/api/mangas/preview` never answers 200 with an empty title.
- [ ] `onhold_sweep` remains excluded from both heartbeat detection figures.
- [ ] Each fix has a test that fails on current `main`.
- [ ] Pin sweep clean; both doc bumps carry a changelog entry.
