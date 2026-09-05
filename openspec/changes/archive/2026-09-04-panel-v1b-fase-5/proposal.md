# Proposal: the design pass of the bookmark list (`panel-v1b-fase-5`)

`execution_mode: auto · artifact_store: hybrid · delivery_strategy: auto-chain · review_budget_lines: 800`

**The *what* is closed and this proposal does not reopen it.** PAN §El rumbo visual, PAN §La tarjeta and the approved prototype are the contract; this document fixes **scope, order and risk**. Anything that looks improvable in the prototype is recorded as a follow-up, never as a change. File-level detail lives in `exploration.md` and is not repeated here.

| Alias | Document |
|---|---|
| PAN | `docs/spec-panel-v1b.md` **v1.10 → v1.11 in this delivery** (§187 el rumbo visual, §203 la tarjeta, §227 fase 5 y sus criterios, §286 las cuatro decisiones abiertas, §273 el pendiente de la pastilla "+N") |
| PROTO | `prototypes/bookmark-list.html` — **binding for behaviour**, not merely illustrative |
| EXP | `openspec/changes/panel-v1b-fase-5/exploration.md` — file map, seams, test breakage, slice sizing |

## Intent

The list is the panel's only indispensable screen and it was built one phase at a time: every phase hung one more control under the poster. Today a card is a cover, then a title, then a progress editor, then a score editor, then a status `<select>`, plus a `+N` pill on the corner. Three consequences, all measured in PAN and none of them cosmetic:

- **The card grows with its data.** A 142-character title moves the grid; two meta lines make the scrim eat the poster — and the poster is the thing the owner navigates by (PAN §108: the title alone does not identify the manga, "Genius" appears in three of them).
- **Two signals cost width and carry nothing.** `+N` fires on **18 of 18** "Leyendo" rows, so as a distinguishing mark it is noise; the loose `~` for approximate progress is on **207 of 284** rows and truncates the chapter on three quarters of the list.
- **There is no way to find a title.** 236 bookmarks, colliding vocabulary, and the only navigation is scrolling a tab. PAN §239 verified the fix is free: the whole list is already in the browser, so search is one more `.filter()` — zero backend, zero requests.

Fase 5 is the phase that is allowed to spend visual decisions (PAN §235), and it is the last of the five that V1b needs.

## Scope

### In scope — three chained slices, in this order

| # | Slice | Deliverable |
|---|---|---|
| **1** | **The card** | Poster + scrim, title/chapter/score **inside**, nothing below; one `nowrap` meta row; hover-swap chapter label (`cap. 94` ↔ `94 / 560`, prefix drops); dotted underline on the number for approximate progress; **`No puntuado`** as a state; caught-up fade + sink; **`Al día`** chip; `.behind-pill` **removed** — JSX call and CSS block, with its custom properties |
| **2** | **The editors** | Shared popover shell mounted on `document.body` (the card needs `overflow: hidden`); chapter popover with `−` / free field / `+` **and the status row**; score popover with `/10` and `Quitar puntuación`; `InlineNumberEdit.tsx` and its test **deleted**; no save button; **ordering frozen while a popover is open** |
| **3** | **The search** | Pure `filterBookmarks(rows, query)` in `domain/`; the **`Todo`** tab, first, with the status pill and its five measured tones; live result count; the **three-way** empty state |

Slice 1 is a hard dependency of slice 2 (the popover needs the scrim/meta markup and the `overflow: hidden` that forces document-level mounting). Slice 3's status chip consumes the prop slice 1 wires unused. Slices 2 and 3 touch the container on independent axes.

### Out of scope — fase-5 items that are not this change

- The heatmap scale (`domain/heatmapBuckets.ts`, its own seam), the timeline entry point, the navigation rework, the logo, `cadence_days_estimate`, and a keyboard shortcut for search.
- **Any reopening of grid-vs-list** (PAN §199: reopened by a new measurement, never by a preference), and any backend work — no endpoint, no query, no index, no pagination.

## Capabilities

### New

- **`panel-bookmark-list`**: the card contract (poster is the link, what lives inside the scrim, the single meta row, the rest/full chapter label, the approximate-progress underline, `No puntuado`, the caught-up fade and `Al día`, the status pill only in `Todo`), the two popover editors and their **commit contract**, the ordering freeze, the tab set including `Todo` and its concatenation order, the pure filter, and the three empty states. **No spec covers this screen today** — fase 1 shipped outside SDD, the same situation `cover-backfill` was in during fase 4.

### Modified

- **None.** `panel-bookmark-score` §Purpose already defers placement, size and colour to fase 5, and its wire contract (0-10, `null` clears, presence-based PATCH) is untouched. `panel-add-manga` is untouched: only where its trigger button sits changes, and the "Ver en «…»" jump must keep landing on a status tab — a regression guarded by the e2e smoke test, not a requirement change.

