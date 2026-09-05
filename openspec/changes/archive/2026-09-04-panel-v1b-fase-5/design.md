# Design: the design pass of the bookmark list (`panel-v1b-fase-5`)

Contract: `docs/spec-panel-v1b.md` v1.10 → **v1.11 in this delivery** (§El rumbo visual, §La tarjeta).
Proposal: `proposal.md` — its "Decisions carried in" table (1-10) is settled and is not reopened here.
File map: `exploration.md`, trusted and not restated. Behaviour: `prototypes/bookmark-list.html` (**PROTO**), binding.

**This phase decides code, not looks.** Every visual question is already answered by PAN and PROTO; what
follows is component boundaries, where state lives, how the popover mounts, how writes serialize, and how the
chain cuts. Copy quoted below is Spanish because it is product copy (CLAUDE.md); everything else is English.

## Technical Approach

No new dependency, no backend, no endpoint. The screen keeps the shape it already has — a container that owns
fetching and the PATCH flow, presentational components below it, pure functions in `domain/` — and gains three
things: a card that is a poster, a portalled popover shell with two bodies, and a pure title filter with a
sixth `Todo` tab. Three of the four slices are additive; the fourth deletes `InlineNumberEdit` and the `+N`
pill.

```
GET /api/bookmarks ──► bookmarks[]            (server truth; refetched after every PATCH)
        │
        ├─ counts ─────────────────────────────────────────► StatusTabs (6 buttons, Todo first)
        │
        └─ filterBookmarks(rows, query)   [domain, pure]
                 │
                 ├─ tab   → sortBookmarksForTab(rows.filter(status), status)   [unchanged signature]
                 └─ "all" → sortBookmarksForAll(rows)  = per-status sort, concatenated
                                   │
                            applyFrozenOrder(rows, frozenIds?)   [domain, pure — the ordering freeze]
                                   │
                            BookmarkGrid ──► BookmarkCard ──► Popover ──portal──► document.body
                                                   │                │
                                                   │                └─ ChapterEditor | ScoreEditor
                                                   ├─ onEditingChange(id, open) ──► container: frozenIds
                                                   └─ onChange{Progress,Score,Status} ──► enqueuePatch
                                                                                            │
                                                                          per-id FIFO queue ─┴─► PATCH ─► refetch
```

## The five open questions, resolved

| # | Question | Decision | Reason |
|---|---|---|---|
| Q1 | Where `Agregar manga` sits | **Confirmed: right end of the search row**, opposite the field. `.panel-toolbar` is retired; the shell is `h1 → search row (field + button) → tabs → result count → grid` | The proposal's three reasons hold, and D3 adds a fourth that is stronger than "no room": the tabs must stay a *filter*, and the only accessible marking that survives the e2e is `aria-current` on the row's buttons — a button that filters nothing would be the one member of the row that `aria-current` can never describe. The e2e's `getByRole("button", { name: "Agregar manga" })` is position-independent, so nothing breaks |
| Q2 | Empty `Todo` copy | **`Todavía no hay mangas en tu lista.`** Message only, no add button (decision 3). The per-status tab keeps `No hay mangas en este estado.` verbatim | Distinct sentence for a distinct fact: one says "this shelf is empty", the other says "the library is empty". Reachable only on a fresh database (236 rows today), so it gets one sentence and no ceremony |
| Q3 | Does the scope jump keep the query | **Yes.** `Buscar en toda la lista` sets the tab to `Todo`, leaves `query` untouched, and refocuses the field | PROTO is binding and already does exactly this (`activeTab = ALL_TAB; render(); q.focus()` — it never clears `query`). Dropping the text would make the affordance strictly worse than clicking the tab |
| Q4 | Does picking a status inside the chapter popover close it | **Yes**, and the close is what lifts the freeze and re-sorts. Focus returns to the trigger if it is still mounted, otherwise to the grid (D6) | The row is usually leaving the tab; leaving a panel open over a card that is about to disappear is the exact failure the freeze exists to prevent |
| Q5 | Is `Al día` suppressed in `Todo` | **Yes — not open.** PROTO: `chip = showStatus ? statusPill : (isDone ? "Al día" : "")`. One chip per corner, status wins in `Todo` | Read off the prototype, as instructed. Recorded because §La tarjeta's bullet list does not name it |

## Architecture Decisions

### D1 — The tabs do **not** become an ARIA tablist. They stay buttons and gain `aria-current`

