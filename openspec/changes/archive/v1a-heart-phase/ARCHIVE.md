# Archive report — v1a-heart-phase

Closed 2026-08-05. All 79 tasks resolved: implemented, or recorded as a deliberate
deviation or non-goal with its reason. Zero open items.

## What shipped

The V1a heart phase and everything that followed it into production: the SQLite
schema and its single capture trigger, the manganato source client with all three
operations, the manual seed loader, the shared detection rule, the Telegram digest,
the weekly heartbeat, `active_sweep`, `feed_check`, `onhold_sweep`, the dead-slug
notice, the orphaned-run reaper, the Kitsu importer with its catalogue behind a
contract, and the Docker deployment.

**In production on the mini-PC since 2026-07-30**, unattended. 347 tests.

## The three items closed without implementing them as written

Recorded here because an archive that hides them is worth less than one that
explains them.

- **2.6** — `job_runs` helpers were prescribed for `storage/repositories.py`; they
  live in `discovery/runs.py` beside the logic that uses them. All SQL is
  parameterized, which is the property the task existed to guarantee. Moving them
  now is a behaviour-free refactor of production code.
- **1.11** — the half that mattered is done: `conftest.py` blocks sockets suite-wide.
  Shared transport fixtures are declined: six suites each have a double tuned to
  what that file proves, and a single fixture would be the union of all of them.
- **6.8** — verified rather than implemented. `cffi` resolves to a prebuilt wheel,
  confirmed against the deployed image.

## What this change deliberately did not do

`reading_history` is at zero and stays there until a UI exists to edit reading
progress. The capture trigger fires on UPDATE only, and nothing updates progress
today. Recorded as an accepted risk in `one-pager-v1a.md` v1.9: the events of this
interval are lost for good, and the digest overstates the backlog a little more
each day. That makes progress editing the primary job of the V1b panel rather than
one of its screens.

## Where the truth lives now

`docs/` — always did. These artifacts were the plan; the specs are the contract.
`docs/spec-cliente-fuente-descubrimiento.md`, `spec-modelo-de-datos.md`,
`spec-bot-telegram.md`, `spec-seed-manual.md`, `spec-importador-kitsu.md` and both
runbooks describe what runs. Read those, not this folder.
