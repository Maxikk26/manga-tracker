# Verify Report: panel-v1b-fase-5 — Slice 1 (The Card)

**Date**: 2026-08-30
**Branch**: `feat/panel-v1b-fase-5-card` (4 commits off `main`@`fdc4e2e`)
**Scope**: Tasks 1.1-1.13 only (slice 1 of the four-slice `panel-v1b-fase-5` chain). Tasks 1.14-1.17 performed but intentionally left unchecked per apply-session instruction; verified true below. Slices 2a, 2b, 3 out of scope.
**Verdict**: **PASS**

## Completeness

| Task range | State | Evidence |
|---|---|---|
| 1.1-1.9 (core) | Checked, code matches | `BookmarkCard.tsx`, `BookmarkGrid.tsx`, `styles.css` read directly, match every clause |
| 1.10-1.13 (tests) | Checked, tests present and green | `BookmarkCard.test.tsx`, `styles.contract.test.ts` |
| 1.14 (unmodified describe blocks) | Unchecked, confirmed true | progress/score/status describes in BookmarkCard.test.tsx byte-identical to pre-slice behaviour; all pass unmodified |
| 1.15 (docs v1.11) | Unchecked, confirmed true | docs/spec-panel-v1b.md diff shows v1.10 to v1.11, new implemented-slice-1 paragraph, fase-5 row updated, changelog entry added; dependency pins (v1.14/v1.9/v1.2) re-verified consistent |
| 1.16 (npm test + build green) | Unchecked, confirmed true | Re-run independently, see Test Evidence |
| 1.17 (pytest untouched-green) | Unchecked, confirmed true | Re-run independently, see Test Evidence |

No unchecked task in the 1.1-1.13 range. No CRITICAL for task completion.

## Test Evidence (re-run independently, not trusted from the apply report)

| Command | Result |
|---|---|
| cd frontend and npm test -- --run | 127 passed (15 test files) - matches apply report exactly |
| cd frontend and npm run build (tsc --noEmit and vite build) | Green, 49 modules transformed, no type errors |
| ./.venv/Scripts/python.exe -m pytest -q | 606 passed, 1 unrelated deprecation warning (httpx/starlette) - matches apply report exactly, confirms manga_tracker/ untouched |
| npx playwright test panel.smoke.spec.ts | 1 passed - duplicate add jumps to the existing tab, then Historial shows the heatmap. Ran against tests/e2e/fixture_server.py on port 8765 (fixed, non-production, temp DB), spec file left byte-identical (not edited). Chromium already installed. This is the only automated proof that the rewritten poster card still renders bookmark.title text, keeps the Agregar manga / Ver en «Abandonado» affordances, and that the tab jump plus heatmap navigation both survive the card rewrite. |

## Guards broken on purpose (mandatory adversarial check)

All four injected regressions were applied, observed to fail RED, then reverted with git checkout and the full suite re-confirmed green (127/127) with git status --short showing only the pre-existing untracked prototypes/.

### 1. Restored the +N backlog pill in BookmarkCard.tsx
Re-inserted the exact pre-slice JSX (bookmark.behind !== null && bookmark.behind > 0 renders a span.behind-pill with title and +Math.round(bookmark.behind)) inside the poster anchor.

Result: RED, caught immediately.
```
FAIL  src/components/BookmarkCard.test.tsx > the backlog-count pill > never renders, at any backlog size
Error: expect(element).not.toBeInTheDocument()
expected document not to contain element, found <span class="behind-pill" title="50 sin leer">+50</span> instead
```
Task 1.10's absence-regression test is a real guard, not decoration.

### 2. Rewrote .card.card-saving as the bare .card-saving (D7 correction)
Result: RED, caught immediately.
```
FAIL  src/styles.contract.test.ts > styles.css contract > writes the saving opacity as the two-class selector, never the bare one (design D7)
Error: selector not found in styles.css: /(?:^|[\s,}])\.card\.card-saving\s*\{([^}]*)\}/
```
Confirms the two-class selector (specificity 0,2,0) is what ships, not the bare single-class rule (0,1,0) that would lose to .card[data-done] (0,1,1) and silently hide the saving signal.

### 3. Removed white-space: nowrap from .meta
Result: RED, caught immediately.
```
FAIL  src/styles.contract.test.ts > styles.css contract > keeps the .meta row from ever wrapping to a second line
AssertionError: expected the rule body to match /white-space:\s*nowrap/, but the rule no longer contained it
```

### 4. Broke the showStatus chip rule -- forced the status pill to always render (const chip = true instead of const chip = showStatus)
Result: RED, caught.
```
FAIL  src/components/BookmarkCard.test.tsx > the caught-up fade and its chip > marks a caught-up card done and shows the Al dia chip outside Todo
TestingLibraryElementError: Unable to find an element with the text: Al dia.
```
Task 1.11's test catches the regression (the Al dia-outside-Todo assertion fails once the chip is forced to the status pill). Task 1.12's own test does not fail here -- its assertion is the positive case (showStatus true shows the pill), which stays true regardless -- but 1.11 alone is a real, discriminating guard against this specific break.

All four guards are real: none is decorative. After every break, git checkout restored the file and the full 127-test suite was re-confirmed green.

## Deliberate items confirmed as contract, not defects