This overrules `exploration.md` ("ideally adopts the prototype's `role="tablist"/role="tab"` pattern") and
PROTO's markup, and the reason is a hard constraint, not a preference.

`frontend/e2e/panel.smoke.spec.ts:35` asserts `page.getByRole("button", { name: /abandonado/i })` carries
`tab-active`. `getByRole` matches the **computed ARIA role**, and an explicit `role="tab"` overrides a
`<button>`'s implicit role. A `<button role="tab">Abandonado</button>` therefore stops being matchable as a
button and the assertion fails — the class name is only one of the two ways to break this test silently, and
the role is the sharper one.

| Alternative | Why rejected |
|---|---|
| `role="tablist"`/`role="tab"`/`aria-selected` per PROTO | Breaks the e2e, which must pass **unmodified**. It also obliges the roving-tabindex + arrow-key contract nobody is implementing, with no `role="tabpanel"` and no `aria-controls` to point at — a half-built tab widget announces worse than a labelled button group |
| Keep today's markup unchanged | Fails the accessibility floor: the accent fill is currently the only signal of which tab is active |

**Shipped shape**: `<nav className="status-tabs" aria-label="Filtrar por estado">` with six
`<button type="button" className="tab tab-active?" aria-current={active ? "true" : undefined}>`. `aria-current`
is the precedent this repo already set in `AppNav.tsx` for exactly this problem (WCAG 4.1.2, comment in place).
`tab-active` and the Spanish labels are byte-identical to today.

### D2 — One popover shell, two bodies — and it mounts through `createPortal`

`Popover.tsx` owns placement, dismissal, focus and `role="dialog"`. `ChapterEditor.tsx` and `ScoreEditor.tsx`
are bodies. Two independent popover components were rejected: PROTO's own comment states the intent — *"same
panel, same placement, same keys. Only the body differs"* — and duplicating the shell means two copies of the
reposition/dismiss/focus-return logic and two chances to drift.

The mount is `createPortal(panel, document.body)` from `react-dom`, already a dependency. It is the React
equivalent of PROTO's `document.body.appendChild`, and it exists for the same reason: the card needs
`overflow: hidden` to round the poster, which clipped a 178px panel inside a 173px card. A side effect worth
keeping: because the panel lives outside the card, the card's `card-saving` fade does not tint the panel.

| Concern | Rule |
|---|---|
| Placement | `useLayoutEffect`, once, from `anchor.getBoundingClientRect()` + the panel's own `offsetWidth/Height`: `left` clamped into `[8, vw - w - 8]`, `top = bottom + 6`, flipped to `top - h - 6` when it would overflow, then `+ window.scrollX/scrollY` (page coordinates, `position: absolute`). PROTO's arithmetic, verbatim |
| Dismiss | `Escape` on the panel; capture-phase document `click` outside panel **and** outside anchor; `scroll` with `{ capture: true, once: true }` — PROTO dismisses on scroll precisely because the anchor rect it measured is invalidated; `focusout` whose `relatedTarget` is a real element outside both |
| `focusout` with `relatedTarget === null` | **Does nothing.** A native `<select>` dropdown and a click outside the window both produce it; closing there kills the status row |
| Focus | On open, the first field, focused and selected. On close, the anchor if `document.contains(anchor)`, else the grid (D6) |
| Roles | `role="dialog"` + Spanish `aria-label`. **No `aria-modal`** — this is a non-modal popover and claiming the page is inert would be a lie; `AddMangaModal` keeps `aria-modal="true"` because it earns it. No focus trap |
| Mutual exclusion | Falls out of the dismiss rule: clicking a second card's trigger is "outside" the first panel and its anchor, so the first closes. No registry needed |
| `z-index` | **10, not PROTO's 30.** `.modal-backdrop` is `z-index: 20` (`styles.css:597`); a popover that outranks the add modal is a defect. Porting `30` verbatim would ship it |

### D3 — The card owns its popover; the container owns only the fact that one is open

`BookmarkCard` holds `open: null | "chapter" | "score"`, the trigger refs, and renders the portal. It reports
upward with one callback, `onEditingChange(id: number, open: boolean)`.

Rejected: the container owning `{id, kind, anchorElement}`. It would push a DOM element up into the layer that
owns data and requests, which is the boundary this frontend keeps by convention. The container needs exactly
one bit — "a row is being edited" — and that is what it gets.

