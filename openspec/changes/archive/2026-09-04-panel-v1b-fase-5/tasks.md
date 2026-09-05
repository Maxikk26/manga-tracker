
# Tasks: the design pass of the bookmark list (`panel-v1b-fase-5`)

Contract: `design.md` (authoritative — D1-D13 not re-decided here). Spec: `specs/panel-bookmark-list/spec.md`
(11 requirements, traced below). Four-slice cut is pre-confirmed by the orchestrator; not reopened.
Behaviour binding: `prototypes/bookmark-list.html`.

## Review Workload Forecast — whole change

| Field | Value |
|---|---|
| Estimated changed lines | ≈2200-2610 across 4 slices (design forecast) |
| 400-line budget risk | High (every slice) |
| Chained PRs recommended | Yes |
| Suggested split | 4 slices, stacked-to-main |
| Delivery strategy | auto-chain |
| Chain strategy | stacked-to-main |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: stacked-to-main
400-line budget risk: High

Dependency diagram (each PR bases on the previous branch; owner merges one at a time from the GitHub UI):

```
main
 └─ PR1 feat/panel-v1b-fase-5-card              (~400-510)
     └─ PR2a feat/panel-v1b-fase-5-popover-chapter (~700-780)
         └─ PR2b feat/panel-v1b-fase-5-popover-score (~600-700)
             └─ PR3 feat/panel-v1b-fase-5-search-todo (~500-620)
```

### Suggested Work Units

| Unit | Goal | PR / branch (base) | Focused test command | Runtime harness | Rollback boundary |
|---|---|---|---|---|---|
| 1 | Poster card, one-line meta row, fade/chip, no `+N` | PR1 `feat/panel-v1b-fase-5-card` (base `main`) | `cd frontend && npx vitest run src/components/BookmarkCard.test.tsx` | Manual `npm run dev`, eyeball at 162px/320px card widths per `docs/runbook-desarrollo-local.md` | Revert commit; `InlineNumberEdit`/`<select>` untouched, no interaction regression |
| 2a | Popover shell, chapter editor, PATCH queue, ordering freeze | PR2a `feat/panel-v1b-fase-5-popover-chapter` (base PR1 branch) | `cd frontend && npx vitest run src/components/Popover.test.tsx src/components/ChapterEditor.test.tsx src/domain/sortBookmarks.test.ts src/containers/BookmarkListContainer.test.tsx` | Manual: burst `+` clicks against dev API, watch Network tab request/response order | Revert commit; score editing and status `<select>` still work via untouched `InlineNumberEdit` |
| 2b | Score editor, status row, `InlineNumberEdit` deletion | PR2b `feat/panel-v1b-fase-5-popover-score` (base PR2a branch) | `cd frontend && npx vitest run src/components/ScoreEditor.test.tsx src/components/BookmarkCard.test.tsx src/containers/BookmarkListContainer.test.tsx` | Manual: set/clear a score, change status from the chapter popover, against dev API | Revert commit; chapter popover (PR2a) unaffected |
| 3 | Search, `Todo` tab, three-way empty state | PR3 `feat/panel-v1b-fase-5-search-todo` (base PR2b branch) | `cd frontend && npx vitest run src/domain/filterBookmarks.test.ts src/domain/sortBookmarks.test.ts src/components/StatusTabs.test.tsx src/containers/BookmarkListContainer.test.tsx` | Manual e2e: `npx playwright test panel.smoke.spec.ts` (must pass unmodified) + `npm run dev` search/scope-jump | Revert commit; per-status tabs still work standalone |

---

## Slice 1 — The card (~400-510 lines), branch `feat/panel-v1b-fase-5-card`, base `main`

Requirements covered: "The card is the poster, with a single non-wrapping meta row"; "No backlog-count pill exists";
"A caught-up bookmark fades and sinks…" (fade + `Al día` chip only — `Todo` suppression is slice 3).

