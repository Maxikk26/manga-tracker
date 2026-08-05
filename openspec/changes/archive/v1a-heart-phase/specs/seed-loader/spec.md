# Seed Loader Specification

## Purpose

A CLI, invocable manually and outside the scheduler, that reads a curated CSV of active reads (<20 titles) and populates the database (spec-seed-manual.md, full doc).

## Requirements

### Requirement: File locations are fixed

The versioned template MUST be `seed-plantilla.csv` at the repo root; the real list MUST default to `data/seed.csv`, overridable by argument; neither the real CSV nor the database file is versioned (spec-seed-manual.md §"El archivo").

#### Scenario: Default path used when no argument given

- GIVEN the loader is invoked with no path argument
- WHEN it runs
- THEN it reads `data/seed.csv`

### Requirement: Validate before writing

The loader MUST validate every row and print a report before writing anything; rows with errors MUST block loading unless the loader is explicitly re-invoked to skip them, and the loader MUST NOT perform a partial load silently (spec-seed-manual.md §"Validación").

#### Scenario: Blocking error halts the row

- GIVEN a row has an empty `title`
- WHEN validation runs
- THEN that row is reported as an error and is not loaded without explicit override

#### Scenario: Warning does not block

- GIVEN a row has `status=reading` with no `last_chapter_read`
- WHEN validation runs
- THEN the row is reported as a warning and still loads

### Requirement: Progress never derives from the URL

The slug MUST be extracted from the segment after `/manga/`, tolerating `www`, trailing slash, query, and fragment, whether the URL is a ficha or a chapter URL; `last_chapter_read` MUST come only from its own CSV column (spec-seed-manual.md §"El archivo").

#### Scenario: Chapter URL pasted by mistake

- GIVEN a row's `url` points to a specific chapter
- WHEN the slug is extracted
- THEN the manga slug is used and the chapter segment is ignored, and progress is taken only from the `last_chapter_read` column

### Requirement: Per-row load sequence

For each valid row the loader MUST, in order: create-or-find the `mangas` row; create the `manga_sites` row with the extracted slug and a canonically reconstructed ficha URL; call `fetch_chapters` to set `latest_chapter_num`, `latest_chapter_url`, `latest_chapter_at`, and `last_checked_at`, writing returned chapters to `chapter_history` with `detected_via=seed_backfill`; create the `bookmarks` row with `origin=seed` and `progress_is_approx=0` (spec-seed-manual.md §"Carga, por cada fila válida").

#### Scenario: seed_backfill history populated

- GIVEN a row's `fetch_chapters` call returns 12 chapters
- WHEN the row loads
- THEN all 12 are written to `chapter_history` with `detected_via=seed_backfill`

### Requirement: A row that fails at the source is fully discarded

If `fetch_chapters` for a row returns a not-found or unexpected failure, the loader MUST discard that row entirely — no `mangas`, `manga_sites`, or `bookmarks` row created — and continue with the remaining rows (spec-seed-manual.md §"Carga, por cada fila válida").

#### Scenario: Bad slug drops the whole row

- GIVEN a row's URL yields a slug that returns 404
- WHEN the loader processes it
- THEN no `mangas`, `manga_sites`, or `bookmarks` row is created for it, and later rows still load

### Requirement: Re-running the file is safe

Re-running the loader MUST reuse existing `mangas`/`manga_sites` rows by slug, update the bookmark's status and progress from the file, rely on `chapter_history`'s uniqueness to avoid duplicate history, and MUST NOT fabricate a `reading_history` event when progress is unchanged (spec-seed-manual.md §"Re-ejecución").

#### Scenario: Unchanged progress fires no reading event

- GIVEN a manga's `last_chapter_read` in the file equals the stored value
- WHEN the loader re-runs
- THEN no `reading_history` row is created for that manga

#### Scenario: Changed progress is captured

- GIVEN a manga's `last_chapter_read` in the file differs from the stored value
- WHEN the loader re-runs
- THEN the bookmark updates and the data-model trigger captures the change in `reading_history`

## References

- spec-seed-manual.md v2.1