The container stores `editingId: number | null` with a last-open-wins setter, because a closing card's
`false` can arrive after a newly opened card's `true`:

```ts
setEditingId((prev) => (open ? id : prev === id ? null : prev));
```

### D4 — The ordering freeze is a frozen list of **ids**, applied by a pure domain function

While `editingId !== null`, the container renders the previously computed sequence.

```ts
// domain/sortBookmarks.ts — pure, knows nothing about popovers
export function applyFrozenOrder(rows: readonly Bookmark[], ids: readonly number[]): Bookmark[];
```

Ids, never row objects. Freezing the objects would freeze the **values** too, so an open chapter panel would
sit over a card still showing the old number — PROTO repaints the card in place as you edit (`refreshPopCard`),
and that behaviour is binding. Freezing the id sequence freezes order only and lets fresh data flow into every
card. Rows whose id is absent from the frozen list are appended; frozen ids no longer present are dropped, so
a refetch that adds or removes rows degrades instead of throwing.

The presentation stays out of the domain by splitting the *reason* from the *operation*: the container knows
why the order is frozen (a popover is open) and captures `frozenIds` from the current `ordered` list on open,
clearing it on close; `applyFrozenOrder` only knows how to re-sequence by a previous order and is unit-testable
with no React in scope.

### D5 — PATCH serialization: one FIFO promise chain per bookmark, and only the last of a burst refetches

`patchBookmark` stays where it is. `applyPatch` gains a queue in the container:

```ts
const tails = useRef(new Map<number, Promise<void>>());   // per-bookmark FIFO
const seqs  = useRef(new Map<number, number>());          // burst counter
```

`enqueuePatch(id, patch)` bumps `seqs[id]`, chains onto `tails[id]`, and each link: `await patchBookmark(...)`;
then `await load(false)` **only if `seqs.get(id)` still equals this link's number**. Failures are caught inside
the link (into `errorMessage`, exactly as today) so a rejection cannot poison the tail. `savingIds` clears on
the last link of the burst.

This is what makes "a slow response must not overwrite a newer value" true by construction: request N+1 is not
sent until N's PATCH *and* its refetch have settled, so responses cannot interleave. It also collapses the
refetch storm — three `+` clicks are three PATCHes but one 236-row GET.

| Alternative | Why rejected |
|---|---|
| Debounce the PATCH | Delays a write the owner was told saves itself, and still races when two fields of one row are touched |
| `AbortController` on the loser | Aborting a PATCH does not un-apply it; the write may already have committed server-side |
| Optimistic local state + version counter | The container is deliberately server-truth (`behind`, `progress_is_approx` are derived server-side and come back on the refetch). Optimism here means re-deriving them in the client, which is the thing this codebase refuses to do |

**Consequence, named because it reverses today's behaviour**: the trigger buttons are **not** `disabled` while
saving. Disabling them would make `+` unusable during exactly the burst it exists for; the queue provides the
ordering that `disabled` used to provide by accident. `card-saving` remains the only in-flight signal.

### D6 — Focus return when the trigger unmounted

A status change from the chapter popover usually removes the card from the tab, so the anchor is gone by the
time focus should return. Rule: focus the anchor when `document.contains(anchor)`; otherwise focus
`.bookmark-grid`, which gains `tabIndex={-1}` as a focus sink. Letting focus fall to `<body>` loses the
keyboard position and the screen-reader cursor, which is the failure PROTO papers over with `?.focus()`.

### D7 — `card-saving` beats the caught-up fade, and the proposal's arithmetic is corrected

**The decision is confirmed**: while saving, the saving opacity is the only one applied.

**The stated arithmetic is wrong and matters.** `opacity` is one property; two declarations on the *same*
element resolve by cascade, they do not multiply. `0.55 × 0.45 = 0.25` requires two nested elements each
carrying an opacity. Ported naively, what actually happens is a specificity fight that **the fade wins**:
`.card[data-done]` is (0,1,1) against `.card-saving`'s (0,1,0), so a saving card would render at 0.45 and the
"being written" signal would silently vanish. Fix: write `.card.card-saving { opacity: 0.55; }` — specificity
(0,2,0) beats both `.card[data-done]` and its `:hover` variant (0,1,2) regardless of source order.

### D8 — The `"all"` sentinel is a literal, and no existing signature is widened

```ts
// domain/types.ts
export const ALL_TAB = "all" as const;
export type TabKey = BookmarkStatus | typeof ALL_TAB;
```

