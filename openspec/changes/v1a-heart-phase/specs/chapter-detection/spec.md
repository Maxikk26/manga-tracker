# Chapter Detection Specification

## Purpose

The shared detection rule and the two mechanisms in scope this phase — `feed_check` (hourly) and `active_sweep` (daily, primary mechanism) — plus notify-before-update orchestration and the dead-slug counter (spec-cliente-fuente-descubrimiento.md Parte B).

## Requirements

### Requirement: One detection rule, shared by every mechanism

All mechanisms MUST route every observed chapter through the same sequence: seal `last_checked_at` (always), compare against `latest_chapter_num`, record the publication, then branch by bookmark state (spec-cliente-fuente-descubrimiento.md §"La regla de detección").

#### Scenario: last_checked_at sealed even without novelty

- GIVEN an observed chapter number is less than or equal to `latest_chapter_num`
- WHEN detection runs
- THEN `last_checked_at` is updated and no further action is taken

### Requirement: A lower observed number is never written backward

If the observed chapter number is strictly less than the stored `latest_chapter_num`, the system MUST log it as a probable renumber/deletion and MUST NOT move the stored value backward.

#### Scenario: Renumbered source

- GIVEN the source now reports chapter 40 for a manga stored at `latest_chapter_num=45`
- WHEN detection compares
- THEN the event is logged and `latest_chapter_num` remains 45

### Requirement: chapter_history is written regardless of notification

The observed chapter MUST be inserted into `chapter_history` with its `detected_via` value before any notification decision is made, independent of whether a notification is later sent (spec-modelo-de-datos.md handoff 1; spec-cliente-fuente-descubrimiento.md step 3).

#### Scenario: History recorded even when notification later fails

- GIVEN a new chapter is detected for an active manga
- WHEN detection records the publication
- THEN the `chapter_history` row exists regardless of the digest send outcome that follows

### Requirement: Branch by bookmark state

`reading`/`want_to_read` MUST become notification candidates accumulated for the run's digest; `on_hold` MUST update `latest_chapter_num`, `latest_chapter_url`, and `latest_chapter_at` immediately and silently, never notifying; `completed`/`dropped` MUST be fully ignored — no update, no history — and MUST receive zero requests, ever (spec-cliente-fuente-descubrimiento.md step 4; spec-modelo-de-datos.md §4).

#### Scenario: on_hold updates silently

- GIVEN an on_hold manga has a new chapter observed via feed
- WHEN detection branches
- THEN the mapping updates immediately and no digest candidate is added

#### Scenario: Terminal states consume nothing

- GIVEN a manga's bookmark is `completed` or `dropped`
- WHEN `active_sweep` builds its population
- THEN that mapping is excluded and receives no request in the run

### Requirement: Notify before update

For active-manga candidates, `latest_chapter_num` and related fields MUST advance only after the digest send succeeds; a failed send MUST leave every included mapping untouched and the run MUST close as `partial` (spec-cliente-fuente-descubrimiento.md §"Orden de operaciones: notificar antes de actualizar").

#### Scenario: Successful send advances fields

- GIVEN a run accumulated 2 active-manga candidates
- WHEN the digest send succeeds
- THEN both mappings' `latest_chapter_num`/url/at advance and `job_runs.notifications_sent` reflects the count

#### Scenario: Failed send advances nothing

- GIVEN a run accumulated 1 active-manga candidate
- WHEN the digest send fails
- THEN `latest_chapter_num` for that mapping is unchanged and the run closes with `status=partial`

#### Scenario: No candidates means silence

- GIVEN a run finds zero active-manga candidates
- WHEN the run closes
- THEN no digest is requested

### Requirement: feed_check

`feed_check` MUST run hourly, call `fetch_latest_feed` once, match items by (site, `source_key`), route matches through the shared rule with `detected_via=feed`, and MUST leave `source_published_at` null for feed-sourced `chapter_history` rows (spec-cliente-fuente-descubrimiento.md §"Mecanismo 1").

#### Scenario: Feed match sets detected_via=feed with null timestamp

- GIVEN a feed item matches a tracked mapping
- WHEN it is recorded
- THEN `chapter_history.detected_via='feed'` and `source_published_at` is null

### Requirement: active_sweep is the primary mechanism

`active_sweep` MUST run daily against every mapping whose bookmark is `reading`/`want_to_read` and has a slug, MUST exclude mappings paused by the dead-slug counter, MUST call `fetch_chapters` per mapping with the request-policy delay, compare only the newest chapter via the shared rule with `detected_via=active_sweep`, and MUST still write the remaining returned chapters to `chapter_history` idempotently (spec-cliente-fuente-descubrimiento.md §"Mecanismo 2").

#### Scenario: Full response written, only newest compared

- GIVEN `fetch_chapters` returns 50 chapters for a mapping
- WHEN `active_sweep` processes it
- THEN only the newest is compared for novelty, and all 50 are written to `chapter_history` (duplicates ignored)

### Requirement: Dead-slug counter

`consecutive_failures` MUST increment only on a not-found classification, MUST reset to 0 on any success, and a mapping at ≥5 MUST be skipped by `active_sweep` without consuming a request (spec-cliente-fuente-descubrimiento.md §"Slugs muertos" steps 1-2, 4).

#### Scenario: Not-found increments, transient does not

- GIVEN a mapping has `consecutive_failures=2`
- WHEN `fetch_chapters` returns a transient error
- THEN `consecutive_failures` remains 2

#### Scenario: Any success resets the counter

- GIVEN a mapping has `consecutive_failures=4`
- WHEN `fetch_chapters` succeeds
- THEN `consecutive_failures` resets to 0

#### Scenario: Threshold pauses the mapping

- GIVEN a mapping reaches `consecutive_failures=5`
- WHEN the next `active_sweep` runs
- THEN that mapping is skipped and consumes no request

### Requirement: No automatic retry or notice for a paused mapping in this phase

This phase MUST NOT provide any low-frequency retry mechanism (`onhold_sweep`) or Telegram dead-slug notice for a mapping paused at the threshold; the pause MUST remain visible only via `job_runs` and logs, with repair being manual (one-pager-v1a.md §"Fases internas de V1a"; v1a-heart-phase proposal "Scope — out").

#### Scenario: Paused mapping has no recovery path this phase

- GIVEN a mapping is paused at `consecutive_failures=5`
- WHEN subsequent runs of `feed_check` and `active_sweep` execute
- THEN nothing retries that mapping automatically and no Telegram message announces the pause

### Requirement: Run recording and overlap guard

Every mechanism MUST open a `job_runs` row at start and close it with `status` (`ok`/`error`/`partial`), `items_checked`, `updates_found`, `notifications_sent`, and `error_summary`; a job MUST NOT start a new run while a prior run of the same `job_name` is still open (spec-cliente-fuente-descubrimiento.md §"Registro de corridas", "Solapamiento").

#### Scenario: Overlapping run is skipped

- GIVEN `active_sweep`'s previous run has no `finished_at`
- WHEN the scheduler triggers a new `active_sweep` run
- THEN the new run is skipped and logged, and the prior row is left as-is

## References

- spec-cliente-fuente-descubrimiento.md v1.2
- spec-modelo-de-datos.md v1.6
- one-pager-v1a.md v1.5
