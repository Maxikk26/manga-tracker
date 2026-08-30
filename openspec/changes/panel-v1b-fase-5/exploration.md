# Exploration: panel-v1b-fase-5 (design pass of the bookmark list screen)

Scope: implementation prep only — the *what* is closed in `docs/spec-panel-v1b.md` §El rumbo visual / §La tarjeta and `prototypes/bookmark-list.html`. This explore is about *where* the code changes land, seams, test breakage and slicing. No visual alternatives proposed.

## Current State

`BookmarkListContainer.tsx` fetches the whole list (`GET /api/bookmarks`, no limit/offset — confirmed in `manga_tracker/web/app.py:227` `list_bookmarks(status: BookmarkStatus | None = None)`), filters client-side by `activeStatus: BookmarkStatus` (no "all"/search yet), sorts via `sortBookmarksForTab`, renders through `BookmarkGrid` → `BookmarkCard`. `BookmarkCard` today: boxed cover image below which sit title, progress (`InlineNumberEdit`), score (`InlineNumberEdit`, placed "plainly, no styling decision made here" per its own comment), a status `<select>`, and a `.behind-pill` ("+N") drawn on the cover corner. `StatusTabs` has 5 buttons (no "Todo", no ARIA tab pattern — no `aria-selected`/`role=tab`, just `.tab-active` class). No search input anywhere. `tests/test_architecture.py` is Python-only (scans `manga_tracker/`), it does **not** touch `frontend/` at all — the container/presentational split for the frontend is convention-only (comments + file location), not test-enforced.

## File Map

- `frontend/src/components/BookmarkCard.tsx` — full rewrite: poster+scrim card (title/chapter/score inside, nothing below), hover-swap chapter control (`cap. 94` ↔ `94 / 560`), "No puntuado" text state, remove the `.behind-pill` block entirely (lines ~93-101), later swap both `InlineNumberEdit` calls for popover triggers. Status `<select>` currently lives in this component with nowhere obvious to go in the new layout (see Contradictions).
- `frontend/src/components/BookmarkGrid.tsx` — thread a `showStatus` prop (Todo-only chip) down to `BookmarkCard`; likely needs to stop owning the empty-state message once 3 empty states exist (tab-empty / search-empty / normal) — recommend the container decides which to render, same pattern it already uses for loading/error, rather than growing branching logic inside this presentational component.
- `frontend/src/components/InlineNumberEdit.tsx` — grep confirms its **only** consumers are `BookmarkCard.tsx` (progress + score) and its own test file. Safe to delete wholesale (both files) once popovers land; nothing else in the frontend imports it.
- `frontend/src/components/AppNav.tsx` — shared List/Historial switcher; logo is fase-5 scope but independent/low-risk, not part of the 3 card/popover/search slices. `AppNav.test.tsx` asserts `aria-current` + accessible names ("Lista"/"Historial") — unaffected by a logo add as long as accessible names don't change.
- `frontend/src/components/StatusTabs.tsx` — **not in the given list but must change**: needs the "Todo" tab (index -1 / sentinel), and ideally adopts the prototype's `role="tablist"/role="tab"/aria-selected` pattern (current markup has neither, a pre-existing G2 gap vs `runbook-diseno-ui.md`). Hard constraint: **must keep the `tab-active` class name and keep "Abandonado" in the button's accessible name** — the e2e smoke test asserts `page.getByRole("button", { name: /abandonado/i })).toHaveClass(/tab-active/)`. No existing `StatusTabs.test.tsx` to break.
- `frontend/src/containers/BookmarkListContainer.tsx` — widen `activeStatus` to include an "all"/"Todo" state, add `query` state + search input JSX, wire `filterBookmarks`, compute 3-way empty state, and (popover slice) add "freeze order while a popover is open" logic — see Risks.
- `frontend/src/domain/sortBookmarks.ts` — needs a real "all" branch. **Do not** copy the prototype's literal `sorted()` (a global isDone-partition applied over the flat concatenation) — that can visibly interleave tabs whenever a non-`reading` status also carries a live `behind` value (on_hold is explicitly still swept: "on_hold updates silently and immediately" per CLAUDE.md). The clean way to satisfy "grouped by status, tab after tab" is: for each status in a fixed order, run `sortBookmarksForTab(rows, status)` and concatenate — that trivially preserves each tab's own internal ordering and guarantees contiguous grouping. Flag as a design nuance for sdd-design/sdd-tasks.
- `frontend/src/domain/statusLabels.ts`, `covers.ts`, `types.ts` — no changes expected beyond maybe a new `"all"` sentinel type if `activeStatus` is widened.
- `frontend/src/api/bookmarks.ts` — no change (spec confirms zero backend, zero new requests for search).
- `frontend/src/styles.css` — large rewrite: `.card`/`.scrim`/`.title`/`.meta`/`.edit`/`.chip`/`.chip-status` (5-tone palette from spec) added; `.behind-pill` block (with its custom-property seam) deleted outright, not filled; `.pop*` popover styles added; `.search-*`/`.tab-all`/`.result-count` added.