1. Status select as a sibling of .card. Confirmed in BookmarkCard.tsx (lines 141-158): rendered as a second top-level element in the components Fragment, with an explicit Temporary-layout comment citing design D12 and the slice-2b popover as its real home. The aria-label built from the bookmark title is unchanged. The existing status describe block in BookmarkCard.test.tsx (select-changes-status, locks-while-saving) passed unmodified in the 127-test run -- not touched, not rewritten.
2. No hover-swap, no No puntuado, no dotted underline. Confirmed: .meta still renders InlineNumberEdit for both progress and score, unchanged; the progress/score describe blocks in BookmarkCard.test.tsx (the tilde-glyph assertion, the em-dash assertion for null score) are byte-identical to pre-slice and pass. The de-total suffix is intact. No chapter-rest/chapter-full CSS class or data-approx dotted-underline styling exists yet in styles.css -- correctly deferred to 2a/2b.

## Independent checks

- vite.config.ts test.css true blast radius: searched the whole frontend/src tree for styles.css imports -- only styles.contract.test.ts (the raw suffix) and main.tsx (a side-effect import, never exercised by vitest) reference it. No other test file imports or inspects computed style. The 127/127 green run (identical to the apply reports count) is empirical confirmation that enabling real CSS content in the test environment changed nothing else.
- The raw-import reasoning holds: the frontend tsconfig types are limited to vite/client, no at-types-node; tsc --noEmit (part of npm run build) passed clean, confirming no Node-only import (fs, path) leaked in. The raw suffix is declared in vite/client.d.ts, so this is dependency-free by construction.
- .behind-pill and its four custom properties: confirmed absent from styles.css (full file read). Searching the repo for behind-pill finds exactly one hit outside the test file: HistoryContainer.tsx line 59, a comment about rounding precedent -- confirmed dead prose, not live code.
- Accessibility floor:
  - Contrast (independently recomputed via the WCAG relative-luminance formula, not trusted from the specs own numbers): reading #15803d on white is about 5.02 to 1; on_hold #c2410c on white is about 5.18 to 1; want_to_read #facc15 with dark text #1f2328 is about 10.3 to 1; dropped #4b5563 on white is about 7.56 to 1; completed #6d28d9 on white is about 7.11 to 1. All five clear the 4.5-to-1 AA floor for normal-size text; want_to_read is confirmed the only dark-text pill, and the reason is arithmetic (white text on that yellow computes to roughly 1.9 to 1). Colours are theme-independent (fixed hex values), so this holds in both light and dark mode.
  - Visible focus: .poster:focus-visible with a 2px solid white outline (offset -3px) is new this slice and is a strict improvement -- the pre-slice .cover anchor had no explicit focus style at all.
  - Touch targets: the poster anchor covers the entire card (absolute position, inset 0), far over 44px. The status select and the InlineNumberEdit trigger buttons are unchanged pre-existing controls this slice explicitly does not touch (the design's own unchanged-editing-behaviour contract) -- their touch-target sizing, if any, is inherited debt for slices 2a/2b new trigger buttons to address, not a slice-1 regression.
- Language contract: BookmarkCard.tsx, BookmarkGrid.tsx, styles.css, and both test files -- all comments and identifiers in English. Product copy read by the user is Spanish: Al dia, the Estado-de aria-label, the de-total suffix, and the Haz-clic-para-editar title (unchanged). No English string leaked into user-facing copy, no Spanish leaked into code or identifiers.
- Dependency pins: docs/spec-panel-v1b.md v1.11 still declares deps on one-pager-v1a.md (v1.14), spec-modelo-de-datos.md (v1.9), decision-arquitectura-v1b.md (v1.2) -- cross-checked against each files actual current version header; all three match exactly.
- Commit hygiene: 4 commits, each a real work unit (SDD planning docs, then feature and tests, then docs v1.11, then the tasks checkbox flip), Conventional Commit format, no Co-Authored-By or AI attribution in any of the four messages (checked verbatim via git log).
- Workload guard: changed lines excluding the openspec planning docs equal 297 insertions and 142 deletions, 439 lines total, inside the designs own 400-510 forecast for this slice; the auto-chain delivery strategy was pre-approved for the whole change, so this is not a new finding.

## Spec Compliance Matrix (slice-1-relevant requirements only)

| Requirement | Scenario | Status |
|---|---|---|
| The card is the poster, with a single non-wrapping meta row | Long title does not grow the grid | PARTIAL -- enforced by CSS (title line-clamp, overflow hidden) only; no jsdom test exists (design's own stated jsdom-layout limitation; not a slice-1 task) |
| same requirement | Widest real pair stays on one line | Covered via styles.contract.test.ts (white-space nowrap proxy), per design's documented jsdom caveat |
| No backlog-count pill exists | No backlog pill in the DOM | PASS -- tested, guard verified real (see above) |
| A caught-up bookmark fades and sinks to the end of its tab | Caught-up row sinks within its tab | N/A this slice -- sort logic (sortBookmarks.ts) untouched, pre-existing from a prior phase |
| same requirement | Todo suppresses the Al dia chip | PASS (chip half only, tested; the Todo wiring itself is slice 3, per task 1.12's own scope note) |

Chapter-swap, approx-underline, No-puntuado, popover, search, and Todo-tab requirements are correctly out of scope for slice 1 and not evaluated here.

## Issues

CRITICAL: none.
WARNING: none.
SUGGESTION: none -- the one PARTIAL item above (long title does not grow the grid) is a documented, deliberate testing-strategy tradeoff (design.md Testing Strategy section, jsdom caveat), not a gap introduced by this slice; no action recommended.

## Final Verdict

PASS. 0 CRITICAL, 0 WARNING, 0 SUGGESTION. All four adversarial guard-breaks caught their intended regression and were cleanly reverted. Frontend 127/127, backend 606/606, e2e smoke 1/1, build green. Ready for sdd-archive (or for the next chain slice, 2a, to proceed on top of this branch once merged).
