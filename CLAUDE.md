# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Read this first

`README.md` covers the product, the three detection mechanisms, the chapter-number glossary, and the recommended reading order for `docs/`. Do not duplicate it here — read it.

This file covers what the README does not: the architectural rules that are easy to violate, and the traps inside the docs themselves.

## Repository state

There is **no application code yet**. Phase 0 is complete: the V1a design is closed across eight documents in `docs/`. `docs/` is the source of truth, not a description of existing code.

Consequences:

- There is no build, lint, or test tooling to run. No `pyproject.toml`, no `requirements.txt`, no `Dockerfile`, no test suite. Do not invent commands — when scaffolding lands, record the real ones in this section.
- Decided but not yet scaffolded: Python, SQLite (single file, Docker volume), curl-cffi, APScheduler inside the process, one container.
- The only executable precedent is the throwaway feed-window measurement script, which deliberately lives outside the repo (see `docs/medicion-ventana-feed.md`).

## Spec authority, and where the docs contradict each other

Per the README, on conflict the more specific document wins, then the more recent version. Three specific traps follow from that, all in `docs/referencia-repo-viejo.md` — a rescue document from the 2025 Go attempt that later specs **overrode**. Its own recommendations are stale:

| `referencia-repo-viejo.md` says | What actually applies |
|---|---|
| Keep `SiteConfig` CSS selectors parameterized in the DB ("rescate crítico") | **Reversed.** `spec-modelo-de-datos.md` table `sites` has no selector columns; source knowledge lives in the client module. Revisit only in V2. |
| Reimplement the dual relative/absolute date parsing in Python | **Obsolete.** The JSON chapters endpoint returns exact UTC. `spec-cliente-fuente-descubrimiento.md`: "Se acabó el parseo dual". |
| Parallelism 3-5 max | **Wrong for V1a.** Zero concurrency; every request is sequential. |

As of v1.1 that document carries a warning banner and inline **SUPERADO** marks on each reversed point, so the trap is signposted. Read it for the antipattern list that killed the previous attempt; treat its forward-looking advice as superseded.

Retired chapter-number and sweep names (`latest_chapter_seen`, `latest_chapter_available`, `daily_sweep`, `weekly_sweep`) no longer appear in any live prose — the only remaining mentions are changelog entries recording the rename. Do not reintroduce them.

Job and detection names describe the **population** they cover (`active_sweep`, `onhold_sweep`), never the frequency. Frequency is a config parameter expected to change; these names live inside CHECK constraints, so renaming them later means migrating a populated database.

Every spec declares the versions it depends on. Those pins are currently all consistent — and a stale pin is what let `daily_sweep` survive in the bot spec through v1.0. When you version a document, update the pins of everything that depends on it; treat a stale pin as a defect, not a cosmetic detail.

## The structural boundary

Two layers that must not leak into each other:

- **Source client** knows manganato: URLs, HTML, the JSON endpoint, ad filtering, anti-bot. It does not know which mangas matter, when to notify, or what is in the database.
- **Discovery** knows the reading list, the states, when to notify, what to write. It does not know what manganato's HTML looks like or what its endpoint is called.

The client returns normalized data; discovery decides what to do with it. If the source changes, only the client changes (playbook in §9 of `manganato-fuente-actual.md`).

A concrete consequence: building a chapter URL from a slug and a number is a **client** operation, not a bot one. The bot asks for URLs; it never assembles them, because the URL pattern is source knowledge.

## Rules that are easy to get wrong

**Notify before update.** For active mangas, `latest_chapter_num` advances *only* after the Telegram digest was sent successfully. Send fails → nothing advances, run closes as `partial`, and the next run re-detects and retries. A duplicated alert is acceptable; a lost one is not.

**`chapter_history` is written regardless of notification.** A publication is a fact, independent of whether a message went out. It is recorded before any notification decision. Its uniqueness constraint on (`manga_site_id`, `chapter_num`) makes reprocessing idempotent.

**The detection rule is one rule, implemented once**, shared by all three mechanisms: seal `last_checked_at` (always) → compare against `latest_chapter_num` → record the publication → decide by bookmark state. A number *lower* than stored means the source renumbered or deleted; log it and never move the stored value backwards.

