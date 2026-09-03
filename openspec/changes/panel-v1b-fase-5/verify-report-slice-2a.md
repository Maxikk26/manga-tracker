# Verify Report -- panel-v1b-fase-5, Slice 2a

**Date**: 2026-09-03
**Branch**: `feat/panel-v1b-fase-5-popover-chapter` @ `3c12e09` (base `feat/panel-v1b-fase-5-card` @ `0311b1f`, itself based on `main`)
**Candidate**: 6 commits `85cf707..3c12e09`, `1206 insertions(+), 124 deletions(-)` against `main` (15 files) -- confirmed via `git diff --shortstat main..3c12e09`. Excluding the `openspec/` planning doc: `1176 insertions(+), 102 deletions(-)` across 14 code/test files (`git diff --shortstat 0311b1f..3c12e09 -- . ':!openspec' ':!prototypes'`).
**Scope**: Slice 2a ONLY -- tasks `2a.1`-`2a.22` in `openspec/changes/panel-v1b-fase-5/tasks.md`. Slice 1 is out of scope (already merged, independently verified, PASS). Slices 2b and 3 are out of scope; confirmed still fully unchecked (`[ ]`) in `tasks.md` -- no leakage.
**Review-driven development**: OFF by global decision. No `gentle-ai review` machinery was invoked. This is a plain SDD verify: source inspection plus real command execution plus targeted guard-breaks.

## Contract documents read

