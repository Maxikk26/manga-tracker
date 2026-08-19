# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Read this first

`README.md` covers the product, the three detection mechanisms, the chapter-number glossary, and the recommended reading order for `docs/`. Do not duplicate it here — read it.

This file covers what the README does not: the architectural rules that are easy to violate, and the traps inside the docs themselves.

## Repository state

**In production since 2026-07-30**, running unattended in Docker on a home mini-PC. `docs/` is still the source of truth: it is where behaviour is decided, and the code follows it, not the other way round.

Real commands — do not invent others:

```
uv run pytest -q                 the suite; 330 tests as of 2026-08-04
docker compose build             required when manga_tracker/, frontend/, pyproject.toml or the Dockerfile change
docker compose up -d             the ONLY redeploy verb; `restart` does not recreate and silently keeps the old image
```

What exists: `manga_tracker/` with `sources/manganato/`, `storage/`, `seed/`, `discovery/`, `notifier/`, `catalogue/`, `importer/`, plus `scheduler.py` and `cli.py`. Python 3.12 under `uv` with a committed lockfile, SQLite in a Docker volume, curl-cffi, APScheduler in-process, one container.

**V1a is done as of 2026-08-10** — all four done-criteria in `one-pager-v1a.md` are met, the last one verified against `job_runs`: the three jobs run unattended, including a full Sunday cycle on 2026-08-09. The database holds 229 mangas and 229 bookmarks (227 from the Kitsu import plus two added by hand on 08-05). **The V1b spec opened on 2026-08-17** (`spec-panel-v1b.md`), after the week of real use that gated it: a web panel in four delivery phases, with reading-progress editing as the core. FastAPI, no auth, same container.

Two things this section got wrong for a week, because nobody updated it: it claimed there was no application code and no test tooling, long after both existed. **A stale statement here is expensive** — it is read at the start of every session and believed. When behaviour changes, this file changes with it.

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

**The feed does not guarantee detection.** Measured window is 41 minutes at peak; `active_sweep` is the primary mechanism and the only guarantee. The feed interval must stay **under** that window (`FEED_CHECK_MINUTES`, default 30) — an interval longer than the window loses publications by construction, not by luck.

This file used to say "raise the sweep frequency — do not touch the feed", and both halves are now wrong. The feed ran hourly against a 41-minute window for five months; when the reading list dropped to ~1 chapter a day, that structural third became everything, and production went five days (4-8 Aug 2026) with the feed contributing zero detections. And raising the sweep frequency stopped working when the prefilter landed: the sweep asks the source which titles moved, the source refreshes that answer once a day at 01:30 UTC, so an intra-day sweep reads a stale answer and skips nearly everything. The lever was written in July and killed by an August change without anyone updating the sentence. Full evidence in `medicion-ventana-feed.md` §"Revisión 2026-08-08".

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

**Every document in `docs/` opens with a `## Resumen` table that makes reading the rest optional.** One row per decision, the cost in figures (time, requests, manual work the owner has to do), what is out of scope, and where each thing lives. It is not the same section as "Decisiones discutibles", which lists only what the reader might want to overturn — a long document carries both. The reason is friction: a 200-line spec that must be read in full to be approved does not get approved, it gets postponed. Full rule, and the list of documents still owing one, in `runbook-mantenimiento.md` §"Todo documento de `docs/` abre con un resumen".

**A pull request body is written in English and follows `.github/pull_request_template.md`.** Read that file before writing one — it is a form with instructions inside an HTML comment, not a draft. Real `##` headings, a blank line before every list, table and fence, bullets rather than paragraphs, and short: twenty lines is a good body, ninety is a symptom, because the commits already carry the reasoning and `docs/` carries the decisions. Its `## Verified` section asks which guard you broke on purpose and what failed; answer it by actually breaking one, since a green suite proves only that nothing you wrote is checked. Hand over **three things, in this order: the compare link, the title, the finished body** — they merge from the GitHub UI and do not write the body. The link is the part that keeps getting dropped: it went missing twice in a row while the rule sat written in a memory note, so it is spelled out here as its own item rather than implied by "never just the compare URL". Warn them when the branch has one commit, because GitHub prefills the commit message above the template and it has to be deleted.

The English part is the same rule as everything else a developer reads, and it is written here because it failed anyway: a Spanish body was handed over on 2026-08-08 while a memory note stating the rule was loaded in context. Quoting a Spanish section name verbatim (`§Validación`) is citation, not authorship, and stays as it is.

**A branch is a unit of delivery, not of authorship.** A spec you are about to implement goes on the same branch as its implementation — splitting them is two PRs and two reviews for one change, and it separates the contract from the thing that fulfils it exactly when reviewing them together is what proves the code matches. Name the branch after the whole delivery (`feat/kitsu-importer`), not the first step (`docs/importer-spec`) — **in English**, like everything else a developer reads. That example used to be Spanish here, and on 2026-08-18 three branches were named in Spanish by copying it, then renamed with the PRs already written. An example that contradicts its own rule costs more than a missing rule: a missing rule gets asked about, an example gets copied. What does ship alone: runbook corrections after a deploy, a stale pin, a recorded deviation, or a spec written to close a decision with no implementation to follow. Full rule in `runbook-mantenimiento.md` §"La rama es una unidad de entrega".