Only two places see `TabKey`: the container's `activeTab` state and `StatusTabs`' props. Everything downstream
keeps `BookmarkStatus` or a boolean:

- `sortBookmarksForTab(rows, status: BookmarkStatus)` — **signature unchanged**. The `"all"` case is a new
  sibling export, `sortBookmarksForAll(rows)`, and the container picks between them with one `if`. Widening the
  existing parameter would push a value into a function whose whole body indexes `TAB_DATE` by status.
- `BookmarkCard`/`BookmarkGrid` receive `showStatus: boolean`, derived once in the container as
  `activeTab === ALL_TAB`. The card never learns the sentinel exists.
- `filterBookmarks(rows, query)` never sees a status at all — that is criterion 3's entire point.

`"all"` over `null`: `null` is this codebase's "unknown" idiom (`behind`, `last_chapter_read`, absent
`TAB_DATE` keys), so a null tab reads as "no tab selected" rather than "every tab"; the literal is also
self-describing in devtools and survives into a URL later.

### D9 — `sortBookmarksForAll` concatenates per-status output; PROTO's global partition is not ported

```ts
export function sortBookmarksForAll(rows: readonly Bookmark[]): Bookmark[] {
  return BOOKMARK_STATUSES.flatMap((s) => sortBookmarksForTab(rows.filter((r) => r.status === s), s));
}
```

`BOOKMARK_STATUSES` order (`reading, want_to_read, completed, on_hold, dropped`) is production's and is
asserted; PROTO's order is arbitrary (decision 7). PROTO's `sorted()` — a global `isDone` partition over the
flat concatenation — interleaves tabs the moment a non-`reading` row carries live `behind` data, and `on_hold`
is still swept (CLAUDE.md). O(5n) over 236 rows is free, and the property is directly testable: for every
status, `sortBookmarksForAll(rows).filter(by status)` must deep-equal that status' own tab output.

`isCaughtUp` is promoted from a private helper to an export of the same module so the card's fade, the `Al día`
chip and the sorter share one definition. Its rule stays **`behind === 0`**, not PROTO's `<= 0`, and `behind` is
never recomputed in the client: the existing docstring's reasoning (a null `behind` is *unknown*, and "I cannot
tell" is not "I am up to date") is a decision already taken. A row read *past* the latest detected chapter
(`behind < 0`) therefore still does not fade — same as today, recorded as a follow-up, not fixed here.

### D10 — `filterBookmarks`: accent-insensitive substring on the title, with the character class escaped

```ts
export function filterBookmarks(rows: readonly Bookmark[], query: string): Bookmark[];
```

Normalization is `s.normalize("NFD").replace(COMBINING_MARKS, "").toLowerCase()`, then a substring match on
`title` only (decision 10). `COMBINING_MARKS` is a module-level regex over the combining-marks block
**U+0300 to U+036F**, and it must be written with numeric escapes (`backslash-u0300` to `backslash-u036f`),
never pasted. PROTO spells that class with the raw marks — which is why its own comment says it "looks empty in
an editor" — and an invisible character class is precisely what a future formatter or editor mangles without a
diff anyone can read. Copying the literal is the one thing this line must not do.

Empty or whitespace-only query returns a copy of the input (`[...rows]`), mirroring `sortBookmarks`' defensive
copy so no caller can mutate the source. Chain order in the container is **filter → scope → sort**: filtering
first keeps the per-status sort working on the visible set, and it is the cheaper order.

### D11 — The editors reuse `DecimalInput`, not `<input type="number">`

PROTO uses `type="number"`; `DecimalInput.tsx` carries a **standing owner decision of 2026-08-19** in its
docstring — no native spinners, no `"0170"` drafts, `inputMode="decimal"` for the touch keyboard, and *"reuse
this for any future numeric field"*. The chapter field takes it as-is (chapters are decimal: the source
publishes 32.2). The score field takes it too; the difference lives in the commit validator, not in a second
component.