- `openspec/changes/panel-v1b-fase-5/specs/panel-bookmark-list/spec.md` (Engram `sdd/panel-v1b-fase-5/spec`, obs #465) -- 11 requirements.
- `openspec/changes/panel-v1b-fase-5/design.md` -- D1-D13, read in full from the filesystem copy.
- `openspec/changes/panel-v1b-fase-5/tasks.md` (Engram `sdd/panel-v1b-fase-5/tasks`, obs #467) -- read in full from the filesystem copy (authoritative, hybrid store).
- `sdd/panel-v1b-fase-5/apply-progress` (Engram obs #468) -- the implementer's own account, cross-checked against code rather than trusted at face value.

## Per-task verdict, 2a.1-2a.22

| Task | Verdict | Evidence |
|---|---|---|
| 2a.1 isCaughtUp export + applyFrozenOrder | PASS | `frontend/src/domain/sortBookmarks.ts:62-64` (isCaughtUp, `behind === 0`), `:102-121` (applyFrozenOrder, never mutates, appends unlisted, drops missing) |
| 2a.2 applyFrozenOrder tests | PASS | `sortBookmarks.test.ts:229-267` -- reorder, append-unlisted, drop-missing, empty-ids-noop, no-mutate. All 5 pass |
| 2a.3 Popover.tsx shell + test | PASS | `createPortal(..., document.body)` (`Popover.tsx:113-126`); `role="dialog"` + `aria-label={label}` present, no `aria-modal` attribute anywhere in the component (grep-confirmed); no focus trap. Test: `Popover.test.tsx:36-43` |
| 2a.4 dismissal rules | PASS | Escape (`handleKeyDown:97-99`), capture-phase outside click (`:79-95`), one-shot capture scroll (`:90`), focusout with real relatedTarget closes, null does not (`handleFocusOut:105-111`) |
| 2a.5 focus mgmt | PASS | First-field focus+select on open (`:61-64`); anchor-if-document.contains, else `.bookmark-grid` on close (`:65-71`) |
| 2a.6 BookmarkGrid tabIndex={-1} | PASS | `BookmarkGrid.tsx:41` |
| 2a.7 .pop CSS z-index: 10 | PASS | `styles.css:459` (`z-index: 10;`), comment at `:456-458` records the correction; `.modal-backdrop` confirmed `z-index: 20` at `styles.css:869` |
| 2a.8 z-index regression guard | PASS | `styles.contract.test.ts:46-56` asserts `.pop` is `z-index: 10` and never `30`, and `.modal-backdrop` is `20` |
| 2a.9 ChapterEditor.tsx + test | PASS | Uses DecimalInput (`ChapterEditor.tsx:99-105`), not `<input type="number">` -- confirmed `DecimalInput.tsx:61` renders `type="text"`; null-guard seed at `:33-35`; stepper commits immediately (step(), `:54-60`); typed commits on blur/Enter (`:62-80`); minus disabled at 0 (`:83,94`); hints verbatim (`:110-114`) |
| 2a.10 chapter trigger button | PASS | `BookmarkCard.tsx:150-168` -- `.chapter-rest`/`.chapter-full` CSS classes present for the hover swap (not testable in jsdom, per design's own caveat -- see Note below); `data-approx` (`:154`); hasTotal gates the swap (`:158`); opens Popover+ChapterEditor (`:179-191`) |
| 2a.11 onEditingChange(id, open) | PASS | `BookmarkCard.tsx:62-70` fires on both open and close; test `BookmarkCard.test.tsx:186-194` asserts `onEditingChange(42, true)` on open |
| 2a.12 shared isCaughtUp | PASS | `BookmarkCard.tsx:5` imports isCaughtUp, used at `:98`. Grepped the whole `frontend/src` tree for `behind === 0` / `behind===0` -- the only match is the definition inside `sortBookmarks.ts` itself. No surviving duplicate |
| 2a.13 editingId + frozenIds, last-open-wins | PASS | `BookmarkListContainer.tsx:30-31` (state), `:121-123` (handleEditingChange, exact last-open-wins setter from D3), `:170-181` (freeze capture/clear via applyFrozenOrder) |
| 2a.14 PATCH FIFO queue | PASS | tails/seqs Maps (`:35-36`), enqueuePatch (`:69-104`) -- chains onto `tails.current.get(id)`, conditional refetch gated on `seqs.current.get(id) === seq`, savingIds cleared only on the burst's last link |
| 2a.15 triggers not disabled while saving | PASS | `BookmarkCard.tsx:150-157` -- chapter trigger button has no `disabled` prop at all (confirmed by reading the JSX). Test: `BookmarkCard.test.tsx:208-211` explicitly renders with `saving: true` and asserts `not.toBeDisabled()` |
| 2a.16 Popover.test.tsx discriminating cases | PASS | 8 tests, including the named discriminating case "does nothing on a focusout whose relatedTarget is null" (`:93-106`) -- proven to actually discriminate via guard-break 3 below |
| 2a.17 ChapterEditor.test.tsx null-seed case | PASS | "seeds an empty field for a never-read bookmark, never the literal string null" (`:25-30`) -- proven to actually discriminate via guard-break 1 below |
| 2a.18 progress PATCH test rewritten to aria-label | PASS | `BookmarkListContainer.test.tsx:75-96` targets `getByRole("button", { name: /^Editar capitulo leido/ })`, not the old `getAllByTitle(/haz clic para editar/i)[0]` |
| 2a.19 write-queue discriminating test | PASS, with the documented deviation confirmed legitimate | `BookmarkListContainer.test.tsx:254-321`. The task as literally written ("resolve the second promise before the first") is impossible against a correctly-FIFO'd D5 implementation -- the second patchBookmark call is never dispatched until the first's cycle settles, so there is no "second deferred promise" to resolve early. The actual test proves the same guarantee by construction: asserts exactly 1 PATCH in flight before either resolves (`:297`, the assertion a naive unqueued implementation fails), then resolves in the only order the queue permits, then asserts exactly one refetch (`:313,319`) and the final displayed value is the later commit (`:314-318`, "cap. 1102"). Independently reproduced this session's own RED/GREEN cycle via guard-break 2 below |
| 2a.20 ordering-freeze test | PASS | `BookmarkListContainer.test.tsx:363-395` -- mid-edit position unchanged while caught-up (`:385`), re-sorts + focus returns to trigger on close (`:391-394`) |
| 2a.21 npm test + npm run build green | PASS | 156/156 tests, `tsc --noEmit` + `vite build` clean (full command output below) |
| 2a.22 pytest -q untouched-green | PASS | 606 passed -- no `manga_tracker/` file touched by this slice (git diff scope confirms) |

**Result: 22/22 PASS, 0 CRITICAL, 0 unchecked task.**

## Guard-breaks (the four called out by the orchestrator)

Each break was applied via a targeted, single-occurrence text patch, the focused test file was re-run to confirm RED, then `git checkout --` reverted the exact file, and the full suite was re-confirmed green before moving to the next break. The working tree was clean (`?? prototypes/` only) between every break.

### 1. Null seed (2a.17) -- ChapterEditor.tsx draft seed

**Break**: replaced `bookmark.last_chapter_read === null ? "" : String(bookmark.last_chapter_read)` with the unconditional `String(bookmark.last_chapter_read)`.

**Result: RED, exactly as predicted.**
```
FAIL  src/components/ChapterEditor.test.tsx > ChapterEditor > seeds an empty field for a never-read bookmark, never the literal string 'null'
AssertionError: expected 'null' to be '' // Object.is equality
- Expected: ""
+ Received: "null"
Tests  1 failed | 11 passed (12)
```
Reverted with `git checkout -- frontend/src/components/ChapterEditor.tsx`. The test genuinely covers the null-seed guard.

### 2. Write-queue staleness check (2a.19) -- BookmarkListContainer.tsx refetch gate

**Break**: removed the `if (seqs.current.get(id) === seq)` guard around the refetch, making `await load(false);` unconditional on every link.

**Result: RED, exactly as predicted.**
```
FAIL  src/containers/BookmarkListContainer.test.tsx > ... the PATCH write queue ...
AssertionError: expected 2 to be 1 // Object.is equality
- Expected: 1
+ Received: 2
  at line 305: expect(getCalls).toBe(1); // still no refetch: link 1's was skipped
Tests  1 failed | 9 passed (10)
```
The test failed on the "link 1's refetch is skipped" assertion (getCalls became 2 instead of staying at 1) -- confirming the staleness gate is what the test actually exercises, not incidental timing. Reverted with `git checkout -- frontend/src/containers/BookmarkListContainer.tsx`.

### 3. focusout with relatedTarget: null (2a.16) -- Popover.tsx dismissal guard

**Break**: removed the `if (related === null) return;` early-out in `handleFocusOut`.

**Result: RED, exactly as predicted.**
```
FAIL  src/components/Popover.test.tsx > Popover > does nothing on a focusout whose relatedTarget is null
AssertionError: expected "vi.fn()" to not be called at all, but actually been called 1 times
Tests  1 failed | 7 passed (8)
```
Reverted with `git checkout -- frontend/src/components/Popover.tsx`.

### 4. z-index correction (2a.8) -- styles.css .pop rule

**Break**: changed `.pop`'s `z-index: 10;` to `z-index: 30;` (PROTO's value, the one design D2 explicitly rejects because `.modal-backdrop` is `20`).

**Result: RED, exactly as predicted.**
```
FAIL  src/styles.contract.test.ts > styles.css contract > keeps the popover below the add-manga modal (design D2 z-index correction)
AssertionError: expected '...z-index: 30;...' to match /z-index:\s*10/
Tests  1 failed | 2 passed (3)
```
Reverted with `git checkout -- frontend/src/styles.css`.

**All four guards are real and discriminating.** No CRITICAL finding here: every targeted test failed for the exact reason the design/task called out, not for an unrelated reason.

## Command results

| Command | Result | Detail |
|---|---|---|
| `cd frontend && npm test` (initial, pre-guard-break) | GREEN | Test Files 17 passed (17), Tests 156 passed (156) |
| `cd frontend && npm run build` (initial) | GREEN | `tsc --noEmit` clean; `vite build` -- 52 modules transformed, dist/assets/index-*.js 213.57 kB |
| `./.venv/Scripts/python.exe -m pytest -q` | GREEN | 606 passed, 1 warning in 10.21s (warning is the pre-existing httpx/starlette.testclient deprecation notice, unrelated to this slice) |
| `cd frontend && npx playwright test panel.smoke.spec.ts` | GREEN | 1 passed (2.4s) -- ran against `npm run build`'s output and its own fixture server, per the runbook; the spec file itself is untouched (confirmed via the diff scope: `frontend/e2e/` does not appear in the 15 changed files) |
| `cd frontend && npm test` (final, post-revert) | GREEN | Test Files 17 passed (17), Tests 156 passed (156) -- identical to the initial run |
| `cd frontend && npm run build` (final, post-revert) | GREEN | identical to the initial run |

## Inspection-only confirmations (beyond the four guard-breaks)

- **2a.15**: chapter trigger button in `BookmarkCard.tsx:150-157` carries no `disabled` attribute in any branch; `BookmarkCard.test.tsx:208-211` explicitly renders with `saving: true` and asserts `not.toBeDisabled()`. Confirmed this reverses slice-1 behaviour: the score trigger (still InlineNumberEdit, slice 2b's job) keeps `disabled={saving}` at `BookmarkCard.tsx:172` -- the reversal is scoped correctly to only the new chapter trigger, as design D5 requires.
- **2a.12**: grep for `behind === 0` / `behind===0` over `frontend/src` returns exactly one match -- the definition inside `sortBookmarks.ts`. No surviving duplicate in `BookmarkCard.tsx` or elsewhere.
- **2a.9**: `DecimalInput.tsx:61` renders `<input type="text" inputMode="decimal" .../>` -- confirmed NOT `type="number"`.
- **2a.3**: `Popover.tsx:117-118` sets `role="dialog"` and `aria-label={label}` (Spanish product copy passed in from `BookmarkCard.tsx:182`, e.g. `Capitulo leido de ${bookmark.title}`); no `aria-modal` attribute exists anywhere in the file (grep-confirmed).

## Design coherence (D1-D13, slice-2a-relevant subset)

| Decision | Status | Note |
|---|---|---|
| D2 (popover placement/dismissal) | Followed | useLayoutEffect placement, all four dismiss triggers, non-modal (no aria-modal, no trap) |
| D3 (onEditingChange, last-open-wins) | Followed | Card owns open state + refs; container owns only `editingId: number \| null` with the exact setter from design |
| D4 (applyFrozenOrder) | Followed | Pure, id-based, never mutates, matches the three degrade-gracefully rules verbatim |
| D5 (PATCH queue, savingIds consequence) | Followed, with one documented and verified-legitimate test-writing deviation (2a.19, see above) | FIFO chain + burst counter implemented exactly as specced; triggers not disabled |
| D6 (focus sink) | Followed | .bookmark-grid tabIndex={-1}, anchor-or-grid focus-return rule |
| D9 (isCaughtUp single definition) | Followed | One export, one consumer set (sorter + card fade + chip) |
| D11 (DecimalInput reuse, null-seed guard) | Followed | Both editors' rule table matches; chapter half fully implemented this slice, score half correctly deferred to 2b |

## Scope leakage check

- tasks.md slice 2b (2b.1-2b.13) and slice 3 (3.1-3.25) remain fully unchecked ([ ]) -- verified by reading the file directly. No leakage.
- `BookmarkCard.tsx` still renders the standalone `<select className="status-select">` below the card (slice 1's temporary layout, explicitly deferred to 2b per design's own Slicing note) -- present and functioning, not prematurely removed.
- The score editor is still InlineNumberEdit (2b's job) -- confirmed untouched at `BookmarkCard.tsx:169-175`.
- `git diff --shortstat main..3c12e09` touches no file under `manga_tracker/`, `api/`, or `frontend/e2e/` -- matches the design's declared "may not touch" list for slice 2a.

## Size finding (carried forward from apply-progress, re-confirmed here, not re-litigated)

Actual diff is 1206/124 (15 files) against main, or 1176/102 (14 files) against the slice-1 base excluding the openspec doc -- against a 700-780 line forecast and an 800-line session cap. This verify pass re-confirms the number is accurate (independently computed via `git diff --shortstat`, not copied from the apply-progress claim) but does not re-litigate the decision: every one of the 22 tasks maps to real, tested code, no task was found padded or unnecessary, and the one place scope crept (premature 2b CSS) was already caught and reverted by the implementer before this commit landed (confirmed absent: no `.pop-select`/`.pop-scale`/`.pop-actions` selectors exist in the current styles.css). This is a WARNING for the orchestrator/maintainer's budget decision, not a CRITICAL blocking archive.

## Issues

**CRITICAL**: None.

**WARNING**:
1. Slice size (1206/124 vs 700-780 forecast, 800 cap) -- flagged by the implementer, independently re-confirmed here. Does not block correctness; is a review-workload risk the maintainer should explicitly accept (size:exception) or use to reconsider the forecast for 2b/3.

**SUGGESTION**: None.

## Working tree state (post-verify)

`git status --porcelain` -> `?? prototypes/` only. All four guard-breaks reverted via `git checkout --`; no other file modified; no commit, no push, no PR opened.

## Final verdict

**PASS.** 22/22 tasks complete and correct against design D2/D3/D4/D5/D6/D9/D11; all four targeted guard-breaks produced genuine RED failures for the exact reason predicted (no test was found to be non-discriminating); npm test (156/156), npm run build (tsc + vite clean), pytest -q (606 passed, untouched-green), and playwright test panel.smoke.spec.ts (1/1, unmodified) are all green both before and after the guard-break exercise. One WARNING (slice-size overage) carried forward for the maintainer's budget decision -- not a blocker for archiving this slice.

CRITICAL: 0 | WARNING: 1 | SUGGESTION: 0
