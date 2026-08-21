# Panel Reading History Specification

## Purpose

Read-side capability exposing `reading_history` and `chapter_history` to the panel: a reading heatmap aggregated by local calendar day, and a per-manga timeline interleaving readings with publications. Read-only — no new writes, no schema change.

## Requirements

### Requirement: Reading History Aggregation Endpoint

The system MUST expose `GET /api/history/reading`, aggregating `reading_history` by local calendar day over a trailing window of `days` days ending today (default 365 trailing days, not the calendar year). Each day's value MUST be the sum of `chapter_num - previous_chapter_num` deltas (chapters read, not edit count). Downward corrections (`chapter_num < previous_chapter_num`) MUST be excluded from the sum; they stay stored unfiltered — exclusion is read-side only.

#### Scenario: Default window is trailing, not calendar-year

- GIVEN today is 2026-08-21 and `days` is omitted
- WHEN a client calls `GET /api/history/reading`
- THEN the response covers the 365 days ending 2026-08-21, not since January 1

#### Scenario: A day's value sums chapter deltas, not edits

- GIVEN two edits on one local day, 175→190 and 40→42
- WHEN that day is aggregated
- THEN its value is 17, not 2

#### Scenario: A downward correction contributes zero

- GIVEN a bookmark corrected from chapter 50 down to 45 on a given day
- WHEN that day is aggregated
- THEN the correction adds nothing to that day's value

### Requirement: Local-Day Grouping Happens In The Backend, Before Aggregation, Via zoneinfo

The system MUST convert each UTC `read_at` to local time with Python `zoneinfo`, routed through `LOCAL_TIMEZONE` config (`manga_tracker/config.py`, default `America/Caracas`), BEFORE grouping by calendar day. The system MUST NOT use SQL date/time functions for this conversion.

#### Scenario: Hard bar — midnight crossing only in local time

- GIVEN a reading recorded at `2026-08-20T03:30:00Z`
- WHEN it is aggregated
- THEN it groups under `2026-08-19` (23:30 America/Caracas), not `2026-08-20`

### Requirement: Per-Manga History Endpoint

The system MUST expose `GET /api/mangas/{id}/history`, returning readings interleaved with `chapter_history` publications in chronological order, tagged by kind. The response/UI MUST note `chapter_history` was capped at `CHAPTER_HISTORY_LIMIT` at the one-time mapping backfill — earlier publications are absent — and the timeline MUST NOT claim completeness.

#### Scenario: Interleaved chronological timeline

- GIVEN a manga with both readings and detected chapters
- WHEN a client calls `GET /api/mangas/{id}/history`
- THEN both kinds appear in one chronological sequence, distinguishable by kind

#### Scenario: Late-mapped manga shows a partial timeline

- GIVEN a manga mapped after already reaching chapter 175 of a longer run
- WHEN its timeline is requested
- THEN the response/UI marks it partial since mapping, never complete

### Requirement: History Screen Reachable From The Primary Screen

The system MUST provide a second screen with the heatmap and per-manga timeline, reachable by a switch from the primary list screen. Visual format (buckets, colors, granularity, the "+N" pill's tone/size, any `cadence_days_estimate` display) is owner-reserved and out of scope, independent of this requirement.

#### Scenario: Switching screens

- GIVEN the primary list screen is open
- WHEN the user activates the history switch
- THEN the history screen renders using both endpoints above

### Requirement: E2E Smoke Coverage For The Last Phase-1 Debt

The system MUST have an automated Playwright smoke test covering the "Ver en «…»" tab-jump interaction — the one remaining phase-1 debt. The terminal-state regression debt is closed (PR #33, `test_panel_api.py:357`); do not relist it.

#### Scenario: Smoke passes locally

- GIVEN the panel is running with seeded data
- WHEN the Playwright smoke suite runs
- THEN the "Ver en «…»" jump is exercised and the suite passes

### Requirement: Spec Documentation Reflects One Remaining Test Debt

`docs/spec-panel-v1b.md` MUST be corrected to state phase 2 carries exactly one open test debt, versioned with a changelog entry.

#### Scenario: Doc no longer overstates debt

- GIVEN the document currently claims two open test debts for phase 2
- WHEN this change is applied
- THEN it states one, with a version bump and changelog line

## Known Limitation — Flagged For Owner, Not Resolved Here

Only downward corrections are excluded, so a large upward correction (e.g. 0→175) reads as marathon reading for one day. Manual adds cannot trigger this — `reading_history` is UPDATE-only; an add is an INSERT. No cap applies here; the exposure is recorded for the owner to decide treatment later.
