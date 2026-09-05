# Verify Report -- `panel-v1b-fase-5`, Slice 2b (Score editor + status row + deletions)

**Date**: 2026-09-03
**Branch**: `feat/panel-v1b-fase-5-popover-score` @ `7b727b0`
**Base**: `feat/panel-v1b-fase-5-popover-chapter` @ `7a26119`
**Scope**: tasks 2b.1-2b.13 only. Slice 3 (3.1-3.25) is untouched and out of scope, confirmed still unchecked in `tasks.md`.

## Contract read

- `openspec/changes/panel-v1b-fase-5/specs/panel-bookmark-list/spec.md` (11 requirements)
- `openspec/changes/panel-v1b-fase-5/design.md` -- D3, D4/D5 (context), D11, D12, D13
- `openspec/changes/panel-v1b-fase-5/tasks.md` -- slice 2b section
- Engram `sdd/panel-v1b-fase-5/apply-progress` (#468) and `sdd/panel-v1b-fase-5/tasks` (#467)

## Per-task verdict (2b.1-2b.13)

| Task | Verdict | Evidence |
|---|---|---|
| 2b.1 `ScoreEditor.tsx` + test | PASS | `DecimalInput` + `/10` + `Quitar puntuacion`; draft seeded `value ?? ''` on open only (guard-break 3 proved this is load-bearing); blur/Enter commit; blank to `null` and close; out-of-range rejected; rounds to integer; unchanged fires nothing. 12 tests in `ScoreEditor.test.tsx`, all green. |
| 2b.2 Score trigger in `BookmarkCard.tsx` | PASS | `scoreEditor()` button, `No puntuado` / `{my_score}/10`, opens `Popover`+`ScoreEditor`, `open: "score"`, `onEditingChange` fired -- read directly in source and exercised by `BookmarkCard.test.tsx`'s `score` describe block (6 tests, green). |
| 2b.3 Status row in `ChapterEditor.tsx` | PASS | `.pop-status` wrapper, `Estado` label, `.pop-select`, `aria-label` verbatim, `onChange` calls `onCommitStatus` then `onRequestClose` (Q4) -- read in source, guard-break 4 confirms the byte-identical label is load-bearing. |
| 2b.4 Remove standalone `<select className="status-select">` | PASS -- this is the deploy unblocker | Confirmed absent from `BookmarkCard.tsx` by inspection. Guard-break 1 (re-adding it) produced a real, informative red (see below): would have been a CRITICAL finding had it NOT gone red -- it did. |
| 2b.5 Delete `InlineNumberEdit.tsx` (+test) | PASS | Files do not exist (glob/ls confirms). `rg -n "InlineNumberEdit" frontend/src` returns exactly one hit: a historical comment in `BookmarkCard.test.tsx:30`, no import/JSX anywhere. |
| 2b.6 Drop dead CSS selectors | PASS | `rg -n "status-select|progress-display|progress-input|approx-marker" frontend/src/styles.css` returns zero matches. |
| 2b.7 `ScoreEditor.test.tsx` RED/GREEN + documented deviation | PASS (deviation accepted, see adjudication below) | Both the adapted `-1` test and the new blur-race regression are present and pass; guard-break 2 reproduces the exact race described (2 commits: stray `5`, then `null`). |
| 2b.8 `ChapterEditor.test.tsx` status-commits-and-closes | PASS | Test present ("a status change commits the new status and closes the popover"); confirmed it depends on the exact `aria-label` via guard-break 4 (went red when the label changed). |
| 2b.9 `BookmarkCard.test.tsx` rewrite | PASS | Zero remaining `getAllByTitle(/haz clic para editar/i)` in the file; no tilde/em-dash assertions found; "No puntuado" assertion present in the score describe block; standalone status describe block confirmed retargeted to go through the chapter popover. |
| 2b.10 `BookmarkListContainer.test.tsx` rewrite | PASS | Score-PATCH and score-clear tests use `screen.getByRole("textbox", { name: /Puntuacion de 0 a/ })`, not the old title selector; zero `getAllByTitle` hits in the file. |
| 2b.11 Grep confirmation | PASS | Independently reproduced: `rg -n "InlineNumberEdit" frontend/src` returns 1 hit, the historical test comment, no live code. |
| 2b.12 `npm test` + `npm run build` green | PASS | 160/160 tests, build clean (see Commands below). |
| 2b.13 backend suite untouched-green | PASS | 606 passed (see Commands below). |

All 13 tasks confirmed complete and matching code state. No unchecked tasks in scope.

## Guard-break results

### 1. The deploy unblocker (2b.4) -- re-add standalone `<select className="status-select">`

Re-inserted the exact old task-1.4 markup as a sibling directly after `</article>` in `BookmarkCard.tsx` (same `aria-label={` + "`Estado de ${bookmark.title}`" + `}` as the one now living inside the popover).

**Result: real RED.** `npm test` dropped from 160/160 to 159/160 passing. The failure:

```
FAIL src/components/BookmarkCard.test.tsx > status (fase 5 slice 2b -- now inside the chapter
popover, design D12) > fires onChangeStatus with the bookmark id and closes the popover

TestingLibraryElementError: Found multiple elements with the role "combobox" and name
"Estado de One Piece"
  at BookmarkCard.test.tsx:285 -- screen.getByRole("combobox", { name: "Estado de One Piece" })
```

Two comboboxes now share the identical accessible name (the stray standalone one plus the popover own), so `getByRole` throws on ambiguity instead of silently picking one. This is not a footnote finding -- it is confirmed automated cover for the single change that makes the panel deployable. Reverted with `git checkout`; re-ran `npm test` and confirmed 160/160 green again.

### 2. The blur-commit race (2b.7) -- remove the `onMouseDown` guard in `ScoreEditor.tsx`

Removed `onMouseDown={(event) => event.preventDefault()}` from the `Quitar puntuacion` button.

**Result: real RED**, reproducing exactly what the apply author documented:

```
FAIL ScoreEditor.test.tsx > clicking Quitar puntuacion while the field is focused with an
uncommitted edit does not fire a stray blur-commit first -- exactly one commit (null) reaches
the caller

AssertionError: expected "vi.fn()" to be called once with arguments: [ null ]
Received: 1st call [5], 2nd call [null]   (2 calls total)
```

Two commits instead of one: the stray blur commits the uncommitted `5` first, then the click own `null`. Reverted; `ScoreEditor.test.tsx` back to 12/12 green.

### 3. The null seed (2b.1) -- seed draft as `String(value)` instead of `value ?? ''`

Changed the seed expression from `bookmark.my_score === null ? "" : String(bookmark.my_score)` to plain `String(bookmark.my_score)`.

**Result: real RED**:

```
FAIL ScoreEditor.test.tsx > seeds an empty field for an unscored bookmark, never the literal
string 'null'

AssertionError: expected 'null' to be ''
```

The field renders the literal string "null" exactly as the guard is meant to prevent. Reverted; green again.

### 4. The verbatim status `aria-label` (D12) -- change it in `ChapterEditor.tsx`

Changed the status select label from Estado-de-title to Status-of-title (an English replacement string, still template-literal-shaped, changing only the wording).

**Result: real RED -- 3 tests, in `ChapterEditor.test.tsx` and `BookmarkCard.test.tsx`:**

```
FAIL BookmarkCard.test.tsx > status ... > fires onChangeStatus with the bookmark id and closes the popover
FAIL ChapterEditor.test.tsx > carries a labelled status select, kept verbatim for existing container-test selectors (design D12)
FAIL ChapterEditor.test.tsx > a status change commits the new status and closes the popover
```

3 failed, 46 passed (of the 3 files run together). Reverted; all green again (confirmed via full `npm test`: 160/160).

**Discrepancy worth flagging explicitly**: the task instructions asserted that "the surviving BookmarkListContainer selectors must go red." Checked directly: `rg -n "Estado de" frontend/src/containers/BookmarkListContainer.test.tsx` returns zero matches, both before and after the break; `BookmarkListContainer.test.tsx` was unaffected either way (0 of its own tests failed). The selectors that actually depend on the byte-identical label live in `ChapterEditor.test.tsx` and `BookmarkCard.test.tsx`, not the container test file. This does not weaken D12 own claim -- the guard-break still proves the aria-label is load-bearing, with a real, verifiable red -- but the specific file named in the task premise is inaccurate. Reading `design.md` own D12 text ("existing container-test selectors survive the move") and the code comment in `ChapterEditor.tsx` ("the existing container-test selectors still select this control...") both use "container test" loosely to mean "the pre-existing status test that predates the popover move" (which lives in `BookmarkCard.test.tsx`, per its own comment: "Carried over from the table deliberately"), not literally the file `BookmarkListContainer.test.tsx`. WARNING, not CRITICAL -- a terminology imprecision in the design doc/task premise, not a gap in test coverage.

## Deviation adjudication (task 2b.7)

**Claim**: the design literal `-1`-rejection test is unreachable through the real UI because `DecimalInput` sanitizer strips the minus sign at every keystroke; the author kept the `parsed < 0` guard as defense-in-depth and replaced the test with a blur-race regression.

**Verification performed**:
- Read `DecimalInput.tsx`'s `sanitizeDecimal` directly: it builds the output character-by-character, keeping only digits 0-9 and the first `.`; any other character (including `-`) is dropped unconditionally. Confirmed: a minus sign cannot survive into the draft under any input path (typed, pasted, or via `onChange`), since sanitization runs on every keystroke before the draft is ever set.
- Reproduced the underlying mechanism myself via guard-break 3 (above) plus direct inspection of `ScoreEditor.test.tsx` lines 78-95: typing `-1{Enter}` leaves the field holding "1", not "-1". The test in the codebase asserts exactly this, and no `onCommit` fires because `1` equals the already-committed score in that test fixture.
- Confirmed the `parsed < 0` guard is retained in `commit()` (dead in practice through this component, live for any hypothetical future caller of `commit()` that bypasses `DecimalInput`) and mirrors the identical, equally-unreachable guard already accepted in `ChapterEditor.tsx` since slice 2a -- this is not a new precedent, it is consistent with one already in the codebase.
- Reproduced the replacement test own claim by guard-break 2: removing the `onMouseDown` preventDefault genuinely produces a double-commit (5 then null), a real bug class, not a manufactured one.

**Verdict: the deviation is sound. Accepted, not raised.** The literal task text described an assertion that is provably false to write as a meaningful red/green test -- a test asserting "-1 is rejected" would in fact be testing the sanitizer contract (that it strips minus signs), which belongs to `DecimalInput`, not `ScoreEditor`. The replacement (a) still exercises the same guard clause presence via an adapted, honest assertion of the real observable behavior, and (b) substitutes a genuinely discriminating regression test for a real race condition that was actually reproduced during RED confirmation (verified independently above, in guard-break 2). This is a strictly better use of one test slot than a test that would pass by construction and prove nothing. No spec requirement is left uncovered by this substitution -- the spec out-of-range rejection requirement (`< 0` or `> 10`) is still covered structurally by the existing `> 10` test (`ScoreEditor.test.tsx` lines 69-76, unaffected) and by the `commit()` guard continued presence and the adapted test own assertion of the sanitizer boundary.

## DOM child-count observation (the deploy claim)

Wrote a temporary, non-committed test rendering `BookmarkGrid` with 48 bookmarks and asserting `document.querySelector(".bookmark-grid").childElementCount`. Result: `childElementCount` equals 48 for 48 bookmarks (assertion `toBe(48)` passed) -- confirmed 1:1, not 2:1. This holds because `BookmarkCard` returns a single top-level `<article className="card">` per bookmark; the two popovers are conditionally rendered and mounted via `createPortal(..., document.body)` (`Popover.tsx`), so they never land as DOM children of `.bookmark-grid` regardless of open/closed state. The temporary file was deleted immediately after the run; it is not part of the diff and was never present in `git status`.

This directly confirms the claim in the task framing: before slice 2b (with the status `<select>` as an extra sibling per bookmark, per task 1.4), the same grid would have yielded 2 direct children per bookmark (96 for 48 bookmarks). After 2b.3+2b.4, it yields exactly 1 per bookmark (48 for 48) -- the deploy blocker is resolved.

## Command results

| Command | Result |
|---|---|
| `cd frontend && npm test` | 160/160 passed, 17 test files, 5.79s |
| `cd frontend && npm run build` | Clean -- `tsc --noEmit` then `vite build`; 52 modules, `dist/assets/index-*.js` 214.26 kB / gzip 67.48 kB |
| `./.venv/Scripts/python.exe -m pytest -q` | 606 passed, 1 warning (unrelated httpx/starlette deprecation notice), 8.72s |
| `cd frontend && npm run build && npx playwright test panel.smoke.spec.ts` | 1/1 passed, unmodified -- "duplicate add jumps to the existing tab, then Historial shows the heatmap" |

All four commands green with the tree in its normal (unbroken) state, both before the guard-breaks and confirmed again after every revert.

## Final tree state

`git status --short` after all reverts: only `?? prototypes/` untracked (pre-existing, untouched). No staged changes, no commits made, no branch switch.

## Verdict

**PASS**

- CRITICAL: 0
- WARNING: 1 -- the task premise misnamed which test file selectors depend on the D12 verbatim `aria-label` (it named `BookmarkListContainer.test.tsx`; the actual dependents are `ChapterEditor.test.tsx` and `BookmarkCard.test.tsx`). The underlying design claim itself is correct and is proven by a real red/green cycle; only the file attribution in the task/verify instructions was imprecise. No action needed against the implementation.
- SUGGESTION: 0

All 13 in-scope tasks (2b.1-2b.13) are complete, checked off, and match the code as inspected. All four guard-breaks produced real, informative failures when broken and clean reverts when restored -- none was a silent no-op. The one documented deviation (2b.7) is adjudicated as sound. The deploy-blocking claim (N bookmarks yielding N, not 2N, direct children of `.bookmark-grid`) is confirmed at the DOM level with exact counts (48 to 48). All four required commands pass with real counts. The tree was left exactly as found.

**Recommendation**: proceed to `sdd-archive` for this slice, or continue with slice 3 (`feat/panel-v1b-fase-5-search-todo`) once the maintainer has reviewed and merged this PR.
