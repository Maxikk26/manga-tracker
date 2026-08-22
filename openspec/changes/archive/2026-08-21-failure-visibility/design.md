# Design: Failure Visibility

## Technical Approach

Three read-and-raise edits: one named SQL fragment (`discovery/`), one status-class branch (source client), one Pydantic constraint (`web/`). No new state, flag, verb, table, job_name or schema change. Detection rule (CLAUDE.md: seal `last_checked_at` → compare → record `chapter_history` → decide by bookmark state) is untouched — this change only alters what is *reported* and what is *classified*.

## Architecture Decisions

### D1 — Finished-evidence predicate: one named SQL fragment, not a helper function

**Choice**: `FINISHED_WITH_EVIDENCE = "finished_at IS NOT NULL AND IFNULL(items_checked, 0) > 0"` in `manga_tracker/discovery/runs.py`, interpolated into the two queries that mean it (`sweep_is_overdue`, `_last_successful_run_at`).

**Alternatives rejected**:

| Option | Tradeoff | Verdict |
|---|---|---|
| Parameterized helper `last_run_at(conn, jobs, statuses, require_items)` | Three parameters to unify three 3-line queries. `require_items` re-introduces at each call site exactly the ambiguity the owner decision just resolved. Adds a verb *and* a flag. | Rejected (over-engineering test) |
| Repeat the literal locally in each place | The drift that let `scheduler.py` and `heartbeat.py` disagree in the first place. | Rejected |

**Home and boundary**: `runs.py` owns `open_run` — the function that *creates* the ambiguity, inserting `status='ok'` with `finished_at` NULL. The corrective definition belongs next to its cause. `discovery.heartbeat → discovery.runs` is intra-package. `scheduler.py` is top-level, so `DIRECTIONAL_RULES` (keyed on `rel.split("/")[0]`) does not reach it; it is constrained only by `CONCRETE_IMPLEMENTATIONS`, and a SQL constant is not a concrete. `scheduler.py` already imports four `discovery.*` modules. **No new architecture rule is needed** — assert `tests/test_architecture.py` stays green rather than adding one. `storage/` was rejected as the home: raw SQL lives in `discovery`/`scheduler` today, and "when detection counts as alive" is a discovery decision, not a persistence one.

**Deliberately scoped to the two evidence conditions, not the status set.** `sweep_is_overdue` needs `status IN ('ok','partial')`; the heartbeat needs `status = 'ok'`. Those differ legitimately (`'partial'` is reported separately by `_degraded_run_count`) and stay local. `_last_onhold_sweep` keeps its own literal `finished_at IS NOT NULL` and does **not** use the constant — its docstring already explains why it wants no `items_checked` condition, and not using the shared name makes that difference visible instead of accidental.

**Reviewer must check**: (1) the literal `IFNULL(items_checked` appears nowhere outside `runs.py`; (2) `_last_onhold_sweep` still omits it, docstring intact; (3) no status set was silently unified.

### D2 — A details non-200 is classified by status class (SPEC AMENDMENT REQUIRED)

| Status | Class | Basis |
|---|---|---|
| 404 | `NotFound` | unchanged |
| 403 / 429 / 5xx (`TRANSIENT_STATUS_CODES`) | **`Transient`** | `docs/spec-cliente-fuente-descubrimiento.md:65` — transitorio = timeout, conexión, **5xx**, bloqueo de **Cloudflare** |
| any other non-200 | `Unexpected` | protocol/shape surprise |
| 200 whose ficha yields no title | `Unexpected` | selectors changed; guarantees the success criterion independently of status |

**Conflict, stated loudly.** `specs/source-client/spec.md:26,30` requires "`Unexpected` on any other non-200". That makes a **500 `Unexpected`**, contradicting `docs/…:65`, which lists 5xx as transitorio; and `openspec/config.yaml` `rules.specs` forbids an SDD artifact silently overriding `docs/`. **That scenario must be amended before apply.** Owner-facing consequence: `_source_error` maps `Transient` → 503 "espera un momento y vuelve a intentar" (the runnable exit) versus `Unexpected` → 502 "probablemente cambió, revisa los logs" (the wrong exit — a WRONG exit outranks a missing one). `docs/…:301` names both candidate causes of an interactive 403 (source throttle, Cloudflare); both mean "hoy no se pudo, mañana quizás", neither means the source changed shape.