**Terminal states consume nothing.** `completed` and `dropped` receive zero requests, ever, and a match on them updates nothing and records no history. `on_hold` updates silently and immediately, and never notifies.

**The `reading_history` trigger fires on UPDATE only, not INSERT.** This is deliberate: bulk seed and Kitsu import must not generate fake reading events ("read 340 mangas the day of the import"). Downward corrections are captured too and are honest data — the consumer treats negative deltas as corrections, not reading.

**The feed does not guarantee detection.** Measured window is 41 minutes at peak, so hourly runs miss roughly a third of peak publications. `active_sweep` is the primary mechanism. If 24h latency becomes annoying, raise the sweep frequency — do not touch the feed.

**Zero real items after ad filtering is an error, not an empty list.** It means the feed structure changed. The ad filter runs first, before any other parsing: discard items with a `hidden` attribute or a class starting with `js-banner-`.

**Timestamps are UTC in the database, always.** Local-time conversion (America/Caracas) belongs to the backend at presentation. Hard rule for calendar-day aggregation: apply the timezone *before* grouping by date, or a 23:00 read lands on the wrong day.

## Request policy (applies to all source operations)

curl-cffi with Chrome impersonation, no Playwright. Organic `Referer` (the manga's page) when calling the JSON endpoint. Random 5-15s delay between consecutive requests, 30s timeout, exactly one retry on transient error, never more than two attempts per item per run, no concurrency.

Failures classify into three categories that discovery reacts to differently: **not found** (404 or false success — feeds the dead-slug counter), **transient** (timeout, 5xx, Cloudflare — says nothing about slug validity), **unexpected** (well-formed response with the wrong shape — the source probably changed; log the relevant fragment).

Initial values for the configurable parameters live in the last section of `spec-cliente-fuente-descubrimiento.md`. Dead-slug threshold is 5 consecutive not-found failures; only not-found increments it, any success resets it.

## Local files that are not in the repo

Per `spec-seed-manual.md`, two files with opposite handling:

| File | Location | Versioned |
|---|---|---|
| Template (header + example rows) | `seed-plantilla.csv`, repo root | Yes |
| Real reading list | `data/seed.csv` (loader default; path is an argument) | No |

`.gitignore` blanket-ignores `*.csv` and re-includes the template by name. **Renaming the template breaks this silently** — a CSV that does not match a re-inclusion pattern is simply ignored, with no error. Verify with `git check-ignore --stdin` (not `-v`, which also reports matches on negation rules and so makes re-included files look ignored).

Operational caveat on `data/seed.csv`: it is hand-typed and not reconstructible, and `git clean -xdf` deletes ignored files. A `.gitignore` prevents committing it, not losing it — back it up outside the repo.

`samples/` (the raw source audit dumps catalogued in §10 of `manganato-fuente-actual.md`) is ignored — every file is re-downloadable and a single feed page is ~155 KB. Trimmed parse-test fixtures belong in `tests/fixtures/`, which is versioned.

## Conventions

Documentation and prose in `docs/` are written in Spanish. Code, identifiers, comments, commit messages, log records, exception messages and CLI output are in English. Domain terms stay verbatim as the specs define them (`last_chapter_read`, `active_sweep`, `source_key`) — do not translate schema names.

**The English rule is code hygiene, and it stops at the reader.** Text a human receives as the product — the Telegram digest, the heartbeat, the dead-slug notice, the manual test message — is **Spanish**, and that is binding per `spec-bot-telegram.md` §"Idioma de los mensajes". The distinction is who the string is for: English for whatever the machine says to a developer, Spanish for whatever the product says to its user.

This is written down because the first implementation got it wrong. "Any string literal is in English" was read to cover product copy, the digest shipped in English, and three real notifications went out that way before anyone noticed — the tests were green because they asserted the English text too. If you are translating this copy back to English to satisfy a convention, you are reintroducing a defect.

When a spec does not cover something, ask; do not fill the gap by your own judgment. The gap is closed as a decision and the corresponding document is versioned, with its changelog and open-pendings list updated.
