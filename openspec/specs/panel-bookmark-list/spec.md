# Panel Bookmark List Specification

## Purpose

Defines the redesigned bookmark list screen (PAN §187, §203; `prototypes/bookmark-list.html`, binding for behaviour): the card, its two popover editors and their commit contract, the ordering freeze, the tab set including "Todo", the pure search filter, and the three empty states. No spec covered this screen before fase 5. `panel-bookmark-score` owns the `my_score`/`last_chapter_read` wire contract; `panel-add-manga` owns the add modal. This spec owns presentation and interaction only.

## Requirements

### Requirement: The card is the poster, with a single non-wrapping meta row
Title, chapter control and score control MUST render inside the poster's scrim; nothing MUST render below it. The chapter+score row MUST stay on one line at every supported card width; it MUST NOT wrap.

#### Scenario: A long title does not grow the grid
- GIVEN a bookmark with a 142-character title
- WHEN its card renders
- THEN the grid footprint is unchanged and the title clips inside the scrim

#### Scenario: The widest real pair stays on one line
- GIVEN a card showing its widest chapter value next to "No puntuado"
- WHEN the card renders at minimum width
- THEN both controls remain on one line, unwrapped

### Requirement: The chapter control swaps between rest and full label
At rest it MUST read "cap. {N}". On pointer devices, hover/focus MUST switch it to "{N} / {total}", dropping the prefix. On devices with no hover, "{N} / {total}" MUST always show. With no known total, only "cap. {N}" MUST render, with no swap.

#### Scenario: Hover reveals the total on a pointer device
- GIVEN `last_chapter_read=94`, `latest_chapter_num=560`
- WHEN the card is hovered
- THEN the control reads "94 / 560"

#### Scenario: Touch device always shows the total
- GIVEN the same bookmark on a touch-only device
- WHEN the card renders
- THEN it reads "94 / 560" without any interaction

### Requirement: Approximate progress and unset scores read as state, not glyphs
When `progress_is_approx` is true, the chapter number MUST carry a dotted underline; no free-standing "~" MUST appear anywhere. When `my_score` is null the score control MUST read "No puntuado"; otherwise "{my_score}/10".

#### Scenario: Approximate chapter is underlined, not tilded
- GIVEN `progress_is_approx=true`
- WHEN the control renders
- THEN the number is underlined and no "~" appears

#### Scenario: Score reads a state
- GIVEN `my_score` is null, then 8
- WHEN each renders
- THEN it reads "No puntuado", then "8/10"

### Requirement: A caught-up bookmark fades and sinks to the end of its tab
A row whose `last_chapter_read` reached `latest_chapter_num` MUST render at reduced opacity and sort after every not-caught-up row in its tab. Outside "Todo" it MUST carry an "Al día" chip; inside "Todo" the status pill occupies that corner and "Al día" MUST NOT render.

#### Scenario: Caught-up row sinks within its tab
- GIVEN one caught-up and one behind row in "Leyendo"
- WHEN the tab renders
- THEN the caught-up row is faded and appears after the behind row

#### Scenario: Todo suppresses the Al día chip
- GIVEN a caught-up bookmark shown while "Todo" is active
- WHEN its card renders
- THEN it shows the status pill, never "Al día"

### Requirement: No backlog-count pill exists
No "+N" backlog indicator MUST render anywhere in the card, for any bookmark.

#### Scenario: No backlog pill in the DOM
- GIVEN any rendered card
- WHEN the DOM is inspected
- THEN no backlog-count element is present

### Requirement: Chapter and score are edited in a popover with no save button
The popover MUST mount outside the card's clipped bounds and MUST NOT include a save button. A stepper click MUST commit immediately. A typed value MUST commit only on blur or Enter, never per keystroke. Commits for one bookmark MUST serialize so an earlier response cannot overwrite a later commit's effect. When `last_chapter_read` is null the field MUST open empty; the literal string "null" MUST NOT render.

#### Scenario: Stepper commits at once
- GIVEN the chapter popover is open
- WHEN "+" is clicked
- THEN a commit request is sent immediately