`TRANSIENT_STATUS_CODES` is reused from `transport.py` (same package, no confinement rule). A second set would be a parallel representation of the same truth.

`fetch_cover` keeps its `status != 200 → Unexpected` shape unchanged: an absent thumbnail on an image host is a known-ordinary 403, a different fact from the ficha's anti-bot 403. Noted so a reviewer does not "harmonize" it.

### D3 — Blast radius: `client.py`, not `transport.py`

`transport.py:181` already states the invariant — the transport returns the raw response "and the client still turns it into `NotFound`/`Transient`/`Unexpected`". Status→class is client work; retry is transport work. `TRANSIENT_STATUS_CODES` stays retry-only there. Raising in the transport would change `fetch_cover` and every batch caller (`covers.py`, `active_sweep`, `feed_check`). **Accepted radius**: the two `fetch_manga_details` callers — `intake/pasted_url.py:49` and `discovery/covers.py:105` — both of which already catch all three classes.

### D4 — The dead-slug counter is provably untouched

`fetch_manga_details` has exactly two callers. `covers.py:83-86` leaves `consecutive_failures` alone in both directions by design; `intake` never touches it. The counter is driven only by `fetch_chapters` inside `active_sweep`/`onhold_sweep`. No choice in D2 can reach it — and per `docs/…:246` only not-found increments it, so `Transient` would not increment it even if it could.

### D5 — Empty title: two gates, not three

1. **Client (D2)**: a 200 with no title raises `Unexpected`, so an empty title is unobtainable from `preview()`. Root fix.
2. **HTTP boundary**: `MangaAddRequest.title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]` → 422. `min_length=1` alone is insufficient — `"   "` passes it. `strip_whitespace` also normalizes the stored title, matching the `TRIM(title)` audit.

**Rejected: a third gate inside `intake.confirm()`.** It would need a new exception class, a `_source_error` branch and a `docs/` taxonomy row — machinery around a one-line constraint — and `confirm()` has exactly one caller (`web/app.py:305`). The two kept gates are not redundant: (1) closes the source-supplied path, (2) the client-supplied/replayed path. **Reversal condition**: if a second `confirm()` caller appears (a CLI add, an importer path), the guard moves into `intake` and the Pydantic constraint becomes the redundant one.

### D6 — The existing transport test does not constrain this

`tests/sources/test_transport.py:582-590` pins set equality for `TRANSIENT_STATUS_CODES`. This design adds no member, so it stays green and stays useful. Widening it is one of the deliberate breaks below.

## Data Flow

    preview:  web ──→ intake ──→ client ─┬─ 404 ────────→ NotFound  → 404
                                          ├─ 403/429/5xx → Transient → 503
                                          ├─ other !200 ─→ Unexpected→ 502
                                          └─ 200, no title → Unexpected→ 502
    confirm:  web (title min_length≥1 after strip → 422) ──→ intake ──→ write

    heartbeat / scheduler ──→ discovery/runs.FINISHED_WITH_EVIDENCE ──→ job_runs

## File Changes

| File | Action | Description |
|---|---|---|
| `manga_tracker/discovery/runs.py` | Modify | Add `FINISHED_WITH_EVIDENCE` next to `open_run` |
| `manga_tracker/discovery/heartbeat.py` | Modify | `_last_successful_run_at` adopts the fragment; `_last_onhold_sweep` untouched |
| `manga_tracker/scheduler.py` | Modify | `sweep_is_overdue` adopts the fragment (same predicate, one name) |
| `manga_tracker/sources/manganato/client.py` | Modify | `fetch_manga_details` status-class branch + empty-title guard |
| `manga_tracker/web/app.py` | Modify | `MangaAddRequest.title` constraint |
| `tests/…` | Modify | Regression tests per the table below |
| `docs/spec-bot-telegram.md` | Modify | v1.6 → v1.7 + changelog + owner expectation note |
| `docs/spec-cliente-fuente-descubrimiento.md` | Modify | v1.8 → v1.9 + changelog |
| `docs/runbook-mantenimiento.md` | Modify | Post-deploy heartbeat expectation (Spanish) |
| `openspec/…/specs/source-client/spec.md` | Modify | Amend the non-200 scenario per D2 |