| Rule | Chapter | Score |
|---|---|---|
| Draft seed | `value === null ? "" : String(value)` — **this is the null guard**; PROTO would render the string `"null"` | same (`?? ''`, as PROTO already does) |
| Seeded | On open only. A refetch landing while the panel is open must never re-seed the draft — same class of bug as the ordering freeze | same |
| Stepper `−`/`+` | Writes the draft **and commits immediately**; `Math.max(0, round(x*10)/10)`; `−` disabled at 0 | n/a |
| Typed value | Commits on **blur or Enter**; Enter also closes | same |
| `Escape` | Closes without committing the typed draft. Stepper commits already landed, so nothing is lost | same |
| Unchanged value | No PATCH (today's `InlineNumberEdit` rule; it is also what stops a blur after a stepper commit from re-sending) | same |
| Blank | No-op | Clears (`{ my_score: null }`) |
| Out of range | `< 0` rejected | `< 0` or `> 10` rejected; committed value is rounded to an integer |

`Quitar puntuación` sets the draft to `""`, commits `null`, and closes.

### D12 — The status control becomes a labelled `<select>` inside the chapter popover

Decision 5 settled *where*; this settles *what*. It stays the shipped `<select>`, restyled as `.pop-select`
under a `Estado` label, keeping `aria-label={`Estado de ${title}`}` verbatim so existing container-test
selectors survive. Five pills do not fit a 178px panel and would add a third visual weight to a panel whose job
is one number; the complaint against the `<select>` was that it consumed *card* space, never that it was the
wrong control. Its `onChange` commits and closes (Q4).

### D13 — Grid metrics, memoization and the copy PROTO fixes

- Grid becomes `repeat(auto-fill, minmax(162px, 1fr))`, gap `1rem` — PROTO's, not production's 150px/1.1rem.
  Not cosmetic: the meta row's width budget ("798 / 1181" beside "No puntuado" fitting with zero margin) was
  measured at PROTO's card width; keeping 150px re-introduces the silent truncation the design pass removed.
  This is the §Pendientes "grilla por ancho de pantalla" item, answered in part.
- `BookmarkCard` is wrapped in `React.memo`. `Todo` renders ~236 cards and every keystroke re-renders the tree;
  the props are already stable (`useCallback` handlers, a boolean `saving`, a row identity that only changes on
  refetch), so `memo` makes typing cheap with zero dependencies. Still measure once on the homelab.
- A never-read row renders **`Sin empezar`** as its chapter label with no hover swap (a ratio needs a left
  side), and the total stays reachable in the popover hint `de {total} publicados`. `Sin leer` is rejected: it
  reads as *unread chapters*, the exact sense the `+N` removal is retiring.
- Copy kept verbatim from PROTO: `No puntuado`, `Al día`, `Se guarda solo.`, `de {n} publicados`,
  `El progreso guardado es aproximado.`, `Buscar por título`, `Limpiar la búsqueda`, `Buscar en toda la lista`,
  `{n} título(s) en toda la lista.`, `{n} resultado(s) en «{tab}».`, `Sin resultados para «{q}» en {tab}.`
  Singular/plural and the `«»` quoting are part of the copy.
- **Three PROTO idioms that are not ported**, each because React does not have the problem they solve:
  `esc()` (JSX escapes; a manual escaper would double-escape), `.grid[data-empty]` (a class-swap/DOM-lookup
  workaround, per its own comment), and `mountShell()` (innerHTML tearing the caret out of the field). The
  React-shaped version of that last hazard is real and is stated as a rule: **the search row is rendered
  outside the loading/error/empty branch and never keyed**, or the input remounts and loses focus mid-word.

## File Changes

| File | Action | Description |
|---|---|---|
| `frontend/src/components/BookmarkCard.tsx` | Rewrite | Poster + scrim + one `nowrap` meta row; `.behind-pill` call deleted; hover-swap chapter; `data-approx` underline; `Sin empezar`/`No puntuado`; chip = status pill in `Todo` else `Al día`; popover triggers; `React.memo` |
| `frontend/src/components/Popover.tsx` (+ test) | New | Portalled shell: placement, dismissal, focus return, `role="dialog"` |
| `frontend/src/components/ChapterEditor.tsx` (+ test) | New | `−` / `DecimalInput` / `+`, hints, and the status `<select>` row |
| `frontend/src/components/ScoreEditor.tsx` (+ test) | New | `DecimalInput` + `/ 10` + `Quitar puntuación` |
| `frontend/src/components/InlineNumberEdit.tsx` + test | **Delete** | Only consumers are the card and its own test |
| `frontend/src/components/BookmarkGrid.tsx` | Modify | Threads `showStatus`; **loses** its empty-state branch (the container decides, as it already does for loading/error); gains `tabIndex={-1}` |
| `frontend/src/components/StatusTabs.tsx` (+ new test) | Rewrite | Six buttons, `Todo` first with the total; `TabKey`; `aria-current`; `tab`/`tab-active` and the Spanish labels unchanged |
| `frontend/src/containers/BookmarkListContainer.tsx` | Modify | `activeTab: TabKey`, `query`, search row + add button, PATCH queue, `editingId` + `frozenIds`, three-way empty state, result count |
| `frontend/src/domain/filterBookmarks.ts` (+ test) | New | Pure `(rows, query) => rows` |
| `frontend/src/domain/sortBookmarks.ts` (+ tests) | Modify | Adds `sortBookmarksForAll`, `applyFrozenOrder`, exports `isCaughtUp`; `sortBookmarksForTab` untouched |
| `frontend/src/domain/types.ts` | Modify | `ALL_TAB`, `TabKey` |
| `frontend/src/styles.css` | Large rewrite | `.card`/`.poster`/`.scrim`/`.title`/`.meta`/`.edit`/`.chip`/`.chip-status`, `.pop*`, `.search-*`, `.result-count`, `.tab-all`, `.tab{min-height:44px}`; `.behind-pill`, `.panel-toolbar`, `.status-select`, `.progress-*`, `.approx-marker` deleted |
| `frontend/src/components/*.test.tsx`, `containers/*.test.tsx` | Rewrite | Selectors move from `getAllByTitle(/haz clic para editar/i)` to the triggers' `aria-label`s |
| `frontend/e2e/panel.smoke.spec.ts` | **Unchanged** | Run manually before slices 3 and 4 land, not after |
| `docs/spec-panel-v1b.md` | Modify | → v1.11 (slice 1) |
| `manga_tracker/` | **Untouched** | `uv run pytest -q` green, zero new tests |

## Interfaces

```ts
// domain/types.ts
export const ALL_TAB = "all" as const;
export type TabKey = BookmarkStatus | typeof ALL_TAB;

// domain/filterBookmarks.ts
export function filterBookmarks(rows: readonly Bookmark[], query: string): Bookmark[];

// domain/sortBookmarks.ts   (sortBookmarksForTab keeps its exact signature)
export function sortBookmarksForAll(rows: readonly Bookmark[]): Bookmark[];
export function applyFrozenOrder(rows: readonly Bookmark[], ids: readonly number[]): Bookmark[];
export function isCaughtUp(bookmark: Bookmark): boolean;

// components/Popover.tsx
interface PopoverProps {
  anchor: HTMLElement | null;
  label: string;                 // Spanish, product copy
  onDismiss: () => void;
  children: ReactNode;
}

// components/BookmarkCard.tsx — the one new upward signal
onEditingChange: (id: number, open: boolean) => void;
showStatus: boolean;
```

`BookmarkPatch` is unchanged: the three single-field members already express every write this phase makes.

## Testing Strategy

| Layer | What | How |
|---|---|---|
| Unit (`domain`) | `filterBookmarks` (accents both ways, case, substring, empty/whitespace, no match, source not mutated); `sortBookmarksForAll` (contiguity + per-status equality with `sortBookmarksForTab`); `applyFrozenOrder` (unknown ids appended, missing ids dropped) | vitest, no React |
| Component | `Popover`: Escape / outside click / scroll dismiss, focus to field on open and back to anchor on close, `role="dialog"` + label, `focusout` with `relatedTarget: null` does **not** close. `ChapterEditor`: null seeds an empty field, stepper commits at once, typed commits on blur and Enter, Escape cancels, unchanged value fires nothing, `−` disabled at 0, status change commits and closes. `ScoreEditor`: clear → `null`, out-of-range rejected. `BookmarkCard`: both chapter labels present, `Sin empezar`, `No puntuado`, `data-approx`, chip is the status pill in `Todo` and `Al día` otherwise, **no `+N` in the DOM**. `StatusTabs`: six tabs, `tab-active` + `aria-current` on the active one, `Todo` total | RTL |
| Container | Two rapid stepper commits PATCH in order with one refetch; a commit that makes a row caught-up does not move it until the popover closes; the three empty states; the scope jump keeps the query and focuses the field; `showStatus` only in `Todo` | RTL + mocked `api/bookmarks` |
| E2E | `panel.smoke.spec.ts` **unmodified** | Manual, per `docs/runbook-desarrollo-local.md` |
| Python | `uv run pytest -q` green and unchanged | Guard: `manga_tracker/` is untouched |

**jsdom caveat, stated so a test is not written against it**: jsdom has no layout, so every rect is 0. Do not
assert popover coordinates or the "flips above" branch; assert the dismiss/focus/commit contract instead. The
placement arithmetic is verified by eye on the homelab, like the rest of the visual pass.

## Threat Matrix

**N/A** — no routing, shell, subprocess, VCS/PR automation, executable-file classification or process
integration. The only untrusted input is the search query, which is rendered through JSX (auto-escaped) and
used as a substring needle; `references/threat-matrix.md` was not loaded and no row applies. Recorded rather
than omitted: PROTO's `esc()` exists because it builds HTML strings, and porting it would double-escape.

## Slicing — four chained PRs, `auto-chain`, budget 800

Order confirmed. Slice 2 is sub-split, and the cut is chosen so **each slice is independently revertible
without losing shipped functionality** — which forces the status `<select>` and `InlineNumberEdit` to survive
longer than the final card design allows. Nothing deploys until the chain merges, so a card that still hangs a
`<select>` under the poster for two PRs is a review artifact, never a shipped regression.

| # | Slice | Est. lines | May touch | May **not** touch |
|---|---|---|---|---|
| **1** | The card | **400-510** | `BookmarkCard.tsx` + test, `BookmarkGrid.tsx` (thread `showStatus`, container passes `false`), `styles.css` card block, `docs/spec-panel-v1b.md` → v1.11 | `InlineNumberEdit` (still renders both values), the status `<select>` (stays, below the poster, with its test), the container, `domain/` |
| **2a** | Popover shell + chapter editor + the write machinery | **700-780** | `Popover.tsx` + test, `ChapterEditor.tsx` (no status row yet) + test, card's chapter trigger, container: PATCH queue + `editingId` + `frozenIds`, `sortBookmarks.ts` (`applyFrozenOrder`, `isCaughtUp` export) + tests, `.pop*` CSS | The score editor (still `InlineNumberEdit`), the `<select>`, `StatusTabs`, search, `filterBookmarks` |
| **2b** | Score editor + the status row + the deletions | **600-700** | `ScoreEditor.tsx` + test, the status row inside `ChapterEditor`, `<select>` removed from the card, **`InlineNumberEdit.tsx` + test deleted** (-255), `BookmarkCard.test.tsx` and `BookmarkListContainer.test.tsx` rewrites | `StatusTabs`, search, `Todo`, `types.ts` |
| **3** | Search + `Todo` | **500-620** | `filterBookmarks.ts` + test, `sortBookmarksForAll` + tests, `types.ts` (`TabKey`), `StatusTabs.tsx` + new test, container (query, search row, add button moved, result count, three-way empty state), `BookmarkGrid` empty branch removed, card status chip, `.search-*`/`.tab-all`/`.result-count`/`.chip-status` CSS | `manga_tracker/`, `api/`, the e2e spec |

Corrections to the exploration's sizing: slice 2's 750-950 was one unit; splitting at the shell/consumer seam
rather than at "shell+chapter | score+container" is what keeps both halves under budget, because the freeze and
the queue are **required by** the chapter editor and cannot be deferred to 2b. Slice 1 grew by the PAN v1.11
prose, which rides with it because it is the contract the other three implement (CLAUDE.md: the spec goes on
the branch of its implementation).

`400-line budget risk: High` for every slice; `Chained PRs recommended: Yes`; the session budget is 800 and all
four fit. The e2e smoke runs before slice 3's PR and again at the end of the chain.

## Migration / Rollout

No migration. No schema, no API, no data written by any slice. Per-slice rollback is a revert; the chain
deploys once with `docker compose build && docker compose up -d` (never `restart`). The `+N` removal is
recoverable only from git history — that is the intent of decision 4.

## Open Questions

None blocking. Three follow-ups deliberately not fixed here:

- [ ] `isCaughtUp` uses `behind === 0`, so a row read past the latest detected chapter neither fades nor sinks.
      Shipped behaviour; changing it moves rows in `reading` for reasons unrelated to a design pass.
- [ ] The status control becomes less discoverable (a visible `<select>` → a row inside a popover). Owner
      decision 5, flagged for the first day of real use.
- [ ] `Todo` renders ~236 cards. `React.memo` and `loading="lazy"` are the answer; measure once on the homelab
      before calling it fine.