## Seams — used vs. retired

- **`.behind-pill` custom properties** (`--behind-pill-bg/-fg/-size/-padding`) were reserved so "a future visual pass changes the values below — never the component". Decision #4 goes further than the seam anticipated: the whole block and its render call in `BookmarkCard.tsx` are **removed**, not re-tuned. State this explicitly so nobody restores it thinking it regressed.
- **`domain/heatmapBuckets.ts`** — the other owner-reserved seam (fase-2), belongs to the History screen's heatmap, not the bookmark list. Out of scope for this exploration; still open for a later fase-5 slice.
- The prototype also draws a small `.chip` "Al día" badge in the same top-right corner (non-`Todo` tabs, caught-up card) — this is real prototype behavior beyond the four closed decisions and easy to miss since it isn't named in §La tarjeta's bullet list; treat it as in-scope (prototype is binding) but call it out.

## InlineNumberEdit — consumers

Only `BookmarkCard.tsx` (progress editor + score editor). No other component imports it. Deleting it alongside its test file is safe once both call sites move to popovers.

## Test surface and what breaks

- `BookmarkCard.test.tsx`: "the behind pill" describe block (5 tests) — delete outright (decision #4). "progress"/"score" tests select controls via `getAllByTitle(/haz clic para editar/i)` (InlineNumberEdit's own title attribute) — this selector strategy dies entirely once popovers replace InlineNumberEdit; needs a full rewrite targeting the new trigger buttons' aria-labels. "renders '~' when progress_is_approx is true" literally asserts the `~` glyph — invalidated by decision (dotted-underline replaces it). "renders an em dash when my_score is null" expects `"—"`; new design wants literal "No puntuado" text. "status" describe block (the `<select>`) has no obvious home in the new card — see Contradictions.
- `BookmarkListContainer.test.tsx`: the progress/score PATCH tests also drive through `getAllByTitle(/haz clic para editar/i)` + `getByRole("spinbutton")` — same InlineNumberEdit coupling, breaks with popovers (adds to slice-2 line count, not slice-1).
- `sortBookmarks.test.ts` — untouched by slices 1/2; needs new "all" cases for slice 3.
- `frontend/e2e/panel.smoke.spec.ts` — asserts, in order: "One Piece" text visible on load; "Agregar manga" button; on a stub duplicate/terminal add, "Ver en «Abandonado»" button and its click; **`tab-active` class survives on the "Abandonado" status button after the jump**; "Historial" nav button; heatmap `aria-label="Mapa de lecturas"` and `.heatmap-cell` counts (unrelated to this screen, safe). The one hard constraint for slice 3's StatusTabs rewrite is the `tab-active` class + accessible name.

## filterBookmarks placement

Belongs in `frontend/src/domain/filterBookmarks.ts`, mirroring `sortBookmarks.ts` exactly: a pure `(rows, query) => rows` function with its own `filterBookmarks.test.ts`, consumed only by `BookmarkListContainer.tsx` inside the existing `useMemo` chain (container already composes `sortBookmarksForTab` there today). `tests/test_architecture.py` has no jurisdiction over `frontend/` — this is purely the project's own container/presentational convention, already well precedented by `sortBookmarks.ts`. Global search is exactly "drop the status-filter argument before calling `filterBookmarks`", per spec.

## Three-slice judgement

Order given (1 card, 2 popovers, 3 search+Todo) is dependency-sound: popovers need the card's `overflow:hidden`/scrim/meta-row markup from slice 1 (hard dependency); the status-chip infra slice 1 wires (prop, unused) is consumed by slice 3. Popover-vs-search ordering is a soft preference, not a hard dependency — both touch the container but on independent axes (sort-freeze vs. query state).

Rough size (additions+deletions, not counting goldens):

- Slice 1 (card+styles, no behavior change to editing): BookmarkCard.tsx (~80-100), BookmarkCard.test.tsx trims (~60), styles.css (~150-200). Total ≈ 350-450 lines.
- Slice 2 (popovers): delete InlineNumberEdit.tsx+test (-255 lines, still counts), new popover component(s)+test (~250-350), BookmarkCard.tsx rewrite of edit controls (~60), BookmarkListContainer.tsx sort-freeze logic + BookmarkListContainer.test.tsx rewrite (~150-200), styles.css `.pop*` (~90). Total ≈ 750-950 lines — **this slice alone likely exceeds the 800-line session budget**.
- Slice 3 (search + Todo): domain/filterBookmarks.ts+test (~120-160), sortBookmarks.ts "all" branch+tests (~40-60), StatusTabs.tsx rewrite (~50-70), BookmarkListContainer.tsx search UI+3-way empty state (~150-250), styles.css search/tab-all (~70-90). Total ≈ 450-600 lines.

Recommendation: keep the given order but flag slice 2 for further sub-splitting at sdd-tasks time (e.g. 2a shared Popover shell + chapter popover, 2b score popover + container reorder-freeze) since it alone risks the 800-line budget once the InlineNumberEdit deletion and both test-file rewrites are counted.

## Contradictions / gaps between prototype and real app

- **Status `<select>` has no home.** The prototype's card never models a status-changing control (its 5 "tabs" ARE the status; there's no in-card status editor). Decision #1 of §La tarjeta says "nothing hangs below" the poster and the meta row is capped at chapter+score in one line — no room is described for the existing fase-1 status dropdown. This is real, tested, shipped functionality (`onChangeStatus`) the prototype simply doesn't show. Needs an explicit design answer (e.g., inside a popover, a menu icon, or elsewhere) before slice 1/2 land — flag for sdd-design.
- **Null `last_chapter_read` is untested by the prototype.** Its demo `REAL` array never has a null chapter value, so `openChapterPop`'s `value="' + row.last_chapter_read + '"` would literally render `value="null"` if adapted verbatim against a never-read bookmark (e.g. the "Berserk" test fixture). The score popover already guards with `?? ''`; the chapter popover does not — a concrete bug to fix during slice 2, not copy verbatim.
- **The add-manga modal, "Ver en «…»" jump, loading/error states, and `card-saving` opacity** are container/modal-level concerns the prototype (a static single-screen demo) never models; none structurally conflict with the redesign, but `card-saving` (opacity 0.55) stacking with the caught-up fade (opacity 0.45) on the same card is worth a visual check, and the add button's position relative to the new search bar/tabs row is explicitly one of the *not decided here* items in the spec (§"Lo que NO se decide aquí") — an open placement question for sdd-design, not something to resolve in this explore.
- **Popover "saves as you type/step" is a client-only simulation in the prototype** (no network). Applied literally against the real PATCH API, committing on every keystroke/step risks request floods and out-of-order responses (last-sent request may not be last-to-resolve). The spec's "se guarda al momento" doesn't resolve this for a networked backend; slice 2 needs an explicit debounce/serialize strategy (e.g., commit typed input on blur/Enter like today's InlineNumberEdit, but commit stepper clicks immediately) before implementation.
- Minor: prototype's `minmax(162px, 1fr)` vs production's current `minmax(150px, 1fr)`, and prototype's tab order (`reading, on_hold, dropped, completed, want_to_read`) vs. `BOOKMARK_STATUSES`'s existing order (`reading, want_to_read, completed, on_hold, dropped`) — small, worth a conscious pick rather than an accidental one, since whichever order is chosen must also be the "Todo" concatenation order.

## Risks

- Slice 2 (popovers) is materially larger than slices 1/3 and likely alone exceeds the 800-line session budget once InlineNumberEdit's deletion and both test-file rewrites are counted — recommend sub-splitting at sdd-tasks.
- Status-select placement is genuinely undecided by the prototype and blocks a clean slice-1/2 cut until resolved.
- "Saves as you go" against a real API needs a debounce/serialization decision not covered by the spec text.
- `sortBookmarksForTab`'s "all" branch must not literally port the prototype's global isDone-partition trick — it can break "grouped by status" whenever a non-reading tab also carries live `behind` data.
- This agent has no file-write tool available in its toolset (Read/Grep/Glob/WebFetch/WebSearch/mem_save only) — `openspec/changes/panel-v1b-fase-5/exploration.md` could **not** be written despite `artifact_store: hybrid` requiring it; only the Engram side of the hybrid persistence was completed. The orchestrator must write the openspec file itself or delegate that to an agent with Write access.

## Ready for Proposal

Yes, with two open questions to resolve at sdd-propose/sdd-design before slicing: (1) where the status-select goes in the new card, (2) the popover commit/debounce strategy against the real API.

---

*Written by the orchestrator from the Engram artifact `sdd/panel-v1b-fase-5/explore` (#463). The `sdd-explore` agent has no Write tool, so it could only persist the Engram half of the hybrid store; this file is its verbatim counterpart, not a summary.*