## Decisions carried in — do not re-ask

| # | Decision | Reason on the record |
|---|---|---|
| 1 | Score stays **`/10`** | `import-scores` reads Kitsu's 0-10 export and always will. Closes PAN §286's "escala de la puntuación" against the `/5` that was floated |
| 2 | **`Todo` with no query stays grouped by status**, tab after tab | Owner. Closes PAN §286's "orden dentro de «Todo»" |
| 3 | **An empty tab shows only a message**, no add button, and **must not** share the search-empty copy | Owner. The shared path would print `Sin resultados para «»`. Closes PAN §286 |
| 4 | **The `+N` pill does not come back.** Deliberate removal of shipped behaviour | Owner. Closes PAN §286 and retires the "tono y tamaño de la pastilla «+N»" pending of §273 as *removed*, not *tuned*. **Nobody should later restore it thinking it regressed** |
| 5 | **The status selector moves into the chapter popover**, as one more row | Owner. §La tarjeta hangs nothing below the poster and caps the meta row at chapter and score; PROTO never modelled it because there the tabs *are* the status. Keeps the card free of a third visible control and keeps **two** popovers, not one |
| 6 | **Commit strategy against the real API**: stepper clicks commit immediately; a typed value commits on **blur or Enter**, as `InlineNumberEdit` does today; requests serialize per bookmark | Orchestrator. PROTO's commit-on-every-keystroke is a client-only simulation — against `PATCH` it is one request per digit, with no ordering guarantee. Owner-visible contract is unchanged: **no save button** |
| 7 | **Tab order stays production's `BOOKMARK_STATUSES`** (`reading, want_to_read, completed, on_hold, dropped`), and that same order is `Todo`'s concatenation order | Orchestrator. PROTO's order is arbitrary; production's is shipped and asserted |
| 8 | **`Todo` concatenates each status's own `sortBookmarksForTab` output** | Orchestrator. PROTO's global `isDone` partition interleaves tabs the moment a non-`reading` row carries live `behind` data — and `on_hold` is still swept |
| 9 | **Slice 2 is sub-split at tasks time** | EXP sizes it at 750-950 lines against an 800-line budget |
| 10 | Matching is **accent-insensitive substring on the title**, nothing else | PROTO is binding (NFD + combining-marks strip). Closes one of PAN §245's "no se decide aquí" items |

## Fase-5 done-criteria (PAN §227) → which slice satisfies which

| Criterio | State | Where |
|---|---|---|
| **(1)** The chosen direction written **in PAN**, not in a loose note | **Met** in v1.9 | Must not regress. No slice |
| **(2)** The card decisions recorded | **Met** in v1.10 §La tarjeta | Slices **1** and **2** implement them |
| **(3)** The bar filtering live, its filter written as a **pure function over the full list**, so the global variant is dropping the status argument and not a rewrite | **Open** | Slice **3** — `domain/filterBookmarks.ts` with its own test, called inside the container's existing `useMemo` chain |
| **(4)** The four decisions PROTO left open — score scale, `Todo` order, empty-tab state, whether `+N` returns | **Answered** by owner decisions 1-4 | Recorded in **PAN v1.11**; implemented by slice **1** (`+N` removal, `/10` display) and slice **3** (`Todo` order, empty tab) |

Criterion 3 arrives with a bonus the spec expected to defer: with `Todo` present, **global search is not "one step away", it is here** — the same pure filter over the concatenated list. PAN §285 already accepted that, and PROTO's `Buscar en toda la lista` jump out of an empty tab result is its bridge.

## Approach

Three chained PRs (four once slice 2 splits), each with a clear start, finish, tests and a revert. No backend commit exists in any of them.

- **Slice 1** rewrites `BookmarkCard.tsx` and the card half of `styles.css`, and trims `BookmarkCard.test.tsx`: the five `.behind-pill` tests go, the `~` glyph assertion and the `—` for a null score are replaced by the underline and `No puntuado`. Editing behaviour is untouched, so `InlineNumberEdit` still stands at the end of this slice.
- **Slice 2** introduces the shared popover (one shell, two bodies: same panel, same placement, same keys), moves both editors and the status control into it, deletes `InlineNumberEdit` and its test, and adds the freeze: the list re-sorts on close, not on commit — otherwise the card goes "al día" and sinks out from under the panel being used.
- **Slice 3** adds `filterBookmarks`, the `Todo` branch in `sortBookmarks.ts`, the `StatusTabs` rewrite, the search row and the empty states. The container decides **which** empty state to render, the way it already decides loading and error; `BookmarkGrid` stops owning that message rather than growing a third branch.

### Three things this change must get right, and they are named here because they are cheap to miss