#### Scenario: Typed value commits on blur, not per keystroke
- GIVEN the owner types a new value
- WHEN the field loses focus without Enter
- THEN exactly one commit request is sent, none earlier

#### Scenario: A later commit is not overwritten by an earlier response
- GIVEN two commits sent in quick succession for one bookmark
- WHEN the first response arrives after the second
- THEN the displayed value reflects the second, later commit

#### Scenario: Never-read bookmark opens blank
- GIVEN `last_chapter_read` is null
- WHEN its chapter popover opens
- THEN the field is empty, never the text "null"

### Requirement: The status control lives inside the chapter popover
The chapter popover MUST include a status row. Selecting a different status MUST close the popover.

#### Scenario: Status change from the popover
- GIVEN the chapter popover is open
- WHEN the owner picks a different status
- THEN the bookmark's status updates and the popover closes

### Requirement: The list does not reorder while a popover is open
While any popover is open, cards MUST NOT reorder, even when the edit changes a card's caught-up state. On close, the list MUST re-sort and return focus to the trigger that opened the popover.

#### Scenario: Mid-edit position is unchanged
- GIVEN a "Leyendo" row's popover is open and the edit makes it caught-up
- WHEN the popover remains open
- THEN the card's position is unchanged

#### Scenario: Closing reorders and restores focus
- GIVEN that popover is then closed
- WHEN the list re-renders
- THEN the card moves to its sorted position and focus returns to its trigger

### Requirement: Search is a pure function over the full list
`filterBookmarks(rows, query)` MUST be pure, matching accent-insensitively as a substring of the title only. The "Todo" (global) search MUST call this identical function over the full concatenated row set, never a separate implementation.

#### Scenario: Accent-insensitive match
- GIVEN a title containing "á" and a query typed without it
- WHEN `filterBookmarks` runs
- THEN the row is included

#### Scenario: Global search reuses the same function
- GIVEN one query applied within a tab and once over all rows
- WHEN both calls run
- THEN both use the identical matching logic, differing only in the rows passed in

### Requirement: "Todo" leads the tabs, grouped contiguously by status
Tabs MUST show "Todo" first, then the five statuses in `BOOKMARK_STATUSES` order. "Todo" with no query MUST concatenate each status's own sorted rows in that order, never a single pass over the merged set. Every card shown in "Todo" MUST carry a status pill bearing the status name, never colour alone.

#### Scenario: Todo groups contiguously by status
- GIVEN bookmarks across all five statuses
- WHEN "Todo" renders with no query
- THEN rows appear grouped by status in `BOOKMARK_STATUSES` order

#### Scenario: Pill names the status
- GIVEN a "dropped" bookmark shown in "Todo"
- WHEN its card renders
- THEN the pill text reads the Spanish label for "dropped"

### Requirement: Empty tab and empty search are distinct states
A tab with zero bookmarks MUST show a message-only state with no add-manga control, and MUST NOT print "Sin resultados para «»". A query matching nothing MUST show "Sin resultados para «{query}» en «{tab}»." plus a control that switches to "Todo" while preserving the typed query and refocusing the search field.

#### Scenario: Empty tab shows its own message
- GIVEN a status tab with zero bookmarks and no query
- WHEN it renders
- THEN a message-only state shows, with no add control and no "Sin resultados" text

#### Scenario: Empty search offers the Todo jump
- GIVEN a non-empty tab where the query matches nothing
- WHEN it renders
- THEN it shows "Sin resultados para «{query}» en «{tab}»." and a jump to "Todo" that keeps the query

## References
- docs/spec-panel-v1b.md v1.11 §El rumbo visual, §La tarjeta, §Fases y criterios de terminado (fase 5)
- prototypes/bookmark-list.html — binding for behaviour
- openspec/changes/panel-v1b-fase-5/proposal.md, exploration.md
- openspec/specs/panel-bookmark-score/spec.md (my_score/last_chapter_read wire contract, unchanged)
- openspec/specs/panel-add-manga/spec.md (add modal, unchanged)
