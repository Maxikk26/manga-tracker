# Verification Report: panel-v1b-fase-1

Verified 2026-08-17 against docs/spec-panel-v1b.md v1.0 (fase 1 scope), docs/decision-arquitectura-v1b.md v1.2, and CLAUDE.md conventions. Branch feat/panel-v1b, diff scoped against origin/main (43 files, +3797/-32).

## Test / build evidence

- ./.venv/Scripts/python.exe -m pytest -q -- 387 passed, 0 failed, exit 0 (1 unrelated httpx deprecation warning from starlette's TestClient).
- cd frontend && npm run build (tsc --noEmit && vite build) -- succeeded, exit 0, no type errors, produced dist/ (not committed; gitignored, workspace left clean afterward -- git status --porcelain empty).
- docker compose config -- merges cleanly: manga-tracker-panel inherits the image built by manga-tracker with no second build: key, PANEL_PORT resolves to a single 8000:8000 ingress mapping, depends_on: manga-tracker.

## Section 1 -- El corazon -- verdict: CONFORME

All bullets verified in manga_tracker/storage/repositories.py::update_panel_bookmark (lines 327-389) and covered by runtime tests in tests/web/test_panel_api.py:

| Requirement | Evidence | Test |
|---|---|---|
| origin='panel' correction, same transaction | with transaction(conn): ... UPDATE reading_history SET origin = 'panel' WHERE id > ceiling AND manga_id = ? | test_patch_progress_captures_a_reading_event_with_origin_panel |
| Ceiling mechanism, not last_insert_rowid() | MAX(id) captured before the UPDATE, corrected WHERE id > ceiling; docstring explicitly documents why last_insert_rowid() is wrong (matches the spec's corrected text: SQLite reverts it when the trigger program ends) | test_patch_correction_targets_the_trigger_row_not_last_insert_rowid -- seeds a pre-existing 'manual' row and proves only the new trigger row flips |
| WHEN-clause mirror in Python | trigger_fired = last_chapter_read is not UNSET and last_chapter_read is not None and last_chapter_read != current_progress, matching schema.sql:92 NEW.last_chapter_read IS NOT OLD.last_chapter_read AND NEW.last_chapter_read IS NOT NULL exactly | test_patch_status_only_creates_no_event_and_rewrites_no_origin, test_patch_with_the_unchanged_value_creates_no_event |
| progress_is_approx to 0 | assignments include "progress_is_approx = 0" unconditional on any progress edit | test_patch_progress_makes_it_exact_and_seals_last_read_at |
| last_read_at sealed UTC | _utc_now() produces %Y-%m-%dT%H:%M:%SZ, passed as now and written alongside the edit | same test, asserts .endswith("Z") |
| Downward edits recorded | No floor check anywhere in the write path | test_patch_accepts_a_downward_correction_and_records_it |
| Validation: enum | BookmarkStatus Enum built from BOOKMARK_STATUSES; FastAPI 422s outside it | test_list_rejects_a_status_outside_the_enum, parametrized 422 cases |
| Validation: >= 0 | Field(default=None, ge=0) on last_chapter_read | parametrized 422 case {"last_chapter_read": -1} |
| No cap vs latest_chapter_num | No such comparison exists in update_panel_bookmark or BookmarkPatch | test_behind_is_null_when_either_side_is_null_and_clamps_at_zero (case "C Ahead") proves reading past the detected chapter is accepted |
| Terminal-state edits harmless | Status-only PATCH to completed/dropped is a plain UPDATE; nothing downstream reads status to block it | not directly tested with completed/dropped specifically, but test_patch_progress_and_status_together exercises a status change end to end |

Direct-SQLite-edit path (trigger still writes 'manual', untouched) is explicitly preserved and pinned by the same trigger-targeting test.

## Section 2 -- API fase-1 rows -- verdict: CONFORME

- GET /api/bookmarks: returns exactly {id, manga_id, title, status, last_chapter_read, progress_is_approx, latest_chapter_num, latest_chapter_url, latest_chapter_at, behind, last_read_at} -- matches the spec row plus the computed behind field ("atraso calculado"). ?status= filters and 422s on an out-of-enum value (test_list_rejects_a_status_outside_the_enum).
- PATCH /api/bookmarks/{id}: progress and/or status, at least one required (_check_presence validator), 404 on unknown id with the id in the message, 422 on the seven invalid-body shapes tested (empty body, negative, non-numeric, explicit null on either field, out-of-enum status, unknown field latest_chapter_num -- confirming extra="forbid" blocks writes to source-side columns).

## Section 3 -- La frontera -- verdict: CONFORME, and genuinely enforced

- Confirmed zero sqlite3 imports outside storage/: web/app.py and web/__init__.py import only manga_tracker.storage.db and manga_tracker.storage.repositories, never sqlite3 directly -- test_third_party_confinement covers this generally (SQLITE_PACKAGE = "storage").
- DIRECTIONAL_RULES["web"] = {"sources.manganato", "notifier.telegram"} exists in tests/test_architecture.py line 27.
- Mechanism check, not just presence: test_boundary_check_flags_an_injected_violation builds a throwaway manga_tracker-named tree with web/probe.py containing an import of manga_tracker.notifier.telegram.TelegramSender, and asserts the violation scanner reports it -- this is a real inject-and-catch test, not a rule that can only pass vacuously (the file's own docstring calls out this repo's prior failure mode of a rule keyed on a prefix that could never match, and explicitly guards against it). test_directional_rules_actually_fire additionally proves the string-matching primitive itself can match a real import for every rule including web's.
- Both tests pass (part of the 387).
- La frontera's precision about fase 3 (web must not reach the source even indirectly, via catalogue/importer) has no code yet -- POST /api/mangas is fase 3 and out of scope; nothing to verify here, consistent with fase-1-only delivery.

## Section 4 -- Topology (Decisiones de plataforma) -- verdict: CONFORME

- docker-compose.yml: manga-tracker-panel has no build key and reuses the same image as manga-tracker (verified live with docker compose config, which merges the two services with manga-tracker-panel correctly inheriting the built image -- no second build). depends_on points at manga-tracker.
- PANEL_PORT is a single knob: the ports mapping uses the same PANEL_PORT variable on both sides of the colon -- docker compose config resolves this to one 8000:8000 ingress mapping, confirming both ends move together.
- Dockerfile: three stages (build, frontend-build, runtime). The runtime stage copies the venv from the build stage and only the compiled dist folder from the frontend-build stage -- the Node binary itself never lands in the runtime image, matching the existing precedent of uv and pytest staying out (same file, same comment pattern).
- manga_tracker/cli.py's panel command handler binds uvicorn to host 0.0.0.0 and config.panel_port; config.panel_port defaults to 8000 in manga_tracker/config.py. Covered by a CLI wiring test and a config default/override test.
- busy_timeout: both the scheduler's connections and the panel's request-scoped connections go through the single storage/db.py connect() function, which issues PRAGMA busy_timeout = 5000 -- confirmed by direct read of db.py and the fact that web/app.py imports and calls this same connect, not a bespoke one.

## Section 5 -- Language rules -- verdict: CONFORME

- Frontend UI copy is neutral-tu Spanish throughout (StatusTabs.tsx, BookmarkTable.tsx, BookmarkRow.tsx, InlineNumberEdit.tsx, BookmarkListContainer.tsx, api/bookmarks.ts): imperative and second-person forms are consistently tu-conjugated (haz clic, intenta de nuevo, cargando, esta corriendo el panel). Zero voseo forms anywhere in frontend/src.
- Code, identifiers, comments and tests are English throughout manga_tracker/web/, the panel family in manga_tracker/storage/repositories.py, tests/web/, and the TS/TSX source (identifiers, comments, JSDoc).
- Domain terms (last_chapter_read, progress_is_approx, origin, statuses) stay verbatim, un-translated, exactly per convention.

## Section 6 -- Test quality -- verdict: PARCIAL

The backend test suite genuinely pins the three riskiest behaviors named in the spec:
- Trigger-row targeting with a decoy: test_patch_correction_targets_the_trigger_row_not_last_insert_rowid seeds a real pre-existing manual-origin row via a direct SQLite UPDATE, then applies a panel PATCH, and asserts the decoy keeps its manual origin while only the new row becomes panel. This is the strongest test in the suite and directly falsifies the spec's original, superseded last_insert_rowid claim.
- Status-only edit not corrupting origin: test_patch_status_only_creates_no_event_and_rewrites_no_origin -- pinned.
- Unchanged-value no-op: test_patch_with_the_unchanged_value_creates_no_event -- pinned.

Untested risky path (backend): no test PATCHes a bookmark already in completed or dropped to confirm the terminal-states-edit-harmlessly rule holds specifically for a progress edit on an already-terminal row (only a combined progress+status transition into completed is tested, not an edit of an already-terminal one). Low risk since the code path is unconditional on status, but the spec calls this bullet out explicitly and it has no dedicated regression test. WARNING, not CRITICAL.

Frontend has zero test files (no *.test.* or *.spec.* files anywhere under frontend/src, and package.json has no test script). This let two real wire-contract mismatches ship undetected, both invisible to tsc --noEmit because they are runtime/JSON-shape mismatches rather than static ones (the fetched JSON is cast to the Bookmark type, never validated at runtime):

1. progress_is_approx type and runtime mismatch. The domain type declares this field as the numeric union 0 or 1, but the API returns a real JSON boolean (confirmed live against the running app: the field serializes as true or false, not 0 or 1). The row component checks this field with strict equality against 1, which is false for every possible wire value. Net effect: the approximate-progress marker in the row component never renders, for any bookmark, ever. WARNING -- cosmetic, not data-affecting; the backend correction of progress_is_approx to 0 on edit is correct and independently tested.
2. last_chapter_read nullability mismatch. The schema column is nullable, and the seed loader's own documented behavior confirms a reading-status bookmark with no chapter recorded is a legitimate, occurring production state -- the seed loader's comment says outright that such a row "loads perfectly well" with a null progress. The domain type declares this field as a non-nullable number, and the inline editor coerces the raw value to a string unconditionally. For a bookmark whose progress is null, the progress cell will display the literal text "null" instead of empty or placeholder text. WARNING -- real, reachable, currently-undetected UI defect; not a data-integrity or spec-compliance issue on the write side, but exactly the class of bug a single frontend rendering test would have caught, and none exist.

Both findings were verified directly against the running FastAPI app via an ad hoc probe script, and against schema.sql and the seed loader's source, not inferred from reading types alone.

## Section 7 -- Refactor findings (severity-tagged, no fixes applied)

- SUGGESTION -- manga_tracker/web/app.py: both endpoint handlers open and close their own connection per request rather than using a shared dependency or lifespan-scoped connection. Consistent with the module's stated one-connection-per-request discipline (mirrors the scheduled jobs'), so this is idiomatic for the codebase, not a defect -- flagged only because a FastAPI dependency could express the same open/close discipline more declaratively if the endpoint count grows in fase 2/3.
- SUGGESTION -- BookmarkListContainer.tsx refetches the entire bookmark list after every single PATCH rather than merging the PATCH response, which already returns the full updated bookmark, into local state. Correct per its own comment that the server stays the only source of truth for derived fields, and at roughly 230 rows on a LAN this is genuinely cheap -- but worth naming now because fase 2/3 growth would make the full-list-refetch-per-edit pattern the first thing to revisit.
- WARNING (restated from Test quality above as a code finding) -- the frontend Bookmark type does not match the actual wire shape for two fields. This is a type-honesty defect: the interface is trusted at every call site with no runtime validation, so the mismatch is silent until checked against real data.
- SUGGESTION -- update_panel_bookmark's docstring is excellent: it documents the falsified last_insert_rowid claim, cites the SQLite version verified against, and explains the WHEN-clause-mirror rationale. Flagged positively as the pattern worth repeating in fase 2/3 endpoints, not a defect.
- No dead code, no duplication, no over-engineering found in the fase-1 backend or frontend. The shared SELECT plus row-mapper reused by both the list and single-bookmark reads is a clean, minimal abstraction, not premature.

## Accepted deviation (not reported as a defect)

Per session context: the spec's original last_insert_rowid mechanism was proven false; spec-panel-v1b.md v1.0 itself now documents the corrected MAX-id-ceiling mechanism in its El corazon section. The implementation matches this corrected spec text exactly, including the WHEN-clause-mirror caveat. Confirmed by direct comparison of the spec prose against update_panel_bookmark's docstring and code -- they agree on the mechanism and its justification.

## Final verdict

PASS WITH WARNINGS. Zero CRITICAL findings. The core corazon mechanism (origin correction, trigger-row targeting, validations, terminal-state safety) is correctly implemented and strongly tested at the backend level; the architecture boundary is genuinely enforced with an inject-and-catch test, not a vacuous rule; topology matches the spec's owner-decided isolation exactly; language conventions are followed throughout. The findings that keep this from a clean PASS are two real, if cosmetic-to-moderate, frontend wire-contract bugs plus the complete absence of frontend tests that would have caught them, and one untested-but-low-risk terminal-state-progress-edit path on the backend.

## Fase-1 done-criterion (spec table)

The spec's stated done-criterion for fase 1 is a real edit made from a browser appearing in reading_history with origin panel, with the next digest using the new value. This is not verifiable from static or test evidence alone -- it requires an actual production edit and is an operational verification step for the deploying owner, not something this review can attest to from the repository. Flagged as an operational follow-up, not a code defect.