- **`tab-active` is a hard constraint.** `frontend/e2e/panel.smoke.spec.ts` asserts `getByRole("button", { name: /abandonado/i })` carries `tab-active` after the "Ver en «…»" jump. The `StatusTabs` rewrite may adopt `role="tablist"`/`aria-selected` (a pre-existing gap against `runbook-diseno-ui.md`), but **the class name and the accessible name stay**. `Agregar manga` is asserted by the same file and stays too.
- **A null `last_chapter_read` must not render the string `"null"`.** PROTO's `value="' + row.last_chapter_read + '"` has no guard — its demo data never has one, production does. The score popover already writes `?? ''`; the chapter popover gets the same treatment, and the card label with it.
- **`card-saving` (0.55) must not stack with the caught-up fade (0.45).** Multiplied they reach 0.25 and the card reads as broken. Proposed answer, for design to confirm: **while saving, the saving opacity is the only one applied** — the fade is suppressed for that card, since "this is being written" outranks "this one is done".

### The add-manga button — a position is proposed, design confirms it

PAN §245 lists the bar's shape and position as undecided. Today the button sits in `.panel-toolbar` beside the tabs; PROTO's shell is `h1 → search row → tabs → result count → grid` and leaves the search field alone on its row.

**Proposal: the button moves to the right end of the search row, opposite the field.** Three reasons: the tabs row becomes six tabs with counts and has no room; a non-tab button inside a `role="tablist"` is an accessibility defect the rewrite would be introducing on purpose; and the search row is otherwise half empty, which is the same reason PAN §285 gave for making `Todo` a tab rather than a scope switch. **Marked as a decision the design phase confirms**, not as one this proposal closes.

## Affected Areas

| Area | Impact | Description |
|---|---|---|
| `frontend/src/components/BookmarkCard.tsx` | Rewritten | Poster + scrim + one meta row. `.behind-pill` render call **deleted**. Editors become popover triggers in slice 2 |
| `frontend/src/components/BookmarkGrid.tsx` | Modified | `showStatus` prop through to the card; stops owning the empty message |
| `frontend/src/components/StatusTabs.tsx` | Rewritten | `Todo` first, sentinel value; keeps `tab-active` and the Spanish labels |
| `frontend/src/components/InlineNumberEdit.tsx` + test | **Deleted** | Only consumers are `BookmarkCard` and its own test (EXP, grep-confirmed) |
| `frontend/src/components/` (new) | New | Popover shell + the two editor bodies, with tests |
| `frontend/src/containers/BookmarkListContainer.tsx` | Modified | `activeStatus` widened with an "all" sentinel, `query` state, `filterBookmarks` in the `useMemo` chain, three-way empty state, popover-open ordering freeze, serialized commits |
| `frontend/src/domain/filterBookmarks.ts` (+ test) | New | Pure `(rows, query) => rows`, mirroring `sortBookmarks.ts` |
| `frontend/src/domain/sortBookmarks.ts` | Modified | "all" branch = per-status `sortBookmarksForTab`, concatenated in `BOOKMARK_STATUSES` order |
| `frontend/src/styles.css` | Large rewrite | `.card`/`.scrim`/`.title`/`.meta`/`.edit`/`.chip`/`.chip-status`, `.pop*`, `.search-*`, `.tab-all`, `.result-count`. `.behind-pill` block deleted outright |
| `frontend/src/components/*.test.tsx`, `frontend/src/containers/*.test.tsx` | Rewritten | Every selector going through `getAllByTitle(/haz clic para editar/i)` dies with `InlineNumberEdit`; new ones target the trigger buttons' `aria-label`s |
| `frontend/e2e/panel.smoke.spec.ts` | **Unchanged, and that is the point** | It passes untouched or the rewrite broke a contract |
| `docs/spec-panel-v1b.md` | Modified | → v1.11: the four open decisions closed, decisions 5-10 recorded, §273's `+N` pending retired as removed. Same branch as the code (CLAUDE.md) |
| `manga_tracker/` | **Untouched** | Zero backend. `uv run pytest -q` must stay green without a single new test |

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| **Slice 2 alone exceeds the 800-line budget** (750-950 per EXP) | High | Sub-split at tasks time: 2a shell + chapter popover (with the status row), 2b score popover + container freeze/serialization. Decision 9 |
| **The `tab-active` assertion breaks silently** in a `role="tablist"` rewrite that "modernizes" the class names | Med | Named as a hard constraint above; run the e2e smoke on slice 3 before the PR, not after |
| **Committing on keystroke ships one PATCH per digit** if PROTO is ported literally | Med-High | Decision 6, written into the spec phase as a requirement with scenarios, not left as an implementation nicety |
| **The status control gets less discoverable**: today it is a visible `<select>`, after slice 2 it is a row inside the chapter popover | Med | Owner decision 5, taken with the constraint stated (no third visible control). Flagged for the first day of real use; reverting it means finding the card room the spec says does not exist |
| **`Todo` renders ~236 cards at once**, up from ~48 in the biggest tab | Low-Med | Data is already in the browser; images are `loading="lazy"` and the endpoint serves `max-age=86400`. Measure once on the homelab before calling it fine |
| **PROTO's popover anchors to a rect that scrolling invalidates** and dismisses on scroll | Low | Keep that behaviour (it is PROTO-binding) and return focus to the trigger, as PROTO does |
| **Test churn hides a real regression**: three test files are rewritten at once | Med | Each slice's tests land in the same commit as its code, and the deleted assertions are enumerated in tasks so a reviewer sees what stopped being checked |
| **The "free search" premise expires** the day `GET /api/bookmarks` paginates (PAN §239) | Low | The pure filter is exactly the shape that moves server-side later; record the caveat in PAN v1.11 rather than assuming it away |

