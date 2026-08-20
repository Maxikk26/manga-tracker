# Archive report — panel-v1b-fase-1

Moved here **2026-08-20**. Fase 1 shipped and deployed on **2026-08-18**, in its own
container, serving on the LAN.

## Why this folder holds one file

`verify-report.md` is the **only** artifact this change ever had in the SDD store. There
is no proposal, no design, no tasks, no apply-progress, and no delta spec. That is not a
loss — they were never written. Fase 1 was implemented directly against
`docs/spec-panel-v1b.md` v1.0, which was written the same week and already carried the
scope, the endpoints, the topology and the done-criterion. The verify phase was the only
SDD phase that ran, and its output was committed on its own in `f898144`
(*"docs: persist the sdd-verify report for panel fase 1"*), 91 lines, nothing else in the
commit.

The folder was left under `openspec/changes/` for two days, where an unarchived directory
means "a change is in flight". It is not; it is a finished delivery with one surviving
record. Moving it here stops it from reading as work in progress.

**The file is preserved byte-identical and must not be deleted.** It is the only record of
that verify pass, and its findings are still load-bearing — see below.

## What the report says

Verified 2026-08-17 against `docs/spec-panel-v1b.md` v1.0 (fase 1 scope) and
`docs/decision-arquitectura-v1b.md` v1.2, on branch `feat/panel-v1b`, 43 files,
+3797/-32. Evidence at the time: 387 backend tests passing, `npm run build` clean,
`docker compose config` merging with `manga-tracker-panel` inheriting the built image and
no second build.

Final verdict: **PASS WITH WARNINGS**, zero CRITICAL findings. Five of the seven sections
came back CONFORME (the `reading_history` origin-correction mechanism, the fase-1 API
rows, the architecture boundary, the container topology, the language rules). Section 6,
test quality, came back **PARCIAL**.

## Why the PARCIAL still matters

Section 6 is where the regression-test debt this project still carries traces back to.
Three findings, all of which outlived the report:

1. **The frontend had zero test files.** No `*.test.*` or `*.spec.*` anywhere under
   `frontend/src`, and no `test` script in `package.json`. That absence is what let the
   next two findings ship undetected.
2. **`progress_is_approx` wire-contract mismatch.** The domain type declared the numeric
   union `0 | 1`; the API returned a real JSON boolean. The row component compared it
   with strict equality against `1`, which is false for every possible wire value, so the
   approximate-progress marker never rendered for any bookmark. Invisible to
   `tsc --noEmit`, because the fetched JSON was cast to the type and never validated at
   runtime.
3. **`last_chapter_read` nullability mismatch.** The column is nullable and a
   reading-status bookmark with no chapter recorded is a documented, occurring production
   state, but the domain type declared the field non-nullable and the inline editor
   coerced it to a string unconditionally — so such a row displayed the literal text
   `null`.

Both wire mismatches were confirmed against the running app, not inferred from reading
types. They are the reason
`docs/spec-panel-v1b.md` §"Decisiones de plataforma" now mandates **Vitest + React
Testing Library from fase 1 onward**, naming "the exact class of defect the SDD
verification found twice".

The fourth finding is still open as scheduled work: **no backend test PATCHes a bookmark
already in `completed` or `dropped`** to confirm the terminal-states-edit-harmlessly rule
holds for a progress edit on an already-terminal row. It is carried in
`docs/spec-panel-v1b.md` §"Fases y criterios de terminado" as part of fase 2's contents
("el test de regresión pendiente"), which is where it is still owed.

## The done-criterion the report could not attest to

The spec's fase-1 done-criterion is a real edit made from a browser appearing in
`reading_history` with `origin='panel'`, with the next digest using the new value. The
report correctly refused to claim it: that is operational verification by the deploying
owner, not something a repository review can attest to. It was satisfied by the
2026-08-18 deployment.

## Where the truth lives now

`docs/spec-panel-v1b.md` — the contract fase 1 was built against and the only document
that decides what the panel does. `README.md` §Estado carries the delivery date.
