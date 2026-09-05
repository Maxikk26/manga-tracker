# Verify Report -- panel-v1b-fase-5, Slice 3 (Search + Todo) -- FINAL SLICE

**Date**: 2026-09-04
**Branch**: feat/panel-v1b-fase-5-search-todo @ 2826750
**Base**: main @ b104cdc
**Scope**: tasks 3.1-3.24. Task 3.25 (re-run the smoke after the PR merges) is a post-merge action and is correctly left unchecked -- not treated as incomplete.

This is the final slice of panel-v1b-fase-5 and of the panel's V1b phase.

## Contract read

- openspec/changes/panel-v1b-fase-5/specs/panel-bookmark-list/spec.md (11 requirements)
- openspec/changes/panel-v1b-fase-5/design.md -- D8, D9, D10, D13 (also D1 for the tab-role correction)
- openspec/changes/panel-v1b-fase-5/tasks.md -- slice 3 section
- docs/spec-panel-v1b.md (v1.11 -> v1.12 in this delivery)
- Engram sdd/panel-v1b-fase-5/spec (#465), .../design (#466), .../tasks (#467), .../apply-progress (#468)

## Per-task verdict (3.1-3.24)

| Task | Verdict | Evidence |
|---|---|---|
| 3.1 ALL_TAB/TabKey in types.ts | PASS | export const ALL_TAB = "all" as const; and TabKey = BookmarkStatus or typeof ALL_TAB present, read directly in source. |
| 3.2 filterBookmarks.ts (new) | PASS | NFD-normalize then strip combining marks then lowercase, substring match on title only, empty/whitespace query returns a copy of rows. Byte-level confirmation below. |
| 3.3 sortBookmarksForAll | PASS | BOOKMARK_STATUSES.flatMap over sortBookmarksForTab per status -- sortBookmarksForTab's own signature untouched. |
| 3.4 filterBookmarks.test.ts (new) | PASS | 10 tests: both accent directions, case-insensitive, substring-not-prefix, empty/whitespace returns everything, no-match returns empty array, no caller-array mutation, no caller-array identity. All pass (see Commands). |
| 3.5 sortBookmarksForAll RED/GREEN property test | PASS | Contiguity test + the per-status deep-equal-against-sortBookmarksForTab property test, both present in sortBookmarks.test.ts and green; guard-break 2 proves the property test is discriminating. |
| 3.6 StatusTabs.tsx rewrite | PASS | Six buttons, Todo first with BOOKMARK_STATUSES.reduce grand total, plain nav/button elements (no role=tablist/role=tab), aria-current set to "true" on the active tab and absent otherwise. Guard-break 1 proves the correction is load-bearing. |
| 3.7 tab-all / tab min-height CSS | PASS | Both rules present in styles.css (confirmed via grep, lines 220/230). |
| 3.8 container activeTab/query/filter-scope-sort chain | PASS | activeTab: TabKey state (default "reading"), query state, filtered = filterBookmarks(bookmarks, query), then sortBookmarksForAll/sortBookmarksForTab picked by activeTab === ALL_TAB, then applyFrozenOrder -- read directly in BookmarkListContainer.tsx. |
| 3.9 search row JSX, outside branches, unkeyed | PASS by inspection | The search-row div renders immediately after the loading/error early returns and before the visible-length-zero empty-state branch; it carries no key prop, so React never remounts it across renders. |
| 3.10 Agregar manga moved into search row | PASS | Button is the second child of search-row, opposite the search field; panel-toolbar does not appear anywhere in styles.css or the container (grep-confirmed absent). |
| 3.11 result count copy | PASS | Singular/plural counts with "titulo(s) en toda la lista" for Todo with no query, empty string per-tab with no query, "resultado(s) en tab" with a query -- verbatim, singular/plural and guillemet quoting present in source. |
| 3.12 three-way empty state | PASS | No-query branch: Todo shows one message, per-status shows another, no add control in either. Query branch shows the Sin resultados message plus a scope-jump button (hidden when activeTab === ALL_TAB). Guard-break 4 proves the two no-query/query message shapes are required to differ. |
| 3.13 BookmarkGrid.tsx empty branch removed | PASS | Confirmed by inspection: the component's own comment states the empty-state branch used to live here; no empty-state paragraph JSX remains, only the grid div. |
| 3.14 real showStatus wiring + Sin empezar copy | PASS | showStatus is computed once as activeTab === ALL_TAB in the container (closes 1.3/1.6's temporary false default); BookmarkCard.tsx renders the Sin empezar copy when last_chapter_read is null, with no hover/rest swap for that case. |
| 3.15 remaining search/result CSS | PASS | search-row, search-field, search-clear, result-count, empty-state button all present (grep-confirmed); chip-status five-tone palette confirmed still present, untouched. |
| 3.16 StatusTabs.test.tsx (new) | PASS | Six tabs render, Todo first with grand total 284 (48+4+28+162+42); active tab carries both tab-active and aria-current true; every inactive tab has aria-current absent (asserted via not.toHaveAttribute, not a false-string check); computed role stays button (queryAllByRole tab has length 0). All 6 tests pass. |
| 3.17 empty-tab-vs-empty-search discriminating case | PASS | Test renders a status with 0 bookmarks and no query, asserts the message does not carry guillemet quoting; then types a non-matching query in a non-empty tab, asserts the message does carry it in the Sin-resultados shape; asserts the two strings are never equal. Guard-break 4 reproduces the exact failure this test exists to catch. |
| 3.18 null-render discriminating case | PASS | A bookmark with last_chapter_read null renders the Sin empezar copy, never the literal string null, both from its own tab (Leyendo) and from Todo. |
| 3.19 scope-jump keeps query, refocuses | PASS | Clicking the scope-jump button sets activeTab to ALL_TAB (asserted via tab-active on the Todo button), leaves the typed query in the field, and the field has focus afterward. |
| 3.20 showStatus gated strictly on Todo | PASS by inspection and tests | showStatus = activeTab === ALL_TAB is the only assignment site; container test 3.18 exercises both tab contexts, and the card-level tests (1.12, carried forward) assert the pill/Al dia mutual exclusion. |
| 3.21 e2e smoke unmodified | PASS | git diff stat of main..HEAD for frontend/e2e/ is empty (reconfirmed independently below); playwright run of panel.smoke.spec.ts -- 1 passed. |
| 3.22 docs/spec-panel-v1b.md v1.12 | PASS | Version header bumped 1.11 to 1.12 (2026-09-04); Resumen "Pantalla principal" row corrected (no longer describes the retired plus-N pill); the tarjeta section's Implementado paragraph updated to name the popover/queue machinery instead of the retired progress editor and standalone select; fase-5 table row closed (all four done-criteria marked met); the four-open-decisions pendientes-abiertos item struck through and closed; one new changelog entry (1.12) covering slices 2a/2b/3. Full diff and pin cross-check below. |
| 3.23 npm test / npm run build green | PASS | 183/183 (19 files); build clean (tsc noEmit plus vite build, 53 modules). |
| 3.24 backend untouched-green | PASS | 606 passed, 1 pre-existing unrelated deprecation warning; zero manga_tracker files touched by this slice (confirmed via empty diff stat against main for that directory, see Commands). |
| 3.25 (out of scope) | Correctly unchecked | Explicitly a post-PR3-merge action per the task text and the session brief; not evaluated as incomplete work. |

All 24 in-scope tasks (3.1-3.24) verified complete and matching code state. No unchecked task blocks this slice's scope.

## Guard-break results

### 1. The role=tab trap (3.6) -- add role=tablist/role=tab to StatusTabs.tsx

Added role=tablist to the nav element and role=tab to both button variants (the Todo button and the five status buttons).

Result: real RED, exactly at panel.smoke.spec.ts line 35, exactly as predicted.

    Error: expect(locator).toHaveClass(expected) failed

    Locator: getByRole('button', { name: /abandonado/i })
    Expected pattern: /tab-active/
    Timeout: 5000ms
    Error: element(s) not found

      33 |   await expect(page.getByRole("dialog")).not.toBeVisible();
    > 35 |   await expect(page.getByRole("button", { name: /abandonado/i })).toHaveClass(
         |                                                                   ^
      36 |     /tab-active/,
      37 |   );

An explicit role=tab overrides the button element's implicit computed role, so getByRole("button", ...) finds zero elements -- this is the single most valuable break in this slice, since only the Playwright run catches it. Reverted with git checkout; rebuilt (the output bundle hash matched the pre-break build byte for byte) and re-ran the smoke: 1 passed again.

### 2. The global-partition bug (3.3/3.5) -- rewrite sortBookmarksForAll to a single global sort

Replaced the per-status flatMap with one global sort over the whole list (caught-up rows last, then title), reproducing the prototype's rejected global-partition approach.

Result: real RED, 2 of 24 tests in sortBookmarks.test.ts failed:

    FAIL sortBookmarksForAll > groups the output contiguously by BOOKMARK_STATUSES order
    AssertionError: expected an order starting with completed/dropped to deeply equal the order starting with reading/want_to_read

    FAIL sortBookmarksForAll > matches, per status, the output of that status own sortBookmarksForTab --
    the property that guards against the prototype global-partition bug ever creeping back in
    AssertionError: two on_hold rows came back in the opposite order from sortBookmarksForTab's own output

Both the contiguity test and the per-status equality property test caught the bug independently. Reverted with git checkout; re-ran: 24 of 24 passed.

### 3. The accent-folding range (3.2) -- corrupt COMBINING_MARKS to the Cyrillic block instead of combining diacriticals

Result: real RED, both directions, 2 of 10 tests in filterBookmarks.test.ts failed:

    FAIL matches a query without accents against a title that carries them
    AssertionError: expected an empty array to deeply equal an array containing "Aguila Roja" with its accent

    FAIL matches a query with accents against a title that carries different ones too
    AssertionError: expected an empty array to deeply equal an array containing "Aguila Roja" with its accent

With the wrong Unicode block, NFD-decomposed combining marks are never stripped, so an unaccented query no longer matches an accented title and vice versa. Reverted with git checkout; re-ran: 10 of 10 passed. Byte-level re-confirmation after revert is below.

### 4. The three-way empty state (3.12/3.17) -- collapse the empty-tab-no-query message into the empty-search message shape

Replaced the no-query branch's conditional text with the same guillemet-quoted shape the query-empty message uses, so the two collide.

Result: real RED, exactly at task 3.17's discriminating assertion, 1 of 14 tests in BookmarkListContainer.test.tsx failed:

    FAIL gives an empty tab with no query a message that never carries guillemet quoting, distinct from
    the "Sin resultados" message a non-matching query produces
    AssertionError: expected the no-query message not to match the guillemet-quote pattern, but it did

Reverted with git checkout; re-ran: 14 of 14 passed.

All four breaks produced real, informative failures -- none was a silent no-op.

## COMBINING_MARKS byte-level confirmation (task 3.2 own trap)

Dumped the raw bytes of the committed HEAD blob of frontend/src/domain/filterBookmarks.ts and the working-tree file independently, both before and after guard-break 3:

    COMBINING_MARKS = /[\u0300-\u036f]/g;

This is the literal ASCII byte sequence for a backslash followed by the letter u and four hex digits, twice over (start and end of the range) -- not the UTF-8 encoding of the actual combining marks themselves, which would appear as multi-byte sequences for each character in the class instead of the six-character escape text. Confirmed identical on the committed HEAD blob and the working tree, and re-confirmed byte-for-byte after guard-break 3's revert. This independently verifies the apply author's claim: the numeric escape sequences survived into the committed file; the JSON-decoding trap described (tool parameters silently decoding these escapes into raw Unicode combining characters) did not reproduce in the final artifact.

## Also confirmed by inspection

- 3.6 -- StatusTabs.tsx sets aria-current to the string "true" on the active tab and leaves the attribute absent otherwise; the component-test file explicitly asserts the attribute is absent (not a "false" string) on every inactive tab, matching the existing AppNav.tsx precedent.
- 3.9 -- confirmed the search-row JSX sits structurally before the loading and error early returns are reached (those are separate early-return branches above it in the render) and before the empty-results conditional; no key prop is present anywhere on the row or its children.
- 3.14 -- showStatus is a plain boolean derived once per render from the active tab and threaded through the grid into the card, closing out the false default from slice 1.
- 3.22 -- version header moved from 1.11 to 1.12, dated 2026-09-04; dependency pins (one-pager-v1a.md at 1.14, spec-modelo-de-datos.md at 1.9, decision-arquitectura-v1b.md at 1.2) independently re-verified against the actual version headers of those three files -- all three match exactly. The fase-5 table row is closed with all four done-criteria marked met; a new 1.12 changelog entry is present and correctly attributes slices 2a, 2b and 3 together, since neither 2a nor 2b carried its own docs task.

## Command results

| Command | Result |
|---|---|
| cd frontend and npm test | 183/183 passed, 19 test files |
| cd frontend and npm run build | Clean -- tsc noEmit then vite build; 53 modules |
| the venv python -m pytest -q | 606 passed, 1 warning (pre-existing, unrelated httpx/starlette deprecation notice) |
| npm run build then npx playwright test panel.smoke.spec.ts | 1 of 1 passed -- the duplicate-add-jumps-to-existing-tab scenario |
| git diff stat main..HEAD for frontend/e2e/ | Empty (confirmed before and after all guard-breaks) |
| git diff stat main..HEAD for manga_tracker/ | Empty (confirms task 3.24 untouched claim structurally, not just by test result) |

All commands green on the unbroken tree, both before the guard-breaks and reconfirmed after every revert.

## Slice-1 bookkeeping gap -- verified, not fixed

The apply-progress artifact and this session brief both describe the gap as tasks 1.14, 1.15 and 1.17 still unchecked. Direct inspection of the current tasks.md shows this undercounts by one: task 1.16 is also unchecked, alongside 1.14, 1.15 and 1.17 -- four boxes, not three:

    [ ] 1.14 keep the existing progress/score/status describe blocks in BookmarkCard.test.tsx unmodified this slice
    [ ] 1.15 docs/spec-panel-v1b.md to v1.11: record the two relevant sections as implemented
    [ ] 1.16 npm test and npm run build both green
    [ ] 1.17 the backend pytest suite untouched-green

Was the work actually done despite the unchecked boxes? Yes, on all four, verified independently against the historical commits rather than taken on faith:

- The slice-1 task-checkoff commit itself (short hash a8aa162, mark panel-v1b-fase-5 slice 1 tasks complete) states in its own message that core and RED/GREEN tests were done and verified with both frontend gates green and the backend suite untouched-green, and that tasks 1.14 through 1.17 are also satisfied by that same delivery but left unchecked per that apply session own explicit scope decision -- contemporaneous, first-party evidence that this was deliberate, not an oversight discovered later.
- Task 1.14: the diff of the slice-1 card-rewrite commit against BookmarkCard.test.tsx touches only the behind-pill describe block (replaced per tasks 1.10-1.12); no hunk touches the progress, score or status describe blocks, confirming they were left unmodified as required.
- Task 1.15: the docs commit from that same session (v1.11, the card ships as slice 1) shows docs/spec-panel-v1b.md was in fact bumped, and the current changelog carries the corresponding 1.11 entry naming the four-slice chain.
- Tasks 1.16 and 1.17: neither of those two slice-1 commits (nor any other slice-1 commit) touches any manga_tracker file, so untouched-green holds structurally; the checkoff commit own message additionally attests both gates were run and green at the time.

Verdict on the gap: the work was done; only the checklist bookkeeping is stale, and it is stale by one more line than previously reported (task 1.16, not just 1.14, 1.15 and 1.17). Recorded here per this session instruction -- not corrected, since flipping slice-1 checkboxes is outside this session assigned scope (3.1 through 3.25) and the orchestrator or maintainer owns that decision.

## Final tree state

git status --porcelain after all guard-breaks and reverts: only the untracked prototypes/ directory (pre-existing, untouched throughout). git diff --stat against the working tree is empty. No staged changes, no commits made, no branch switch -- still on feat/panel-v1b-fase-5-search-todo at commit 2826750.

## Verdict

PASS

- CRITICAL: 0
- WARNING: 1 -- the slice-1 bookkeeping gap is one task larger than reported (task 1.16 is also unchecked, not just 1.14, 1.15 and 1.17); the underlying work is confirmed done in all four cases, so this is a documentation-accuracy finding about the report of the gap, not a functional gap in the delivered code. No action taken, per this session explicit instruction not to fix it.
- SUGGESTION: 1 -- BookmarkGrid.tsx own prop-doc comment on showStatus still describes the container as not yet wiring the real Todo-tab value, which is now stale prose since the wiring landed in this slice; harmless, but a future reader of that file alone would be misled about the current state without cross-checking BookmarkListContainer.tsx.

All 24 in-scope tasks (3.1 through 3.24) are complete, checked off, and match the code as inspected. All four required guard-breaks produced real, informative failures when broken and clean, byte-identical reverts when restored. The COMBINING_MARKS byte-level trap this task exists for is independently confirmed absent from both the working tree and the committed HEAD blob. All four required commands pass with real counts, and the e2e smoke spec file is confirmed byte-identical to main. The tree was left exactly as found.

This closes the fourth and final slice of panel-v1b-fase-5 and the panel V1b design pass. docs/spec-panel-v1b.md v1.12 records all four fase-5 done-criteria as met, pending only the chain merge and joint deployment (task 3.25).

Recommendation: proceed to sdd-archive for panel-v1b-fase-5 once the four-PR chain has been reviewed and merged by the maintainer, and do not forget task 3.25 (re-running the smoke once more post-merge) and the slice-1 checkbox gap (now four boxes: 1.14, 1.15, 1.16 and 1.17) as the two remaining pieces of bookkeeping the orchestrator owns.