## Rollback Plan

- **Per slice: revert the commit.** No schema, no migration, no API, no data written by any of the three. The panel container restarts from the previous image (`docker compose up -d`, never `restart`).
- **The `+N` removal is recoverable only from git history**, since its CSS seam goes with it. That is the intent of decision 4, and it is why the removal is written down instead of implied.
- **Docs**: PAN v1.11 is prose; reverting it is a revert.

## Dependencies

- Fases 1-4 deployed. `my_score` must be in the list payload (fase 4, migration 3) — the card renders it, so slice 1 assumes it.
- `GET /api/bookmarks` stays unpaginated for the life of this change (PAN §239).
- No new package. No new endpoint. Nothing on the homelab beyond the usual `docker compose build && docker compose up -d`.

## Success Criteria

- [ ] A card is a poster with title, chapter and score **inside** it; a 142-character title does not move the grid, and nothing hangs below the image.
- [ ] The chapter reads `cap. 94` at rest and `94 / 560` on hover, with the prefix gone; on a touch device the total is always shown.
- [ ] Approximate progress is a dotted underline on the number. **No `~` survives anywhere in the card.**
- [ ] An unscored manga reads `No puntuado`; a caught-up one is faded, sunk to the bottom of its tab, and carries `Al día` outside `Todo`.
- [ ] **No `+N` pill exists in the DOM or in `styles.css`.**
- [ ] Chapter and score are edited in a popover with **no save button**; `−`/`+` commit at once, a typed value commits on blur or Enter, and the status row changes the state from the same panel.
- [ ] A never-read bookmark opens the chapter popover with an **empty field**, never the string `null`.
- [ ] The list does not reorder while a popover is open, and reorders when it closes with focus back on the trigger.
- [ ] Typing filters live within the active tab; `Todo` searches all five; `filterBookmarks` is pure and its test proves the global variant is the same call without the status filter.
- [ ] The three empty states are distinct: empty tab (message only, no add button), no search results (`Sin resultados para «…» en «…».` plus the jump to `Todo` outside it), and the normal grid.
- [ ] `npm test` and `npm run build` green; **`frontend/e2e/panel.smoke.spec.ts` passes unmodified**; `uv run pytest -q` green and unchanged.
- [ ] PAN is at v1.11 with criteria 3 and 4 marked met and decisions 5-10 on the record.

## Proposal question round

`execution_mode: auto`, so these were not asked interactively. Owner decisions 1-5 are **settled and not reopened**. What follows is what is genuinely still open at the product level; each changes behaviour, not mechanics. Correct any assumption before design.

| # | Question | Assumption taken |
|---|---|---|
| 1 | **Where does `Agregar manga` sit** once the search row exists? | Right end of the search row, opposite the field. Reasons above. Design confirms; PAN §245 says this is exactly the kind of question the pass exists to answer |
| 2 | **What does an empty `Todo` say** — a whole empty list is not the same sentence as an empty tab | Empty status tab keeps today's `No hay mangas en este estado.`; an empty `Todo` gets its own copy. Both are message-only, no add button (decision 3) |
| 3 | **Does `Buscar en toda la lista` keep the typed query?** | Yes: it switches to `Todo`, keeps the text and refocuses the field. Losing the query would make it a worse version of clicking the tab |
| 4 | **Does changing the status from the chapter popover close it?** | Yes, and the list re-sorts on that close — the card is likely leaving the tab, so leaving the panel open over a card that is about to disappear is the same problem the freeze exists to prevent |
| 5 | **Is the `Al día` chip suppressed in `Todo`,** where the status pill takes the same corner? | Yes, per PROTO: one chip per corner, status wins in `Todo`. Recorded because it is real prototype behaviour that §La tarjeta's bullet list does not name |