Plus the full pin sweep named in the proposal — a stale pin is a defect.

## Testing Strategy

| Layer | What | Approach |
|---|---|---|
| Unit | in-flight / killed / zero-item rows excluded; qualifying row reported | `job_runs` fixtures against `_last_successful_run_at` |
| Unit | `sweep_is_overdue` unchanged after adopting the fragment | existing tests must stay green untouched |
| Unit | `onhold_sweep` still excluded from both figures | existing tests |
| Unit | details 403/500/other/200-no-title → the D2 class | fake `Transport` returning each status |
| Integration | `/api/mangas/preview` never 200-with-empty-title; 403 → 503 | FastAPI TestClient + stub intake |
| Integration | `POST /api/mangas` with `""` and `"   "` → 422, zero rows | TestClient + DB assertion |
| Architecture | boundary unchanged | `tests/test_architecture.py` green, no new rule |

**Guards the apply phase MUST break on purpose** (a green suite proves only that nothing written is checked):

1. Drop `IFNULL(items_checked, 0) > 0` from the fragment → the zero-item test must fail.
2. Drop `finished_at IS NOT NULL` → the in-flight and killed-run tests must fail.
3. Point the fragment at `"1=1"` → tests must fail in **both** call sites, proving the constant is load-bearing in each and not merely defined.
4. Remove the 403 branch → the `Transient` test and the 503 preview test must fail.
5. Remove `strip_whitespace` (keep `min_length=1`) → the `"   "` test must fail with a written row.
6. Add `404` to `TRANSIENT_STATUS_CODES` → `test_the_transient_status_set_is_exactly_the_documented_one` must fail.

Command: `uv run pytest -q` (532 backend tests). No frontend change.

## Threat Matrix

N/A — no routing, shell command, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary. The single input-validation surface is D5, designed above rather than expanded into matrix rows.

## Migration / Rollout

**No schema change, and none is needed.** Nothing here writes `job_runs.job_name`, so the CHECK `('feed_check','active_sweep','onhold_sweep')` is untouched and no table rebuild runs against the populated production database (229 mangas / 229 bookmarks, unattended in Docker since 2026-07-30).

**Owner prerequisite — not run here.** `docker` is installed but this account has no permission on `/var/run/docker.sock`, so this was NOT verified:

```sql
SELECT id, title FROM mangas WHERE TRIM(title) = '';
```

Expect zero rows. Any row is a pre-existing empty-title add from the sibling defect; remediation is owner-decided and outside this change (no backfill, no migration).

**Telling the owner about the heartbeat.** The renderer already maps `None` → "ninguna todavía" (`notifier/telegram.py:92-96`), so **no notifier code change**. The realistic production effect is a timestamp that is equal or slightly older, not "ninguna todavía": with `feed_check` every 30 minutes and a daily sweep over 229 titles, qualifying rows are plentiful. The expectation is set in `docs/runbook-mantenimiento.md` and the `spec-bot-telegram.md` v1.7 changelog so the first post-deploy reading is recognizable as the fix working. The Spanish label "Última detección exitosa" stays true and is untouched.

**Rollback**: revert the commit, then `docker compose build && docker compose up -d` (never `restart` — it keeps the old image). Neither fix writes a row; the 403 fix *prevents* a write.

## Open Questions

- [ ] **Blocking before apply**: `specs/source-client/spec.md:26,30` must be amended per D2, or the implementation will ship a 5xx classification that contradicts `docs/spec-cliente-fuente-descubrimiento.md:65`.
- [ ] Declared open, not designed for: option (c) `MAX(detected_at) FROM chapter_history` as the meaning of "última detección exitosa" — rejected by owner decision in favour of (b).
- [ ] Non-goal, stays open upstream: distinguishing a source-throttling 403 from a Cloudflare 403 by cause (`docs/spec-cliente-fuente-descubrimiento.md:301`). The policy class is not visible at classification time — `client.py` receives only the `Transport` Protocol, and `cli.py:250-267,302-323` records that the intake never learns which class it is on.
