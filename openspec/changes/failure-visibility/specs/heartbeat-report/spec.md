# Heartbeat Report Specification

## Purpose

The weekly heartbeat (`docs/spec-bot-telegram.md` §"Mensaje 2") claims whether `feed_check`/`active_sweep` are alive. This capability defines what evidence justifies that claim, so a healthy-looking message cannot rest on a run that never finished or examined nothing.

## Requirements

### Requirement: Last successful detection run requires finished, non-empty evidence

`last_successful_run_at` MUST report the `started_at` of the most recent `job_runs` row where `job_name` IN (`feed_check`, `active_sweep`), `status = 'ok'`, `finished_at IS NOT NULL`, AND `IFNULL(items_checked, 0) > 0` — the same three-condition shape `sweep_is_overdue` already applies (`manga_tracker/scheduler.py`). A row satisfying only `status = 'ok'` MUST NOT be sufficient evidence.

#### Scenario: In-flight run does not count

- GIVEN a `feed_check` row was opened (`status='ok'`, `finished_at` NULL) and has not closed
- WHEN the heartbeat computes `last_successful_run_at`
- THEN that row is excluded, even though its `status` is `'ok'`

#### Scenario: A run killed mid-sweep, left open forever, does not count

- GIVEN an `active_sweep` process died mid-run and its row stayed open (`finished_at` NULL) permanently
- WHEN the heartbeat computes `last_successful_run_at`
- THEN that row is excluded regardless of how long it stays open

#### Scenario: A finished run that examined nothing does not count

- GIVEN a `feed_check` row closed `status='ok'`, `finished_at` set, `items_checked = 0`
- WHEN the heartbeat computes `last_successful_run_at`
- THEN that row is excluded

#### Scenario: A finished run with items examined counts

- GIVEN an `active_sweep` row closed `status='ok'`, `finished_at` set, `items_checked > 0`
- WHEN the heartbeat computes `last_successful_run_at`
- THEN that row's `started_at` is reported

#### Scenario: No qualifying run ever occurred is reported truthfully

- GIVEN `job_runs` holds no row meeting all three conditions for `feed_check` or `active_sweep`
- WHEN the heartbeat renders the report
- THEN `last_successful_run_at` is `None` and the message states no successful run exists — truthful output, not a regression, even where an in-flight or killed row previously produced a timestamp under the old query

### Requirement: onhold_sweep stays excluded from the detection health signal

`onhold_sweep` MUST NOT contribute to `last_successful_run_at` or to `degraded_run_count`, unchanged by this fix. It notifies nothing, so its success is no evidence the notifying mechanisms are alive; counting it would mask dead `feed_check`/`active_sweep` runs behind a healthy-looking message.

#### Scenario: onhold_sweep success never substitutes for detection

- GIVEN `onhold_sweep` closed `status='ok'`, `finished_at` set, items examined, and no `feed_check`/`active_sweep` row ever qualifies
- WHEN the heartbeat renders the report
- THEN `last_successful_run_at` is still `None`

#### Scenario: onhold_sweep failures do not inflate degraded_run_count

- GIVEN `onhold_sweep` closed `status='error'` within the past 7 days
- WHEN the heartbeat computes `degraded_run_count`
- THEN that row is not counted

## Non-Normative Notes

- Doc bump: `spec-bot-telegram.md` v1.6 → v1.7 for this semantics correction; stale pins to fix: `runbook-mantenimiento.md:3`, `one-pager-v1a.md:170`.
- Owner prerequisite (not a system requirement): before closing this change, run `SELECT id FROM mangas WHERE TRIM(title) = ''` against production to confirm no empty-title row already landed from the sibling defect below.

## References

- docs/spec-bot-telegram.md §"Mensaje 2" ("última corrida de detección exitosa")
- manga_tracker/scheduler.py §"sweep_is_overdue"
