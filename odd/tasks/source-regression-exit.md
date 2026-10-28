# source-regression-exit

Locator: `odd/tasks/source-regression-exit.md` · Engram mirror: `odd/source-regression-exit/tasks`
Branch: `fix/source-regression-exit` (worktree `../manga-tracker-ratchet`, off `origin/main` f3684ba)

## Objective

Stop an inflated `manga_sites.latest_chapter_num` from muting a title forever, and stop notifying chapters the owner has already read.

## Problem (production audit 2026-10-28)

`discovery/detection.py:83` only moves `latest_chapter_num` up. When the stored value is itself wrong, every real chapter below it is dropped with a daily `observed N < stored M` warning:

- ms 93: stored 373 (bogus feed row 2026-08-26), source at 302, owner read 288 → 298–302 never notified.
- ms 199: stored 231, source at 164, owner read 154 → 158–164 never notified.
- ms 200: stored 560 (seed_backfill), source at 145.
- ms 160: likely the same (history jumps 584 → 1593), unverified.

Separately, the digest notifies chapters `<= last_chapter_read` (owner reads some titles elsewhere: The Steward 912 vs source 804, Return of the Mad Demon 216 vs 202).

## Decisions (owner, 2026-10-28)

- A sweep observation lower than the stored value lowers `latest_chapter_num` to the observed value. The feed never lowers it.
- Implemented without a schema change: the correction happens on the first sweep that observes the regression, not after 3 consecutive ones (a streak would need a column and a migration on the populated DB). Worst case of a transient truncated list is one duplicated digest line, which the project already accepts ("a duplicated alert is acceptable; a lost one is not").
- A chapter `<= last_chapter_read` is recorded and advances `latest_chapter_num` silently (like `on_hold`); it is never notified.
- `bookmarks.last_chapter_read` is never written by detection. Guarded by a test.

## Out of scope

Multi-source / sibling-slug lookup (`fetch_known_slugs`) stays V2. Heartbeat and watchdog pendings (audit says drop the migration; separate round). Bug B (feed nulls `latest_chapter_at`) and bug C (partial feed run without `error_summary`).

## Tasks

- [x] T1 Spec: `spec-cliente-fuente-descubrimiento.md` detection rule (step 2 special case), Pendientes #4 status, changelog + version bump, dependent pins; `spec-bot-telegram.md` if it states what gets notified.
- [x] T2 Ratchet exit in the detection rule, sweeps only, with tests (RED first).
- [x] T3 Read-progress silence with tests (RED first), including the `last_chapter_read` never-written guard.

Route: delegated direct, one writer (writer trigger: 2+ non-trivial files across docs, `detection.py`, sweep callers, tests).

## Checks

`uv run pytest -q` green at each task close. RDD: off (global) — ordinary checks only.

## Progress

- T1 — commit `54859d3` (route: delegated writer). `spec-cliente-fuente-descubrimiento.md` v1.12: step 2 split (sweeps lower, feed logs), step 5 read-progress silence + "detection never writes `bookmarks`", Pendientes #4 status (stalled slug stays V2; read > latest = read elsewhere), new `## Resumen` (debt the doc owed; runbook-mantenimiento v1.12 lowers the debt count 5 -> 4), feed cost 24 -> 48 runs/day fixed. Pins v1.11 -> v1.12 updated in place in 6 docs (precedent: pins are updated without bumping the pinning doc). `CLAUDE.md` rule rewritten. RED/GREEN: n/a (passive docs). Check: `uv run pytest -q` 632 passed (no code touched). `spec-bot-telegram.md`: pin only — it delegates "what is a novelty" to CD.
- T2 — commit `3d35483` (route: delegated writer). `detection.py`: `LOWERING_DETECTED_VIA = {active_sweep, onhold_sweep}`; a lower newest chapter from a sweep rewrites `latest_chapter_num/url/at`, logs WARNING old -> new with `manga_sites.id`, returns `NOTHING_DETECTED` (no history, no candidate, not in `updates_found`). Feed keeps the old warning. Terminal untouched (returns before the comparison). Verified the sweeps pass only `chapters[0]` to the rule; `chapters[1:]` go straight to history, so an older listed chapter never triggers a lowering (test added). RED: `tests/discovery/test_detection.py` 6 failed (`373.0 != 302`), sweep tests 2 failed (active 231->164, onhold 560->145). GREEN: discovery 148 passed; full suite 644 passed. Guard broken on purpose: adding `feed` to the set fails `test_the_feed_never_moves_the_stored_value_backward`.
- T3 (route: delegated writer). `detection.py`: `_already_read` (novelty `<= last_chapter_read`, null progress excluded) joins the `on_hold` silent branch: history row, immediate `latest_chapter_*` advance, `Detection(recorded=True)` with no candidate. RED: 5 failed (4 parametrized detection cases, 1 active_sweep digest case). GREEN: full suite 655 passed. Bookmark guard `test_detection_never_writes_the_bookmark` (5 scenarios incl. stored/read 912 vs source 804) checks the SQL trace, the row and `reading_history`; it passed before the change (guard, not RED) and was proven by breaking it: a same-value `UPDATE bookmarks` in step 1 fails all 5. Second break: returning a candidate from the silent path fails 7 tests. Both restored; suite 655 passed.

Next step: parent review; push/PR are the owner's call. Follow-ups not done here: `spec-bot-telegram.md` §Pendientes still says the #4 prior decision is open (pin-only update, no version bump); `spec-modelo-de-datos.md` describes `latest_chapter_num` as written by "la siembra, el feed, el barrido diario y el semanal" without the downward correction.