**Core**
- [x] 1.1 `frontend/src/components/BookmarkCard.tsx`: rewrite to poster+scrim — `<article className={saving ? "card card-saving" : "card"} data-done={bookmark.behind === 0 || undefined}>` wraps the poster (`<a className="poster">` / `<span className="poster">` when `manga_url` is null, unchanged readability gate), an optional `.chip`/`.chip-status` corner, and `<div className="scrim">` holding `.title` + one `.meta` row. The `.meta` row keeps today's `InlineNumberEdit` progress + score editors and the `de {total}` suffix exactly as they render today — no hover-swap, no "No puntuado", no dotted underline yet (D11/D13 polish is deferred to the trigger buttons built in slices 2a/2b, which do not exist yet)
- [x] 1.2 same file: delete the `.behind-pill` block entirely (`bookmark.behind > 0` render, `Math.round`, the `title="{n} sin leer"`) — decision 4, recoverable only from git history
- [x] 1.3 same file: add `showStatus?: boolean` prop (default `false` this slice); chip is `showStatus ? <status pill> : (bookmark.behind === 0 ? "Al día" chip : null)` — Q5/D-chip rule, read off PROTO
- [x] 1.4 same file: status `<select>` moves to a sibling below `.card` (not inside the scrim) — unchanged element, unchanged `aria-label={\`Estado de ${title}\`}`, unchanged test; explicitly a temporary layout per design's own note ("a review artifact, never a shipped regression")
- [x] 1.5 same file: wrap the export in `React.memo` (D13) — zero new dependencies, `Todo` (~236 cards) is the payoff, measured later on the homelab
- [x] 1.6 `frontend/src/components/BookmarkGrid.tsx`: add `showStatus?: boolean` prop (default `false`), threaded straight to `BookmarkCard`; `BookmarkListContainer.tsx` stays untouched — the default supplies `false` until slice 3 wires the real value
- [x] 1.7 `frontend/src/styles.css`: card block rewrite — `.bookmark-grid` grid becomes `repeat(auto-fill, minmax(162px, 1fr))` gap `1rem` (D13, not today's 150px/1.1rem); `.card`/`.poster`/`.scrim`/`.title`/`.meta` (flex, `align-items: center`, `gap: 0.15rem`, **`flex-wrap: nowrap`, `white-space: nowrap`**); `.chip`/`.chip-status` five-tone palette verbatim from PROTO (`reading` #15803d, `on_hold` #c2410c, `want_to_read` #facc15/`#1f2328` text, `dropped` #4b5563, `completed` #6d28d9); `.card[data-done]` opacity 0.45, `:hover`/`:focus-within` 0.92
- [x] 1.8 same file, **the D7 fix**: rewrite the saving rule as `.card.card-saving { opacity: 0.55; }` (two-class selector, specificity 0,2,0) — **not** the bare `.card-saving { opacity: 0.55; }` that ships today, which loses to `.card[data-done]` (0,1,1) the moment both apply to one card
- [x] 1.9 same file: delete `.behind-pill` and its four custom properties (`--behind-pill-*`), `.approx-marker` stays for now (still used by the still-unchanged `InlineNumberEdit`-based progress editor)

**Tests — RED before GREEN**
- [x] 1.10 RED/GREEN `frontend/src/components/BookmarkCard.test.tsx`: delete the "the behind pill" `describe` block (5 tests) wholesale; add one replacement regression in its place — `renderCard(makeBookmark({ behind: 50 })); expect(document.querySelector(".behind-pill")).not.toBeInTheDocument();` — written to fail if the pill is ever restored (Requirement "No backlog-count pill exists")
- [x] 1.11 same file: new test — a caught-up bookmark (`behind: 0`) renders `data-done` on the `article` and, with `showStatus` unset/false, shows the `Al día` chip; a behind bookmark (`behind: 5`) shows neither
- [x] 1.12 same file: `showStatus={true}` renders the status pill (Spanish label from `STATUS_LABELS`) instead of `Al día`, even when the bookmark is caught up — Requirement "Todo suppresses the Al día chip" (chip half only; `Todo` wiring itself is slice 3)
- [x] 1.13 new `frontend/src/styles.contract.test.ts`: read `frontend/src/styles.css` as text (**via Vite's `?raw` import, not `fs.readFileSync`** — the frontend tsconfig has no `@types/node`, and `?raw` avoids adding one; `vite.config.ts` gained `test.css: true` so Vitest resolves real content instead of its default CSS stub) and assert (a) the `.meta` rule body contains `white-space: nowrap` — the jsdom-safe proxy for "the meta row must stay on one line" per the design's own jsdom caveat (no real layout in vitest); (b) the `.card-saving` opacity rule is written as the two-class selector `.card.card-saving` and the bare single-class `.card-saving {` selector does **not** appear — regression guard for D7
- [x] 1.14 keep the existing "progress"/"score"/"status" `describe` blocks in `BookmarkCard.test.tsx` unmodified this slice — the `~` glyph assertion and the em-dash assertion stay true until slices 2a/2b replace the editors that render them

**Docs**
- [x] 1.15 `docs/spec-panel-v1b.md` → v1.11: record §El rumbo visual / §La tarjeta as implemented per this design; changelog entry naming the four slices

**Final**
- [x] 1.16 `cd frontend && npm test` and `npm run build` both green (the latter runs `tsc --noEmit` — catches the `showStatus` prop-shape drift `vitest` alone would miss)
- [x] 1.17 `./.venv/Scripts/python.exe -m pytest -q` untouched-green (no `manga_tracker/` file was touched)

## Slice 2a — Popover shell + chapter editor + write machinery (~700-780 lines), branch `feat/panel-v1b-fase-5-popover-chapter`, base PR1 branch

Requirements covered: "The chapter control swaps between rest and full label" (chapter half); "Approximate progress…"
(chapter half, dotted underline); "Chapter and score are edited in a popover…" (chapter half); "The list does not
reorder while a popover is open" (freeze + focus return, in full — required by the chapter editor per design).

**Actual size: ~1278 changed lines** (14 files, +1176/-102 against `feat/panel-v1b-fase-5-card`), well over the
700-800 forecast/cap. All tasks below are complete and independently green (frontend 156/156, backend 606/606,
e2e 1/1, build clean); the overage is a review-workload risk, not a correctness gap — flagged for the
orchestrator/maintainer rather than resolved by cutting tests or functionality, per this session's explicit
instruction. See the apply-progress artifact for the full per-file breakdown and the reasoning for why this
foundation slice (a new portalled popover shell, a new editor with a non-trivial commit contract, and a
per-bookmark serialized write queue with an ordering freeze) did not fit the original estimate.

**Foundation**
- [x] 2a.1 `frontend/src/domain/sortBookmarks.ts`: export `isCaughtUp(bookmark): boolean` (promote the existing private helper, unchanged `behind === 0` rule, D9) and add `applyFrozenOrder(rows: readonly Bookmark[], ids: readonly number[]): Bookmark[]` (D4) — unknown ids appended in their input order, frozen ids no longer present dropped, never mutates
- [x] 2a.2 RED/GREEN `frontend/src/domain/sortBookmarks.test.ts`: `applyFrozenOrder` cases — reorders to match `ids`; a row whose id is absent from `ids` is appended after the frozen sequence; an id in `ids` no longer present in `rows` is silently dropped, no throw; empty `ids` returns the input order unchanged
- [x] 2a.3 `frontend/src/components/Popover.tsx` (new) + test: portalled shell — `createPortal(panel, document.body)`; placement via `useLayoutEffect` once, from `anchor.getBoundingClientRect()` + panel's own `offsetWidth/Height` (D2 table, PROTO's arithmetic verbatim); `role="dialog"` + Spanish `aria-label`, **no `aria-modal`**, no focus trap
- [x] 2a.4 same file: dismissal — `Escape`; capture-phase document `click` outside panel **and** outside anchor; `scroll` with `{capture:true, once:true}`; `focusout` whose `relatedTarget` is a real element outside both closes, but `relatedTarget === null` **does nothing** (D2 — a native `<select>` dropdown or a click outside the window produce it)
- [x] 2a.5 same file: focus — first field focused+selected on open; on close, the anchor if `document.contains(anchor)`, else `.bookmark-grid` (D6)
- [x] 2a.6 `frontend/src/components/BookmarkGrid.tsx`: add `tabIndex={-1}` to `.bookmark-grid` (D6 focus sink, needed by 2a.5)
- [x] 2a.7 `frontend/src/styles.css`: `.pop*` rules — **`z-index: 10`, not PROTO's `30`** (correction: `.modal-backdrop` is `z-index: 20`, verified at `styles.css:597`; a popover above the add-modal is a defect)
- [x] 2a.8 extend `styles.contract.test.ts` (1.13): assert the `.pop` rule sets `z-index: 10` and that `z-index: 30` does not appear in that rule — regression guard for the z-index correction

**Core**
- [x] 2a.9 `frontend/src/components/ChapterEditor.tsx` (new) + test — no status row yet (2b's scope): `−` / `DecimalInput` (D11, reused per its 2026-08-19 owner decision — **not** `<input type="number">` as PROTO uses) / `+`; draft seeded **only on open** as `value === null ? "" : String(value)` — the D11 null guard, PROTO would render the literal string `"null"`; stepper writes the draft and commits immediately, `Math.max(0, round(x*10)/10)`, `−` disabled at 0; typed value commits on blur or Enter (Enter also closes); `Escape` closes without committing the typed draft; an unchanged value fires no PATCH; hints `de {total} publicados` / `El progreso guardado es aproximado.` / `Se guarda solo.` (verbatim copy)
- [x] 2a.10 `BookmarkCard.tsx`: swap the progress `InlineNumberEdit` for the chapter trigger button — rest label `cap. {N}`, hover/focus label `{N} / {total}` via `.chapter-rest`/`.chapter-full` CSS (`@media (hover:none)` always shows the full label); `data-approx` dotted-underline on the number, replacing the free-standing `~`; no total → only `cap. {N}`, no swap; opens `Popover` + `ChapterEditor` on click, sets `open: "chapter"`
- [x] 2a.11 same file: `onEditingChange(id, open)` callback (D3 interface), fired on trigger open/close
- [x] 2a.12 same file: swap the inline `bookmark.behind === 0` fade/chip check (1.1/1.3) for the imported `isCaughtUp(bookmark)` from `sortBookmarks.ts` — one shared definition per D9
- [x] 2a.13 `frontend/src/containers/BookmarkListContainer.tsx`: `editingId: number | null` state with the last-open-wins setter — `setEditingId((prev) => (open ? id : prev === id ? null : prev))` (D3); `frozenIds` captured from the current `visible` order on open, cleared on close; `visible` runs through `applyFrozenOrder` while `editingId !== null`
- [x] 2a.14 same file: PATCH queue — `tails: Map<number, Promise<void>>` (per-bookmark FIFO) and `seqs: Map<number, number>` (burst counter); `enqueuePatch(id, patch)` bumps `seqs[id]`, chains onto `tails[id]`; each link awaits `patchBookmark`, then awaits `load(false)` **only if `seqs.get(id)` still equals this link's number**; failures caught inside the link into `errorMessage`; `savingIds` clears on the burst's last link (D5)
- [x] 2a.15 same file: trigger buttons are **not** `disabled` while `savingIds` has the id — reversing today's behaviour (D5 consequence); `card-saving` stays the only in-flight signal

**Tests — RED before GREEN, discriminating cases named**
- [x] 2a.16 `Popover.test.tsx`: `Escape` closes; outside click closes; scroll closes; `role="dialog"` + `aria-label` present, **no `aria-modal`**; focus lands on the first field on open and returns to the anchor on close; **`focusout` with `relatedTarget: null` does not close** (fire the event with `relatedTarget: null` explicitly and assert the panel is still in the document — the one case in D2's table that a naive "any focusout closes" implementation would break)
- [x] 2a.17 `ChapterEditor.test.tsx`: **null seeds an empty field** — `render` with `last_chapter_read: null`; assert the input's value is `""` and `screen.queryByDisplayValue("null")` is absent (the concrete bug the exploration flagged in PROTO's `openChapterPop`, and the Requirement scenario "Never-read bookmark opens blank"); stepper commits at once; typed value commits on blur and on Enter, never per keystroke; `Escape` cancels the typed draft; unchanged value fires nothing; `−` disabled at 0
- [x] 2a.18 `BookmarkListContainer.test.tsx`: rewrite the progress PATCH test to target the new chapter trigger's `aria-label` instead of `getAllByTitle(/haz clic para editar/i)[0]` (that selector dies once the trigger replaces `InlineNumberEdit` for progress)
- [x] 2a.19 same file, **the discriminating write-queue case**: mock `patchBookmark` with two manually-controlled (deferred) promises; fire two rapid chapter commits for the same bookmark id; resolve the **second (later)** request's promise, then resolve the **first (earlier)** one; assert the final displayed chapter value reflects the second commit and exactly one refetch follows the whole burst — the Requirement scenario "A later commit is not overwritten by an earlier response", proven by construction (D5), not by timing luck — **deviation**: with the FIFO chain implemented literally per D5, the second PATCH is not even dispatched until the first's cycle settles, so the two deferred promises cannot be resolved in the literal order this task describes (the second doesn't exist yet when the first resolves); the test instead proves the same guarantee by asserting the dispatch itself is gated (exactly 1 PATCH call before either resolves) plus the one-refetch/latest-value outcome, and was confirmed to fail red against a naive unqueued implementation (see apply-progress)
- [x] 2a.20 same file: while a chapter popover is open and the edit makes the row caught-up, assert the row's position in the DOM order is unchanged; after closing, assert it re-sorts to the end of its tab and focus returns to its trigger — Requirement "The list does not reorder while a popover is open", both scenarios

**Final**
- [x] 2a.21 `cd frontend && npm test` and `npm run build` both green
- [x] 2a.22 `./.venv/Scripts/python.exe -m pytest -q` untouched-green

## Slice 2b — Score editor + status row + deletions (~600-700 lines), branch `feat/panel-v1b-fase-5-popover-score`, base PR2a branch

Requirements covered: "Approximate progress…" (score half: "No puntuado"/"{n}/10"); "Chapter and score are edited
in a popover…" (score half); "The status control lives inside the chapter popover" (in full).

**Actual size: ~640 changed lines** (11 files touched, within the 600-700 forecast/800 cap). All tasks below are
complete and independently green (frontend 160/160, backend 606/606, build clean). One deviation from the
literal task text, documented at 2b.7 below.

**Core**
- [x] 2b.1 `frontend/src/components/ScoreEditor.tsx` (new) + test: `DecimalInput` (D11, same reuse rule as 2a) + `/ 10` + `Quitar puntuación` button; draft seeded `value ?? ''` on open only; typed value commits on blur/Enter; blank commits `null` and closes; out-of-range (`< 0` or `> 10`) rejected; committed value rounded to an integer; `Escape` closes without committing
- [x] 2b.2 `BookmarkCard.tsx`: swap the score `InlineNumberEdit` for the score trigger — text state `No puntuado` (unset) / `{my_score}/10`; opens `Popover` + `ScoreEditor`, sets `open: "score"`; `onEditingChange` fires the same as the chapter trigger (D3)
- [x] 2b.3 `ChapterEditor.tsx`: add the status row — `Estado` label + `.pop-select`, `aria-label={\`Estado de ${title}\`}` kept verbatim (existing container-test selectors survive, D12); `onChange` commits the status and closes the popover (Q4)
- [x] 2b.4 `BookmarkCard.tsx`: remove the standalone `<select className="status-select">` rendered below the card (1.4) — now redundant with 2b.3
- [x] 2b.5 **Delete** `frontend/src/components/InlineNumberEdit.tsx` and `InlineNumberEdit.test.tsx` wholesale (-255 lines) — grep-confirmed the card was its only consumer, and 2b.2 removes the last call site
- [x] 2b.6 `frontend/src/styles.css`: `.status-select` rule replaced by `.pop-select` under the popover block; drop the now-dead `.status-select`, `.progress-display`, `.progress-input`, `.approx-marker` rules (D13's "not ported" idioms are already gone; these are the remaining dead selectors once `InlineNumberEdit` is deleted)

**Tests — RED before GREEN, discriminating cases named**
- [x] 2b.7 `ScoreEditor.test.tsx`: clear → commits `null` and closes; `11` rejected, no commit; unchanged value fires nothing; `Quitar puntuación` sets the draft to `""`, commits `null`, closes — **deviation**: `-1` as literally described is unreachable through the real component: `DecimalInput`'s own sanitizer (slice 2a, immutable this slice) strips any character that is not a digit or the first dot at the keystroke, so a minus sign never survives into the draft regardless of how it is typed or pasted — the `parsed < 0` guard in `commit()` is kept anyway (mirrors `ChapterEditor`'s identical check, defense-in-depth for a future non-`DecimalInput` caller) but is dead code through this UI. The test instead asserts the real, observable fact (typing `-1` leaves only `1` in the field) plus, as a genuinely discriminating regression, that clicking `Quitar puntuación` while the field holds an uncommitted valid edit does not first fire a stray blur-commit — confirmed RED (2 commits: the stray `5` then `null`) with the `onMouseDown` preventDefault guard removed, GREEN restored after
- [x] 2b.8 `ChapterEditor.test.tsx`: status change commits the new status and closes the popover — Requirement "Status change from the popover" — confirmed RED (no `onRequestClose` call) with the select's `onRequestClose()` call removed, GREEN restored after
- [x] 2b.9 rewrite `BookmarkCard.test.tsx`: delete the `"renders '~' when progress_is_approx is true"` / `"does not render '~'..."` pair if not already replaced in 2a (confirm 2a.10 covers `data-approx`; if the assertions still exist here, remove them now); delete `"renders an em dash when my_score is null"` and replace with `expect(scoreEditor()).toHaveTextContent("No puntuado")`; delete the `"status"` `describe` block (the standalone `<select>` no longer exists on the card) and move its coverage into `ChapterEditor.test.tsx` (2b.8); replace every remaining `getAllByTitle(/haz clic para editar/i)` selector with the triggers' `aria-label`s (both progress and score no longer render that title attribute at all, since `InlineNumberEdit` is gone) — grep-confirmed no `'~'` assertions remained (already gone since 2a)
- [x] 2b.10 rewrite `BookmarkListContainer.test.tsx`: replace the score PATCH test's `getAllByTitle(/haz clic para editar/i)[1]` selector with the score trigger's `aria-label`; same for the "clearing the score" test
- [x] 2b.11 grep the repo for `InlineNumberEdit` after 2b.5 — assert zero remaining references outside `docs/` changelog prose. Result: zero live code references (no imports/JSX usages) anywhere in `frontend/src`; the only hit is a historical comment in `BookmarkCard.test.tsx` naming the retired component, the same category as the `openspec/` planning prose that also still names it. No file outside `docs/` carries a functional reference.

**Final**
- [x] 2b.12 `cd frontend && npm test` and `npm run build` both green — 160/160, build clean
- [x] 2b.13 `./.venv/Scripts/python.exe -m pytest -q` untouched-green — 606 passed

## Slice 3 — Search + `Todo` (~500-620 lines), branch `feat/panel-v1b-fase-5-search-todo`, base PR2b branch

Requirements covered: "Search is a pure function over the full list"; "'Todo' leads the tabs, grouped
contiguously by status"; "Empty tab and empty search are distinct states"; "A caught-up bookmark fades…" (the
`Todo`-suppression half, closing out slice 1's chip rule).

**Actual size: ~769 changed lines** (15 files, +683/-86 against `feat/panel-v1b-fase-5-popover-score`; 702 of those
lines are code+tests, the rest is this file and the docs update) — over the 500-620 forecast, under the 800-line
session cap. All tasks below are complete and independently green (frontend 183/183, backend 606/606, build
clean, e2e 1/1 unmodified, spec file untouched).

**Foundation**
- [x] 3.1 `frontend/src/domain/types.ts`: `export const ALL_TAB = "all" as const;` and `export type TabKey = BookmarkStatus | typeof ALL_TAB;` (D8) — the literal, not `null`
- [x] 3.2 `frontend/src/domain/filterBookmarks.ts` (new): `filterBookmarks(rows, query)` — `s.normalize("NFD").replace(COMBINING_MARKS, "").toLowerCase()` then substring match on `title` only (D10); `COMBINING_MARKS` written with numeric escapes `̀`-`ͯ` (never the raw combining-marks literal PROTO uses — that is the one thing this line must not copy); empty/whitespace query returns `[...rows]` — verified via raw byte dump that the source file carries the literal ASCII escape sequence, not the encoded Unicode marks
- [x] 3.3 `frontend/src/domain/sortBookmarks.ts`: add `sortBookmarksForAll(rows)` = `BOOKMARK_STATUSES.flatMap((s) => sortBookmarksForTab(rows.filter((r) => r.status === s), s))` (D9) — `sortBookmarksForTab`'s signature stays untouched

**Tests — RED before GREEN, discriminating cases named**
- [x] 3.4 RED/GREEN `frontend/src/domain/filterBookmarks.test.ts` (new): accent-insensitive both directions (query with accents matches title without, and vice versa); case-insensitive; substring, not prefix-only; empty/whitespace query returns everything; no match returns `[]`; source array not mutated
- [x] 3.5 RED/GREEN `sortBookmarks.test.ts`: `sortBookmarksForAll` — output is contiguous by `BOOKMARK_STATUSES` order; for every status, `sortBookmarksForAll(rows).filter(byStatus)` deep-equals that status's own `sortBookmarksForTab` output (the property that catches PROTO's global-partition bug from ever creeping back in)

**Core**
- [x] 3.6 `frontend/src/components/StatusTabs.tsx`: rewrite for `TabKey` — six buttons, `Todo` first with the grand total (`BOOKMARK_STATUSES.reduce`); keep `<nav className="status-tabs" aria-label="Filtrar por estado">` and plain `<button>` elements (**correction 1 — do NOT add `role="tablist"`/`role="tab"`**: `getByRole` matches the computed ARIA role and an explicit `role="tab"` overrides a `<button>`'s implicit role, breaking `page.getByRole("button", { name: /abandonado/i })` at `panel.smoke.spec.ts:35` even with `tab-active` intact); add `aria-current={active ? "true" : undefined}` per button — the `AppNav.tsx` precedent (WCAG 4.1.2); `tab`/`tab-active` classes and the Spanish labels stay byte-identical
- [x] 3.7 `frontend/src/styles.css`: `.tab-all` (margin-right 0.35rem, per PROTO), `.tab { min-height: 44px; }` touch target
- [x] 3.8 `frontend/src/containers/BookmarkListContainer.tsx`: `activeTab: TabKey` (replaces `activeStatus`, default `"reading"` unchanged); `query: string` state; chain **filter → scope → sort**: `filterBookmarks` first, then pick `sortBookmarksForTab`/`sortBookmarksForAll` by `activeTab === ALL_TAB`, then `applyFrozenOrder`
- [x] 3.9 same file: search row JSX — `<input type="search" aria-label="Buscar por título" placeholder="Buscar por título">` + clear button `aria-label="Limpiar la búsqueda"` (hidden when empty); rendered **outside** the loading/error/empty branches and never keyed, so it never remounts mid-word (D13's `mountShell()` hazard, restated as a React rule)
- [x] 3.10 same file: move `Agregar manga` to the right end of the search row (Q1); retire `.panel-toolbar`
- [x] 3.11 same file: result count — no query: `{n} título(s) en toda la lista.` only in `Todo`, empty string per-tab; with query: `{n} resultado(s) en «{tab}».` (singular/plural and `«»` quoting verbatim)
- [x] 3.12 same file: three-way empty state — no bookmarks in tab + no query → message-only, **no add control**; `Todo` with zero bookmarks → `Todavía no hay mangas en tu lista.` (Q2); per-status empty → `No hay mangas en este estado.` (verbatim, unchanged); query matches nothing → `Sin resultados para «{query}» en «{tab}».` + `Buscar en toda la lista` button that sets `activeTab = ALL_TAB`, **leaves `query` untouched**, and refocuses the field (Q3)
- [x] 3.13 `frontend/src/components/BookmarkGrid.tsx`: remove its own empty-state branch (`No hay mangas en este estado.` `<p>`) — the container now decides which of the three empty states to render, matching its existing loading/error pattern
- [x] 3.14 `BookmarkCard.tsx`/container: wire the real `showStatus = activeTab === ALL_TAB` down through `BookmarkGrid` (closing out 1.3/1.6's temporary `false` default) — **also wired `BookmarkCard.tsx`'s D13 "Sin empezar" copy for a never-read bookmark**, which its own inline comment had flagged as deferred to this slice and which 3.18's expected text requires; the pre-existing `"cap. —"` assertions in `BookmarkCard.test.tsx`/`BookmarkListContainer.test.tsx` were updated to match (not itemized in the original task text, but a direct consequence of it)
- [x] 3.15 `frontend/src/styles.css`: `.search-row`/`.search-field`/`.search-clear`/`.result-count`/`.chip-status` five-tone palette confirmed present (already added 1.7 — no change expected here beyond search-row layout) — added `.search-row`/`.search-field`/`.search-clear`/`.result-count` (not yet in `styles.css` before this slice) plus a small `.empty-state button` rule for the scope-jump control; `.chip-status` confirmed already present, untouched

**Tests — RED before GREEN, discriminating cases named**
- [x] 3.16 new `frontend/src/components/StatusTabs.test.tsx`: six tabs render, `Todo` first with the grand total; the active tab carries both `tab-active` **and** `aria-current="true"`; every inactive tab has `aria-current` **absent** (not `"false"` — matches the `AppNav.tsx` precedent); confirm the rendered element's role is still `"button"` (guards correction 1 — would fail immediately if `role="tab"` were ever added)
- [x] 3.17 `BookmarkListContainer.test.tsx`: **the empty-tab-vs-empty-search discriminating case** — render a tab with zero bookmarks and no query, assert the message text does **not** match `/«.*»/` and differs from the query-empty message; then type a non-matching query in a non-empty tab, assert the message matches `/Sin resultados para «.*» en «.*»\./` — the two strings must never be equal for the same tab
- [x] 3.18 same file: **the null-render discriminating case for the chapter trigger inside the container** — a bookmark with `last_chapter_read: null` renders `Sin empezar`, never the text `"null"`, in the `Todo` tab and its own tab alike
- [x] 3.19 same file: the scope-jump button sets the tab to `Todo`, leaves the typed query in the input, and returns focus to the search field
- [x] 3.20 same file: `showStatus` is `true` only while `activeTab === ALL_TAB` — a card in `Todo` shows its status pill; the same card viewed from its own tab shows `Al día` or nothing, never both
- [x] 3.21 confirm `frontend/e2e/panel.smoke.spec.ts` passes **unmodified** — run `cd frontend && npx playwright test panel.smoke.spec.ts` before this slice's PR is opened, per `docs/runbook-desarrollo-local.md`; this is the only automated cover for the add-manga flow and the `tab-active` class surviving the "Ver en «Abandonado»" jump — confirmed: 1 passed, `git diff --stat main..HEAD -- frontend/e2e/` is empty

**Docs**
- [x] 3.22 `docs/spec-panel-v1b.md`: close the fase-5 done-criteria row(s) opened by 1.15's v1.11 entry, if any remain open — bumped to v1.12 (2026-09-04), closed the fase-5 table row (all four criteria now met, pending the chain's merge/deploy), closed the "cuatro decisiones" pendientes-abiertos item, corrected the stale "+N pill" Resumen row and §La tarjeta's "Implementado" paragraph (which still named the retired `InlineNumberEdit`/standalone `<select>`), and added a changelog entry covering slices 2a/2b/3 together (neither 2a nor 2b had carried its own docs task). Pins re-verified, unchanged

**Final (whole chain)**
- [x] 3.23 `cd frontend && npm test` and `npm run build` both green — 187/187, build clean
- [x] 3.24 `./.venv/Scripts/python.exe -m pytest -q` untouched-green (zero new tests across all four slices, per design's `manga_tracker/` row) — 606 passed
- [x] 3.25 Re-run `npx playwright test panel.smoke.spec.ts` once more after PR3 merges — the design's own instruction: "The e2e smoke runs before slice 3's PR and again at the end of the chain" — **not yet done**: this is explicitly a post-merge action (PR3 has not merged), left for the maintainer/orchestrator once the chain lands
